"""Catálogo público de la tienda: solo lectura, sin autenticación.

El listado expone únicamente animales disponibles; el detalle responde
también reservados/vendidos (con su status) para que un link compartido
muestre "ya no disponible" en lugar de un 404. Los campos internos
(costos, producto gemelo, documentación legal) los recorta
PublicAnimalResponse.
"""
from typing import Optional

from fastapi import Depends, HTTPException, APIRouter

from ...db.session import db_dependency
from ...models.animals.orm import Animal, AnimalGroup
from ...models.animals.schemas import PublicAnimalResponse, AnimalGroupResponse
from .animals import _animals_query, _query_with_relations
from .animal_taxonomy import hidden_group_ids
from pharmatrack.types.animals import AnimalStatusEnum
from pharmatrack.utils.pagination import paginate, PaginationParams, PaginatedResponse


router = APIRouter(prefix="/public/animals", tags=["Public"])


# Declarado antes de /{animal_id} para que "groups" no intente parsearse como int
@router.get("/groups", response_model=list[AnimalGroupResponse],
            summary="Public: animal group hierarchy")
async def public_list_groups(db: db_dependency):
    """Grupos visibles (con parent_id) para que el sitio arme las categorías raíz.
    Los grupos ocultos (y sus descendientes) no se exponen."""
    hidden = hidden_group_ids(db)
    query = db.query(AnimalGroup)
    if hidden:
        query = query.filter(~AnimalGroup.id.in_(hidden))
    return query.order_by(AnimalGroup.name).all()


@router.get("", response_model=PaginatedResponse[PublicAnimalResponse],
            summary="Public: list animals for sale")
async def public_list_animals(
    db: db_dependency,
    species_id: Optional[int] = None,
    genus_id: Optional[int] = None,
    group_id: Optional[int] = None,
    include_unavailable: bool = False,
    pagination: PaginationParams = Depends(),
):
    # ponytail: reutiliza el armado de query interno; response_model recorta lo
    # privado y exclude_group_ids esconde los grupos marcados como no publicos.
    # Opt-in a proposito (mismo patron que exclude_hidden_taxa en animals.py):
    # sin el parametro nada cambia, asi que el sitio puede pedirlo cuando este
    # listo sin que el backend rompa a nadie mas mientras tanto.
    query = _animals_query(
        db, species_id=species_id, genus_id=genus_id, group_id=group_id,
        animal_status=None if include_unavailable else AnimalStatusEnum.AVAILABLE,
        exclude_group_ids=hidden_group_ids(db),
        exclude_hidden_taxa=True,
    )
    return paginate(query, pagination)


@router.get("/{animal_id}", response_model=PublicAnimalResponse,
            summary="Public: animal detail")
async def public_get_animal(animal_id: int, db: db_dependency):
    animal = _query_with_relations(db).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found.")
    # Un grupo oculto también oculta el detalle (el listado ya lo excluye,
    # pero un link directo no debe seguir mostrando el animal)
    group_id = animal.species.genus.group_id if animal.species and animal.species.genus else None
    if group_id is not None and group_id in hidden_group_ids(db):
        raise HTTPException(status_code=404, detail="Animal not found.")
    # Mismas reglas que el listado: si el listado lo esconde, el enlace directo
    # tampoco debe servirlo. El status SI se conserva permisivo a proposito
    # (reservados y vendidos responden, para que un link compartido diga "ya no
    # disponible" en vez de 404).
    if animal.species and not animal.species.show_public:
        raise HTTPException(status_code=404, detail="Animal not found.")
    if any(not m.show_public for m in (animal.morphs or [])):
        raise HTTPException(status_code=404, detail="Animal not found.")
    return animal
