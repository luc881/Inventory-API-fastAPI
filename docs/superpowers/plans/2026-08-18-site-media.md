# Media del sitio editable desde el dashboard — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el video del hero y las 6 imágenes decorativas del sitio público se cambien desde el dashboard, sin tocar código ni desplegar.

**Architecture:** Nueve slots con nombre fijo viven en el blob JSON `site` de la tabla `app_settings`, que ya existe y ya se sirve público en `GET /api/v1/settings/site`. El dashboard sube el archivo a Cloudinary (que ya usa para fotos de animales) y guarda la URL en su slot con un `PUT` parcial. El sitio lee ese blob en sus server components y lo reparte como props. No hay endpoints nuevos ni tablas nuevas.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy + pytest (API) · React 19 + Vite + MUI + SWR (dashboard) · Next.js 16 App Router + MUI (sitio) · Cloudinary (unsigned upload preset)

**Spec:** `docs/superpowers/specs/2026-08-18-site-media-design.md` (este mismo repo)

## Global Constraints

- Los tres repos commitean y pushean **directo a `main`**. Nunca abrir PRs.
- **No tocar** la lógica de Mercado Pago ni de Resend. Este trabajo no las roza.
- Nunca imprimir `PROD_DATABASE_URL` ni pedirle secretos al usuario por chat.
- Mensajes de commit terminan con:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` y
  `Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm`
- Los 9 nombres de slot son exactamente: `hero_video_mp4`, `hero_video_webm`,
  `hero_poster`, `moss_tall`, `moss_wide`, `leaf_litter`, `terrarium`,
  `isopod_zebra`, `isopod_cubaris`. Se escriben igual en Python, en el dashboard
  y en el sitio.
- Rutas de los repos: `~/dev/pharmatrack-api`, `~/dev/pharmatrack-frontend`
  (dashboard), `~/dev/pharmatrack-web` (sitio).

## Mapa de archivos

**`pharmatrack-api`**
| Archivo | Responsabilidad |
| --- | --- |
| `src/pharmatrack/api/routes/settings.py` | Modelos `SiteMedia`/`SiteSettings`, `SITE_DEFAULTS`, merge parcial en el PUT |
| `src/pharmatrack/utils/permissions.py` | `CAN_*_SETTINGS` vía `_crud("settings")` |
| `src/pharmatrack/seeds/seed_permissions.py` | Alta de `settings.read` / `settings.update` |
| `tests/test_settings_site.py` (nuevo) | Merge parcial y merge por slot |
| `scripts/seed_site_media.py` (nuevo, desechable) | Sube los 9 archivos actuales e imprime las URLs |

**`pharmatrack-frontend` (dashboard)**
| Archivo | Responsabilidad |
| --- | --- |
| `src/lib/cloudinary.js` | Acepta `resourceType` para poder subir video |
| `src/actions/site.js` (nuevo) | `useGetSiteSettings()` + `updateSiteMedia()` |
| `src/sections/site/view/site-media-view.jsx` (nuevo) | Rejilla de tarjetas de slot |
| `src/sections/site/view/index.js` (nuevo) | Barrel del módulo |
| `src/pages/dashboard/site/media.jsx` (nuevo) | Página delgada |
| `src/routes/paths.js` | `paths.dashboard.site.media` |
| `src/routes/sections/dashboard.jsx` | Ruta con `guard(P.siteUpdate, …)` |
| `src/layouts/nav-config-dashboard.jsx` | Item "Sitio web" |

**`pharmatrack-web` (sitio)**
| Archivo | Responsabilidad |
| --- | --- |
| `src/lib/public-api.js` | `SITE_DEFAULTS.media` de respaldo |
| `src/app/page.jsx` | Pasa `media` a `OdHomeView` |
| `src/sections/home/od/od-home-view.jsx` | Consume `media` en `IMG` y en el hero |
| `src/app/layout.jsx` | Pasa `heroPoster` a `SiteSplash` |
| `src/components/loading-screen/site-splash.jsx` | Recibe `heroPoster` por prop |
| `src/layouts/od/od-layout.jsx` | Hace el fetch y pasa `media` a `OdDivider3d` |
| `src/layouts/od/od-divider-3d.jsx` | Recibe `media` (usa `moss_tall` y `terrarium`) |
| `src/sections/home/od/od-faq.jsx` | Recibe `mossTall` por prop |
| `src/app/criadero/page.jsx` | Consume `media.moss_tall` |
| `public/video/`, `public/assets/redesign/` | Se borran al final |

---

## Task 1: Sembrar los 9 archivos actuales en Cloudinary

Va primero a propósito: aquí vive el único riesgo técnico real del proyecto. Si
el preset unsigned rechaza `/video/upload`, hay que saberlo antes de construir
la UI.

El script es **desechable**: se corre una vez, se copian las URLs y se borra. No
se commitea código de producción aquí.

**Files:**
- Create (temporal): `~/dev/pharmatrack-api/scripts/seed_site_media.py`

**Interfaces:**
- Consumes: nada.
- Produces: nueve URLs `https://res.cloudinary.com/...`, una por slot. La Task 3
  las pega en `SITE_DEFAULTS["media"]`.

- [ ] **Step 1: Confirmar las credenciales de Cloudinary**

El dashboard sube con un *unsigned upload preset*. Ese par de valores **no son
secretos**: viajan en el bundle del navegador con prefijo `VITE_`. Aun así el
usuario los pone él mismo, no por chat.

Revisar que `~/dev/pharmatrack-frontend/.env.local` tenga:

```env
VITE_CLOUDINARY_CLOUD_NAME=...
VITE_CLOUDINARY_UPLOAD_PRESET=...
```

**Hoy no están.** Si faltan, pedirle al usuario que los agregue (los saca del
panel de Cloudinary, o de las variables de entorno del dashboard desplegado) y
esperar confirmación antes de seguir.

- [ ] **Step 2: Escribir el script de siembra**

