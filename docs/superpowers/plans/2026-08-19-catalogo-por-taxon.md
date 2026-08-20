# Catálogo armado por taxón — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las especies y morphs visibles aparezcan en el catálogo público aunque no tengan ningún ejemplar registrado, marcados como agotados y con foto propia.

**Architecture:** El catálogo deja de derivarse de los ejemplares y pasa a derivarse de los taxones visibles, a los que se les adjuntan sus ejemplares. El servidor gana un endpoint que expone esos taxones y una columna de imagen en especies y morphs; el agrupamiento en tarjetas sigue viviendo en un solo lugar, el sitio.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (API) · Next.js 16 App Router + MUI (sitio) · React 19 + Vite + MUI (dashboard)

**Spec:** `docs/superpowers/specs/2026-08-19-catalogo-por-taxon-design.md` (este mismo repo)

## Global Constraints

- Los tres repos commitean y pushean **directo a `main`**. Nunca abrir PRs.
- **No tocar** Mercado Pago ni Resend, ni la lógica de carrito/checkout (`routes/shop.py`).
- Nunca imprimir `PROD_DATABASE_URL` ni pedir secretos por chat.
- Mensajes de commit terminan con:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` y
  `Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm`
- `image` es un campo **público**: va en `SpeciesBase` / `MorphBase`. Es la
  excepción deliberada al patrón de `show_public`, que sí es administrativo.
- La marca **"Nominal"** aparece **siempre** en la especie base, tenga morphs o
  no, y **nunca** en un morph.
- Tests del backend con `poetry run python -m pytest`. Si aparecen cientos de
  errores raros de SQLAlchemy, son procesos `python.exe` colgados:
  `taskkill //F //IM python.exe`, esperar unos segundos y reintentar.
- Rutas: `~/dev/pharmatrack-api`, `~/dev/pharmatrack-web` (sitio),
  `~/dev/pharmatrack-frontend` (dashboard).

## Mapa de archivos

**`pharmatrack-api`**
| Archivo | Responsabilidad |
| --- | --- |
| `migrations/versions/taxonimage01_add_image_to_species_and_morphs.py` (nuevo) | La columna |
| `src/pharmatrack/models/animals/orm.py` | `image` en `Species` y `Morph` |
| `src/pharmatrack/models/animals/schemas.py` | `image` en las clases Base y en los Update |
| `src/pharmatrack/api/routes/public_species.py` (nuevo) | `GET /public/species` |
| `src/pharmatrack/api/v1.py` | Registra el router nuevo |
| `tests/test_public_species.py` (nuevo) | Las pruebas del endpoint |

**`pharmatrack-web` (sitio)**
| Archivo | Responsabilidad |
| --- | --- |
| `src/lib/public-api.js` | `getSpeciesCatalog()` |
| `src/sections/catalog/utils.js` | `buildListings` invertida |
| `app/page.jsx`, `catalogo/page.jsx`, `catalogo/[id]/page.jsx`, `favoritos/page.jsx`, `sitemap.js`, `api/search/route.js` | Los seis consumidores |
| `src/sections/catalog/od/od-catalog-view.jsx` | `animalToCard` expone la marca |
| `src/sections/catalog/od/od-catalog-card.jsx` | Banda de agotado y marca Nominal |
| `src/sections/catalog/od/od-species-details-view.jsx` | Marca Nominal en la ficha |

**`pharmatrack-frontend` (dashboard)**
| Archivo | Responsabilidad |
| --- | --- |
| `src/sections/animal/taxon-dialog.jsx` | Subida de imagen de especie y morph |
| `src/sections/animal/view/animal-taxonomy-view.jsx` | Marca "Nominal" |
| `src/sections/animal/view/site-animals-view.jsx` | Marca "Nominal" |

---

## Task 1: La columna `image` en especies y morphs

