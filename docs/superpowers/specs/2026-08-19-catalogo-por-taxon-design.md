# El catálogo público se arma por taxón, no por ejemplar

Fecha: 2026-08-19
Estado: aprobado, pendiente de implementar

## Problema

En producción hay **38 especies visibles y un solo ejemplar registrado**. El
dashboard las muestra correctamente como "Agotado" y con su interruptor
encendido, pero **ninguna aparece en el sitio público**.

La causa no es el filtro de disponibilidad que se agregó antes
(`include_unavailable`, ya desplegado y funcionando). Es más de fondo:

> El catálogo público construye sus tarjetas **a partir de los ejemplares**
> (`buildListings(animals)` en `pharmatrack-web/src/sections/catalog/utils.js`).
> Una especie sin ningún ejemplar no produce tarjeta.

`include_unavailable` sirve para incluir ejemplares **vendidos o apartados**.
Esas 37 especies no tienen ninguno que incluir: tienen cero.

Hay un segundo problema encadenado: **las fotos cuelgan del ejemplar**
(`Animal.image` y la tabla `animal_photos`), no de la especie. Aunque el
catálogo empezara a listarlas, saldrían 37 tarjetas sin foto.

## Alcance

1. Imagen propia en **especies** y en **morphs**.
2. Un endpoint público que exponga los taxones visibles, tengan ejemplares o no.
3. El catálogo del sitio pasa a armarse **por taxón**, adjuntándole sus
   ejemplares, en vez de derivarse de ellos.
4. Banda de "Agotado" en la esquina de la tarjeta, visible y roja.
5. Marca "Nominal" en la especie base, en el sitio y en las dos pantallas
   del dashboard que listan especies.
6. Subida de esa imagen desde el dashboard.

**Fuera de alcance:**

- Galería de varias fotos por especie: una imagen basta para la tarjeta; el
  detalle sigue usando las fotos de los ejemplares cuando existan.
- Precios por taxón más allá de los `price_tiers` que ya existen.
- Cambiar la ficha de especie del sitio, que ya sabe representar agotado.

## Decisiones tomadas

### La imagen va en especie **y** en morph

El sitio arma una tarjeta por morph, no solo por especie (`buildListings`
agrupa por `(especie, primer morph)`). En la captura del dueño, morphs como
'Dairy Cow', 'Milkback' y 'Orange' aparecen agotados por separado. Si la imagen
viviera solo en la especie, todos los morphs de una especie compartirían foto y
se perdería justo lo que los distingue.

Mismo criterio que `show_public`, que ya vive en los dos niveles.

### El servidor devuelve taxonomía; el sitio sigue armando las tarjetas

El endpoint nuevo **no** devuelve tarjetas ya agrupadas. Devuelve las especies
visibles con sus morphs visibles anidados, y el sitio conserva `buildListings`
como única implementación del agrupamiento.

Razón: duplicar la lógica de agrupamiento en el servidor crearía dos
implementaciones de la misma regla que pueden divergir. En esta misma feature ya
se corrigieron tres bugs exactamente por eso.

### `buildListings` se invierte

Hoy recorre ejemplares y crea entradas al vuelo. Pasa a recorrer **los taxones
visibles** y adjuntarles los ejemplares que les correspondan.

Consecuencia buscada: un taxón sin ejemplares produce una entrada con `count: 0`
y por lo tanto cae en el camino "Agotado" que `animalToCard` **ya implementa**
(`soldOut = i.count === 0`). No hace falta un estado nuevo.

### Una tarjeta por taxón visible, y la nominal se marca "Nominal"

Cada fila que el dueño ve en el dashboard se convierte en una tarjeta: la
especie y cada uno de sus morphs. Si no vende la forma nominal, la apaga con su
interruptor y desaparece del sitio. Así el dashboard y el catálogo se
corresponden uno a uno, y el control queda en manos del dueño en vez de
depender de si existe un ejemplar sin morph asignado.

Esto **ya es el comportamiento del sitio para los morphs**: `buildListings`
agrupa por `(especie, primer morph)`, así que cada morph ya es su propia
tarjeta con su propia URL. Lo que cambia es que ahora también existirán las
tarjetas sin ejemplares detrás.

**La tarjeta de la especie a secas se marca como "Nominal"**, para distinguir la
forma base de sus variantes. Sin esa marca, "Laevis" y "Laevis 'Dairy Cow'" se
leen como si la primera fuera un resumen de la segunda.

La marca aparece en las tres superficies, con el mismo texto:

- **Sitio público:** en la tarjeta del catálogo y en la ficha.
- **Dashboard → Taxonomía**, pestaña Especies.
- **Dashboard → Sitio web → Animales**, nivel Especies.

