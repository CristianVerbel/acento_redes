# acento_redes

App de generación y publicación de posts de redes sociales, adaptada para
**Canal 1** (canal1.com.co).

Parte de dos piezas de Acento Colombia (`CristianVerbel/acentocolombia`),
copiadas aquí y separadas de la marca Acento:

| Carpeta | Qué es | De dónde viene |
|---|---|---|
| `video/` | Generador de reels 1080x1920 (Python + ffmpeg) y kit para CapCut | `scripts/reels/` |
| `marca/canal1/` | Colores, fuentes, logos, música y textos de Canal 1 | nuevo |
| `supabase/` | Gestor de redes: cola de publicaciones, envío con ritmo a Instagram, Facebook y X, métricas y limpieza | `supabase/functions/publicador-co/` (`redes.ts` y la cola) |

Lo de Acento que **no** se copió: la redacción automática de notas con IA,
los carruseles generados a partir de notas, la pauta de Tamix, la música y los
logos de Acento.

## Flujo

1. Se arma el reel: `python3 video/reel.py guion.json salida/reel.mp4`
   (ver `video/README.md`).
2. Se suben el mp4 y la portada al bucket `redes` de Supabase.
3. Se encola la publicación (una fila por red en `publicaciones_redes`),
   insertando las filas o llamando a la función:
   ```json
   POST /functions/v1/gestor-redes
   { "encolar": { "texto": "…", "imagen_url": ["…/reel.mp4", "…/reel-portada.jpg"],
                  "redes": ["instagram", "facebook"], "destacada": false } }
   ```
4. Cada 15 minutos el gestor envía lo que toca, una pieza por red y por vuelta,
   respetando el hueco mínimo entre posts y el tope diario de cada red. Lo
   destacado sale en la primera vuelta. Lo que no salió en 6 horas caduca.

Una fila de `publicaciones_redes` es:

- **imagen**: una URL en `imagen_url`.
- **carrusel** de Instagram: varias URL, una por línea (Facebook y X usan la primera).
- **reel**: la primera URL es un `.mp4`/`.mov`; la siguiente imagen es la portada.
  `prueba = true` lo publica como reel de prueba (solo para no seguidores).
- **historia** de Instagram: texto que empieza por `[HISTORIA]`.
- `colaboradores`: hasta 3 cuentas de Instagram invitadas a colaborar.

## Puesta en marcha (Supabase)

Va en un proyecto de Supabase propio para Canal 1.

1. Aplicar `supabase/migrations/` (tablas, bucket `redes`, cron).
   Antes de la de cron, guardar en el Vault `url_proyecto`, `clave_anon` y
   `cron_secret` (ver el comentario de la migración).
2. Desplegar la función: `supabase functions deploy gestor-redes --no-verify-jwt`.
3. Secretos de Edge Functions:
   - `CRON_SECRET` (el mismo del Vault).
   - Meta: `META_PAGE_ID`, `META_PAGE_TOKEN` (token de página de larga
     duración), `META_IG_USER_ID`, opcional `META_GRAPH_VERSION`.
   - X: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`.
   - Opcionales: `HUECO_MIN_*`, `TOPE_DIARIO_*`, `CADUCA_MIN`.
   Cada red se enciende sola cuando tiene sus credenciales.
4. Dar de alta al equipo: `insert into equipo_redes (user_id, rol) values ('<uuid>', 'admin');`

## Pendiente para Canal 1

- Manual de marca: colores, tipografías y logos (PNG blanco y a color) en
  `marca/canal1/`. Los valores actuales son provisionales.
- Música propia (opcional) y, si aplica, la pauta de sus anunciantes.
- Cuentas de Meta y X de Canal 1 con acceso a la API.
