# Publicación de animales por especie y morph — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poder sacar del sitio público una especie o un morph concreto, sin mentir sobre el inventario ni esconder un grupo taxonómico entero, y ver desde el dashboard por qué algo no aparece.

**Architecture:** Una bandera `show_public` en `species` y en `morphs`, respetada por el listado y el detalle públicos mediante un filtro **opt-in** en el constructor de queries que hoy comparten la ruta admin y la pública. Encima, una pantalla `Sitio web → Animales` agrupada por especie con sus morphs anidados —igual que el sitio arma sus tarjetas— que muestra el switch y, cuando algo no se ve, el motivo.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (API) · React 19 + Vite + MUI + MUI X DataGrid + SWR (dashboard)

**Spec:** `docs/superpowers/specs/2026-08-19-animal-publishing-design.md` (este mismo repo)

## Global Constraints

- Los dos repos commitean y pushean **directo a `main`**. Nunca abrir PRs.
- **No tocar** Mercado Pago ni Resend.
- Nunca imprimir `PROD_DATABASE_URL` ni pedir secretos por chat.
- Mensajes de commit terminan con:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` y
  `Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm`
- El campo se llama **`show_public`**, no `show_online`: en el árbol de tablas de
  animales ese nombre ya significa esto (`animal_groups.show_public`).
- `show_public` es un campo **de administración**: va en `SpeciesAdminResponse` /
  `MorphAdminResponse` y en los `*Update`, **nunca** en `SpeciesBase`/
  `SpeciesResponse`/`MorphBase`/`MorphResponse`, que son los que el sitio público
  embebe en cada animal.
- Los tests del backend se corren con **`poetry run python -m pytest`** (el repo
  usa Poetry y no hay venv activo).
- **Antes de correr la suite completa, matar procesos `python.exe` colgados**
  (`taskkill //F //IM python.exe`): corridas simultáneas contra la base de
  pruebas producen cientos de errores de SQLAlchemy que parecen bugs del código
  y no lo son.
- Rutas: `~/dev/pharmatrack-api`, `~/dev/pharmatrack-frontend` (dashboard).

## Mapa de archivos

**`pharmatrack-api`**
| Archivo | Responsabilidad |
| --- | --- |
| `migrations/versions/showpublictaxa01_add_show_public_to_species_and_morphs.py` (nuevo) | Agrega las dos columnas |
| `src/pharmatrack/models/animals/orm.py` | Campo `show_public` en `Species` y `Morph` |
| `src/pharmatrack/models/animals/schemas.py` | Campo en `SpeciesUpdate`, `SpeciesAdminResponse`, `MorphUpdate`, `MorphAdminResponse` |
| `src/pharmatrack/api/routes/animals.py` | `_animals_query` acepta `exclude_hidden_taxa` (opt-in) |
| `src/pharmatrack/api/routes/public_animals.py` | Listado y detalle aplican el filtro |
| `tests/test_public_animals.py` | Las cinco pruebas del spec |

**`pharmatrack-frontend` (dashboard)**
| Archivo | Responsabilidad |
| --- | --- |
| `src/sections/animal/view/site-animals-view.jsx` (nuevo) | La pantalla |
| `src/pages/dashboard/site/animals.jsx` (nuevo) | Página delgada |
| `src/routes/paths.js` | `dashboard.site.animals` |
| `src/routes/sections/dashboard.jsx` | Ruta con guard |
| `src/layouts/nav-config-dashboard.jsx` | Ítem "Animales" bajo Sitio web |

No hace falta tocar `src/actions/animal.js`: `updateSpecies(id, data)`,
`updateMorph(id, data)` y `updateAnimalGroup(id, data)` ya existen y el `PUT` del
backend ya es parcial (`model_dump(exclude_unset=True)`), así que mandar
`{ show_public: false }` basta. **No se crea un endpoint `toggle-` como el de
productos**: ahí hizo falta porque el `PUT` de productos reemplaza el objeto
completo; aquí no.

---

## Task 1: La bandera en el modelo, el esquema y la migración

