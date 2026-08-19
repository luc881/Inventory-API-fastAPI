# Publicar y despublicar animales por especie y morph

Fecha: 2026-08-19
Estado: aprobado, pendiente de implementar

## Problema

Los productos tienen dos banderas independientes: `is_active` (¿seguimos
vendiéndolo?) y `show_online` (¿lo anunciamos?). Esa separación hace predecible
la pregunta "¿por qué esto no aparece en el sitio?": la respuesta está en dos
columnas de la misma fila.

Los animales no tienen equivalente. Un ejemplar aparece en el sitio si:

1. `Animal.status == available`, y
2. el grupo raíz de su género no está marcado `show_public = False`.

Las dos palancas están mal dimensionadas para publicar:

- **`status` es demasiado fino y es inventario**, no marketing. Marcar un
  ejemplar como reservado para que no se anuncie miente sobre el inventario.
- **`show_public` de grupo es demasiado grueso.** Medido sobre la base real:
  6 grupos raíz para 25 especies, repartidas Arácnidos 6, Reptiles 6,
  Insectos 5, Anfibios 3, Crustáceos 3, Miriápodos 2. Ocultar una sola especie
  hoy obliga a ocultar entre 2 y 6.

No existe forma de decir "esta especie está en cultivo pero todavía no la
anuncio" sin mentir sobre el inventario o esconder media taxonomía.

Además, para diagnosticar por qué algo no aparece hay que cruzar dos pantallas
distintas (el estado del ejemplar, y si el grupo raíz está oculto). Ninguna vista
las junta.

## Alcance

1. Bandera `show_public` en **especies** y en **morphs**.
2. Las rutas públicas la respetan, listado **y** detalle.
3. Pantalla nueva `Sitio web → Animales`, agrupada como el sitio agrupa, que
   responde "¿esto se ve?, y si no, ¿por qué?".
4. Los controles de visibilidad del grupo raíz, accesibles desde esa pantalla.

**Fuera de alcance, por decisión explícita:**

- **Bandera por ejemplar.** Mezclaría marketing con ciclo de vida, que es
  justo la separación que Product ya tiene bien resuelta. Un ejemplar no es un
  artículo: su presencia en el sitio depende de estar disponible para venta.
- Edición de precios, SKU o estado de venta desde la pantalla nueva.
- Filtros de marca/SKU: no existen en el dominio de animales.
- Reordenar el catálogo público.

## Decisiones tomadas

### El nombre es `show_public`, no `show_online`

`animal_groups.show_public` ya significa exactamente esto en el mismo árbol de
tablas. Importar el vocabulario de productos dejaría dos nombres para una misma
idea dentro del mismo dominio. La consistencia dentro del subárbol de animales
pesa más que la simetría con productos.

### Granularidad: especie **y** morph

El sitio arma sus tarjetas por morph, no por especie (`buildListings` en
`pharmatrack-web/src/sections/catalog/utils.js`). Una bandera solo de especie
no permitiría esconder un morph suelto.

Hay precedente en el repo: `husbandry_status` y `low_stock_threshold` ya existen
por especie **y** por morph, con la cría independiente entre ambos.

### Un morph oculto esconde el ejemplar completo

Medido sobre la base real: de 93 ejemplares, 27 tienen morphs y **7 tienen dos
morphs a la vez**. El caso no es hipotético.

Si el ejemplar A es "Papaya + Rubber Ducky" y se oculta *Papaya*, A desaparece
del sitio, incluso de la tarjeta de *Rubber Ducky*.

