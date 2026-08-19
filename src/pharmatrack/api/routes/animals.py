"""CRUD de animales (individuos). Cada animal tiene un producto gemelo con un
lote de quantity=1, así se vende por el POS reutilizando todo el flujo de ventas."""
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, APIRouter, Query
from sqlalchemy.orm import Session, selectinload, joinedload
from starlette import status

from ...db.session import db_dependency
from ...models.animals.orm import Genus, Species, Morph, Animal, AnimalPhoto
from ...models.animals.schemas import AnimalCreate, AnimalUpdate, AnimalResponse
from .animal_taxonomy import descendant_group_ids, hidden_group_ids
from ...models.products.orm import Product
from ...models.product_batch.orm import ProductBatch
from ...models.product_categories.orm import ProductCategory
from ...models.sale_details.orm import SaleDetail
from ...utils.permissions import (
    CAN_READ_ANIMALS, CAN_CREATE_ANIMALS, CAN_UPDATE_ANIMALS, CAN_DELETE_ANIMALS,
)
from pharmatrack.types.animals import AnimalStatusEnum
from pharmatrack.utils.pagination import paginate, PaginationParams, PaginatedResponse
from pharmatrack.utils.slugify import slugify


router = APIRouter(prefix="/animals", tags=["Animals"])

ANIMALS_CATEGORY_SLUG = "animales"


# =========================================================
# Helpers
# =========================================================
def _animals_category_id(db: Session) -> int:
    """Categoría 'Animales' para los productos gemelos (se crea si no existe)."""
    cat = db.query(ProductCategory).filter(ProductCategory.slug == ANIMALS_CATEGORY_SLUG).first()
    if not cat:
        cat = ProductCategory(name="Animales", slug=ANIMALS_CATEGORY_SLUG, is_active=True)
        db.add(cat)
        db.flush()
    return cat.id


def _validate_morphs(db: Session, morph_ids: list[int], species_id: int) -> list[Morph]:
    if not morph_ids:
        return []
    morphs = db.query(Morph).filter(Morph.id.in_(morph_ids)).all()
    if len(morphs) != len(set(morph_ids)):
        raise HTTPException(status_code=400, detail="One or more morphs not found.")
    wrong = [m.name for m in morphs if m.species_id != species_id]
    if wrong:
        raise HTTPException(
            status_code=400,
            detail=f"Morphs do not belong to the animal's species: {', '.join(wrong)}",
        )
    return morphs


def _animal_title(species: Species, code: str, morphs: list[Morph] | None = None) -> str:
    # El morph en el título distingue gemelos de la misma especie en el POS
    # y en el buscador de paquetes ("Murina Glacier AN-X" vs "Murina Papaya AN-Y")
    parts = [species.common_name or species.name]
    parts.extend(m.name for m in (morphs or []))
    parts.append(code)
    return " ".join(parts)


def _query_with_relations(db: Session):
    return db.query(Animal).options(
        joinedload(Animal.species).joinedload(Species.genus).joinedload(Genus.group),
        selectinload(Animal.morphs),
        selectinload(Animal.photos),
        # la propiedad stock suma los lotes del producto gemelo
        selectinload(Animal.product).selectinload(Product.batches),
    )


def _validate_compare_at(price, compare_at):
    # La oferta solo tiene sentido si el precio anterior es mayor al actual
    if compare_at is not None and float(compare_at) <= float(price):
        raise HTTPException(
            status_code=400,
            detail="El precio anterior (tachado) debe ser mayor al precio actual.",
        )


def _validate_stock(species: Species, stock: int):
    # Los individuales tienen folio único: su stock siempre es 1.
    # Cantidades mayores son solo para especies en cepa/paquete.
    if stock != 1 and species.sale_format == "individual":
        raise HTTPException(
            status_code=400,
            detail="Solo las especies en cepa o paquete aceptan stock mayor a 1.",
        )


