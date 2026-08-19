from fastapi import Depends, HTTPException, APIRouter, Request
from sqlalchemy import or_
from datetime import datetime, timezone
from typing import Annotated
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ...db.session import get_db, db_dependency
from starlette import status

from ...models.products.orm import Product, BundleItem
from ...models.products.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    ProductDetailsResponse,
    PaginationParams,
    PaginatedResponse,
    BulkDeleteRequest,
    _product_slug,
)
from ...utils.permissions import CAN_READ_PRODUCTS, CAN_CREATE_PRODUCTS, CAN_UPDATE_PRODUCTS, CAN_DELETE_PRODUCTS
from pharmatrack.models.product_has_ingredients.orm import ProductHasIngredient
from pharmatrack.models.ingredients.orm import Ingredient
from pharmatrack.utils.validators import (
    validate_units_schema,
    normalize_units,
    merge_product_units,
    validate_unit_name_for_sale,
)
from pharmatrack.utils.pagination import paginate
from ...utils.rate_limit import limiter, LIMIT_READ, LIMIT_WRITE
from ...utils.logger import get_logger

logger = get_logger(__name__)


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


# =========================================================
# GET /
# =========================================================
_ORDERING_MAP = {
    "title":          Product.title.asc(),
    "-title":         Product.title.desc(),
    "price_retail":   Product.price_retail.asc(),
    "-price_retail":  Product.price_retail.desc(),
    "price_cost":     Product.price_cost.asc(),
    "-price_cost":    Product.price_cost.desc(),
    "created_at":     Product.created_at.asc(),
    "-created_at":    Product.created_at.desc(),
}


@router.get("",
            response_model=PaginatedResponse[ProductResponse],
            summary="List all products",
            status_code=status.HTTP_200_OK,
            dependencies=CAN_READ_PRODUCTS)
@limiter.limit(LIMIT_READ)
async def read_all(
    request: Request,
    db: db_dependency,
    pagination: PaginationParams = Depends(),
    search: str | None = None,
    sku: str | None = None,
    brand_id: int | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    show_online: bool | None = None,
    ordering: str | None = None,
    exclude_animal_twins: bool = False,
    only_bundles: bool = False,
):
    query = db.query(Product).filter(Product.deleted_at.is_(None))

    # Los gemelos de animales viven en la sección Animales; la relación
    # animals.product_id es la fuente de verdad (no hay flag que desincronizar)
    if exclude_animal_twins:
        from ...models.animals.orm import Animal
        query = query.filter(~Product.id.in_(db.query(Animal.product_id)))

    # Paquetes = productos con componentes (bundle_items)
    if only_bundles:
        query = query.filter(Product.id.in_(db.query(BundleItem.bundle_product_id)))

    if sku:
        query = query.filter(Product.sku == sku)
    elif search:
        query = query.filter(
            or_(Product.title.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"))
        )

    if brand_id is not None:
        query = query.filter(Product.brand_id == brand_id)
    if category_id is not None:
        query = query.filter(Product.product_category_id == category_id)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if show_online is not None:
        query = query.filter(Product.show_online == show_online)

    order_clause = _ORDERING_MAP.get(ordering) if ordering else None
    if order_clause is None:
        order_clause = Product.created_at.desc()
    # id como desempate: created_at se repite en importaciones masivas y sin un orden
    # total la paginacion devuelve paginas traslapadas (productos duplicados y faltantes)
    query = query.order_by(order_clause, Product.id.desc())

    return paginate(query, pagination)


# =========================================================
# GET /{product_id}
# =========================================================
@router.get("/{product_id}",
            response_model=ProductDetailsResponse,
            summary="Get product details",
            status_code=status.HTTP_200_OK,
            dependencies=CAN_READ_PRODUCTS)
async def read_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id, Product.deleted_at.is_(None)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


# =========================================================
# POST /
# =========================================================
@router.post("",
             response_model=ProductDetailsResponse,
             summary="Create a new product",
             status_code=status.HTTP_201_CREATED,
             dependencies=CAN_CREATE_PRODUCTS)
@limiter.limit(LIMIT_WRITE)
async def create_product(request: Request, product: ProductCreate, db: db_dependency):
    # normalize_units modifica en-place (no retorna nada)
    normalize_units(product)
    validate_units_schema(product)
    validate_unit_name_for_sale(product)

    # Validar SKU unico
    if db.query(Product).filter(Product.sku == product.sku).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product with this SKU already exists."
        )

    # Validar slug unico
    if db.query(Product).filter(Product.slug == product.slug).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A product with this title and SKU combination already exists."
        )

    # Validar ingredientes ANTES de crear
    if product.ingredients:
        ingredient_ids = {ing.ingredient_id for ing in product.ingredients}
        valid_ids = {
            row[0]
            for row in db.query(Ingredient.id).filter(Ingredient.id.in_(ingredient_ids)).all()
        }
        missing = ingredient_ids - valid_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingredient not found: {list(missing)}"
            )

    # slug tiene Field(exclude=True) -> hay que inyectarlo manualmente
    slug = product.slug
    product_data = product.model_dump(mode="json", exclude={"ingredients"}, exclude_none=True)
    product_data["slug"] = slug

    new_product = Product(**product_data)
    db.add(new_product)
    db.flush()

    if product.ingredients:
        db.add_all([
            ProductHasIngredient(
                product_id=new_product.id,
                ingredient_id=ing.ingredient_id,
                amount=ing.amount,
            )
            for ing in product.ingredients
        ])

    db.commit()
    db.refresh(new_product)
    logger.info("Product created id=%s title=%s sku=%s", new_product.id, new_product.title, new_product.sku)
    return new_product


