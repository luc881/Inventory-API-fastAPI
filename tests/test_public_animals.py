"""El catálogo público responde sin token y oculta los campos internos."""
from fastapi import status

from .utils import client, route_client_factory
from .test_animals import _make_taxonomy, _create_animal
from pharmatrack.models.animals.orm import Animal

_, _, animals_put, _, _ = route_client_factory(client, "animals")
_, _, species_put, _, _ = route_client_factory(client, "species")
_, morphs_post, morphs_put, _, _ = route_client_factory(client, "morphs")


def test_public_list_no_auth_and_hides_private_fields(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])

    res = client.get("/api/v1/public/animals")
    assert res.status_code == status.HTTP_200_OK
    row = next(a for a in res.json()["data"] if a["id"] == animal["id"])
    for private in ("price_cost", "product_id", "legal_doc", "legal_doc_url", "requires_legal_doc"):
        assert private not in row
    assert row["species"]["genus"]["name"] == "Brachypelma"
    assert row["species"]["sale_format"] == "individual"
    # la ficha de cuidados viaja al sitio público
    assert "origin" in row["species"] and "difficulty" in row["species"]

    detail = client.get(f"/api/v1/public/animals/{animal['id']}")
    assert detail.status_code == status.HTTP_200_OK
    assert "price_cost" not in detail.json()


def test_public_list_only_available_but_detail_keeps_shared_links(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])
    animals_put(f"/{animal['id']}", json={"status": "reserved"}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert all(a["id"] != animal["id"] for a in data)

    detail = client.get(f"/api/v1/public/animals/{animal['id']}")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.json()["status"] == "reserved"


def _mark_sold(db_session, animal_id):
    # "sold" no se puede poner vía PUT (lo asigna el flujo de venta), así que
    # para estos tests se escribe directo en la sesión que comparte el TestClient.
    db_session.query(Animal).filter(Animal.id == animal_id).update({"status": "sold"})
    db_session.commit()


def test_public_list_default_excludes_sold(auth_headers, db_session):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])
    _mark_sold(db_session, animal["id"])

    data = client.get("/api/v1/public/animals").json()["data"]
    assert all(a["id"] != animal["id"] for a in data)


def test_public_list_include_unavailable_shows_sold_with_status(auth_headers, db_session):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])
    _mark_sold(db_session, animal["id"])

    data = client.get("/api/v1/public/animals", params={"include_unavailable": "true"}).json()["data"]
    row = next(a for a in data if a["id"] == animal["id"])
    assert row["status"] == "sold"


def test_public_list_include_unavailable_no_salta_especie_oculta(auth_headers, db_session):
    """El parametro relaja disponibilidad, no privacidad: una especie oculta
    sigue sin aparecer aunque el ejemplar este vendido y se pida include_unavailable."""
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])
    _mark_sold(db_session, animal["id"])
    species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals", params={"include_unavailable": "true"}).json()["data"]
    assert all(a["id"] != animal["id"] for a in data)


def test_public_species_care_info_roundtrip(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])

    care = {"origin": "Vietnam", "temperature": "22-26 °C", "humidity": "70-80 %",
            "adult_size": "15 mm", "difficulty": "Medio", "rarity": "Muy raro",
            "description": "Especie activa y rápida.",
            "habitat": "Hojarasca húmeda de bosque tropical.",
            "diet": "Detritívoro: hojas secas y madera en descomposición.",
            "notes": "Colonia establecida desde 2024."}
    assert species_put(f"/{sp['id']}", json=care, headers=auth_headers).status_code == status.HTTP_200_OK

    detail = client.get(f"/api/v1/public/animals/{animal['id']}").json()
    assert detail["species"]["origin"] == "Vietnam"
    assert detail["species"]["difficulty"] == "Medio"
    assert detail["species"]["description"] == "Especie activa y rápida."
    assert detail["species"]["habitat"] == "Hojarasca húmeda de bosque tropical."
    assert detail["species"]["diet"] == "Detritívoro: hojas secas y madera en descomposición."
    assert detail["species"]["notes"] == "Colonia establecida desde 2024."