```python
"""Desechable: sube la media actual del sitio a Cloudinary e imprime las URLs.

Se corre UNA vez para poblar SITE_DEFAULTS["media"] y despues se borra.
Lee el cloud name y el preset unsigned del .env.local del dashboard.
"""
import sys
from pathlib import Path

import requests

WEB = Path.home() / "dev" / "pharmatrack-web" / "public"
ENV = Path.home() / "dev" / "pharmatrack-frontend" / ".env.local"

# slot -> (ruta relativa a public/, tipo de recurso en Cloudinary)
SLOTS = {
    "hero_video_mp4": ("video/hero-moss.mp4", "video"),
    "hero_video_webm": ("video/hero-moss.webm", "video"),
    "hero_poster": ("video/hero-moss.jpg", "image"),
    "moss_tall": ("assets/redesign/moss-forest-1.jpg", "image"),
    "moss_wide": ("assets/redesign/moss-forest-2.jpg", "image"),
    "leaf_litter": ("assets/redesign/leaf-litter.jpg", "image"),
    "terrarium": ("assets/redesign/terrarium.jpg", "image"),
    "isopod_zebra": ("assets/redesign/isopod-zebra.jpg", "image"),
    "isopod_cubaris": ("assets/redesign/isopod-cubaris.jpg", "image"),
}


def read_env() -> tuple[str, str]:
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    cloud = values.get("VITE_CLOUDINARY_CLOUD_NAME")
    preset = values.get("VITE_CLOUDINARY_UPLOAD_PRESET")
    if not cloud or not preset:
        sys.exit("Faltan VITE_CLOUDINARY_CLOUD_NAME / _UPLOAD_PRESET en .env.local")
    return cloud, preset


def upload(cloud: str, preset: str, path: Path, resource_type: str) -> str:
    url = f"https://api.cloudinary.com/v1_1/{cloud}/{resource_type}/upload"
    with path.open("rb") as fh:
        res = requests.post(url, data={"upload_preset": preset},
                            files={"file": fh}, timeout=180)
    if not res.ok:
        sys.exit(f"FALLO {path.name} ({resource_type}): {res.status_code} {res.text}")
    return res.json()["secure_url"]


def main() -> None:
    cloud, preset = read_env()
    print('    "media": {')
    for slot, (rel, resource_type) in SLOTS.items():
        path = WEB / rel
        if not path.exists():
            sys.exit(f"No existe {path}")
        secure_url = upload(cloud, preset, path, resource_type)
        print(f'        "{slot}": "{secure_url}",')
    print("    },")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Correr el script**

```bash
cd ~/dev/pharmatrack-api && python scripts/seed_site_media.py
```

Esperado: nueve líneas `"slot": "https://res.cloudinary.com/...",` listas para
pegar.

**GATE — si los dos slots de video fallan:** parar aquí y reportarle al usuario.
El preset unsigned no acepta video. Opciones a plantearle, sin elegir por él:
subir los dos videos a mano desde el panel de Cloudinary y pegar esas URLs;
crear un preset aparte que sí acepte video; o dejar el video en el repo y hacer
dinámicas solo las 7 imágenes. No seguir a la Task 2 sin decisión.

- [ ] **Step 4: Guardar la salida y borrar el script**

Copiar las nueve líneas a un archivo temporal del scratchpad (la Task 3 las
necesita) y borrar el script:

```bash
rm ~/dev/pharmatrack-api/scripts/seed_site_media.py
```

No hay commit en esta task: no queda código.

---

## Task 2: `PUT /settings/site` deja de pisar los campos que no recibe

Arregla un bug que ya existe en producción, independiente del resto del
proyecto. Hoy apagar los envíos y luego tocar el switch de "Explorar por
categorías" vuelve a encender los envíos.

**Files:**
- Modify: `src/pharmatrack/api/routes/settings.py:121-140`
- Test: `tests/test_settings_site.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces: `update_site_settings` con semántica de merge. La Task 3 se apoya en
  ella para mezclar `media` slot por slot.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_settings_site.py`:

```python
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
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd ~/dev/pharmatrack-api && pytest tests/test_settings_site.py -v
```

Esperado: FALLA en `assert body["shipping_enabled"] is False` — devuelve `True`
porque Pydantic rellenó el campo ausente con su default y se persistió.

- [ ] **Step 3: Hacer opcionales los campos y mezclar en vez de reemplazar**

En `src/pharmatrack/api/routes/settings.py`, sustituir la clase `SiteSettings` y
la función `update_site_settings` por:

```python
class SiteSettings(BaseModel):
    # Todos opcionales: el PUT es parcial y solo escribe lo que llega.
    # Sin esto, Pydantic rellenaba los ausentes con su default y los persistia,
    # asi que tocar un ajuste reseteaba los demas.
    show_category_browse: Optional[bool] = None
    shipping_enabled: Optional[bool] = None


@router.put("/site", dependencies=CAN_UPDATE_ANIMAL_GROUPS,
            summary="Guardar ajustes del sitio")
def update_site_settings(body: SiteSettings, db: db_dependency):
    row = db.query(AppSetting).filter(AppSetting.key == "site").first()
    if not row:
        row = AppSetting(key="site", value="{}")
        db.add(row)

    stored = json.loads(row.value)
    patch = body.model_dump(exclude_unset=True)
    row.value = json.dumps({**stored, **patch})
    db.commit()
    return get_site_settings(db)
```

`exclude_unset=True` es la pieza clave: deja fuera los campos que el cliente no
mandó, en vez de incluirlos con su valor por defecto.

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
cd ~/dev/pharmatrack-api && pytest tests/test_settings_site.py tests/test_shop.py tests/test_group_visibility.py -v
```

Esperado: todo PASS. `test_shop.py` y `test_group_visibility.py` se incluyen
porque son los que ya usaban este endpoint.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/pharmatrack-api
git add src/pharmatrack/api/routes/settings.py tests/test_settings_site.py
git commit -m "$(cat <<'EOF'
fix(settings): PUT /settings/site deja de pisar los campos que no recibe

SiteSettings tenia defaults, asi que Pydantic rellenaba los campos ausentes y
model_dump() los persistia: apagar los envios y luego tocar el switch de
"Explorar por categorias" volvia a encender los envios en silencio.

Ahora los campos son opcionales y el PUT mezcla exclude_unset sobre lo guardado.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 3: Slots de media en el blob `site`

**Files:**
- Modify: `src/pharmatrack/api/routes/settings.py` (`SITE_DEFAULTS`, `SiteMedia`, `SiteSettings`, `update_site_settings`)
- Test: `tests/test_settings_site.py`