**Se marca siempre, tenga morphs o no.** "Nominal" no es una comparación con
las variantes: es lo que esa tarjeta *es*, la forma base de la especie.
Mostrarla solo a veces la convertiría en una etiqueta condicional en vez de una
identidad, y el dueño tendría que deducir el tipo de tarjeta a partir de si
existen hermanas.

### El precio sale de `price_tiers` cuando no hay ejemplares

`Species.price_tiers` ya existe y `buildListings` ya lo consulta. Una especie sin
ejemplares puede mostrar precio de referencia en vez de un guion.

## Diseño

### Modelo y migración

```python
# Species y Morph
image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
```

Una sola revisión de Alembic con las dos columnas, siguiendo
`showpublictaxa01_add_show_public_to_species_and_morphs.py`. Nulo por defecto:
nada cambia al desplegar.

El campo es **público** (es la foto del catálogo), así que va en `SpeciesBase` /
`MorphBase` — a diferencia de `show_public`, que es administrativo. Es la
excepción deliberada al patrón, y por eso se anota aquí.

### Endpoint público

`GET /api/v1/public/species`

Devuelve las especies visibles, cada una con sus morphs visibles anidados.
Aplica **las mismas tres reglas de taxonomía** que el listado de animales:

1. el grupo raíz no está oculto (cascada por ancestros, vía `hidden_group_ids`),
2. `Species.show_public`,
3. y en cada morph anidado, `Morph.show_public`.

**No** aplica ninguna regla de disponibilidad: su propósito es exponer también lo
que no tiene existencias.

Campos por especie: `id`, `name`, `common_name`, `image`, `sale_format`,
`price_tiers`, `genus` (con su grupo), y `morphs[]` con `id`, `name`,
`description`, `image`.

Reutiliza los esquemas públicos que ya existen (`SpeciesResponse`,
`MorphResponse`) más el campo `image` nuevo. **No** expone `show_public` ni los
campos privados de cría.

### El sitio

- `getSpeciesCatalog()` en `src/lib/public-api.js`, con el mismo
  `next: { revalidate: 60 }` que el resto.
- `buildListings(animals, taxa)` recibe ahora también los taxones visibles:
  crea una entrada por cada uno y le adjunta sus ejemplares. Los conteos y
  precios siguen calculándose **solo con ejemplares disponibles**, como ya se
  corrigió.
- La foto de una entrada: la del primer ejemplar si existe; si no, la del morph;
  si no, la de la especie.
- Todos los consumidores de `getAnimals()` + `buildListings` deben pasar también
  los taxones: catálogo, home, ficha de especie, sitemap, buscador y favoritos.

### La banda de "Agotado"

En `OdCatalogCard`, una banda diagonal en una esquina de la imagen, en rojo, con
el texto "Agotado", cuando `card.soldOut`. Sustituye o acompaña al badge actual
según se vea mejor, pero debe leerse de un vistazo desde la rejilla.

Debe respetar el modo oscuro y no tapar el corazón de favoritos ni la barra de
acciones que aparece al pasar el cursor.

### El dashboard

Subida de imagen para especie y morph desde `TaxonDialog`, reusando
`uploadToCloudinary` — el mismo componente que ya sube fotos de animales y la
media del sitio. Una imagen por taxón, con vista previa y opción de quitarla.

## Pruebas

Backend:

1. `GET /public/species` devuelve una especie **sin ejemplares**.
2. Respeta las tres reglas de taxonomía: especie oculta, morph oculto y grupo
   oculto (en cascada) no aparecen.
3. **No** expone `show_public` ni campos privados de cría.

4. Una especie con morphs y otra sin morphs: la marca "Nominal" aparece en la
   tarjeta base de **ambas**, y nunca en la de un morph.

Sitio y dashboard: lint, build y verificación en vivo del catálogo, que no
requiere sesión. La marca "Nominal" se comprueba en el catálogo público; en
las dos pantallas del dashboard queda pendiente del acceso del dueño.

## Riesgos

| Riesgo | Mitigación |
| --- | --- |
| `buildListings` la usan seis superficies; invertirla puede romper alguna | Cambiar su firma obliga a visitar las seis; el build falla si falta una |
| Las 37 tarjetas salen sin foto hasta que el dueño las suba | Marcador de imagen decente; la subida llega en la misma entrega |
| Duplicar el agrupamiento en el servidor | Decisión explícita: el servidor solo devuelve taxonomía |
| La banda tapa controles de la tarjeta | Se verifica en vivo, en rejilla y en lista |
