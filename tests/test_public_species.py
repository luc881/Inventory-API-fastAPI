"""El catalogo por taxon: las especies visibles se exponen tengan o no
ejemplares, para que el sitio pueda mostrarlas como agotadas."""
from fastapi import status

from .utils import client, route_client_factory
from .test_animals import _make_taxonomy

_, _, species_put, _, _ = route_client_factory(client, "species")
_, morphs_post, morphs_put, _, _ = route_client_factory(client, "morphs")
_, _, groups_put, _, _ = route_client_factory(client, "animal-groups")


def _names(res):
    return {s["name"] for s in res.json()}


def test_una_especie_sin_ejemplares_aparece(auth_headers):
    """El motivo de existir del endpoint: el listado de animales no puede
    mostrarla porque no hay ningun ejemplar del que derivarla."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)

    res = client.get("/api/v1/public/species")
    assert res.status_code == status.HTTP_200_OK
    assert sp["name"] in _names(res)

    fila = next(s for s in res.json() if s["name"] == sp["name"])
    assert [m["name"] for m in fila["morphs"]] == [morph["name"]]


def test_respeta_las_reglas_de_taxonomia(auth_headers):
    _, _, _, sp, morph = _make_taxonomy(auth_headers)

    # morph oculto: desaparece el morph, no la especie
    morphs_put(f"/{morph['id']}", json={"show_public": False}, headers=auth_headers)
    fila = next(s for s in client.get("/api/v1/public/species").json() if s["name"] == sp["name"])
    assert fila["morphs"] == []

    # especie oculta: desaparece la especie
    species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)
    assert sp["name"] not in _names(client.get("/api/v1/public/species"))


def test_un_grupo_raiz_oculto_esconde_sus_especies(auth_headers):
    root, _sub, _genus, sp, _morph = _make_taxonomy(auth_headers)
    assert sp["name"] in _names(client.get("/api/v1/public/species"))

    # el genero cuelga de un SUBgrupo: esto prueba la cascada, no el caso trivial
    groups_put(f"/{root['id']}", json={"show_public": False}, headers=auth_headers)
    assert sp["name"] not in _names(client.get("/api/v1/public/species"))


def test_no_expone_campos_privados(auth_headers):
    _make_taxonomy(auth_headers)
    fila = client.get("/api/v1/public/species").json()[0]
    for privado in ("show_public", "husbandry_status", "low_stock_threshold", "private_notes"):
        assert privado not in fila, f"{privado} no debe viajar al sitio publico"
    for m in fila["morphs"]:
        for privado in ("show_public", "husbandry_status", "private_notes"):
            assert privado not in m