**Interfaces:**
- Consumes: las nueve URLs de la Task 1; el merge de la Task 2.
- Produces: `GET /api/v1/settings/site` devuelve
  `{"show_category_browse": bool, "shipping_enabled": bool, "media": {<9 slots>: str}}`.
  Es el contrato que consumen las Tasks 5 a 8.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_settings_site.py`:

```python
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
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
cd ~/dev/pharmatrack-api && pytest tests/test_settings_site.py -v
```

Esperado: FALLAN con `KeyError: 'media'` — el blob todavía no tiene ese campo.

- [ ] **Step 3: Agregar el modelo, los defaults y el merge anidado**

En `src/pharmatrack/api/routes/settings.py`, reemplazar el bloque
`SITE_DEFAULTS` / `SiteSettings` / `update_site_settings` por:

```python
# Media del sitio publico. Cloudinary es la unica fuente: estos defaults son
# las versiones sembradas, no archivos del repo (ver docs/superpowers/specs/
# 2026-08-18-site-media-design.md). Agregar un slot aqui es un cambio de
# diseno del sitio, por eso no hay slots dinamicos.
SITE_MEDIA_DEFAULTS = {
    # <<< PEGAR AQUI las nueve URLs impresas por la Task 1 >>>
    "hero_video_mp4": "",
    "hero_video_webm": "",
    "hero_poster": "",
    "moss_tall": "",
    "moss_wide": "",
    "leaf_litter": "",
    "terrarium": "",
    "isopod_zebra": "",
    "isopod_cubaris": "",
}

SITE_DEFAULTS = {
    "show_category_browse": True,  # seccion "Explora por grupo" en la home
    # Apagado: el sitio solo ofrece entrega personal en CDMX y la API rechaza
    # pedidos con envio (ver create_order en routes/shop.py)
    "shipping_enabled": True,
    "media": SITE_MEDIA_DEFAULTS,
}


def get_site_settings(db) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == "site").first()
    stored = json.loads(row.value) if row else {}
    # media se mezcla aparte: un slot guardado no debe esconder los defaults
    # de los otros ocho.
    media = {**SITE_MEDIA_DEFAULTS, **stored.get("media", {})}
    return {**SITE_DEFAULTS, **stored, "media": media}


class SiteMedia(BaseModel):
    hero_video_mp4: Optional[str] = None
    hero_video_webm: Optional[str] = None
    hero_poster: Optional[str] = None
    moss_tall: Optional[str] = None
    moss_wide: Optional[str] = None
    leaf_litter: Optional[str] = None
    terrarium: Optional[str] = None
    isopod_zebra: Optional[str] = None
    isopod_cubaris: Optional[str] = None


class SiteSettings(BaseModel):
    # Todos opcionales: el PUT es parcial y solo escribe lo que llega.
    show_category_browse: Optional[bool] = None
    shipping_enabled: Optional[bool] = None
    media: Optional[SiteMedia] = None


@router.put("/site", dependencies=CAN_UPDATE_ANIMAL_GROUPS,
            summary="Guardar ajustes del sitio")
def update_site_settings(body: SiteSettings, db: db_dependency):
    row = db.query(AppSetting).filter(AppSetting.key == "site").first()
    if not row:
        row = AppSetting(key="site", value="{}")
        db.add(row)

    stored = json.loads(row.value)
    patch = body.model_dump(exclude_unset=True)

    # media se mezcla un nivel mas adentro: mandar un slot no borra los otros
    if "media" in patch:
        patch["media"] = {
            **stored.get("media", {}),
            **{k: v for k, v in patch["media"].items() if v is not None},
        }

    row.value = json.dumps({**stored, **patch})
    db.commit()
    return get_site_settings(db)
```

**IMPORTANTE:** reemplazar las nueve cadenas vacías de `SITE_MEDIA_DEFAULTS` por
las URLs que imprimió la Task 1 antes de correr los tests. El test
`test_media_trae_los_nueve_slots_por_defecto` verifica que empiecen con
`https://`, así que falla si quedan vacías.

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
cd ~/dev/pharmatrack-api && pytest tests/test_settings_site.py tests/test_shop.py tests/test_group_visibility.py -v
```

Esperado: todo PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/pharmatrack-api
git add src/pharmatrack/api/routes/settings.py tests/test_settings_site.py
git commit -m "$(cat <<'EOF'
feat(settings): nueve slots de media del sitio en el blob site

Video del hero (mp4, webm, poster) y las seis imagenes decorativas pasan a
guardarse como URLs de Cloudinary en app_settings. media se mezcla un nivel mas
adentro que el resto: mandar un slot no borra los otros ocho.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 4: Permiso propio `settings.update`

Hoy el endpoint se protege con `animalgroups.update`, que no tiene relación con
lo que guarda.

**Files:**
- Modify: `src/pharmatrack/utils/permissions.py:34` (zona de los `_crud`)
- Modify: `src/pharmatrack/seeds/seed_permissions.py` (lista `PERMISSIONS`)
- Modify: `src/pharmatrack/api/routes/settings.py:13` (import) y el decorador del PUT
- Test: `tests/test_settings_site.py`

**Interfaces:**
- Consumes: el endpoint de las Tasks 2 y 3.
- Produces: los permisos `settings.read` y `settings.update`. La Task 6 usa
  `settings.update` en el guard del dashboard.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_settings_site.py`:

```python
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
```

Nota: el fixture `auth_headers` construye un rol con **toda** la lista
`PERMISSIONS` del seed (`tests/fixtures/roles.py:30-40`), así que basta con
agregar el permiso a esa lista para que el test lo ejercite. Un test negativo
con un rol recortado exigiría un fixture nuevo; queda fuera de alcance.

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd ~/dev/pharmatrack-api && pytest tests/test_settings_site.py -v
```

Esperado: FALLA en `assert "settings.update" in PERMISSIONS`.

- [ ] **Step 3: Declarar el permiso**

En `src/pharmatrack/utils/permissions.py`, junto a los otros `_crud` (después de
la línea de `orders`):

```python
CAN_READ_SETTINGS, CAN_CREATE_SETTINGS, CAN_UPDATE_SETTINGS, CAN_DELETE_SETTINGS = _crud("settings")
```

En `src/pharmatrack/seeds/seed_permissions.py`, al final de la lista
`PERMISSIONS`, antes del `]`:

```python
    # Ajustes del sitio publico (media, switches de la home)
    "settings.read", "settings.create", "settings.update", "settings.delete",