**Files:**
- Create: `migrations/versions/showpublictaxa01_add_show_public_to_species_and_morphs.py`
- Modify: `src/pharmatrack/models/animals/orm.py` (clases `Species` y `Morph`)
- Modify: `src/pharmatrack/models/animals/schemas.py`
- Test: `tests/test_public_animals.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Species.show_public` y `Morph.show_public` (bool, no nulo, default
  `True`). Expuestos en `SpeciesAdminResponse` y `MorphAdminResponse`, y
  escribibles por `PUT /api/v1/species/{id}` y `PUT /api/v1/morphs/{id}` con un
  cuerpo parcial `{"show_public": false}`. Las tasks 2 y 4 dependen de esto.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_public_animals.py`:

```python
def test_show_public_es_administrativo_y_default_true(auth_headers):
    """La bandera nace encendida, se puede apagar con un PUT parcial, y NO se
    filtra al sitio publico dentro de la especie embebida en cada animal."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    # nace encendida en la respuesta de administracion
    assert sp["show_public"] is True
    assert morph["show_public"] is True

    # se apaga con un PUT parcial, sin mandar el resto del objeto
    res = species_put(sp["id"], json={"show_public": False}, headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK, res.text
    assert res.json()["show_public"] is False
    # y no piso otros campos
    assert res.json()["name"] == sp["name"]

    # el sitio publico nunca ve el campo (la especie va embebida en el animal)
    row = next(a for a in client.get("/api/v1/public/animals").json()["data"]
               if a["id"] == animal["id"])
    assert "show_public" not in row["species"]
```

Este test necesita clientes de morphs. Agregar junto a los otros factories del
inicio del archivo — **incluye el `post`, que la Task 2 también usa**, para no
declarar la misma línea dos veces:

```python
morphs_post, _, morphs_put, _, _ = route_client_factory(client, "morphs")
```

Revisa el orden real de la tupla que devuelve `route_client_factory` en
`tests/utils.py` y ajusta el desempaquetado: los otros archivos de prueba ya lo
usan y sirven de referencia.

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_animals.py::test_show_public_es_administrativo_y_default_true -v
```

Esperado: FALLA con `KeyError: 'show_public'` — el campo todavía no existe.

- [ ] **Step 3: Agregar la columna al modelo**

En `src/pharmatrack/models/animals/orm.py`, en la clase `Species`, justo antes
del bloque comentado `=== Manejo/cria (PRIVADO ...) ===`:

```python
    # Visible en el sitio publico. Independiente del inventario: una especie
    # puede estar en cultivo y no anunciarse todavia. El grupo raiz manda por
    # encima (si el grupo esta oculto, esto no la rescata).
    show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
```

En la clase `Morph`, en la misma posición relativa:

```python
    # Visible en el sitio publico, independiente de su especie: se puede
    # esconder un morph suelto dejando el resto a la venta.
    show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
```

`Boolean` ya está importado en ese archivo (lo usa `AnimalGroup.show_public`);
verificarlo antes de agregar el import.

- [ ] **Step 4: Agregar el campo a los esquemas**

En `src/pharmatrack/models/animals/schemas.py`:

- `SpeciesUpdate`: `show_public: Optional[bool] = None`
- `SpeciesAdminResponse`: `show_public: bool = True`
- `MorphUpdate`: `show_public: Optional[bool] = None`
- `MorphAdminResponse`: `show_public: bool = True`

**No lo agregues a `SpeciesBase`, `SpeciesResponse`, `MorphBase` ni
`MorphResponse`.** Esos son los que el sitio público embebe en cada animal; el
test del Step 1 falla si se filtra.

- [ ] **Step 5: Escribir la migración**

Crear `migrations/versions/showpublictaxa01_add_show_public_to_species_and_morphs.py`:

```python
"""add show_public to species and morphs (publicar/despublicar por taxon)

