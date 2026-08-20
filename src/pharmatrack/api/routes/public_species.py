"""Catalogo por taxon: especies visibles con sus morphs visibles.

El listado de animales no basta para armar el catalogo: una especie sin ningun
ejemplar no aparece ahi, porque no hay nada de lo que derivarla. Este endpoint
expone los taxones para que el sitio pueda mostrarlos como agotados.

Devuelve taxonomia, NO tarjetas: el agrupamiento en tarjetas vive en el sitio
(buildListings), y duplicarlo aqui crearia dos reglas que pueden divergir.
"""
from typing import List

from fastapi import APIRouter
from pydantic import ConfigDict
from sqlalchemy.orm import joinedload, selectinload

from ...db.session import db_dependency
from ...models.animals.orm import Genus, Species
from ...models.animals.schemas import MorphResponse, SpeciesResponse
from .animal_taxonomy import hidden_group_ids

router = APIRouter(prefix="/public/species", tags=["Public"])


class PublicSpeciesResponse(SpeciesResponse):
    """La especie publica mas sus morphs visibles anidados."""

    morphs: List[MorphResponse] = []

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[PublicSpeciesResponse],
            summary="Especies visibles en el sitio, con o sin ejemplares")
async def public_list_species(db: db_dependency):
    hidden = hidden_group_ids(db)

    query = (
        db.query(Species)
        .options(
            # PublicSpeciesResponse anida genus -> group (GenusResponse trae
            # AnimalGroupResponse); sin cargar hasta group, Pydantic dispara
            # una consulta perezosa por cada genero distinto al serializar.
            joinedload(Species.genus).joinedload(Genus.group),
            selectinload(Species.morphs),
        )
        .filter(Species.show_public.is_(True))
    )
    if hidden:
        # Mismo criterio que el listado de animales: un grupo raiz oculto
        # esconde en cascada todo lo que cuelga de el.
        hidden_genus_ids = db.query(Genus.id).filter(Genus.group_id.in_(hidden))
        query = query.filter(~Species.genus_id.in_(hidden_genus_ids))

    rows = query.order_by(Species.name.asc()).all()

    return [
        PublicSpeciesResponse.model_validate(
            {
                **SpeciesResponse.model_validate(sp).model_dump(),
                "morphs": [
                    MorphResponse.model_validate(m).model_dump()
                    for m in sp.morphs
                    if m.show_public
                ],
            }
        )
        for sp in rows
    ]