```

- [ ] **Step 4: Usarlo en el endpoint**

En `src/pharmatrack/api/routes/settings.py`, cambiar el import de la línea 13:

```python
from ...utils.permissions import CAN_READ_SALES, CAN_UPDATE_SALES, CAN_UPDATE_SETTINGS
```

y el decorador del PUT:

```python
@router.put("/site", dependencies=CAN_UPDATE_SETTINGS,
            summary="Guardar ajustes del sitio")
```

Verificar que `CAN_UPDATE_ANIMAL_GROUPS` ya no se use en este archivo:

```bash
cd ~/dev/pharmatrack-api && grep -n "CAN_UPDATE_ANIMAL_GROUPS" src/pharmatrack/api/routes/settings.py
```

Esperado: sin resultados.

- [ ] **Step 5: Correr la suite completa**

```bash
cd ~/dev/pharmatrack-api && pytest -q
```

Esperado: todo PASS. La suite completa porque cambiar la lista `PERMISSIONS`
afecta al fixture de rol que usan todos los tests autenticados.

- [ ] **Step 6: Commit**

```bash
cd ~/dev/pharmatrack-api
git add src/pharmatrack/utils/permissions.py src/pharmatrack/seeds/seed_permissions.py src/pharmatrack/api/routes/settings.py tests/test_settings_site.py
git commit -m "$(cat <<'EOF'
feat(settings): permiso propio settings.update para los ajustes del sitio

El PUT se protegia con animalgroups.update, que no tiene relacion con lo que
guarda. Con un permiso propio se puede dar acceso a la media del sitio sin dar
acceso a la taxonomia.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

- [ ] **Step 7: Avisarle al usuario del paso manual**

Tras desplegar, el permiso existe pero nadie lo tiene. Reportar textualmente:

> Corre el seed de permisos en producción, asigna `settings.update` a tu rol
> desde Dashboard → Roles, y **vuelve a iniciar sesión**: el JWT lleva los
> permisos incrustados al momento de crearse, así que tu token actual no lo
> trae.

---

## Task 5: Capa de datos del dashboard

**Files:**
- Modify: `~/dev/pharmatrack-frontend/src/lib/cloudinary.js`
- Create: `~/dev/pharmatrack-frontend/src/actions/site.js`

**Interfaces:**
- Consumes: `GET/PUT /api/v1/settings/site` de las Tasks 2-4.
- Produces:
  - `uploadToCloudinary(source, resourceType = 'image') => Promise<string>`
  - `useGetSiteSettings() => { site, siteLoading, siteError, siteMutate }`
    donde `site.media` es el objeto de nueve slots.
  - `updateSiteMedia(patch) => Promise<object>` con `patch` = `{ [slot]: url }`.

- [ ] **Step 1: Aceptar video en `uploadToCloudinary`**

Reemplazar el cuerpo de `src/lib/cloudinary.js` por:

```js
// ----------------------------------------------------------------------

/**
 * Sube una imagen o un video a Cloudinary usando un upload preset sin firma.
 * Acepta un File (desde disco) o una URL string (Cloudinary la descarga por su cuenta).
 * Requiere las variables de entorno:
 *   VITE_CLOUDINARY_CLOUD_NAME
 *   VITE_CLOUDINARY_UPLOAD_PRESET
 *
 * @param {File | string} source — archivo o URL remota
 * @param {'image' | 'video'} resourceType — endpoint de Cloudinary a usar
 * @returns {Promise<string>} URL pública (secure_url)
 */
export async function uploadToCloudinary(source, resourceType = 'image') {
  const cloudName = import.meta.env.VITE_CLOUDINARY_CLOUD_NAME;
  const uploadPreset = import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET;

  const formData = new FormData();
  formData.append('file', source); // Cloudinary acepta File o URL string
  formData.append('upload_preset', uploadPreset);

  const res = await fetch(
    `https://api.cloudinary.com/v1_1/${cloudName}/${resourceType}/upload`,
    { method: 'POST', body: formData }
  );

  if (!res.ok) {
    throw new Error('Error al subir el archivo a Cloudinary');
  }

  const data = await res.json();
  return data.secure_url;
}
```

El default `'image'` mantiene compatible a quien ya lo llama (fotos de animales).

- [ ] **Step 2: Verificar que no rompiste a los llamadores existentes**

```bash
cd ~/dev/pharmatrack-frontend && grep -rn "uploadToCloudinary" src/ --include=*.jsx --include=*.js
```

Esperado: todas las llamadas existentes pasan un solo argumento, así que caen en
`'image'` como antes.

- [ ] **Step 3: Crear `src/actions/site.js`**

```js
import useSWR from 'swr';
import { useMemo } from 'react';

import axiosInstance, { fetcher } from 'src/lib/axios';

// ----------------------------------------------------------------------
// Ajustes del sitio publico. Es un solo blob JSON (app_settings key="site"):
// switches de la home mas los nueve slots de media.
// ----------------------------------------------------------------------

const SITE_URL = '/api/v1/settings/site';

const swrOptions = {
  revalidateIfStale: false,
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
};

export function useGetSiteSettings() {
  const { data, isLoading, error, mutate } = useSWR(SITE_URL, fetcher, swrOptions);
  return useMemo(
    () => ({ site: data ?? null, siteLoading: isLoading, siteError: error, siteMutate: mutate }),
    [data, isLoading, error, mutate]
  );
}

// El PUT es parcial: manda solo los slots que cambian y el backend los mezcla.
export async function updateSiteMedia(patch) {
  const res = await axiosInstance.put(SITE_URL, { media: patch });
  return res.data;
}
```

- [ ] **Step 4: Lint**

```bash
cd ~/dev/pharmatrack-frontend && corepack yarn lint
```

Esperado: 0 errores. Si `perfectionist/sort-imports` se queja, correr
`corepack yarn lint:fix`.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/pharmatrack-frontend
git add src/lib/cloudinary.js src/actions/site.js
git commit -m "$(cat <<'EOF'
feat(site): capa de datos para los ajustes del sitio publico

uploadToCloudinary acepta resourceType para poder subir el video del hero
(tenia /image/upload fijo en la URL); actions/site.js expone el blob de ajustes
por SWR y un PUT parcial de media.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 6: Sección "Sitio web" en el dashboard

**Files:**
- Create: `~/dev/pharmatrack-frontend/src/sections/site/view/site-media-view.jsx`
- Create: `~/dev/pharmatrack-frontend/src/sections/site/view/index.js`
- Create: `~/dev/pharmatrack-frontend/src/pages/dashboard/site/media.jsx`
- Modify: `~/dev/pharmatrack-frontend/src/routes/paths.js:94-101` (bloque `dashboard`)
- Modify: `~/dev/pharmatrack-frontend/src/routes/sections/dashboard.jsx` (lazy import, `P`, ruta)
- Modify: `~/dev/pharmatrack-frontend/src/layouts/nav-config-dashboard.jsx:133-142`

**Interfaces:**
- Consumes: `useGetSiteSettings`, `updateSiteMedia`, `uploadToCloudinary` de la Task 5.
- Produces: la ruta `/dashboard/site/media`. Nada más depende de ella.

- [ ] **Step 1: Crear la vista**

`src/sections/site/view/site-media-view.jsx`:

```jsx
import { useState } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Grid from '@mui/material/Grid';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';

