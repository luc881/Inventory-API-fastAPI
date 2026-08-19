"""Ajustes del sitio publico: el PUT es parcial, no reemplaza el blob."""
from .utils import client


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


def test_escribir_ajustes_exige_permiso_de_settings(auth_headers, db_session):
    """El rol de pruebas trae toda la lista del seed. Si settings.update no
    esta en esa lista, este PUT devuelve 403."""
    from pharmatrack.seeds.seed_permissions import PERMISSIONS
    assert "settings.update" in PERMISSIONS

    res = client.put("/api/v1/settings/site",
                     json={"shipping_enabled": True}, headers=auth_headers)
    assert res.status_code == 200, res.text


def test_escribir_ajustes_sin_token_es_rechazado():
    res = client.put("/api/v1/settings/site", json={"shipping_enabled": True})
    assert res.status_code in (401, 403)