# =========================================================
# PUT /{product_id}
# =========================================================
@router.put("/{product_id}",
            response_model=ProductDetailsResponse,
            summary="Update a product",
            status_code=status.HTTP_200_OK,
            dependencies=CAN_UPDATE_PRODUCTS)
async def update_product(product_id: int, product_request: ProductUpdate, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    # Validar unidades (estado final fusionado)
    merged = merge_product_units(product, product_request)
    normalize_units(merged)
    validate_units_schema(merged)
    validate_unit_name_for_sale(merged)

    # Validar SKU duplicado
    if product_request.sku and product_request.sku != product.sku:
        if db.query(Product).filter(Product.sku == product_request.sku).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product with this SKU already exists."
            )

    # Recalcular slug si cambia title o sku
    if product_request.title is not None or product_request.sku is not None:
        final_title = product_request.title or product.title
        final_sku = product_request.sku if product_request.sku is not None else product.sku
        new_slug = _product_slug(final_title, final_sku)
        if new_slug != product.slug:
            if db.query(Product).filter(Product.slug == new_slug, Product.id != product_id).first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A product with this title and SKU combination already exists."
                )
            product_request.slug = new_slug

    # Validar ingredientes ANTES de modificar nada
    if product_request.ingredients is not None:
        ingredient_ids = {ing.ingredient_id for ing in product_request.ingredients}
        valid_ids = {
            row[0]
            for row in db.query(Ingredient.id).filter(Ingredient.id.in_(ingredient_ids)).all()
        }
        missing = ingredient_ids - valid_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingredient not found: {list(missing)}"
            )

    update_data = product_request.model_dump(
        mode="json",
        exclude={"ingredients"},
        exclude_unset=True,
    )
    if product_request.slug is not None:
        update_data["slug"] = product_request.slug

    for key, value in update_data.items():
        setattr(product, key, value)

    if product_request.ingredients is not None:
        db.query(ProductHasIngredient).filter(
            ProductHasIngredient.product_id == product.id
        ).delete()
        db.add_all([
            ProductHasIngredient(
                product_id=product.id,
                ingredient_id=ing.ingredient_id,
                amount=ing.amount,
            )
            for ing in product_request.ingredients
        ])

    try:
        db.commit()
        db.refresh(product)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating product id=%s: %s", product_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update product.")

    logger.info("Product updated id=%s", product_id)
    return product


# =========================================================
# PATCH /{product_id}/toggle-active
# =========================================================
@router.patch("/{product_id}/toggle-active",
              response_model=ProductDetailsResponse,
              summary="Toggle product availability",
              dependencies=CAN_UPDATE_PRODUCTS)