import { DashboardContent } from 'src/layouts/dashboard';
import { uploadToCloudinary } from 'src/lib/cloudinary';
import { updateSiteMedia, useGetSiteSettings } from 'src/actions/site';

import { toast } from 'src/components/snackbar';
import { Iconify } from 'src/components/iconify';
import { CustomBreadcrumbs } from 'src/components/custom-breadcrumbs';

// ----------------------------------------------------------------------
// Media del sitio publico. Son slots con nombre fijo, no una biblioteca: cada
// hueco dice donde aparece, porque el sitio tiene diseno editorial y cambiar
// una foto por otra de proporcion distinta se nota.
// ----------------------------------------------------------------------

const SLOTS = [
  { key: 'hero_video_mp4', label: 'Video del hero (MP4)', where: 'Portada · fondo de la primera pantalla', type: 'video' },
  { key: 'hero_video_webm', label: 'Video del hero (WebM)', where: 'Portada · mismo video, formato alterno', type: 'video' },
  { key: 'hero_poster', label: 'Poster del hero', where: 'Portada · cuadro fijo mientras carga el video', type: 'image' },
  { key: 'moss_tall', label: 'Musgo vertical', where: 'Preguntas frecuentes, El criadero y el divisor 3D', type: 'image' },
  { key: 'moss_wide', label: 'Musgo horizontal', where: 'Portada · cierre y rejilla de categorías', type: 'image' },
  { key: 'leaf_litter', label: 'Hojarasca', where: 'Portada · bloque de sustrato y categorías', type: 'image' },
  { key: 'terrarium', label: 'Terrario', where: 'Divisor 3D de las vistas interiores', type: 'image' },
  { key: 'isopod_zebra', label: 'Isópodo cebra', where: 'Portada · bloque de proteína y categorías', type: 'image' },
  { key: 'isopod_cubaris', label: 'Isópodo Cubaris', where: 'Portada · bloque de calcio y categorías', type: 'image' },
];

export function SiteMediaView() {
  const { site, siteLoading, siteMutate } = useGetSiteSettings();
  const [busy, setBusy] = useState(null); // key del slot que se está subiendo

  const handlePick = async (slot, file) => {
    if (!file) return;
    setBusy(slot.key);
    try {
      const url = await uploadToCloudinary(file, slot.type);
      await updateSiteMedia({ [slot.key]: url });
      await siteMutate();
      toast.success('Actualizado. El sitio lo muestra en ~1 minuto.');
    } catch (error) {
      toast.error(error.message || 'Error al subir el archivo');
    } finally {
      setBusy(null);
    }
  };

  return (
    <DashboardContent>
      <CustomBreadcrumbs
        heading="Media del sitio"
        links={[
          { name: 'Dashboard', href: paths.dashboard.root },
          { name: 'Sitio web' },
          { name: 'Media' },
        ]}
        sx={{ mb: { xs: 3, md: 5 } }}
      />

      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        Los cambios aparecen en el sitio en aproximadamente un minuto.
      </Typography>

      {siteLoading ? (
        <Typography>Cargando…</Typography>
      ) : (
        <Grid container spacing={3}>
          {SLOTS.map((slot) => (
            <Grid key={slot.key} size={{ xs: 12, sm: 6, md: 4 }}>
              <SlotCard
                slot={slot}
                src={site?.media?.[slot.key] ?? ''}
                busy={busy === slot.key}
                disabled={!!busy}
                onPick={(file) => handlePick(slot, file)}
              />
            </Grid>
          ))}
        </Grid>
      )}
    </DashboardContent>
  );
}

// ----------------------------------------------------------------------