# =========================================================
# GET /
# =========================================================
def _animals_query(db, species_id=None, genus_id=None, group_id=None,
                   animal_status=None, exclude_group_ids=None,
                   exclude_hidden_taxa=False):
    query = _query_with_relations(db)
    if species_id is not None:
        query = query.filter(Animal.species_id == species_id)
    if genus_id is not None:
        query = query.filter(
            Animal.species_id.in_(db.query(Species.id).filter(Species.genus_id == genus_id))
        )
    if group_id is not None:
        # Incluye animales de subgrupos (Arácnidos trae Tarántulas, Escorpiones…)
        genus_ids = db.query(Genus.id).filter(
            Genus.group_id.in_(descendant_group_ids(db, group_id))
        )
        query = query.filter(
            Animal.species_id.in_(db.query(Species.id).filter(Species.genus_id.in_(genus_ids)))
        )
    if exclude_group_ids:
        hidden_genus_ids = db.query(Genus.id).filter(Genus.group_id.in_(exclude_group_ids))
        hidden_species_ids = db.query(Species.id).filter(Species.genus_id.in_(hidden_genus_ids))
        query = query.filter(~Animal.species_id.in_(hidden_species_ids))
    # Opt-in a proposito: esta query la comparten el listado admin y el publico.
    # Si el filtro se aplicara siempre, una especie oculta desapareceria tambien
    # del dashboard y nadie podria volver a publicarla.
    if exclude_hidden_taxa:
        query = query.filter(
            Animal.species_id.in_(db.query(Species.id).filter(Species.show_public.is_(True)))
        )
        # Un ejemplar puede llevar varios morphs: si CUALQUIERA esta oculto, el
        # ejemplar se esconde. Sigue llevando ese morph, asi que su ficha lo
        # mostraria; esconder de menos seria la fuga.
        hidden_morph_ids = db.query(Morph.id).filter(Morph.show_public.is_(False))
        query = query.filter(
            ~Animal.morphs.any(Morph.id.in_(hidden_morph_ids))
        )
    if animal_status is not None:
        query = query.filter(Animal.status == animal_status.value)
    return query.order_by(Animal.id.desc())


@router.get("", response_model=PaginatedResponse[AnimalResponse],
            summary="List animals", dependencies=CAN_READ_ANIMALS)
async def list_animals(
    db: db_dependency,
    species_id: Optional[int] = None,
    genus_id: Optional[int] = None,
    group_id: Optional[int] = None,
    animal_status: Optional[AnimalStatusEnum] = Query(None, alias="status"),
    pagination: PaginationParams = Depends(),
):
    return paginate(
        _animals_query(db, species_id, genus_id, group_id, animal_status), pagination
    )


# =========================================================
# GET /{animal_id}
# =========================================================
@router.get("/{animal_id}", response_model=AnimalResponse,
            summary="Get animal by ID", dependencies=CAN_READ_ANIMALS)
async def get_animal(animal_id: int, db: db_dependency):
    animal = _query_with_relations(db).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")
    return animal


# =========================================================
# POST /
# =========================================================
@router.post("", response_model=AnimalResponse, status_code=status.HTTP_201_CREATED,
             summary="Create an animal (auto-creates its POS product)",
             dependencies=CAN_CREATE_ANIMALS)
async def create_animal(payload: AnimalCreate, db: db_dependency):
    species = db.get(Species, payload.species_id)
    if not species:
        raise HTTPException(status_code=400, detail="Species not found.")

    morphs = _validate_morphs(db, payload.morph_ids, species.id)
    _validate_stock(species, payload.stock)
    _validate_compare_at(payload.price, payload.compare_at_price)

    code = payload.code or f"AN-{uuid.uuid4().hex[:8].upper()}"
    if db.query(Animal.id).filter(Animal.code == code).first():
        raise HTTPException(status_code=400, detail="An animal with this code already exists.")

    # Sin image explícita, la primera foto es la principal
    main_image = payload.image or (payload.photos[0] if payload.photos else None)

    title = _animal_title(species, code, morphs)
    product = Product(
        title=title,
        slug=slugify(title),
        sku=code,
        price_retail=payload.price,
        price_cost=payload.price_cost,
        compare_at_price=payload.compare_at_price,
        product_category_id=_animals_category_id(db),
        is_unit_sale=True,
        unit_name="pieza",
        tracks_batches=True,
        image=main_image,
        description=payload.description,
    )
    db.add(product)
    db.flush()

    # Lote único sin caducidad: el FIFO existente descuenta cada venta.
    # Individuales: 1 (imposible vender el mismo folio dos veces);
    # cepas/paquetes: N unidades idénticas bajo un solo registro.
    db.add(ProductBatch(
        product_id=product.id,
        quantity=payload.stock,
        purchase_price=payload.price_cost,
    ))

    animal = Animal(
        species_id=species.id,
        product_id=product.id,
        code=code,
        sex=payload.sex.value,
        birth_date=payload.birth_date,
        price=payload.price,
        compare_at_price=payload.compare_at_price,
        price_cost=payload.price_cost,
        description=payload.description,
        image=main_image,
        requires_legal_doc=payload.requires_legal_doc,
        legal_doc=payload.legal_doc,
        legal_doc_url=payload.legal_doc_url,
    )
    animal.morphs = morphs
    animal.photos = [AnimalPhoto(url=u) for u in payload.photos]
    db.add(animal)
    db.commit()

    return _query_with_relations(db).filter(Animal.id == animal.id).first()