Revision ID: showpublictaxa01
Revises: checkoutat01
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'showpublictaxa01'
down_revision: Union[str, Sequence[str], None] = 'checkoutat01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('species', 'morphs'):
        op.add_column(
            table,
            sa.Column('show_public', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        )


def downgrade() -> None:
    for table in ('species', 'morphs'):
        op.drop_column(table, 'show_public')
```

**Antes de escribirla, confirmar cuál es la cabeza actual de migraciones** — si
otra rama agregó una después de `checkoutat01`, `down_revision` debe apuntar a
esa, no a esta:

```bash
cd ~/dev/pharmatrack-api && poetry run alembic heads
```

Si imprime algo distinto de `checkoutat01`, usar ese valor en `down_revision`.

- [ ] **Step 6: Aplicar la migración y correr el test**

```bash
cd ~/dev/pharmatrack-api && poetry run alembic upgrade head
poetry run python -m pytest tests/test_public_animals.py -v
```

Esperado: PASS. (Los tests crean su propio esquema con `create_all`, pero la
migración debe aplicarse igual para que la base de desarrollo quede al día.)

- [ ] **Step 7: Commit**

```bash
cd ~/dev/pharmatrack-api
git add migrations/versions/showpublictaxa01_add_show_public_to_species_and_morphs.py src/pharmatrack/models/animals/orm.py src/pharmatrack/models/animals/schemas.py tests/test_public_animals.py
git commit -m "$(cat <<'EOF'
feat(taxonomia): bandera show_public en especies y morphs

Los animales solo tenian dos palancas para lo publico y ninguna servia para
publicar: status es inventario, y show_public de grupo apaga entre 2 y 6
especies de golpe. La bandera es administrativa: no viaja en SpeciesResponse ni
MorphResponse, que son las que el sitio embebe en cada animal.

Todavia no filtra nada; eso llega en el commit siguiente.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 2: El filtro público, opt-in

Es la task delicada del plan: `_animals_query` lo comparten la ruta admin y la
pública.

**Files:**
- Modify: `src/pharmatrack/api/routes/animals.py:100-123` (`_animals_query`)
- Modify: `src/pharmatrack/api/routes/public_animals.py` (listado y detalle)
- Test: `tests/test_public_animals.py`

**Interfaces:**
- Consumes: `Species.show_public` y `Morph.show_public` de la Task 1.
- Produces: `_animals_query(..., exclude_hidden_taxa: bool = False)`. El listado
  público lo llama con `True`; el listado admin **no lo pasa**. La Task 4 se
  apoya en que el admin siga viendo todo.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_public_animals.py`:

```python
def test_especie_oculta_desaparece_del_listado_publico(auth_headers):
    _, _, _, sp, _ = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"])

    assert any(a["id"] == animal["id"] for a in client.get("/api/v1/public/animals").json()["data"])

    species_put(sp["id"], json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert not any(a["id"] == animal["id"] for a in data)


def test_morph_oculto_desaparece_del_listado_publico(auth_headers):
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    assert any(a["id"] == animal["id"] for a in client.get("/api/v1/public/animals").json()["data"])

    morphs_put(morph["id"], json={"show_public": False}, headers=auth_headers)

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

    morphs_put(morph_a["id"], json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/public/animals").json()["data"]
    assert not any(a["id"] == animal["id"] for a in data), \
        "un ejemplar con un morph oculto no debe aparecer, ni por su otro morph"


def test_enlace_directo_respeta_las_banderas(auth_headers):
    """Sin esto hay fuga: el listado esconde pero la URL directa sigue sirviendo."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    a1 = _create_animal(auth_headers, sp["id"])
    a2 = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    assert client.get(f"/api/v1/public/animals/{a1['id']}").status_code == status.HTTP_200_OK

    species_put(sp["id"], json={"show_public": False}, headers=auth_headers)
    assert client.get(f"/api/v1/public/animals/{a1['id']}").status_code == status.HTTP_404_NOT_FOUND

    species_put(sp["id"], json={"show_public": True}, headers=auth_headers)
    morphs_put(morph["id"], json={"show_public": False}, headers=auth_headers)
    assert client.get(f"/api/v1/public/animals/{a2['id']}").status_code == status.HTTP_404_NOT_FOUND


def test_el_listado_admin_sigue_viendo_lo_oculto(auth_headers):
    """El filtro es opt-in. Si se aplicara siempre, las especies ocultas
    desapareceran del dashboard y nadie podria volver a publicarlas."""
    _, _, _, sp, morph = _make_taxonomy(auth_headers)
    animal = _create_animal(auth_headers, sp["id"], morph_ids=[morph["id"]])

    species_put(sp["id"], json={"show_public": False}, headers=auth_headers)
    morphs_put(morph["id"], json={"show_public": False}, headers=auth_headers)

    data = client.get("/api/v1/animals", headers=auth_headers).json()["data"]
    assert any(a["id"] == animal["id"] for a in data), \
        "el listado admin debe seguir mostrando los taxones ocultos"
```

`morphs_post` y `morphs_put` ya quedaron declarados en la Task 1; **no vuelvas a
declararlos**.

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_animals.py -v
```

Esperado: los cuatro primeros FALLAN (el animal sigue apareciendo / el detalle
sigue dando 200). El quinto (`admin sigue viendo`) **debe PASAR ya**, porque
todavía no hay filtro: es la red que detecta si más adelante se aplica de más.

- [ ] **Step 3: Agregar el parámetro opt-in a `_animals_query`**

En `src/pharmatrack/api/routes/animals.py`, cambiar la firma y agregar el bloque
justo después del de `exclude_group_ids`:

```python
def _animals_query(db, species_id=None, genus_id=None, group_id=None,
                   animal_status=None, exclude_group_ids=None,
                   exclude_hidden_taxa=False):
```

```python
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
```

`Morph` debe estar importado en ese archivo. Verificar con
`grep -n "^from\|^import" src/pharmatrack/api/routes/animals.py` y agregarlo al
import de modelos si falta. `Animal.morphs` es la relación muchos-a-muchos vía
`animal_has_morphs`; `.any()` es su forma correcta de filtrar.

- [ ] **Step 4: Activarlo en el listado público**

En `src/pharmatrack/api/routes/public_animals.py`, en `public_list_animals`:

```python
    query = _animals_query(
        db, species_id=species_id, genus_id=genus_id, group_id=group_id,
        animal_status=AnimalStatusEnum.AVAILABLE, exclude_group_ids=hidden_group_ids(db),
        exclude_hidden_taxa=True,
    )
```

- [ ] **Step 5: Aplicarlo también al detalle**

En la misma ruta, `public_get_animal` ya rechaza los grupos ocultos. Agregar las
dos condiciones nuevas después de esa comprobación:

```python
    # Mismas reglas que el listado: si el listado lo esconde, el enlace directo
    # tampoco debe servirlo. El status SI se conserva permisivo a proposito
    # (reservados y vendidos responden, para que un link compartido diga "ya no
    # disponible" en vez de 404).
    if animal.species and not animal.species.show_public:
        raise HTTPException(status_code=404, detail="Animal not found.")
    if any(not m.show_public for m in (animal.morphs or [])):
        raise HTTPException(status_code=404, detail="Animal not found.")
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

```bash
cd ~/dev/pharmatrack-api && poetry run python -m pytest tests/test_public_animals.py tests/test_animals.py tests/test_group_visibility.py -v
```

Esperado: todo PASS, incluidas las pruebas ya existentes de animales y de
visibilidad por grupo.

- [ ] **Step 7: Correr la suite completa**

```bash
cd ~/dev/pharmatrack-api
taskkill //F //IM python.exe 2>/dev/null; sleep 3
poetry run python -m pytest -q
```

Esperado: todo PASS (la referencia reciente es 496). El `taskkill` va primero
porque procesos colgados de corridas previas producen cientos de errores falsos.

- [ ] **Step 8: Commit**

```bash
cd ~/dev/pharmatrack-api
git add src/pharmatrack/api/routes/animals.py src/pharmatrack/api/routes/public_animals.py tests/test_public_animals.py
git commit -m "$(cat <<'EOF'
feat(publico): el sitio respeta show_public de especies y morphs

Listado y detalle aplican las mismas reglas: si el listado lo esconde, el enlace
directo tampoco lo sirve. Un ejemplar con varios morphs se esconde si CUALQUIERA
esta oculto: sigue llevando ese morph y su ficha lo mostraria.

El filtro es opt-in porque _animals_query la comparten el listado admin y el
publico; si se aplicara siempre, una especie oculta desapareceria del dashboard
y nadie podria volver a publicarla. Hay prueba dedicada para eso.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 3: La pantalla `Sitio web → Animales`

**Files:**
- Create: `~/dev/pharmatrack-frontend/src/sections/animal/view/site-animals-view.jsx`
- Create: `~/dev/pharmatrack-frontend/src/pages/dashboard/site/animals.jsx`
- Modify: `~/dev/pharmatrack-frontend/src/routes/paths.js` (objeto `dashboard.site`)
- Modify: `~/dev/pharmatrack-frontend/src/routes/sections/dashboard.jsx`
- Modify: `~/dev/pharmatrack-frontend/src/layouts/nav-config-dashboard.jsx`

**Interfaces:**
- Consumes: `show_public` en las respuestas de administración de especies y
  morphs (Task 1); el hecho de que el listado admin siga devolviéndolos
  aunque estén ocultos (Task 2).
- Produces: la ruta `/dashboard/site/animals`. Nada depende de ella.

- [ ] **Step 1: Crear la vista**

`src/sections/animal/view/site-animals-view.jsx`. Nada de esto necesita acciones
nuevas: `useAllSpecies`, `useAllMorphs`, `useGetAnimals`, `useAnimalGroupTree`,
`updateSpecies`, `updateMorph` y `updateAnimalGroup` ya existen en
`src/actions/animal.js`.

Estructura obligatoria:

1. **Panel de grupos raíz** arriba: cada grupo con su casilla `show_public`,
   escribiendo con `updateAnimalGroup(id, { show_public })`. Copiar el patrón
   optimista de `handleFlag` en `src/sections/animal/view/animal-taxonomy-view.jsx`
   (líneas ~146-164): actualiza la UI al instante y revalida detrás.
2. **Tabla de especies con morphs anidados**, igual que la pestaña Especies de
   Taxonomía. Reutiliza su forma de armar las filas (`speciesTree`, con
   `__kind: 'species' | 'morph'` y `depth`).
3. **Conteos de disponibles** por especie y por morph: copiar
   `availableBySpecies` y `availableByMorph` de `animal-taxonomy-view.jsx`
   (líneas ~175-196). Suman `stock ?? 1` de los animales con
   `status === 'available'`.

Columnas: Nombre · Grupo raíz · Disponibles · Precio · **En el sitio** (switch)
· **Estado**.

El precio es el rango de los ejemplares disponibles detrás de esa fila, en el
mismo barrido donde ya cuentas los disponibles:

```js
// junto a availableBySpecies / availableByMorph
const priceRange = (prices) => {
  if (!prices.length) return '—';
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  return min === max ? fCurrency(min) : `${fCurrency(min)} – ${fCurrency(max)}`;
};
```

`fCurrency` viene de `src/utils/format-number`, que ya usa la lista de animales.
Ignora los ejemplares sin precio al armar el arreglo.

El switch escribe según el tipo de fila:

```jsx
const write = row.__kind === 'morph' ? updateMorph : updateSpecies;
await write(row.id, { show_public: !row.show_public });
```

La columna **Estado** es el corazón de la pantalla. Motivos, en este orden de
precedencia (el primero que aplique gana):

```
1. 'Grupo oculto'               — el grupo raíz de su género tiene show_public = false
2. 'Especie oculta'             — solo en filas de morph, cuando su especie está apagada
3. 'Sin ejemplares disponibles' — la bandera está prendida pero no hay qué vender
(ninguno)                       — se ve en el sitio
```

Renderiza el motivo con `Label` de `src/components/label` en color `warning`, y
deja la celda vacía cuando sí se ve.

**Permisos:** la pantalla escribe tres recursos y `RoleBasedGuard` solo puede
exigir uno (evalúa con OR). Deshabilita cada switch cuando falte su permiso,
leyendo de `useAuthContext()`:

```jsx
const { user } = useAuthContext();
const has = (perm) => user?.permissions?.includes(perm);
// filas de especie -> has('species.update')
// filas de morph   -> has('morphs.update')
// panel de grupos  -> has('animalgroups.update')
```

Un switch deshabilitado debe decir por qué (un `title` basta).

- [ ] **Step 2: Crear la página**

`src/pages/dashboard/site/animals.jsx`, copiando la forma exacta de
`src/pages/dashboard/site/media.jsx`:

```jsx
import { CONFIG } from 'src/global-config';

import { SiteAnimalsView } from 'src/sections/animal/view/site-animals-view';

// ----------------------------------------------------------------------

const metadata = { title: `Animales del sitio | Dashboard - ${CONFIG.appName}` };

export default function Page() {
  return (<><title>{metadata.title}</title><SiteAnimalsView /></>);
}
```

- [ ] **Step 3: Registrar ruta y navegación**

En `src/routes/paths.js`, dentro del objeto `dashboard.site` que ya tiene
`media` y `products`:

```js
      animals: `${ROOTS.DASHBOARD}/site/animals`,
```

En `src/routes/sections/dashboard.jsx`, junto a los otros `lazy`:

```js
const SiteAnimalsPage = lazy(() => import('src/pages/dashboard/site/animals'));
```

En el objeto `P`, junto a los permisos de animales:

```js
  speciesUpdate: ['species.update'],
```

Y dentro del bloque de ruta `site` que ya existe:

```jsx
          { path: 'animals', element: guard(P.speciesUpdate, <SiteAnimalsPage />) },
```

**`species.update`, no un permiso de lectura:** la pantalla existe para mover
switches. Precedente reciente: la de Productos se gateó con `products.read` y
era un error, se entraba a una página donde todo daba 403.

En `src/layouts/nav-config-dashboard.jsx`, el ítem "Sitio web" ya existe con sus
hijos y una lista `allowedRoles` que funciona como OR. Agregar el permiso a esa
lista y el hijo nuevo:

```jsx
        allowedRoles: ['settings.update', 'products.update', 'articles.read', 'species.update'],
        children: [
          // ...los que ya están...
          { title: 'Animales',   path: paths.dashboard.site.animals,  allowedRoles: ['species.update'] },
        ],
```

**Localiza los puntos de inserción leyendo cada archivo**, no por número de
línea.

- [ ] **Step 4: Lint y build**

```bash
cd ~/dev/pharmatrack-frontend && corepack yarn lint && corepack yarn build
```

Esperado: lint con 0 errores (los 3 warnings preexistentes siguen y no se
tocan), build en verde. Si `perfectionist/sort-imports` protesta, correr
`corepack yarn lint:fix`.

- [ ] **Step 5: Verificación manual**

El stack local corre en `http://127.0.0.1:8000` (API) y `http://localhost:3030`
(dashboard). Si no responden, levantarlos:

```bash
cd ~/dev/pharmatrack-api && PYTHONPATH=src PYTHONIOENCODING=utf-8 poetry run uvicorn pharmatrack.main:app --host 127.0.0.1 --port 8000 &
cd ~/dev/pharmatrack-frontend && corepack yarn dev &
```

`PYTHONIOENCODING=utf-8` no es opcional: sin él, un emoji en un log de arranque
mata el servidor en la consola de Windows.

Entrar a `/dashboard/site/animals` y comprobar:

1. Se listan las especies con sus morphs anidados.
2. Apagar el switch de una especie hace que sus ejemplares desaparezcan de
   `http://localhost:3033` (el sitio) tras ~60 s, o de inmediato en
   `curl http://127.0.0.1:8000/api/v1/public/animals`.
3. La columna Estado muestra el motivo correcto al ocultar un grupo raíz.
4. La especie oculta **sigue apareciendo en esta pantalla** (si desaparece, el
   filtro de la Task 2 se aplicó al admin y hay que arreglarlo).

Si el login local no conecta, reportarlo y **no dar por verificado lo que no se
vio**.

- [ ] **Step 6: Commit**

```bash
cd ~/dev/pharmatrack-frontend
git add src/sections/animal/view/site-animals-view.jsx src/pages/dashboard/site/animals.jsx src/routes/paths.js src/routes/sections/dashboard.jsx src/layouts/nav-config-dashboard.jsx
git commit -m "$(cat <<'EOF'
feat(sitio): pantalla Animales, agrupada por especie y morph

Agrupa como el sitio arma sus tarjetas, no un renglon por ejemplar. La columna
Estado dice POR QUE algo no se ve (grupo oculto, especie oculta, sin ejemplares
disponibles), que es la pregunta que hoy obliga a ir a comprobar a la pagina.

Los switches se deshabilitan cuando falta su permiso: la pantalla escribe tres
recursos y el guard de ruta solo puede exigir uno.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Notas de revisión del plan

Contra el spec, dos cosas se resolvieron mejor de lo previsto al leer el código:

1. **No hace falta un endpoint `toggle-`.** El spec no lo pedía explícitamente,
   pero el paralelo con productos lo sugería. El `PUT` de especies y morphs ya
   usa `model_dump(exclude_unset=True)`, así que un cuerpo parcial
   `{"show_public": false}` ya funciona sin pisar nada. Productos necesitó el
   endpoint dedicado porque su `PUT` reemplaza el objeto completo.
2. **La bandera no necesita cambios en las rutas de administración.** Al ir en
   `SpeciesUpdate`/`MorphUpdate` y en las respuestas `*AdminResponse`, los
   endpoints existentes la leen y escriben sin tocarlos.

El spec no necesita corrección.