function SlotCard({ slot, src, busy, disabled, onPick }) {
  const inputId = `slot-${slot.key}`;

  return (
    <Card sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box
        sx={{
          aspectRatio: '16 / 10',
          borderRadius: 1.5,
          overflow: 'hidden',
          bgcolor: 'background.neutral',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        {!src ? (
          <Iconify icon="solar:gallery-bold" width={32} sx={{ color: 'text.disabled' }} />
        ) : slot.type === 'video' ? (
          // muted+loop: la vista previa no debe hacer ruido al abrir la pagina
          <Box component="video" src={src} muted loop playsInline controls sx={{ width: 1, height: 1, objectFit: 'cover' }} />
        ) : (
          <Box component="img" src={src} alt={slot.label} sx={{ width: 1, height: 1, objectFit: 'cover' }} />
        )}
      </Box>

      <Box sx={{ flexGrow: 1 }}>
        <Typography variant="subtitle2">{slot.label}</Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {slot.where}
        </Typography>
      </Box>

      <Button
        component="label"
        htmlFor={inputId}
        variant="outlined"
        size="small"
        disabled={disabled}
        startIcon={<Iconify icon={busy ? 'eos-icons:loading' : 'solar:upload-bold'} width={16} />}
      >
        {busy ? 'Subiendo…' : 'Reemplazar'}
        <Box
          id={inputId}
          component="input"
          type="file"
          accept={slot.type === 'video' ? 'video/*' : 'image/*'}
          hidden
          // value se limpia para poder volver a elegir el MISMO archivo
          onChange={(event) => {
            onPick(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
      </Button>
    </Card>
  );
}
```

- [ ] **Step 2: Crear el barrel y la página**

`src/sections/site/view/index.js`:

```js
export * from './site-media-view';
```

`src/pages/dashboard/site/media.jsx`:

```jsx
import { CONFIG } from 'src/global-config';

import { SiteMediaView } from 'src/sections/site/view';

// ----------------------------------------------------------------------

const metadata = { title: `Media del sitio | Dashboard - ${CONFIG.appName}` };

export default function Page() {
  return (<><title>{metadata.title}</title><SiteMediaView /></>);
}
```

Si `src/pages/dashboard/sale/email-template.jsx` usa otra forma de armar
`metadata`, copiar esa — es el precedente más cercano (página de ajustes suelta).

- [ ] **Step 3: Registrar la ruta**

En `src/routes/paths.js`, dentro del objeto `dashboard`, junto al bloque
`animal` (línea ~94):

```js
    site: {
      media: `${ROOTS.DASHBOARD}/site/media`,
    },
```

En `src/routes/sections/dashboard.jsx`, junto a los otros `lazy` (línea ~82):

```js
const SiteMediaPage = lazy(() => import('src/pages/dashboard/site/media'));
```

En el objeto `P` (línea ~145, junto a `articlesUpdate`):

```js
  // Sitio publico
  siteUpdate: ['settings.update'],
```

Y el bloque de ruta, después del bloque `animal` (línea ~340):

```jsx
      // ── Sitio publico ───────────────────────────────────────────────
      {
        path: 'site',
        children: [
          { index: true,    element: guard(P.siteUpdate, <SiteMediaPage />) },
          { path: 'media',  element: guard(P.siteUpdate, <SiteMediaPage />) },
        ],
      },
```

- [ ] **Step 4: Agregar el item de navegación**

En `src/layouts/nav-config-dashboard.jsx`, después del bloque `Artículos`
(línea ~152):

```jsx
      {
        title: 'Sitio web',
        path: paths.dashboard.site.media,
        icon: ICONS.file,
        allowedRoles: ['settings.update'],
        children: [{ title: 'Media', path: paths.dashboard.site.media }],
      },
```

- [ ] **Step 5: Lint y build**

```bash
cd ~/dev/pharmatrack-frontend && corepack yarn lint && corepack yarn build
```

Esperado: lint con 0 errores (los 3 warnings preexistentes siguen), build en
verde.

- [ ] **Step 6: Verificación manual**

Levantar el dashboard, entrar a `/dashboard/site/media` y confirmar:

1. Se ven las nueve tarjetas con su vista previa actual.
2. Reemplazar una imagen la sube y la tarjeta muestra la nueva.
3. Reemplazar un slot **no** vacía los otros (recargar y comprobar).

Si el login local no conecta, reportarlo y no dar por verificado lo que no se
vio. `corepack yarn dev` corre en el puerto 3030 y `.env.local` apunta a
`http://localhost:8000`.

- [ ] **Step 7: Commit**

```bash
cd ~/dev/pharmatrack-frontend
git add src/sections/site src/pages/dashboard/site src/routes/paths.js src/routes/sections/dashboard.jsx src/layouts/nav-config-dashboard.jsx
git commit -m "$(cat <<'EOF'
feat(site): seccion "Sitio web" para cambiar la media del sitio publico

Nueve tarjetas de slot con nombre fijo, cada una diciendo donde aparece en el
sitio: se elige archivo, sube a Cloudinary y se guarda la URL en su slot.
Protegida con settings.update.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 7: La portada del sitio consume `media`

**Files:**
- Modify: `~/dev/pharmatrack-web/src/lib/public-api.js:57`
- Modify: `~/dev/pharmatrack-web/src/app/page.jsx`
- Modify: `~/dev/pharmatrack-web/src/sections/home/od/od-home-view.jsx:32-39,53-61,132-136,343,421`

**Interfaces:**
- Consumes: `getSiteSettings()` devuelve `.media` con los nueve slots (Task 3).
- Produces: `OdHomeView` acepta la prop `media` (objeto de nueve slots). La
  Task 8 usa el mismo objeto en el resto de componentes.

- [ ] **Step 1: Defaults de respaldo en `public-api.js`**

Reemplazar la línea 57 de `src/lib/public-api.js`:

```js
// Respaldo si el API no responde. Son las mismas URLs sembradas en Cloudinary
// que usa SITE_DEFAULTS del backend: aqui no hay archivos locales que servir.
const SITE_MEDIA_DEFAULTS = {
  // <<< PEGAR las mismas nueve URLs de la Task 1 >>>
  hero_video_mp4: '',
  hero_video_webm: '',
  hero_poster: '',
  moss_tall: '',
  moss_wide: '',
  leaf_litter: '',
  terrarium: '',
  isopod_zebra: '',
  isopod_cubaris: '',
};

const SITE_DEFAULTS = {
  show_category_browse: true,
  shipping_enabled: true,
  media: SITE_MEDIA_DEFAULTS,
};
```

Pegar las URLs reales de la Task 1, no dejarlas vacías.

- [ ] **Step 2: Pasar `media` desde `app/page.jsx`**

```jsx
import { OdLayout } from 'src/layouts/od/od-layout';
import { getAnimals, getProducts, getArticles, getSiteSettings } from 'src/lib/public-api';

import { buildListings } from 'src/sections/catalog/utils';
import { OdHomeView } from 'src/sections/home/od/od-home-view';

// ----------------------------------------------------------------------

export default async function Page() {
  const [{ data: animals }, products, articles, site] = await Promise.all([
    getAnimals(),
    getProducts(),
    getArticles(),
    getSiteSettings(),
  ]);

  const listings = buildListings(animals);

  return (
    <OdLayout homeMasthead>
      <OdHomeView species={listings} products={products} articles={articles} media={site.media} />
    </OdLayout>
  );
}
```

- [ ] **Step 3: Consumir `media` en `od-home-view.jsx`**

La constante `IMG` (línea 32) y las listas que la usan (`53-61`) están a nivel de
módulo, pero `media` llega por prop. Convertir `IMG` en función y mover las dos
listas dentro del componente.

Borrar el bloque `const IMG = {...}` (líneas 32-39) y poner en su lugar:

```jsx
// Las seis imagenes decorativas ya no son archivos del repo: llegan del blob
// de ajustes (Dashboard -> Sitio web -> Media).
const buildImg = (media) => ({
  mossTall: media.moss_tall,
  leafLitter: media.leaf_litter,
  isopodZebra: media.isopod_zebra,
  terrarium: media.terrarium,
  isopodCubaris: media.isopod_cubaris,
  mossWide: media.moss_wide,
});
```

Las dos constantes de módulo que usan `IMG.` son `INGREDIENTS` (líneas 52-59) y
`CAT_IMAGES` (línea 61). `STATS` (línea 44) **no** usa `IMG`, se queda donde
está. Borrar `INGREDIENTS` y `CAT_IMAGES` de nivel de módulo y recrearlas
**dentro** del componente, justo después de la firma:

```jsx
export function OdHomeView({ species, products, articles, media }) {
  const IMG = buildImg(media);

  // Los 6 elementos del bloque oscuro "Seis cosas dentro del frasco".
  const INGREDIENTS = [
    { n: '01', title: 'Sustrato húmedo', body: 'Coco, tierra y carbón: sostienen el gradiente de humedad sin encharcarse.', img: IMG.mossTall },
    { n: '02', title: 'Hojarasca curada', body: 'Roble y magnolia secos: alimento base y refugio donde mudan tranquilos.', img: IMG.leafLitter },
    { n: '03', title: 'Madera blanda', body: 'Piezas en descomposición que aportan celulosa y estructura al montaje.', img: IMG.terrarium },
    { n: '04', title: 'Calcio', body: 'Sepia molida o cáscara: sin ella la muda falla y la colonia deja de crecer.', img: IMG.isopodCubaris },
    { n: '05', title: 'Proteína', body: 'Una pizca cada dos semanas. Más que eso y aparecen ácaros.', img: IMG.isopodZebra },
    { n: '06', title: 'Colémbolos', body: 'El copiloto invisible: consumen el moho antes de que llegue a la camada.', img: IMG.mossWide },
  ];

  const CAT_IMAGES = [IMG.isopodCubaris, IMG.mossTall, IMG.leafLitter, IMG.terrarium, IMG.isopodZebra, IMG.mossWide];
```

`CAT_IMAGES` ya se usa dentro del componente (línea 117, en `catCards`), así que
solo cambia de dónde viene. Verificar dónde se consume `INGREDIENTS` y que siga
en el ámbito correcto:

```bash
cd ~/dev/pharmatrack-web && grep -n "INGREDIENTS" src/sections/home/od/od-home-view.jsx
```

- [ ] **Step 4: El video del hero sale de `media`**

En el bloque del hero (líneas 125-137), sustituir las rutas fijas:

```jsx
          poster={media.hero_poster}
          sx={{ position: 'absolute', inset: 0, width: 1, height: 1, objectFit: 'cover', bgcolor: 'var(--color-neutral-800)' }}
        >
          <source src={media.hero_video_webm} type="video/webm" />
          <source src={media.hero_video_mp4} type="video/mp4" />
```

- [ ] **Step 5: Lint y build**

```bash
cd ~/dev/pharmatrack-web && corepack yarn lint:fix && corepack yarn build
```

Esperado: build en verde. Si falla por `IMG is not defined`, quedó un uso de
`IMG.` fuera del componente: buscarlo con
`grep -n "IMG\." src/sections/home/od/od-home-view.jsx`.

- [ ] **Step 6: Commit**

```bash
cd ~/dev/pharmatrack-web
git add src/lib/public-api.js src/app/page.jsx src/sections/home/od/od-home-view.jsx
git commit -m "$(cat <<'EOF'
feat(home): la portada toma su media del blob de ajustes

Las seis imagenes decorativas y el video del hero dejan de ser rutas fijas del
repo y llegan por prop desde getSiteSettings, para poder cambiarlas desde el
dashboard sin desplegar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Task 8: El resto del sitio consume `media` y se borran los archivos

Quedan cuatro consumidores fuera de la portada. Dos no estaban en el spec y
salieron al leer el código: el fondo CSS del divisor 3D y el splash de carga.

**Files:**
- Modify: `~/dev/pharmatrack-web/src/layouts/od/od-layout.jsx`
- Modify: `~/dev/pharmatrack-web/src/layouts/od/od-divider-3d.jsx:31-40`
- Modify: `~/dev/pharmatrack-web/src/sections/home/od/od-faq.jsx:55`
- Modify: `~/dev/pharmatrack-web/src/app/criadero/page.jsx:59-62`
- Modify: `~/dev/pharmatrack-web/src/app/layout.jsx:65,91`
- Modify: `~/dev/pharmatrack-web/src/components/loading-screen/site-splash.jsx:32`
- Delete: `~/dev/pharmatrack-web/public/video/`, `~/dev/pharmatrack-web/public/assets/redesign/`

**Interfaces:**
- Consumes: `media` (Task 3), `getSiteSettings()` (Task 7).
- Produces: nada; es la última task.

- [ ] **Step 1: `OdLayout` hace el fetch y reparte**

`OdLayout` es server component, así que puede pedir los ajustes él mismo en vez
de que cada página se los pase. `OdDivider3d` es client, pero recibe strings, que
cruzan la frontera RSC sin problema.

En `src/layouts/od/od-layout.jsx`:

```jsx
import Box from '@mui/material/Box';

import { getSiteSettings } from 'src/lib/public-api';
import { CloseCursor } from 'src/layouts/components/close-cursor';

import { OdHeader } from './od-header';
import { OdFooter } from './od-footer';
import { OdTopbar } from './od-topbar';
import { OdTabBar } from './od-tab-bar';
import { OdDivider3d } from './od-divider-3d';
```

y la firma pasa a `async`:

```jsx
export async function OdLayout({ children, homeMasthead = false, divider3d = true, hideTabBar = false }) {
  // Server component: pide la media aqui en vez de que cada pagina la herede.
  // El fetch se deduplica dentro del render y ya trae revalidate de 60 s.
  const { media } = await getSiteSettings();

  return (
```

y la línea del divisor:

```jsx
      {!homeMasthead && divider3d && <OdDivider3d media={media} />}
```

- [ ] **Step 2: `OdDivider3d` recibe `media`**

Tiene **dos** referencias: el `backgroundImage` de CSS (línea 35) y el
`fallbackSrc` de la escena (línea 39).

```jsx
export function OdDivider3d({ media }) {
  return (
    <>
      <Ticker />
      <Box component="section" data-dark="1" sx={{ position: 'relative', display: 'grid', placeItems: 'center', px: '40px', py: { xs: '64px', md: '96px' }, overflow: 'hidden', isolation: 'isolate' }}>
        <Box sx={{ position: 'absolute', inset: 0, zIndex: -2, backgroundImage: `url(${media.moss_tall})`, backgroundSize: 'cover', backgroundPosition: 'center' }} />
        <Box sx={{ position: 'absolute', inset: 0, zIndex: -1, bgcolor: 'rgba(32,31,29,0.22)' }} />
        <Box sx={{ display: 'grid', gap: '26px', justifyItems: 'center' }}>
          <OdScene
            scene="stack"
            fallbackSrc={media.terrarium}
            fallbackLabel="Cultivos por especie"
            ratio="1 / 1"
            sx={{ width: 'min(460px, 74vw)' }}
          />
```

El resto del componente no cambia.

- [ ] **Step 3: FAQ y El criadero**

`src/sections/home/od/od-faq.jsx` es client y lo renderiza `OdHomeView`. Cambiar
su firma a `export function OdFaq({ mossTall })` y la línea 55:

```jsx
              <OdScene scene="log" fallbackSrc={mossTall} fallbackLabel="Tronco con musgo" ratio="3 / 5" />
```

En `od-home-view.jsx` línea 447, donde se renderiza: `<OdFaq mossTall={IMG.mossTall} />`.

`src/app/criadero/page.jsx` tiene **cuatro** referencias, no una: el array
`PHOTOS` (líneas 18-22) usa tres imágenes y el `fallbackSrc` de la línea 61 usa
una cuarta. Además hoy **no es async** (línea 31: `export default function Page()`),
así que hay que convertirla.

Agregar el import y volverla async, moviendo `PHOTOS` adentro:

```jsx
import { getSiteSettings } from 'src/lib/public-api';
```

Borrar el bloque `const PHOTOS = [...]` de las líneas 18-22 y reescribir la
firma:

```jsx
export default async function Page() {
  const { media } = await getSiteSettings();

  const PHOTOS = [
    { src: media.terrarium, label: 'Estantería de colonias' },
    { src: media.moss_tall, label: 'Montaje de un frasco' },
    { src: media.leaf_litter, label: 'Hojarasca curada' },
  ];
```

`STATS` (líneas 24-29) no usa imágenes: se queda a nivel de módulo. Y el
`fallbackSrc` de la línea 61:

```jsx
              fallbackSrc={media.moss_tall}
```

- [ ] **Step 4: El splash de carga**

`site-splash.jsx` es client y hoy tiene `const HERO_IMG = '/video/hero-moss.jpg'`
(línea 32). Lo renderiza `src/app/layout.jsx:91`, que ya es `async`.

En `site-splash.jsx`, borrar la constante `HERO_IMG` y su comentario, pasar la
URL por prop y usarla donde estaba:

```jsx
// Imagen dominante de la primera pantalla. La pinta un componente cliente DESPUÉS
// de hidratar, así que no está en el HTML inicial y `window.load` no la espera:
// por eso el splash se iba y el fondo del hero aparecía de golpe justo después.
export function SiteSplash({ heroPoster }) {
```

`HERO_IMG` tiene un solo uso, en la línea 77. Cambiarlo por la prop:

```jsx
      img.src = heroPoster;
```

En `src/app/layout.jsx`, dentro de `RootLayout` (ya es async), agregar el fetch
y pasar la prop:

```jsx
  const { media } = await getSiteSettings();
```

```jsx
                <SiteSplash heroPoster={media.hero_poster} />
```

más el import de `getSiteSettings` desde `src/lib/public-api`.

- [ ] **Step 5: Verificar que no queda ninguna referencia a los archivos**

```bash
cd ~/dev/pharmatrack-web && grep -rn "/video/hero-moss\|/assets/redesign/" src/
```

Esperado: **sin resultados**. Si aparece alguno, arreglarlo antes de borrar
nada.

- [ ] **Step 6: Borrar los archivos**

```bash
cd ~/dev/pharmatrack-web && rm -rf public/video public/assets/redesign
```

- [ ] **Step 7: Lint y build**

```bash
cd ~/dev/pharmatrack-web && corepack yarn lint:fix && corepack yarn build
```

Esperado: build en verde. Un 404 de imagen no rompe el build, por eso el Step 5
va antes que el borrado.

- [ ] **Step 8: Verificación manual**

```bash
cd ~/dev/pharmatrack-web && corepack yarn dev
```

Abrir la portada y confirmar: el video del hero se reproduce, las seis imágenes
decorativas cargan, y una vista interior (p. ej. `/carrito` no, que desactiva el
divisor — usar `/criadero`) muestra el divisor 3D con su fondo.

- [ ] **Step 9: Commit**

```bash
cd ~/dev/pharmatrack-web
git add -A
git commit -m "$(cat <<'EOF'
feat(sitio): el resto de la media sale del blob de ajustes; se borra public/

OdLayout (server component) pide los ajustes y reparte media al divisor 3D; FAQ,
El criadero y el splash de carga reciben su imagen por prop. Cloudinary queda
como unica fuente, asi que se borran public/video y public/assets/redesign.

El fondo CSS del divisor y el poster del splash no estaban en el spec: salieron
al revisar los consumidores reales antes de borrar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Y681g8AWJLT3aosGeXQojm
EOF
)"
git push origin main
```

---

## Notas de revisión del plan

Contra el spec, tres cosas cambiaron al leer el código:

1. **`moss_tall` tiene cuatro consumidores, no uno.** El spec decía "fallback de
   la escena del tronco"; además es el `backgroundImage` CSS del divisor 3D
   (`od-divider-3d.jsx:35`), el fallback de El criadero (línea 61) y una de las
   fotos de su array `PHOTOS`.
2. **`site-splash.jsx` no estaba en el spec.** Hardcodea el poster del hero
   (línea 32) y lo precarga en la 77. Si se borra `public/video/` sin tocarlo, el
   splash precarga una imagen rota. Cubierto en la Task 8, Step 4.
3. **`criadero/page.jsx` no es async y tiene un array `PHOTOS` con tres
   imágenes** que el spec no contaba. Hay que convertir la página a async.
   Cubierto en la Task 8, Step 3.

El spec no necesita corrección: los nueve slots siguen siendo nueve, y ninguna
decisión de diseño cambia. Lo que creció es la lista de archivos que los leen —
razón por la que el Step 5 de la Task 8 hace un `grep` de verificación **antes**
de borrar nada.