def test_public_species_price_tiers_sorted(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])

    res = species_put(f"/{sp['id']}", json={
        "price_tiers": [{"quantity": 12, "price": 270}, {"quantity": 6, "price": 150}],
    }, headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK

    tiers = client.get(f"/api/v1/public/animals/{animal['id']}").json()["species"]["price_tiers"]
    assert [t["quantity"] for t in tiers] == [6, 12]
    assert tiers[0]["price"] == 150


def test_public_groups_no_auth_returns_hierarchy(auth_headers):
    group, subgroup, _, _, _ = _make_taxonomy(auth_headers)

    res = client.get("/api/v1/public/animals/groups")
    assert res.status_code == status.HTTP_200_OK
    by_id = {g["id"]: g for g in res.json()}
    assert by_id[group["id"]]["parent_id"] is None
    assert by_id[subgroup["id"]]["parent_id"] == group["id"]


def test_public_list_genus_filter(auth_headers):
    _, _, genus, sp, _ = _make_taxonomy(auth_headers)
    _, _, _, other_sp, _ = _make_taxonomy(
        auth_headers, group_name="Serpientes", subgroup_name="Pitones",
        genus_name="Python", species_name="Regius", morph_name="Banana",
    )
    animal = _create_animal(auth_headers, sp["id"])
    other_animal = _create_animal(auth_headers, other_sp["id"])

    ids = [a["id"] for a in client.get(
        "/api/v1/public/animals", params={"genus_id": genus["id"]}
    ).json()["data"]]
    assert animal["id"] in ids
    assert other_animal["id"] not in ids


def test_show_public_es_administrativo_y_default_true(auth_headers):
    """La bandera nace encendida, se puede apagar con un PUT parcial, y NO se
    filtra al sitio publico dentro de la especie embebida en cada animal."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    # nace encendida en la respuesta de administracion
    assert sp["show_public"] is True
    assert morph["show_public"] is True

    # se apaga con un PUT parcial, sin mandar el resto del objeto
    res = species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK, res.text
    assert res.json()["show_public"] is False
    # y no piso otros campos
    assert res.json()["name"] == sp["name"]

    # la vuelvo a prender: aqui se prueba la fuga del campo, no el filtro de
    # visibilidad (eso lo cubren los tests de mas abajo)
    species_put(f"/{sp['id']}", json={"show_public": True}, headers=auth_headers)

    # el sitio publico nunca ve el campo (la especie va embebida en el animal)
    row = next(a for a in client.get("/api/v1/public/animals").json()["data"]
               if a["id"] == animal["id"])
    assert "show_public" not in row["species"]


def test_especie_oculta_desaparece_del_listado_publico(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])

    assert any(a["id"] == animal["id"] for a in client.get("/api/v1/public/animals").json()["data"])

    species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert not any(a["id"] == animal["id"] for a in data)


def test_morph_oculto_desaparece_del_listado_publico(auth_headers):
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    assert any(a["id"] == animal["id"] for a in client.get("/api/v1/public/animals").json()["data"])

    morphs_put(f"/{morph['id']}", json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert not any(a["id"] == animal["id"] for a in data)


def test_un_morph_oculto_esconde_el_ejemplar_aunque_el_otro_sea_visible(auth_headers):
    """Decision del spec: si un ejemplar lleva un morph oculto, sigue llevandolo,
    asi que desaparece incluso de la tarjeta del morph visible. Esconder de mas
    es correcto; esconder de menos deja fugas en la ficha."""
    _, _, _, sp, morph_a = _make_taxonomy(auth_headers)
    morph_b = morphs_post(json={"species_id": sp["id"], "name": "Rubber Ducky"},
                          headers=auth_headers).json()
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph_a["id"], morph_b["id"]])

    morphs_put(f"/{morph_a['id']}", json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert not any(a["id"] == animal["id"] for a in data), \
        "un ejemplar con un morph oculto no debe aparecer, ni por su otro morph"


def test_enlace_directo_respeta_las_banderas(auth_headers):
    """Sin esto hay fuga: el listado esconde pero la URL directa sigue sirviendo."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    a1 = _create_animal(auth_headers, sp["id"])
    a2 = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    assert client.get(f"/api/v1/public/animals/{a1['id']}").status_code == status.HTTP_200_OK

    species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)
    assert client.get(f"/api/v1/public/animals/{a1['id']}").status_code == status.HTTP_404_NOT_FOUND

    species_put(f"/{sp['id']}", json={"show_public": True}, headers=auth_headers)
    morphs_put(f"/{morph['id']}", json={"show_public": False}, headers=auth_headers)
    assert client.get(f"/api/v1/public/animals/{a2['id']}").status_code == status.HTTP_404_NOT_FOUND


def test_el_listado_admin_sigue_viendo_lo_oculto(auth_headers):
    """El filtro es opt-in. Si se aplicara siempre, las especies ocultas
    desapareceran del dashboard y nadie podria volver a publicarlas."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    species_put(f"/{sp['id']}", json={"show_public": False}, headers=auth_headers)
    morphs_put(f"/{morph['id']}", json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/animals", headers=auth_headers).json()["data"]
    assert any(a["id"] == animal["id"] for a in data), \
        "el listado admin debe seguir mostrando los taxones ocultos"


def test_image_de_taxon_es_publica(auth_headers):
    """A diferencia de show_public, la imagen del taxon SI viaja al sitio:
    es la foto de la tarjeta cuando la especie no tiene ejemplares."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    url = "https://res.cloudinary.com/demo/image/upload/v1/especie.jpg"
    res = species_put(f"/{sp['id']}", json={"image": url}, headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK, res.text
    assert res.json()["image"] == url
    assert res.json()["name"] == sp["name"], "el PUT parcial no debe pisar otros campos"

    murl = "https://res.cloudinary.com/demo/image/upload/v1/morph.jpg"
    assert morphs_put(f"/{morph['id']}", json={"image": murl},
                      headers=auth_headers).status_code == status.HTTP_200_OK

    row = next(a for a in client.get("/api/v1/public/animals").json()["data"]
               if a["id"] == animal["id"])
    assert row["species"]["image"] == url
    assert row["morphs"][0]["image"] == murl
