# Generador de reels

`reel.py` arma reels verticales (1080x1920, 30 fps) a partir de videos y fotos,
cada escena con su texto. Es el generador de reels de Acento, separado de su
marca: colores, fuentes, logos, música y textos salen de
`marca/<nombre>/marca.json`. Por defecto usa `marca/canal1`.

Requisitos: Python 3 con Pillow, y `ffmpeg`/`ffprobe` en el PATH.

```bash
python3 video/reel.py guion.json salida.mp4                # marca Canal 1
MARCA=otra python3 video/reel.py guion.json salida.mp4     # otra carpeta de marca/
python3 video/kit_capcut.py kit/ [pauta.mp4]               # capas para editar a mano en CapCut
```

Junto al video sale `salida-portada.jpg` cuando el guion trae `portada`.

## Guion

Ver `ejemplo/guion.json`. Las rutas son relativas al guion.

| campo | qué es |
|---|---|
| `credito` | crédito del autor del material, va bajo el logo (siempre se da) |
| `transcripcion` | opcional: JSON de faster-whisper con tiempos por palabra (`[{"w": [[ini, fin, "palabra"], …]}, …]`) |
| `portada` | `{"titular", "foto"}`: primer cuadro y portada del reel en la cuadrícula del perfil |
| `escenas` | lista de escenas (abajo) |
| `publicidad` | opcional: `{"src": "pauta.mp4", "primera": 7, "cada": 20}`, franja que aparece varias veces |
| `volumen_musica` | opcional, 0.16 por defecto (solo si la marca tiene música) |

| tipo de escena | campos |
|---|---|
| `foto` | `src`, `dur`, `antetitulo`, `texto`, `bajada`, `tam` |
| `video` | `src`, `desde`, `hasta`, `subtitulos`, `antetitulo`, `texto`, `bajada`, `tam`, `pantalla` (`completa`/`recuadro`) |
| `cierre` | `dur`, `texto`, `bajada` (por defecto, los de `marca.json`) |

## Reglas de diseño (heredadas de los reels de Acento)

- Zonas seguras de Instagram: nada en los 120 px de arriba, nada desde y=1600
  (nombre de la cuenta y texto del post), nada a la derecha de x=940 desde
  y=1100 (botones). El script avisa si el titular baja de y=1400.
- Nunca se recorta ni se deforma un rostro: un video horizontal va completo en
  el recuadro central y el fondo es el mismo video desenfocado bajo un velo del
  color de fondo. Un video vertical va a pantalla completa.
- El video del recuadro nunca se opaca: el velo va solo sobre el fondo.
- La portada es obligatoria para que la miniatura del perfil nunca salga negra.

## La marca

`marca/canal1/marca.json` define:

- `colores`: `fondo` (degradados, velo, cierre), `acento` (barra del titular,
  caja del antetítulo, franjas del cierre), `texto_acento`, `panel` y `tinta`
  (portada), `bajada`, `subtitulos`.
- `fuentes`: un archivo `.ttf` por rol (`titular`, `entrada`, `credito`,
  `texto`) y `familia_subtitulos` (nombre de familia para ffmpeg). Se buscan en
  `marca/canal1/`, `marca/canal1/fuentes/` y `video/assets/fuentes/`.
- `logos`: `blanco` (sobre video y cierre) y `color` (portada), PNG con
  transparencia en `marca/canal1/`. Mientras no estén, se pinta el nombre.
- `musica`: archivo de la carpeta de la marca, o `null` (sin música).
- `cierre`: textos de la tarjeta final.

**Pendiente:** los colores, las fuentes y los logos de Canal 1 son
provisionales hasta tener su manual de marca.

## Publicarlo

Subir el mp4 y la portada a un almacenamiento público y crear la fila en
`publicaciones_redes` con la URL del video y, en la línea siguiente, la de la
portada en `imagen_url`. El gestor de redes (`supabase/functions/gestor-redes`)
lo publica como reel en Instagram y como video en Facebook (`prueba=true` para
un reel de prueba).
