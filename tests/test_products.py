import pytest
from pharmatrack.api.routes.products import get_db as original_get_db
from .utils import override_get_db, app, client, route_client_factory
from fastapi import status

app.dependency_overrides[original_get_db] = override_get_db
product_get, product_post, product_put, product_patch, product_delete = route_client_factory(client, prefix="products")


# =========================================================
# Helpers
# =========================================================

def _slugify_product(title: str, sku: str = None) -> str:
    from pharmatrack.utils.slugify import slugify
    parts = [title, sku] if sku else [title]
    return slugify(" ".join(parts))


def _make_category(db_session):
    from pharmatrack.models.product_categories.orm import ProductCategory
    from pharmatrack.utils.slugify import slugify
    import uuid
    name = f"Cat-{uuid.uuid4().hex[:6]}"
    cat = ProductCategory(name=name, slug=slugify(name), is_active=True)
    db_session.add(cat)
    db_session.flush()
    return cat


# =========================================================
# Fixtures
# =========================================================

@pytest.fixture
def test_product(db_session):
    from pharmatrack.models.products.orm import Product
    cat = _make_category(db_session)
    sku = "COLA600ML"
    title = "Refresco Cola 600ml"
    p = Product(
        title=title,
        slug=_slugify_product(title, sku),
        image="https://example.com/images/cola600.png",
        price_retail=20.0,
        price_cost=18.0,
        description="Refresco de cola en presentación de 600ml",
        sku=sku,
        is_active=True,
        allow_warranty=False,
        is_unit_sale=True,   # unit sale: evita requerir base_unit_name/units_per_base
        unit_name="pieza",
        product_category_id=cat.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def another_product(db_session):
    from pharmatrack.models.products.orm import Product
    cat = _make_category(db_session)
    sku = "GALLETASCHOC"
    title = "Galletas de Chocolate"
    p = Product(
        title=title,
        slug=_slugify_product(title, sku),
        image="https://example.com/images/galletas_chocolate.png",
        price_retail=15.0,
        price_cost=13.0,
        description="Deliciosas galletas de chocolate",
        sku=sku,
        is_active=True,
        allow_warranty=False,
        is_unit_sale=True,
        unit_name="pieza",
        product_category_id=cat.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def another_test_ingredient(db_session):
    from pharmatrack.models.ingredients.orm import Ingredient
    from pharmatrack.utils.slugify import slugify
    # Nombre en minúsculas sin tildes — el validator normaliza a lowercase
    # y solo acepta [a-z0-9._\- ]+
    ing = Ingredient(name="codeina", slug=slugify("codeina"))
    db_session.add(ing)
    db_session.commit()
    db_session.refresh(ing)
    return ing


@pytest.fixture
def product_with_ingredients(db_session, test_ingredient, another_test_ingredient):
    from pharmatrack.models.products.orm import Product
    from pharmatrack.models.product_has_ingredients.orm import ProductHasIngredient
    cat = _make_category(db_session)
    sku = "MEDCOMBINADO"
    title = "Medicamento Combinado"
    p = Product(
        title=title,
        slug=_slugify_product(title, sku),
        image="https://example.com/images/medicamento_combinado.png",
        price_retail=50.0,
        price_cost=40.0,
        description="Medicamento que combina varios ingredientes activos",
        sku=sku,
        is_active=True,
        max_discount=10.0,
        tax_percentage=16.0,
        allow_warranty=False,
        warranty_days=0,
        is_unit_sale=False,
        unit_name="caja",
        product_category_id=cat.id,
    )
    db_session.add(p)
    db_session.flush()

    assoc1 = ProductHasIngredient(product_id=p.id, ingredient_id=test_ingredient.id, amount=500.0, unit="mg")
    assoc2 = ProductHasIngredient(product_id=p.id, ingredient_id=another_test_ingredient.id, amount=5.0, unit="mg")
    db_session.add_all([assoc1, assoc2])
    db_session.commit()
    db_session.refresh(p)
    return p


# Payload de producto válido para POST/PUT (sin campos prohibidos)
def _valid_payload(title="Test Product", sku="SKU001", category_id=None):
    return {
        "title": title,
        "image": "https://example.com/img.png",
        "price_retail": 20.0,
        "price_cost": 15.0,
        "description": "Descripción de prueba",
        "sku": sku,
        "is_active": True,
        "allow_warranty": False,
        "is_unit_sale": True,   # unit sale: no requiere base_unit_name/units_per_base
        "unit_name": "pieza",
        **({"product_category_id": category_id} if category_id else {}),
    }


# =========================================================
# 🔹 GET /  — PaginatedResponse
# =========================================================

def test_read_all_empty(auth_headers, db_session):
    from pharmatrack.models.products.orm import Product
    db_session.query(Product).delete()
    db_session.commit()
    response = product_get(headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert data["total"] == 0


def test_read_all_with_data(auth_headers, test_product):
    response = product_get(headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] >= 1
    ids = [p["id"] for p in data["data"]]
    assert test_product.id in ids


def test_read_all_no_auth():
    response = product_get()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_read_all_order(auth_headers, db_session):
    """Productos ordenados por created_at descendente."""
    from pharmatrack.models.products.orm import Product
    from datetime import datetime, timedelta, timezone

    db_session.query(Product).delete()
    db_session.commit()

    cat = _make_category(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    p1 = Product(title="Primero", slug=_slugify_product("Primero", "P1"), sku="P1",
                 price_retail=10, price_cost=5, unit_name="pieza",
                 product_category_id=cat.id, created_at=now)
    p2 = Product(title="Segundo", slug=_slugify_product("Segundo", "P2"), sku="P2",
                 price_retail=20, price_cost=15, unit_name="pieza",
                 product_category_id=cat.id, created_at=now + timedelta(seconds=10))
    db_session.add_all([p1, p2])
    db_session.commit()

    response = product_get(headers=auth_headers)
    data = response.json()["data"]
    assert data[0]["title"] == "Segundo"
    assert data[1]["title"] == "Primero"


# =========================================================
# 🔹 GET /{id}  — ProductDetailsResponse
# =========================================================

def test_read_single_product(auth_headers, test_product):
    response = product_get(str(test_product.id), headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_product.id
    assert data["title"] == test_product.title
    assert data["sku"] == test_product.sku
    assert data["price_retail"] == test_product.price_retail
    assert data["price_cost"] == test_product.price_cost
    assert data["is_active"] == test_product.is_active
    assert "ingredients" in data
    assert isinstance(data["ingredients"], list)


def test_read_product_not_found(auth_headers):
    response = product_get("999999", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found."


def test_read_product_with_ingredients(auth_headers, product_with_ingredients):
    response = product_get(str(product_with_ingredients.id), headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "ingredients" in data
    assert len(data["ingredients"]) == 2

    ingredient_ids = {ing["ingredient_id"] for ing in data["ingredients"]}
    expected_ids = {
        product_with_ingredients.ingredients[0].ingredient_id,
        product_with_ingredients.ingredients[1].ingredient_id,
    }
    assert ingredient_ids == expected_ids


def test_read_product_no_ingredients(auth_headers, test_product):
    response = product_get(str(test_product.id), headers=auth_headers)
    data = response.json()
    assert "ingredients" in data
    assert data["ingredients"] == []


# =========================================================
# 🔹 GET /?search=  — filtro del listado base (el /search fue eliminado)
# =========================================================

def test_list_search_by_title(auth_headers, test_product):
    response = product_get("", params={"search": test_product.title}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] >= 1
    assert any(test_product.title.lower() in p["title"].lower() for p in data["data"])


def test_list_search_no_match(auth_headers):
    response = product_get("", params={"search": "NoExiste12345XYZ"}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] == 0


# =========================================================
# 🔹 GET /?show_online=  — filtro del listado base
# =========================================================

def test_list_filter_show_online_true(auth_headers, test_product, another_product, db_session):
    test_product.show_online = True
    another_product.show_online = False
    db_session.commit()

    response = product_get("", params={"show_online": "true"}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    ids = [p["id"] for p in response.json()["data"]]
    assert test_product.id in ids
    assert another_product.id not in ids


def test_list_filter_show_online_false(auth_headers, test_product, another_product, db_session):
    test_product.show_online = True
    another_product.show_online = False
    db_session.commit()

    response = product_get("", params={"show_online": "false"}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    ids = [p["id"] for p in response.json()["data"]]
    assert another_product.id in ids
    assert test_product.id not in ids


# =========================================================
# 🔹 POST /
# =========================================================

def test_create_product_basic(auth_headers, test_product_category):
    payload = _valid_payload("Basic Product", "BASICPRODUCT", test_product_category.id)
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["sku"] == payload["sku"]


def test_create_product_with_ingredients(auth_headers, test_product_category, test_ingredient, another_test_ingredient):
    payload = _valid_payload("New Product", "NEWPRODUCT", test_product_category.id)
    payload["ingredients"] = [
        {"ingredient_id": test_ingredient.id, "amount": 500, "unit": "mg"},
        {"ingredient_id": another_test_ingredient.id, "amount": 5, "unit": "mg"},
    ]
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["title"] == payload["title"]
    assert len(data["ingredients"]) == 2


def test_create_product_with_empty_ingredients(auth_headers, test_product_category):
    payload = _valid_payload("No Ingredients", "SKU_NO_ING", test_product_category.id)
    payload["ingredients"] = []
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["ingredients"] == []


def test_create_product_ingredients_none(auth_headers, test_product_category):
    payload = _valid_payload("None Ingredients", "SKU_NONE_ING", test_product_category.id)
    payload["ingredients"] = None
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["ingredients"] == []


def test_create_product_duplicate_sku(auth_headers, test_product):
    payload = _valid_payload("Duplicate SKU", test_product.sku, test_product.product_category_id)
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Product with this SKU already exists."

def test_create_product_non_existent_ingredient(auth_headers, test_product_category):
    payload = _valid_payload("Bad Ingredient", "SKU_BAD_ING", test_product_category.id)
    payload["ingredients"] = [{"ingredient_id": 99999, "amount": 100, "unit": "mg"}]
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Ingredient not found" in response.json()["detail"]


def test_create_product_mixed_valid_invalid_ingredients(auth_headers, test_product_category, test_ingredient):
    payload = _valid_payload("Mixed Ing", "SKU_MIXED", test_product_category.id)
    payload["ingredients"] = [
        {"ingredient_id": test_ingredient.id, "amount": 100, "unit": "mg"},
        {"ingredient_id": 9999, "amount": 50, "unit": "mg"},
    ]
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "9999" in response.json()["detail"]


def test_create_product_missing_title(auth_headers):
    payload = {
        "image": "https://example.com/img.png",
        "price_retail": 20,
        "price_cost": 10,
        "sku": "SKU_NO_TITLE",
        "unit_name": "pieza",
        "product_category_id": 1,
    }
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_product_extra_fields_forbidden(auth_headers):
    payload = _valid_payload("Extra Field", "SKU_EXTRA")
    payload["unexpected_field"] = "should not be allowed"
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_product_empty_sku(auth_headers):
    payload = _valid_payload("Empty SKU", "")
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_product_ingredients_wrong_type(auth_headers, test_product_category):
    payload = _valid_payload("Wrong Type", "SKU_BAD_ING_TYPE", test_product_category.id)
    payload["ingredients"] = {"ingredient_id": 1}  # dict en vez de lista
    response = product_post(json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_product_no_auth():
    payload = _valid_payload("Unauthorized", "SKU_UNAUTH")
    response = product_post(json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =========================================================
# 🔹 PUT /{id}
# =========================================================

def test_update_product(auth_headers, test_product):
    payload = {
        "title": "Updated Product",
        "image": "https://example.com/images/updated_product.png",
        "price_retail": 25.0,
        "price_cost": 22.0,
        "description": "Updated description",
        "is_active": True,
        "sku": test_product.sku,
    }
    response = product_put(str(test_product.id), json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == payload["title"]
    assert data["sku"] == payload["sku"]


def test_update_product_duplicate_sku(auth_headers, test_product, another_product):
    payload = {"sku": another_product.sku}
    response = product_put(str(test_product.id), json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Product with this SKU already exists."


def test_update_product_not_found(auth_headers):
    response = product_put("999", json={"title": "Ghost"}, headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found."


def test_update_product_no_auth(test_product):
    response = product_put(str(test_product.id), json={"title": "No auth"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_update_product_with_new_sku(auth_headers, test_product):
    payload = {"sku": "NONEXISTENTSKU", "title": "Updated Title"}
    response = product_put(str(test_product.id), json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["sku"] == "NONEXISTENTSKU"


def test_update_product_with_ingredients(auth_headers, test_product, test_ingredient, another_test_ingredient):
    payload = {
        "ingredients": [
            {"ingredient_id": test_ingredient.id, "amount": 500, "unit": "mg"},
            {"ingredient_id": another_test_ingredient.id, "amount": 250, "unit": "mg"},
        ]
    }
    response = product_put(str(test_product.id), json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    ingredient_ids = [ing["ingredient_id"] for ing in response.json()["ingredients"]]
    assert test_ingredient.id in ingredient_ids
    assert another_test_ingredient.id in ingredient_ids


def test_update_product_clear_ingredients(auth_headers, test_product, test_ingredient):
    # Asignar primero
    product_put(str(test_product.id), json={
        "ingredients": [{"ingredient_id": test_ingredient.id, "amount": 500, "unit": "mg"}]
    }, headers=auth_headers)

    # Luego limpiar
    response = product_put(str(test_product.id), json={"ingredients": []}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["ingredients"] == []


def test_update_product_ingredients_none_keeps_existing(auth_headers, test_product, test_ingredient):
    """ingredients=None no modifica los existentes."""
    product_put(str(test_product.id), json={
        "ingredients": [{"ingredient_id": test_ingredient.id, "amount": 500, "unit": "mg"}]
    }, headers=auth_headers)

    response = product_put(str(test_product.id), json={"title": "Updated"}, headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["ingredients"]) == 1


def test_update_product_mixed_valid_invalid_ingredients(auth_headers, test_product, test_ingredient):
    payload = {
        "ingredients": [
            {"ingredient_id": test_ingredient.id, "amount": 500, "unit": "mg"},
            {"ingredient_id": 9999, "amount": 100, "unit": "mg"},
        ]
    }
    response = product_put(str(test_product.id), json=payload, headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "9999" in response.json()["detail"]


def test_update_product_invalid_ingredients_type(auth_headers, test_product):
    response = product_put(str(test_product.id), json={"ingredients": "INVALID"}, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_update_product_extra_fields_forbidden(auth_headers, test_product):
    response = product_put(str(test_product.id), json={"extra_field": "bad"}, headers=auth_headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =========================================================
# 🔹 PATCH /{id}/toggle-active
# =========================================================

def test_patch_toggle_active(auth_headers, test_product):
    original = test_product.is_active
    response = product_patch(f"{test_product.id}/toggle-active", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_active"] == (not original)


def test_patch_toggle_active_not_found(auth_headers):
    response = product_patch("999/toggle-active", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found."


def test_patch_toggle_no_auth(test_product):
    response = product_patch(f"{test_product.id}/toggle-active")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =========================================================
# 🔹 PATCH /{id}/toggle-online
# =========================================================

def test_patch_toggle_online(auth_headers, test_product):
    original = test_product.show_online
    response = product_patch(f"{test_product.id}/toggle-online", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["show_online"] == (not original)


def test_patch_toggle_online_twice_reverts(auth_headers, test_product):
    original = test_product.show_online
    product_patch(f"{test_product.id}/toggle-online", headers=auth_headers)
    response = product_patch(f"{test_product.id}/toggle-online", headers=auth_headers)
    assert response.json()["show_online"] == original


def test_patch_toggle_online_only_touches_show_online(auth_headers, test_product):
    original_is_active = test_product.is_active
    original_title = test_product.title
    original_price_retail = test_product.price_retail

    response = product_patch(f"{test_product.id}/toggle-online", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_active"] == original_is_active
    assert data["title"] == original_title
    assert data["price_retail"] == original_price_retail


def test_patch_toggle_online_not_found(auth_headers):
    response = product_patch("999/toggle-online", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found."


def test_patch_toggle_online_no_auth(test_product):
    response = product_patch(f"{test_product.id}/toggle-online")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =========================================================
# 🔹 DELETE /{id}
# =========================================================

def test_delete_product(auth_headers, test_product):
    response = product_delete(str(test_product.id), headers=auth_headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_delete_product_verify_gone(auth_headers, test_product):
    product_delete(str(test_product.id), headers=auth_headers)
    response = product_get(str(test_product.id), headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_product_not_found(auth_headers):
    response = product_delete("999", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found."


def test_delete_product_no_auth(test_product):
    response = product_delete(str(test_product.id))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED