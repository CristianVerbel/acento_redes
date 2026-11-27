# Reels de Canal 1 en CapCut: guía del equipo

Este kit trae todo para editar a mano un reel con el mismo diseño de los
reels que arma `reel.py`. Todas las capas PNG y las pautas están en **1080x1920**:
se ponen **a pantalla completa, sin mover ni escalar**, y cada elemento ya
queda en su sitio.

## 1. Preparar CapCut (una sola vez)

1. Instalar las fuentes de la carpeta `fuentes/` (las de la marca). En CapCut:
   Texto > Fuente > Agregar fuente (o instalarlas en el computador y
   reiniciar CapCut). **Nunca otra fuente.**
2. Nuevo proyecto con relación de aspecto **9:16** (1080x1920, 30 fps).

## 2. Orden de las capas (de abajo hacia arriba)

| # | Capa | Archivo |
|---|---|---|
| 1 | Video o foto | el material |
| 2 | Degradado y barra del titular (solo si lleva titular) | `02_degradado_y_barra_titular.png` |
| 3 | Logo arriba (siempre) | `01_logo_arriba.png` |
| 4 | Textos: crédito, antetítulo, titular, subtítulos | texto de CapCut |
| 5 | Pauta (si hay) | `06_pauta_baja_verde.mp4` o `_alta_verde.mp4` |
| 6 | Guía de zonas (solo mientras edita) | `00_GUIA_zonas_seguras_BORRAR.png` |

Al inicio va la portada (0,6 s) y al final el cierre (`05_cierre_3s.mp4`).

## 3. Según el tipo de video

**Video vertical** (celular, 9:16): a pantalla completa, sin recortar caras.
Encima solo el logo, el crédito y la pauta. Si el video ya trae sus propios
subtítulos, use la pauta **alta** (`06_pauta_alta_verde.mp4`) para no
taparlos. **No oscurezca el video.**

**Video horizontal** (TV, 16:9):
1. Duplique el clip. El de abajo: escálelo hasta llenar la pantalla,
   Efectos > Desenfoque fuerte, y encima `03_velo_fondo_horizontal.png`.
2. El de arriba: ancho de 1040 px, con el borde de arriba en la línea
   «video horizontal (arriba)» de la guía (y=450). Va **limpio, sin velo**.
3. Subtítulos amarillos debajo, en la línea «subtítulos».
4. Antetítulo y titular en la línea «antetítulo / titular», con la capa 02.
5. Pauta **baja** (`06_pauta_baja_verde.mp4`), si el reel lleva pauta.

## 4. Textos

| Elemento | Fuente | Color | Dónde |
|---|---|---|---|
| Crédito («Video: @cuenta») | fuente de crédito, pequeña | blanco con borde negro | centrado, pegado bajo el logo |
| Antetítulo | fuente de entrada, MAYÚSCULAS | color `texto_acento` sobre caja del color `acento` (ver `marca.json`) | a la izquierda, sobre la línea del titular |
| Titular (máx. 3 líneas) | fuente de titular | blanco | a la izquierda, junto a la barra de color |
| Subtítulos (máx. 4 palabras) | fuente de entrada | color `subtitulos` con borde negro | centrados en la línea «subtítulos» |

Ningún texto pasa la línea vertical amarilla de la derecha (botones de
Instagram) ni baja de «límite inferior».

## 5. Pauta (cuando el reel lleva publicidad)

Debe salir **varias veces**: la primera hacia el segundo 7-9 y luego cada
20-25 segundos, nunca en los últimos 4 segundos. Cada vez dura 6 s.

- `06_pauta_baja_verde.mp4` / `_alta_verde.mp4`: pantalla completa, la
  pauta ya está en su sitio. Póngala encima y aplíquele Eliminar fondo >
  Recortar color (croma) sobre el verde.
- `06_pauta_franja_transparente.mov`: solo la tarjeta, con
  transparencia. Péguela a la izquierda (margen de 40 px) con el borde de
  arriba en la línea «pauta» de la guía.

## 6. Música

`07_musica.*` (si la marca tiene) de fondo, bien baja si hay voz (volumen 8-15 %),
con salida suave al final.

## 7. Portada (obligatoria, para que la miniatura nunca salga negra)

1. Foto real (nunca un texto), escalada para llenar el hueco de arriba de
   `04_portada_marco.png` (1080x690, centrado en la pantalla).
2. Encima el marco y el titular en la fuente de titular, color #131313,
   centrado en el panel gris.
3. Expórtela también como imagen: se sube como portada del reel.

## 8. Antes de exportar

- [ ] Borrar la capa de guía de zonas.
- [ ] Ninguna cara cortada ni deformada.
- [ ] Crédito del autor del video.
- [ ] Si lleva pauta, sale varias veces.
- [ ] Exportar en 1080p, 30 fps.

Cuando esté listo el proyecto con todo puesto, guárdelo en CapCut como
plantilla propia (Crear plantilla) para reutilizarlo.