async def toggle_product_active(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id, Product.deleted_at.is_(None)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    product.is_active = not product.is_active
    db.commit()
    db.refresh(product)
    logger.info("Product id=%s toggled is_active=%s", product_id, product.is_active)
    return product


# =========================================================
# PATCH /{product_id}/toggle-online
# =========================================================
# Endpoint dedicado (no PUT): PUT reemplaza el producto entero, así que mandar
# el objeto completo solo para voltear un booleano invita a pisar otros campos.
@router.patch("/{product_id}/toggle-online",
              response_model=ProductDetailsResponse,
              summary="Toggle product visibility on the public site",
              dependencies=CAN_UPDATE_PRODUCTS)
async def toggle_product_online(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id, Product.deleted_at.is_(None)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    product.show_online = not product.show_online
    db.commit()
    db.refresh(product)
    logger.info("Product id=%s toggled show_online=%s", product_id, product.show_online)
    return product


# =========================================================
# DELETE /bulk
# =========================================================
@router.delete("/bulk",
               status_code=status.HTTP_200_OK,
               summary="Bulk delete products",
               description="Deletes multiple products atomically. Fails if any ID does not exist.",
               dependencies=CAN_DELETE_PRODUCTS)
@limiter.limit(LIMIT_WRITE)
async def bulk_delete_products(request: Request, payload: BulkDeleteRequest, db: db_dependency):
    products = db.query(Product).filter(Product.id.in_(payload.ids), Product.deleted_at.is_(None)).all()
    found_ids = {p.id for p in products}
    missing = [i for i in payload.ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Products not found: {missing}")
    now = datetime.now(timezone.utc)
    for product in products:
        product.deleted_at = now
    db.commit()
    return {"deleted": len(products)}


# =========================================================
# DELETE /{product_id}
# =========================================================
@router.delete("/{product_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Soft-delete a product",
               dependencies=CAN_DELETE_PRODUCTS)
@limiter.limit(LIMIT_WRITE)
async def delete_product(request: Request, product_id: int, db: db_dependency):
    existing_product = db.query(Product).filter(Product.id == product_id, Product.deleted_at.is_(None)).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    existing_product.deleted_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Product soft-deleted id=%s", product_id)
    return None


# =========================================================
# PATCH /{product_id}/restore
# =========================================================
@router.patch("/{product_id}/restore",
              status_code=status.HTTP_200_OK,
              response_model=ProductDetailsResponse,
              summary="Restore a soft-deleted product",
              dependencies=CAN_UPDATE_PRODUCTS)
async def restore_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id, Product.deleted_at.isnot(None)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or not deleted")
    product.deleted_at = None
    db.commit()
    db.refresh(product)
    logger.info("Product restored id=%s", product_id)
    return product

# =========================================================
# Paquetes (bundles): componentes de un producto
# =========================================================
from ...models.products.schemas import BundleItemIn, BundleItemOut  # noqa: E402


@router.get("/{product_id}/bundle-items",
            response_model=list[BundleItemOut],
            summary="Componentes del paquete",
            dependencies=CAN_READ_PRODUCTS)
async def list_bundle_items(product_id: int, db: db_dependency):
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    from sqlalchemy.orm import selectinload
    return (
        db.query(BundleItem)
        .options(selectinload(BundleItem.component))
        .filter(BundleItem.bundle_product_id == product_id)
        .all()
    )


@router.put("/{product_id}/bundle-items",
            response_model=list[BundleItemOut],
            summary="Reemplaza los componentes del paquete (replace-all)",
            dependencies=CAN_UPDATE_PRODUCTS)
async def set_bundle_items(product_id: int, items: list[BundleItemIn], db: db_dependency):
    bundle = db.get(Product, product_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Product not found")

    component_ids = [item.component_product_id for item in items]
    if len(component_ids) != len(set(component_ids)):
        raise HTTPException(status_code=400, detail="Componentes duplicados en el paquete.")
    if product_id in component_ids:
        raise HTTPException(status_code=400, detail="Un paquete no puede contenerse a sí mismo.")

    if component_ids:
        found = db.query(Product).filter(
            Product.id.in_(component_ids), Product.deleted_at.is_(None)
        ).all()
        if len(found) != len(component_ids):
            raise HTTPException(status_code=404, detail="Uno o más componentes no existen.")
        # Sin paquetes anidados: mantiene la expansión de venta en un nivel
        nested = db.query(BundleItem.bundle_product_id).filter(
            BundleItem.bundle_product_id.in_(component_ids)
        ).first()
        if nested:
            raise HTTPException(status_code=400, detail="Un paquete no puede contener otro paquete.")

    # Tampoco al revés: si este producto ya es componente de otro paquete,
    # volverlo paquete crearía anidamiento en la venta
    if items and db.query(BundleItem.id).filter(
        BundleItem.component_product_id == product_id
    ).first():
        raise HTTPException(
            status_code=400,
            detail="Este producto es componente de otro paquete; no puede ser paquete a la vez.",
        )

    db.query(BundleItem).filter(BundleItem.bundle_product_id == product_id).delete()
    for item in items:
        db.add(BundleItem(
            bundle_product_id=product_id,
            component_product_id=item.component_product_id,
            quantity=item.quantity,
        ))
    db.commit()

    from sqlalchemy.orm import selectinload
    return (
        db.query(BundleItem)
        .options(selectinload(BundleItem.component))
        .filter(BundleItem.bundle_product_id == product_id)
        .all()
    )
