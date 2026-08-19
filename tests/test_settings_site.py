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