# =========================================================
# PUT /{animal_id}
# =========================================================
@router.put("/{animal_id}", response_model=AnimalResponse,
            summary="Update an animal", dependencies=CAN_UPDATE_ANIMALS)
async def update_animal(animal_id: int, payload: AnimalUpdate, db: db_dependency):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")

    final_species_id = payload.species_id if payload.species_id is not None else animal.species_id
    species = db.get(Species, final_species_id)
    if not species:
        raise HTTPException(status_code=400, detail="Species not found.")

    if payload.morph_ids is not None:
        animal.morphs = _validate_morphs(db, payload.morph_ids, final_species_id)
    elif payload.species_id is not None and payload.species_id != animal.species_id:
        wrong = [m.name for m in animal.morphs if m.species_id != final_species_id]
        if wrong:
            raise HTTPException(
                status_code=400,
                detail="Changing species invalidates current morphs; send morph_ids with the update.",
            )

    if payload.code is not None and payload.code != animal.code:
        if db.query(Animal.id).filter(Animal.code == payload.code, Animal.id != animal_id).first():
            raise HTTPException(status_code=400, detail="An animal with this code already exists.")

    if payload.photos is not None:
        animal.photos = [AnimalPhoto(url=u) for u in payload.photos]

    update_data = payload.model_dump(exclude_unset=True, exclude={"morph_ids", "photos", "stock"})
    for key, value in update_data.items():
        setattr(animal, key, value.value if hasattr(value, "value") else value)

    # Ajustar stock = reescribir el lote del producto gemelo (resurtir cepa)
    if payload.stock is not None:
        _validate_stock(species, payload.stock)
        batches = (
            db.query(ProductBatch)
            .filter(ProductBatch.product_id == animal.product_id)
            .order_by(ProductBatch.id)
            .all()
        )
        if batches:
            batches[0].quantity = payload.stock
            for extra in batches[1:]:
                extra.quantity = 0
        else:
            db.add(ProductBatch(
                product_id=animal.product_id,
                quantity=payload.stock,
                purchase_price=animal.price_cost,
            ))
        # Resurtir una cepa agotada la regresa a la venta
        if animal.status == AnimalStatusEnum.SOLD.value:
            animal.status = AnimalStatusEnum.AVAILABLE.value

    _validate_compare_at(animal.price, animal.compare_at_price)

    # Sincronizar el producto gemelo
    product = db.get(Product, animal.product_id)
    if product:
        product.price_retail = animal.price
        product.compare_at_price = animal.compare_at_price
        product.price_cost = animal.price_cost
        product.sku = animal.code
        product.description = animal.description
        product.image = animal.image
        title = _animal_title(species, animal.code, animal.morphs)
        if title != product.title:
            product.title = title
            product.slug = slugify(title)

    db.commit()
    return _query_with_relations(db).filter(Animal.id == animal_id).first()


# =========================================================
# DELETE /{animal_id}
# =========================================================
@router.delete("/{animal_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete an animal (and its POS product)",
               dependencies=CAN_DELETE_ANIMALS)
async def delete_animal(animal_id: int, db: db_dependency):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")
    if animal.status == AnimalStatusEnum.SOLD.value:
        raise HTTPException(status_code=400, detail="Cannot delete a sold animal.")

    if db.query(SaleDetail.id).filter(SaleDetail.product_id == animal.product_id).first():
        raise HTTPException(status_code=400, detail="Cannot delete an animal referenced by a sale.")

    product = db.get(Product, animal.product_id)
    db.delete(animal)
    if product:
        db.delete(product)  # cascade elimina su lote
    db.commit()
