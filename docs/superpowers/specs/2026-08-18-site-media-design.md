# Media del sitio público editable desde el dashboard

Fecha: 2026-08-18
Estado: aprobado, pendiente de implementar

## Problema

Las imágenes decorativas y el video del hero de `opuntiaden.com` viven como
archivos en el repo `pharmatrack-web`. Cambiar cualquiera de ellos exige editar
código y desplegar, así que en la práctica no se cambian.

Las fotos de productos, especies y artículos ya son dinámicas (vienen del API) y
quedan fuera de este trabajo.

## Alcance

Nueve slots de media con nombre fijo, editables desde el dashboard:

| Slot | Dónde aparece |
| --- | --- |
| `hero_video_mp4` | Portada, video de fondo |
| `hero_video_webm` | Portada, video de fondo (formato alterno) |
| `hero_poster` | Portada, cuadro fijo mientras carga el video |
| `moss_tall` | Fallback de la escena 3D del tronco (FAQs) y página El criadero |
| `moss_wide` | Home |
| `leaf_litter` | Home |
| `terrarium` | Fallback del divisor 3D interior |
| `isopod_zebra` | Home |
| `isopod_cubaris` | Home |

**Fuera de alcance, por decisión explícita:** textos (marquesina, `STATS`,
títulos), prender/apagar o reordenar secciones, biblioteca de medios, recorte de
imágenes, historial de versiones, subida múltiple, preview embebido del sitio.

Son slots con nombre fijo, no un constructor de páginas: agregar un slot nuevo
requiere tocar código, porque un slot nuevo es un cambio de diseño.

## Decisiones tomadas

1. **Cloudinary como única fuente.** Se borran los archivos de `public/`. Para
   que ningún slot quede vacío, los valores por defecto de `SITE_DEFAULTS`
   apuntan a las versiones actuales ya subidas a Cloudinary (ver Fase 1).
2. **Permiso propio `settings.update`.** Hoy `PUT /settings/site` usa
   `animalgroups.update`, que no tiene relación con lo que protege.
3. **Sin endpoints nuevos.** Se reutiliza el blob `site` de `AppSetting`.

## Bug preexistente que este trabajo debe arreglar

`PUT /api/v1/settings/site` reemplaza el blob completo, pero el dashboard manda
un solo campo:

```python
# src/pharmatrack/api/routes/settings.py
row.value = json.dumps(body.model_dump())   # escribe TODO el modelo
```

```js
// pharmatrack-frontend/src/sections/animal/view/animal-taxonomy-view.jsx
axiosInstance.put('/api/v1/settings/site', { show_category_browse })
```

`SiteSettings` tiene `shipping_enabled: bool = True`, así que Pydantic rellena el
campo ausente con su default y lo persiste. Hoy, apagar los envíos y después
tocar el switch de "Explorar por categorías" vuelve a encender los envíos en
silencio.

Con nueve campos de media encima, cambiar una imagen reseteaba todos los
ajustes. El arreglo es parte de esta feature, no un extra.

## Diseño

### Modelo de datos

```python
class SiteMedia(BaseModel):
    hero_video_mp4: str | None = None
    hero_video_webm: str | None = None
    hero_poster: str | None = None
    moss_tall: str | None = None
    moss_wide: str | None = None
    leaf_litter: str | None = None
    terrarium: str | None = None
    isopod_zebra: str | None = None
    isopod_cubaris: str | None = None


class SiteSettings(BaseModel):
    show_category_browse: bool | None = None
    shipping_enabled: bool | None = None
    media: SiteMedia | None = None


SITE_DEFAULTS = {
    "show_category_browse": True,
    "shipping_enabled": True,
    "media": { ...urls sembradas en la Fase 1... },
}
```

Todos los campos son opcionales para que un PUT parcial sea representable.

### Escritura con merge

`update_site_settings` deja de reemplazar y pasa a mezclar:

1. Lee lo guardado.
2. `body.model_dump(exclude_unset=True)` — solo los campos que el cliente mandó.
3. Mezcla de un nivel: `media` se mezcla slot por slot en vez de sustituirse
   entero.
4. Persiste el resultado.

`GET /settings/site` no cambia: sigue siendo público y sigue devolviendo
`{**SITE_DEFAULTS, **stored}`. Las URLs de media son públicas por naturaleza.

### Permisos

- `utils/permissions.py`: `CAN_READ_SETTINGS, CAN_CREATE_SETTINGS,
  CAN_UPDATE_SETTINGS, CAN_DELETE_SETTINGS = _crud("settings")`.
- `seeds/seed_permissions.py`: agregar `settings.read` y `settings.update` a la
  lista. El seed es idempotente, solo crea los que faltan.
- `PUT /settings/site` pasa a `dependencies=CAN_UPDATE_SETTINGS`.

**Paso manual tras desplegar:** asignar los permisos nuevos al rol correspondiente
desde la UI de Roles y volver a iniciar sesión. El JWT lleva los permisos
incrustados al momento de crearse, así que un token vigente no los incluye.

### Dashboard (`pharmatrack-frontend`)

- `lib/cloudinary.js` — `uploadToCloudinary(source, resourceType = 'image')`;
  hoy tiene `/image/upload` fijo en la URL y el video necesita `/video/upload`.
- `actions/site.js` — `useGetSiteSettings()` (SWR) y `updateSiteSettings(patch)`.
- `sections/site/view/site-media-view.jsx` — rejilla de tarjetas de slot. Cada
  tarjeta muestra el nombre del slot, dónde aparece, la vista previa actual y un
  botón *Reemplazar*: selector de archivo → `uploadToCloudinary` → PUT de ese
  slot solamente.
- `pages/dashboard/site/media.jsx` — página delgada.
- `routes/sections/dashboard.jsx` — ruta con `guard(P.site, …)`, con
  `P.site = ['settings.update']`.
- Item de navegación "Sitio web".

### Sitio público (`pharmatrack-web`)

El reparto no necesita pasar props por toda la app:

- `layouts/od/od-layout.jsx` **es server component**: hace
  `await getSiteSettings()` y pasa `media` a `OdDivider3d`, que es client. Son
  strings, cruzan la frontera RSC sin problema.
- `app/page.jsx` ya es async: pasa `media` a `OdHomeView`, que reemplaza su
  constante `IMG` (`od-home-view.jsx:32`) y las `<source>` del hero
  (`od-home-view.jsx:132-136`).
- `app/criadero/page.jsx` y `sections/home/od/od-faq.jsx`: sus `fallbackSrc`
  pasan a leerse de `media`.
- `lib/public-api.js`: `SITE_DEFAULTS` incluye el sub-objeto `media` para que el
  sitio siga en pie si el API no responde.
- Se borran `public/video/` y `public/assets/redesign/`.

Los cambios aparecen solos en ~60 s: `getSiteSettings` ya usa
`next: { revalidate: 60 }`. No hace falta invalidación manual.

## Fases

**Fase 1 — Siembra (va primero a propósito).** Un script desechable sube los 9
archivos actuales de `public/` a Cloudinary con el preset unsigned e imprime las
URLs para pegarlas en `SITE_DEFAULTS`: los 3 de `public/video/` (mp4, webm,
poster) y los 6 de `public/assets/redesign/`.

Se hace antes que todo porque es donde vive el único riesgo técnico real: si el
preset unsigned rechaza `/video/upload`, hay que saberlo antes de construir la
UI, no después. Si lo rechaza, parar y decidir (firmar la subida, subir el video
a mano por el panel de Cloudinary, o dejar el video en el repo).

**Fase 2 — Backend.** Modelo, merge, permisos, seed, pruebas.

**Fase 3 — Dashboard.** `resourceType` en Cloudinary, actions, vista, ruta, nav.

**Fase 4 — Sitio.** Consumir `media`, borrar los archivos de `public/`.

## Pruebas

`tests/test_settings_site.py` cubre la lógica no trivial, que es el merge:

- Un PUT parcial con solo `show_category_browse` no cambia `shipping_enabled`
  (la regresión que hoy existe).
- Un PUT que actualiza un slot de `media` no borra los otros ocho.
- `GET` devuelve los defaults sembrados cuando no hay nada guardado.

El resto es cableado y lo cubren `yarn build` y `yarn lint` de cada frontend.

## Riesgos

| Riesgo | Mitigación |
| --- | --- |
| El preset unsigned de Cloudinary no acepta video | Fase 1 lo descubre antes de escribir UI |
| Ancho de banda de Cloudinary por servir video en la portada | El hero pesa ~780 KB; vigilar el consumo del plan |
| Modo offline (`image_cache.py`) solo reescribe URLs de imagen de Cloudinary | El sitio público no corre en el stack offline (es el POS); verificar si eso cambia |
| Un token vigente no trae `settings.update` | Documentado: reasignar rol y volver a entrar |