Razón: para un control de visibilidad, esconder de más es correcto y esconder de
menos es un error. Un ejemplar que lleva un morph oculto **sigue llevándolo**, y
su ficha lo mostraría. La alternativa ("ocultar solo si TODOS sus morphs están
ocultos") deja fugas visibles en el detalle.

El efecto secundario —el ejemplar también sale de la tarjeta del morph
visible— se hace evidente en la pantalla nueva, que muestra los conteos de
ejemplares detrás de cada renglón.

## Diseño

### Modelo y migración

```python
# Species y Morph
show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
```

Una sola revisión de Alembic que agrega ambas columnas, siguiendo
`migrations/versions/husbandrymorph01_add_husbandry_to_morphs.py`. Default `true`:
nada cambia de visibilidad al desplegar.

`Procfile` ya corre `alembic upgrade head`, así que se aplica sola.

### Regla de visibilidad pública

Un ejemplar aparece en el listado público si cumple **todo**:

1. `Animal.status == available`
2. El grupo raíz de su género no está en `hidden_group_ids(db)`
3. `Species.show_public` es verdadero
4. Ninguno de sus morphs tiene `show_public` falso

El detalle público (`GET /public/animals/{id}`) aplica las condiciones 2, 3 y 4.
La 1 no: hoy responde a propósito los reservados y vendidos con su status, para
que un enlace compartido diga "ya no disponible" en vez de dar 404. Ese
comportamiento se conserva.

### El filtro es opt-in — punto crítico

`_animals_query` (`src/pharmatrack/api/routes/animals.py:100-123`) **lo comparten
el listado admin y el público**. `exclude_group_ids` ya resuelve esto siendo un
parámetro que solo la ruta pública pasa.

Las condiciones 3 y 4 deben seguir el mismo patrón: un parámetro nuevo
(`exclude_hidden_taxa: bool = False`) que **solo las rutas públicas activan**.

Si el filtro se aplicara sin condición, las especies ocultas desaparecerían
también del dashboard, y el dueño no podría volver a publicarlas: quedarían
invisibles en la única pantalla desde la que se prenden. Es un bug silencioso y
difícil de diagnosticar, y por eso tiene prueba propia.

### Pantalla `Sitio web → Animales`

Ruta `/dashboard/site/animals`, junto a Media, Productos y Artículos.

Agrupada **por especie, con sus morphs anidados** — como la pestaña Especies de
Taxonomía, y como el sitio arma sus tarjetas. No un renglón por ejemplar: eso no
se parece a nada que vea un visitante.

Por renglón:

| Columna | Contenido |
| --- | --- |
| Nombre | Especie (científico + común) o morph anidado |
| Grupo | Grupo raíz al que pertenece |
| Disponibles | Ejemplares con `status = available` detrás de ese renglón |
| Precio | Rango mín–máx de esos ejemplares |
| En el sitio | Switch: escribe `species.show_public` en renglones de especie y `morphs.show_public` en renglones de morph |
| Estado | Vacío si se ve; si no, **el motivo** |

Los motivos posibles, en orden de precedencia:

1. `Grupo oculto` — el grupo raíz tiene `show_public = False`
2. `Especie oculta` — solo en renglones de morph, cuando la especie padre está apagada
3. `Sin ejemplares disponibles` — la bandera está prendida pero no hay qué vender

Esa columna es el corazón de la pantalla: es la pregunta que hoy obliga a ir a
comprobar al sitio.

Los conteos por especie y por morph **ya se calculan** en
`animal-taxonomy-view.jsx` (`availableBySpecies` / `availableByMorph`) y en
`cultivos-view.jsx`. Se reutilizan; no se inventa un tercer cálculo.

### Controles de grupo

Un panel compacto arriba de la tabla lista los grupos raíz con su casilla
`show_public`, reusando `updateAnimalGroup`, que ya existe.

Hoy viven solo en Taxonomía → Grupos, y son la causa más común de "no aparece y
no sé por qué". El panel no reemplaza esa pestaña: la refleja.

### Permisos

La pantalla escribe (`species.update`, `morphs.update`, `animalgroups.update`),
así que la ruta se protege con **`species.update`**, no con un permiso de
lectura. Precedente reciente: la pantalla de Productos se gateó primero con
`products.read` y era un error — se entraba a una página donde todo daba 403.

El ítem del menú se filtra con el mismo permiso. `allowedRoles` es un OR, así
que el grupo "Sitio web" ya lista sus permisos y solo hay que sumar el nuevo.

**La pantalla escribe tres recursos distintos y el guard solo puede exigir uno.**
`RoleBasedGuard` evalúa sus permisos con `.some()`, es decir un OR: no hay forma
de expresar "necesita los tres". Un rol con `species.update` pero sin
`morphs.update` entraría y recibiría 403 al mover el switch de un morph — el
mismo defecto que tuvo la pantalla de Productos.

Se resuelve en el cliente: cada switch se **deshabilita** si el usuario no trae
el permiso que ese renglón necesita (`morphs.update` para morphs,
`animalgroups.update` para el panel de grupos), con un texto que lo explique. El
backend sigue siendo la autoridad; esto solo evita ofrecer un control que va a
fallar.

## Pruebas

Backend, en el archivo de pruebas de animales públicos:

1. Una especie con `show_public = False` desaparece del listado público.
2. Un morph con `show_public = False` desaparece del listado público.
3. **Un ejemplar con dos morphs desaparece si uno solo está oculto.** Es la
   decisión no obvia del diseño; sin prueba, el primer refactor la revierte.
4. **El detalle por enlace directo respeta ambas banderas** (404). Sin esto hay
   fuga: el listado esconde pero la URL directa sigue sirviendo.
5. **El listado ADMIN sigue mostrando las especies y morphs ocultos.** Es la
   prueba del filtro opt-in; si falla, el dueño no puede volver a publicar.

Frontend: lint, build y revisión en vivo con el usuario.

## Riesgos

| Riesgo | Mitigación |
| --- | --- |
| El filtro se aplica también al admin y las especies ocultas se vuelven inalcanzables | Parámetro opt-in + prueba 5 |
| El detalle público olvida la bandera y filtra por URL directa | Prueba 4 |
| La regla de multi-morph se "simplifica" en un refactor futuro | Prueba 3 + la decisión documentada arriba |
| Confusión sobre dónde se edita la visibilidad del grupo (Taxonomía vs. pantalla nueva) | Ambas escriben por `updateAnimalGroup`; misma fuente de verdad, dos vistas |