**Files:**
- Create: `migrations/versions/taxonimage01_add_image_to_species_and_morphs.py`
- Modify: `src/pharmatrack/models/animals/orm.py` (clases `Species` y `Morph`)
- Modify: `src/pharmatrack/models/animals/schemas.py`
- Test: `tests/test_public_animals.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Species.image` y `Morph.image` (`str | None`), escribibles con
  `PUT /api/v1/species/{id}` y `PUT /api/v1/morphs/{id}` con cuerpo parcial
  `{"image": "https://..."}`, y **legibles desde el sitio público** porque van en
  las clases Base. Las tasks 2, 3 y 5 dependen de esto.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_public_animals.py`:

```python
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
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_animals.py::test_image_de_taxon_es_publica -v
```

Esperado: FALLA con `KeyError: 'image'`.

- [ ] **Step 3: Agregar la columna al modelo**

En `src/pharmatrack/models/animals/orm.py`, clase `Species`, junto a los campos
de la ficha pública (antes del bloque `=== Manejo/cria (PRIVADO ===`):

```python
    # Foto del taxon para la tarjeta del catalogo. Las fotos "reales" cuelgan
    # del ejemplar; esta es la que se usa cuando la especie no tiene ninguno.
    image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
```

Y en la clase `Morph`, en la misma posición relativa:

```python
    # Foto propia del morph: sin ella, todos los morphs de una especie
    # compartirian imagen y se perderia justo lo que los distingue.
    image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
```

`String` y `Optional` ya están importados en ese archivo; confírmalo antes.

- [ ] **Step 4: Agregar el campo a los esquemas**

En `src/pharmatrack/models/animals/schemas.py`:

- `SpeciesBase`: `image: Optional[str] = Field(None, max_length=250)`
- `SpeciesUpdate`: `image: Optional[str] = Field(None, max_length=250)`
- `MorphBase`: `image: Optional[str] = Field(None, max_length=250)`
- `MorphUpdate`: `image: Optional[str] = Field(None, max_length=250)`

**Va en las clases Base a propósito**, al revés que `show_public`: la imagen es
contenido público, es la foto que ve el visitante. Las `*AdminResponse` la
heredan solas.

- [ ] **Step 5: Escribir la migración**

Crear `migrations/versions/taxonimage01_add_image_to_species_and_morphs.py`:

```python
"""add image to species and morphs (foto del taxon para la tarjeta)

Revision ID: taxonimage01
Revises: showpublictaxa01
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'taxonimage01'
down_revision: Union[str, Sequence[str], None] = 'showpublictaxa01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('species', 'morphs'):
        op.add_column(table, sa.Column('image', sa.String(length=250), nullable=True))


def downgrade() -> None:
    for table in ('species', 'morphs'):
        op.drop_column(table, 'image')
```

**Confirma la cabeza real antes** — si no es `showpublictaxa01`, usa la que imprima:

```bash
cd ~/dev/pharmatrack-api && poetry run alembic heads
```

- [ ] **Step 6: Aplicar la migración y correr las pruebas**

```bash
cd ~/dev/pharmatrack-api && poetry run alembic upgrade head
poetry run python -m pytest tests/test_public_animals.py -v
```

Esperado: todo PASS.

- [ ] **Step 7: Commit**

```bash
cd ~/dev/pharmatrack-api
git add migrations/versions/taxonimage01_add_image_to_species_and_morphs.py src/pharmatrack/models/animals/orm.py src/pharmatrack/models/animals/schemas.py tests/test_public_animals.py
git commit -m "feat(taxonomia): imagen propia en especies y morphs

Las fotos cuelgan del ejemplar, asi que una especie sin ninguno no tiene ninguna
imagen que mostrar en el catalogo. El campo es publico (va en las clases Base,
al reves que show_public): es la foto que ve el visitante.

Va tambien en el morph porque el sitio arma una tarjeta por morph; con la imagen
solo en la especie, todos compartirian foto.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm"
git push origin main
```

---

## Task 2: `GET /public/species`

**Files:**
- Create: `src/pharmatrack/api/routes/public_species.py`
- Modify: `src/pharmatrack/api/v1.py:43` (zona de routers públicos)
- Test: `tests/test_public_species.py` (crear)

**Interfaces:**
- Consumes: `Species.image` / `Morph.image` de la Task 1.
- Produces: `GET /api/v1/public/species` → lista de especies visibles, cada una
  con `morphs[]` anidados (solo los visibles). La Task 3 la consume.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_public_species.py`:

```python
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
```

Revisa el orden real de la tupla que devuelve `route_client_factory` en
`tests/utils.py` (es `get, post, put, patch, delete`) y confirma el prefijo real
de la ruta de grupos; los otros archivos de prueba sirven de referencia.

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_species.py -v
```

Esperado: FALLAN con 404 — la ruta no existe.

- [ ] **Step 3: Escribir el endpoint**

Crear `src/pharmatrack/api/routes/public_species.py`:

```python
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
        .options(joinedload(Species.genus), selectinload(Species.morphs))
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
```

`Species.morphs` existe como relación: la clase `Morph` declara
`species = relationship("Species", back_populates="morphs")`. Confírmalo.

- [ ] **Step 4: Registrar el router**

En `src/pharmatrack/api/v1.py`, junto a los otros routers públicos (línea ~43):

```python
api_v1_router.include_router(public_species.router)
```

más su import arriba, con los demás.

- [ ] **Step 5: Correr las pruebas**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_species.py tests/test_public_animals.py -v
```

Esperado: todo PASS.

- [ ] **Step 6: Correr la suite completa**

```bash
cd ~/dev/pharmatrack-api
taskkill //F //IM python.exe 2>/dev/null; sleep 3
poetry run python -m pytest -q
```

Esperado: todo PASS (referencia reciente: 505 más las nuevas).

- [ ] **Step 7: Commit**

```bash
cd ~/dev/pharmatrack-api
git add src/pharmatrack/api/routes/public_species.py src/pharmatrack/api/v1.py tests/test_public_species.py
git commit -m "feat(publico): endpoint de especies visibles, con o sin ejemplares

El listado de animales no puede mostrar una especie sin ejemplares: no hay nada
de lo que derivarla. Este endpoint expone los taxones visibles para que el sitio
los pinte como agotados.

Devuelve taxonomia, no tarjetas: el agrupamiento sigue viviendo solo en el sitio
para que no haya dos reglas que puedan divergir.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm"
git push origin main
```

---

## Task 3: El catálogo del sitio se arma por taxón

Es la task de más alcance: `buildListings` la usan **seis** superficies.

**Files:**
- Modify: `~/dev/pharmatrack-web/src/lib/public-api.js`
- Modify: `~/dev/pharmatrack-web/src/sections/catalog/utils.js` (`buildListings`, líneas ~157-215)
- Modify: `~/dev/pharmatrack-web/src/app/page.jsx:17`
- Modify: `~/dev/pharmatrack-web/src/app/catalogo/page.jsx:20`
- Modify: `~/dev/pharmatrack-web/src/app/catalogo/[id]/page.jsx:45`
- Modify: `~/dev/pharmatrack-web/src/app/favoritos/page.jsx:20`
- Modify: `~/dev/pharmatrack-web/src/app/sitemap.js:19`
- Modify: `~/dev/pharmatrack-web/src/app/api/search/route.js:16`

**Interfaces:**
- Consumes: `GET /api/v1/public/species` de la Task 2.
- Produces: `getSpeciesCatalog()` y `buildListings(animals, taxa)`. La Task 4
  consume las entradas que produce, incluidas las de `count: 0`.

- [ ] **Step 1: Agregar `getSpeciesCatalog()`**

En `src/lib/public-api.js`, siguiendo el patrón de las otras funciones (mismo
`next: { revalidate: 60 }`, mismo `try/catch` con respaldo):

```js
// Taxones visibles del catalogo. Complementa a getAnimals(): una especie sin
// ejemplares no aparece alli, pero debe salir en el sitio como agotada.
export async function getSpeciesCatalog() {
  try {
    const res = await fetch(`${CONFIG.serverUrl}/api/v1/public/species`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}
```

El respaldo es `[]` a propósito: si este endpoint falla, el catálogo se arma
solo con los taxones que tengan ejemplares — degrada al comportamiento anterior
en vez de quedarse vacío.

- [ ] **Step 2: Invertir `buildListings`**

En `src/sections/catalog/utils.js`, acepta un segundo argumento y **siembra una
entrada por cada taxón visible antes** de recorrer los ejemplares:

```js
// Antes esta funcion nacia de los ejemplares, asi que una especie sin ninguno
// no producia tarjeta. Ahora nace de los taxones visibles y les adjunta sus
// ejemplares: los que no tengan quedan con count 0, que es exactamente el
// camino "Agotado" que animalToCard ya implementa.
export function buildListings(animals, taxa = []) {
  const map = new Map();

  const seed = (species, morph) => {
    const key = listingKey(species, morph);
    if (map.has(key)) return map.get(key);
    const entry = {
      key,
      species,
      morph,
      title: listingTitle(species, morph),
      slug: listingSlug(species, morph),
      description: morph?.description ?? species.description ?? null,
      minPrice: null,
      maxPrice: null,
      compareAt: null,
      lastPrice: null,
      latestId: 0,
      count: 0,
      // La foto del taxon es el respaldo: si llega un ejemplar con foto propia,
      // se antepone al recorrerlos.
      photos: [morph?.image ?? species.image].filter(Boolean),
      morphs: morph ? [morph] : [],
      sexes: [],
    };
    map.set(key, entry);
    return entry;
  };

  // 1) Una entrada por cada taxon visible: la especie base y cada morph.
  taxa.forEach((species) => {
    seed(species, null);
    (species.morphs ?? []).forEach((morph) => seed(species, morph));
  });

  // 2) Adjuntar los ejemplares a su entrada (creandola si el taxon no vino).
  animals.forEach((animal) => {
    if (!animal.species) return;
    const morph = animal.morphs?.[0] ?? null;
    const entry = seed(animal.species, morph);
    entry.lastPrice = animal.price;
    // ...aqui sigue, sin cambios, el cuerpo actual del forEach...
  });
```

**Conserva intacto** el resto del cuerpo actual: el bloque
`if (animal.status === 'available')` que suma `count` y calcula
`minPrice`/`maxPrice`, el `latestId`, los `sexes`, las fotos, y el `map` final
que aplica `price_tiers`. Solo cambia de dónde nacen las entradas.

Ojo con `latestId`: hoy se inicializa con el id del primer ejemplar. Al sembrar
desde el taxón ya no hay ejemplar, así que arranca en `0` y el
`Math.max(entry.latestId, animal.id)` que ya existe lo corrige en cuanto llegue
uno. Verifica que nadie asuma que `latestId` es un id real de animal.

- [ ] **Step 3: Actualizar los seis consumidores**

Cada uno debe pedir también los taxones y pasarlos. En los que ya usan
`Promise.all`, agrega `getSpeciesCatalog()` ahí; en los que no, créalo.

```js
const [{ data: animals }, taxa] = await Promise.all([getAnimals(), getSpeciesCatalog()]);
const listings = buildListings(animals, taxa);
```

Los seis, con su línea actual:
- `src/app/page.jsx:17` — `buildListings(animals)`
- `src/app/catalogo/page.jsx:20` — dentro del JSX
- `src/app/catalogo/[id]/page.jsx:45` — `listings: buildListings(animals)`
- `src/app/favoritos/page.jsx:20` — dentro del JSX
- `src/app/sitemap.js:19` — dentro del spread
- `src/app/api/search/route.js:16` — `buildListings(animals).map(...)`

**No dejes ninguno sin actualizar.** Uno que siga llamando con un solo argumento
no falla —`taxa` tiene default `[]`— pero mostraría un catálogo distinto al de
las otras páginas, que es peor que un error visible.

- [ ] **Step 4: Lint y build**

```bash
cd ~/dev/pharmatrack-web && corepack yarn lint:fix && corepack yarn build
```

Esperado: verde.

- [ ] **Step 5: Verificar en vivo**

El sitio público no pide sesión, así que esto sí se puede comprobar.

Con el backend local en `http://127.0.0.1:8000` (si hace falta levantarlo:
`PYTHONPATH=src PYTHONIOENCODING=utf-8 poetry run uvicorn pharmatrack.main:app --host 127.0.0.1 --port 8000`
— el `PYTHONIOENCODING` no es opcional, sin él un emoji en un log mata el
arranque en Windows) y el sitio en `http://localhost:3033`:

1. El número de resultados **subió**: ahora hay una tarjeta por taxón visible,
   no solo por los que tienen ejemplares.
2. Las especies con ejemplares siguen mostrando su precio y su conteo correctos.
3. Las que no tienen ejemplares aparecen con el badge "Agotado".

Reporta los números concretos que viste antes y después.

- [ ] **Step 6: Commit**

```bash
cd ~/dev/pharmatrack-web
git add -A
git commit -m "feat(catalogo): las tarjetas nacen del taxon, no del ejemplar

Una especie sin ejemplares no producia tarjeta, asi que las 37 que el dueno
tiene publicadas no aparecian en el sitio. Ahora buildListings siembra una
entrada por taxon visible y les adjunta sus ejemplares: las que no tengan quedan
en count 0, que es el camino Agotado que animalToCard ya implementaba.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm"
git push origin main
```

---

## Task 4: Banda de "Agotado" y marca "Nominal" en el sitio

**Files:**
- Modify: `~/dev/pharmatrack-web/src/sections/catalog/od/od-catalog-view.jsx` (`animalToCard`, líneas ~57-90)
- Modify: `~/dev/pharmatrack-web/src/sections/catalog/od/od-catalog-card.jsx` (bloque `media`, líneas ~34-63)
- Modify: `~/dev/pharmatrack-web/src/sections/catalog/od/od-species-details-view.jsx`

**Interfaces:**
- Consumes: las entradas de `buildListings` (Task 3), que ya traen `morph`.
- Produces: nada que otra task consuma.

- [ ] **Step 1: Exponer la marca desde `animalToCard`**

En `od-catalog-view.jsx`, `animalToCard` ya calcula `soldOut = i.count === 0`.
Agrega al objeto que devuelve:

```js
    // "Nominal" distingue la forma base de sus variantes. Va como campo aparte
    // y NO dentro de title: listingSlug deriva del titulo, asi que meterlo ahi
    // cambiaria la URL de todas las especies y romperia los enlaces existentes.
    taxonLabel: i.morph ? null : 'Nominal',
```

**Ese comentario no es decorativo:** `listingSlug` llama a `listingTitle`
(`utils.js:142-144`), así que cualquier cambio en el título cambia el slug.

- [ ] **Step 2: Pintar la banda y la marca en la tarjeta**

En `od-catalog-card.jsx`, dentro del `Box` de `media` (que ya es
`position: 'relative'`), después del badge existente:

```jsx
      {soldOut && (
        <Box
          sx={{
            position: 'absolute',
            top: 18,
            right: -34,
            width: 140,
            transform: 'rotate(45deg)',
            bgcolor: '#b3261e',
            color: '#fff',
            textAlign: 'center',
            py: '5px',
            fontSize: 11,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            pointerEvents: 'none',
            zIndex: 2,
          }}
        >
          Agotado
        </Box>
      )}
```

La banda va en la esquina **superior derecha** y `pointerEvents: 'none'` para no
robarle el clic al corazón de favoritos, que vive cerca. Verifica en vivo que no
lo tape ni tape la barra de acciones del hover; si choca, mueve uno de los dos,
no elimines ninguno.

Si `src/global.css` ya define un token de error, úsalo en vez del rojo literal.

Y la marca Nominal, junto al código y la categoría que la tarjeta ya pinta:

```jsx
        {card.taxonLabel && (
          <Box component="span" sx={{ opacity: 0.7 }}> · {card.taxonLabel}</Box>
        )}
```

- [ ] **Step 3: La marca en la ficha de especie**

En `od-species-details-view.jsx`, junto al título, muestra `Nominal` cuando el
listado **no** tiene morph (`!item.morph`). Usa el lenguaje visual sobrio del
resto de la ficha (una `Pill` o texto pequeño en mayúsculas, como los que esa
vista ya usa).

- [ ] **Step 4: Lint, build y verificación en vivo**

```bash
cd ~/dev/pharmatrack-web && corepack yarn lint:fix && corepack yarn build
```

En `http://localhost:3033/catalogo` comprueba:
1. Las tarjetas agotadas llevan **banda roja** en la esquina, legible.
2. La banda **no tapa** el corazón de favoritos ni la barra de acciones del hover.
3. Las tarjetas de especie base dicen **"Nominal"**; las de morph, no.
4. Prueba también la vista de lista (el selector "ver" de la barra superior),
   donde la tarjeta se pinta horizontal: la banda no debe descuadrarla.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/pharmatrack-web
git add -A
git commit -m "feat(catalogo): banda de agotado y marca Nominal en la tarjeta

La marca va como campo aparte y no dentro del titulo: listingSlug deriva del
titulo, asi que meterla ahi cambiaria la URL de todas las especies.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm"
git push origin main
```

---

## Task 5: Subir la imagen y marcar "Nominal" en el dashboard

**Files:**
- Modify: `~/dev/pharmatrack-frontend/src/sections/animal/taxon-dialog.jsx`
- Modify: `~/dev/pharmatrack-frontend/src/sections/animal/view/animal-taxonomy-view.jsx`
- Modify: `~/dev/pharmatrack-frontend/src/sections/animal/view/site-animals-view.jsx`

**Interfaces:**
- Consumes: `image` en `SpeciesUpdate` / `MorphUpdate` (Task 1).
- Produces: nada que otra task consuma.

- [ ] **Step 1: Subida de imagen en `TaxonDialog`**

`src/sections/animal/taxon-dialog.jsx` es el diálogo que crea y edita grupos,
géneros, especies y morphs. Hoy **no sube imágenes** (cero coincidencias de
`uploadToCloudinary` en el archivo).

Agrega un campo de imagen visible **solo** para `tab === 'species'` y
`tab === 'morphs'`:
- Un botón que abra el selector de archivo y suba con `uploadToCloudinary(file)`
  de `src/lib/cloudinary.js` (ya existe; su segundo argumento `resourceType`
  tiene default `'image'`, así que no hace falta pasarlo).
- Vista previa de la imagen actual.
- Opción de quitarla (manda `image: null`).
- Mientras sube, el botón de guardar del diálogo deshabilitado.

El valor viaja en el mismo `payload` que el diálogo ya arma, como un campo más:
el `PUT` del backend es parcial y no pisa nada.

**Copia el patrón de subida de `src/sections/site/view/site-media-view.jsx`**,
que ya resuelve el input de archivo anidado en un label (sin `htmlFor`, para no
disparar el selector dos veces) y el estado de "subiendo".

- [ ] **Step 2: Marca "Nominal" en Taxonomía**

En `src/sections/animal/view/animal-taxonomy-view.jsx`, pestaña Especies: la
tabla anida especies (`__kind === 'species'`) y morphs (`__kind === 'morph'`).
En la columna del nombre, para las filas de especie, agrega una `Label` de
`src/components/label` con el texto `Nominal`.

**Siempre**, tenga morphs o no: es lo que esa fila *es*, no una comparación con
sus variantes.

- [ ] **Step 3: Marca "Nominal" en Sitio web → Animales**

En `src/sections/animal/view/site-animals-view.jsx`, nivel Especies, la misma
marca con el mismo texto y el mismo componente, para que las dos pantallas se
lean igual.

Cuida que **no se confunda con las marcas que ya viven cerca**: `Agotado` (fila
visible sin existencias) y los motivos de no-visibilidad (`Grupo oculto`,
`Especie oculta`). `Nominal` dice *qué es* la fila; las otras dicen *cómo está*.
Usa una variante o color distinto y, si hace falta, colócala junto al nombre en
vez de en la columna Estado.

- [ ] **Step 4: Lint y build**

```bash
cd ~/dev/pharmatrack-frontend && corepack yarn lint && corepack yarn build
```

Esperado: lint con 0 errores (los 3 warnings preexistentes siguen; no los
toques), build en verde.

- [ ] **Step 5: Verificación manual**

El login local del dashboard viene fallando y **no debes escribir contraseñas en
ningún campo**. No intentes autenticarte: reporta la verificación visual como no
realizada. Es una limitación conocida, no un fallo tuyo.

- [ ] **Step 6: Commit**

```bash
cd ~/dev/pharmatrack-frontend
git add -A
git commit -m "feat(taxonomia): subir imagen del taxon y marcar la especie como Nominal

La imagen es la foto de la tarjeta cuando la especie no tiene ejemplares, que es
el caso de 37 de las 38 publicadas hoy.

Nominal distingue la forma base de sus morphs y aparece siempre: dice QUE es la
fila, a diferencia de Agotado o Grupo oculto, que dicen COMO esta.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm"
git push origin main
```

---

## Notas de revisión del plan

Dos cosas salieron al leer el código y no estaban en el spec:

1. **La marca "Nominal" no puede ir en el título.** `listingSlug` deriva de
   `listingTitle` (`utils.js:142-144`), así que meterla ahí cambiaría el slug de
   **todas** las especies y rompería los enlaces ya compartidos e indexados. Va
   como campo aparte (`taxonLabel`), y el plan lo advierte donde se escribe.
2. **`latestId` se inicializaba con el id del primer ejemplar.** Al sembrar
   entradas desde el taxón ya no hay ejemplar del que tomarlo, así que arranca
   en `0`. Se usa para ordenar por "recién llegados"; un taxón sin ejemplares
   queda al final de ese orden, que es lo correcto.

El spec no necesita corrección.
