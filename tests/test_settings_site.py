"""Ajustes del sitio publico: el PUT es parcial, no reemplaza el blob."""
import pytest
from datetime import timedelta
from passlib.context import CryptContext
from pharmatrack.utils.security import create_jwt_token
from .utils import client

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
def role_without_settings_update(db_session, make_permission):
    """Rol con todos los permisos del seed EXCEPTO settings.update."""
    from pharmatrack.models.roles.orm import Role
    from pharmatrack.seeds.seed_permissions import PERMISSIONS

    role = Role(name="limited_user")
    # Agregar todos los permisos MENOS settings.update
    perms_to_add = [name for name in PERMISSIONS if name != "settings.update"]
    role.permissions.extend(make_permission(name) for name in perms_to_add)

    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture
def user_without_settings_update(db_session, role_without_settings_update, test_branch):
    """Usuario con rol que no tiene settings.update."""
    from pharmatrack.models.users.orm import User

    user_data = {
        "name": "limited",
        "surname": "user",
        "email": "limited@example.com",
        "password": bcrypt_context.hash("secureMpassword123"),
        "avatar": "http://example.com/avatar.jpg",
        "phone": "3333333333",
        "type_document": "INE",
        "n_document": "DEF654321",
        "gender": "F",
        "role_id": role_without_settings_update.id,
        "branch_id": test_branch.id
    }
    user = User(**user_data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_without_settings_update(user_without_settings_update):
    """Auth headers para usuario sin settings.update."""
    token = create_jwt_token(
        username=user_without_settings_update.email,
        user_id=user_without_settings_update.id,
        role=user_without_settings_update.role.name,
        expires_delta=timedelta(minutes=30)
    )
    return {"Authorization": f"Bearer {token}"}


def test_put_parcial_no_pisa_los_otros_campos(auth_headers):
    # apaga envios
    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": False}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["shipping_enabled"] is False

    # toca OTRO campo: los envios deben seguir apagados
    res = client.put("/api/v1/settings/site",
                     json={"show_category_browse": False}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["show_category_browse"] is False
    assert body["shipping_enabled"] is False, "el PUT parcial piso shipping_enabled"

    # y la lectura publica coincide
    assert client.get("/api/v1/settings/site").json()["shipping_enabled"] is False


def test_put_null_explicito_no_cambia_el_valor(auth_headers):
    # establece shipping como False
    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": False}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["shipping_enabled"] is False

    # manda null explicito: no debe cambiar el valor
    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": None}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    # Debe seguir siendo False, no None
    assert body["shipping_enabled"] is False, "null explicito no debe cambiar el valor"
    assert isinstance(body["shipping_enabled"], bool), "el valor debe seguir siendo booleano"


def test_media_trae_los_nueve_slots_por_defecto():
    media = client.get("/api/v1/settings/site").json()["media"]
    assert set(media) == {
        "hero_video_mp4", "hero_video_webm", "hero_poster",
        "moss_tall", "moss_wide", "leaf_litter",
        "terrarium", "isopod_zebra", "isopod_cubaris",
    }
    assert all(url.startswith("https://") for url in media.values())


def test_actualizar_un_slot_no_borra_los_demas(auth_headers):
    antes = client.get("/api/v1/settings/site").json()["media"]

    res = client.put("/api/v1/settings/site",
                     json={"media": {"terrarium": "https://example.com/nuevo.jpg"}},
                     headers=auth_headers)
    assert res.status_code == 200, res.text

    despues = res.json()["media"]
    assert despues["terrarium"] == "https://example.com/nuevo.jpg"
    assert despues["moss_tall"] == antes["moss_tall"], "el PUT borro otro slot"
    assert len(despues) == 9


def test_escribir_ajustes_con_permiso_es_permitido(auth_headers):
    """Verificar que con settings.update se permite el PUT."""
    from pharmatrack.seeds.seed_permissions import PERMISSIONS
    assert "settings.update" in PERMISSIONS

    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": True}, headers=auth_headers)
    assert res.status_code == 200, res.text


def test_escribir_ajustes_rechaza_sin_settings_update(auth_headers_without_settings_update):
    """El decorador debe proteger con settings.update específicamente.
    Un rol sin settings.update debe recibir 403 incluso si tiene otros permisos."""
    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": True},
                     headers=auth_headers_without_settings_update)
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"


def test_escribir_ajustes_sin_token_es_rechazado():
    res = client.put("/api/v1/settings/site", json={"shipping_enabled": True})
    assert res.status_code in (401, 403)
