-- Gestor de redes de Canal 1
-- ==========================
--
-- La cola de publicaciones y las métricas, copiadas del motor de redes de
-- Acento Colombia (`publicaciones_redes`, `metricas_redes`) para un proyecto
-- de Supabase propio. Diferencias con el original:
--   · No depende de `articles`: una fila es una pieza para una red; las filas
--     de la misma pieza comparten `grupo`. `enlace` guarda la nota de la web.
--   · El acceso del equipo va por `equipo_redes` (sin `editorial_roles`).
--   · `tomada_at` marca cuándo una vuelta tomó la fila (para las colgadas).
--
-- Se puede aplicar más de una vez.

-- ── Equipo ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.equipo_redes (
  user_id    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  rol        TEXT NOT NULL DEFAULT 'editor' CHECK (rol IN ('admin', 'editor')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.equipo_redes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.es_equipo_redes()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.equipo_redes WHERE user_id = auth.uid());
$$;

DROP POLICY IF EXISTS "Equipo: se ve a sí mismo" ON public.equipo_redes;
CREATE POLICY "Equipo: se ve a sí mismo" ON public.equipo_redes
  FOR SELECT USING (public.es_equipo_redes());

-- ── Cola ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.publicaciones_redes (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sitio            TEXT NOT NULL DEFAULT 'canal1',
  grupo            UUID NOT NULL DEFAULT gen_random_uuid(),
  red              TEXT NOT NULL CHECK (red IN ('instagram', 'facebook', 'x')),
  -- En Instagram, «[HISTORIA]» al comienzo publica una historia (sin texto).
  texto            TEXT NOT NULL,
  -- Una URL por línea: varias imágenes = carrusel de Instagram (Facebook y X
  -- usan la primera). Si la primera es un .mp4/.mov es un reel, y la
  -- siguiente imagen, su portada.
  imagen_url       TEXT,
  enlace           TEXT,
  destacada        BOOLEAN NOT NULL DEFAULT false,
  -- Reel de prueba de Instagram: solo lo ve gente que no sigue la cuenta.
  prueba           BOOLEAN NOT NULL DEFAULT false,
  -- Cuentas de Instagram invitadas a colaborar (sin @, hasta 3).
  colaboradores    TEXT[],
  programada_para  TIMESTAMPTZ NOT NULL DEFAULT now(),
  estado           TEXT NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente', 'publicando', 'publicada', 'error', 'descartada')),
  intentos         INTEGER NOT NULL DEFAULT 0,
  id_externo       TEXT,
  error            TEXT,
  tomada_at        TIMESTAMPTZ,
  publicada_at     TIMESTAMPTZ,
  archivos_borrados BOOLEAN NOT NULL DEFAULT false,
  creada_por       UUID DEFAULT auth.uid(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS publicaciones_redes_cola_idx
  ON public.publicaciones_redes (sitio, red, programada_para)
  WHERE estado = 'pendiente';
CREATE INDEX IF NOT EXISTS publicaciones_redes_grupo_idx
  ON public.publicaciones_redes (grupo);
CREATE INDEX IF NOT EXISTS publicaciones_redes_limpieza_idx
  ON public.publicaciones_redes (created_at)
  WHERE NOT archivos_borrados;

ALTER TABLE public.publicaciones_redes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Publicaciones en redes: el equipo" ON public.publicaciones_redes;
CREATE POLICY "Publicaciones en redes: el equipo" ON public.publicaciones_redes
  FOR ALL USING (public.es_equipo_redes()) WITH CHECK (public.es_equipo_redes());

-- ── Métricas ────────────────────────────────────────────────────────────────
--
-- Una medición por publicación y día (hora de Colombia). `datos` guarda la
-- respuesta completa de Meta; las columnas son las que se comparan.

CREATE TABLE IF NOT EXISTS public.metricas_redes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  publicacion_id uuid NOT NULL REFERENCES public.publicaciones_redes(id) ON DELETE CASCADE,
  sitio text NOT NULL,
  red text NOT NULL,
  fecha date NOT NULL,
  tipo text,                      -- REELS, FEED (carrusel o foto)
  vistas integer,
  alcance integer,
  guardados integer,
  compartidos integer,
  tiempo_medio_ms integer,        -- reels: tiempo medio que se quedan, en ms
  salto_3s numeric,               -- reels: % que se va en los 3 primeros segundos
  datos jsonb,
  medido_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (publicacion_id, fecha)
);
ALTER TABLE public.metricas_redes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Métricas: el equipo las ve" ON public.metricas_redes;
CREATE POLICY "Métricas: el equipo las ve" ON public.metricas_redes
  FOR SELECT USING (public.es_equipo_redes());

-- ── Archivos solo de redes ──────────────────────────────────────────────────
--
-- Bucket público donde el equipo sube videos, portadas e imágenes para redes.
-- Dos días después de que una publicación termina, sus archivos se borran,
-- salvo que los use una publicación que sigue en cola.

INSERT INTO storage.buckets (id, name, public)
VALUES ('redes', 'redes', true)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "Redes: el equipo sube" ON storage.objects;
CREATE POLICY "Redes: el equipo sube" ON storage.objects
  FOR INSERT WITH CHECK (bucket_id = 'redes' AND public.es_equipo_redes());

CREATE OR REPLACE FUNCTION public.archivos_redes_limpiables(lim integer DEFAULT 300, bucket text DEFAULT 'redes')
RETURNS TABLE (publicacion_id uuid, ruta text, accion text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  WITH lote AS (
    SELECT p.id, p.imagen_url
    FROM publicaciones_redes p
    WHERE NOT p.archivos_borrados
      AND p.estado IN ('publicada', 'descartada', 'error')
      AND coalesce(p.publicada_at, p.programada_para, p.created_at) < now() - interval '2 days'
    ORDER BY p.created_at
    LIMIT lim
  ),
  urls AS (
    SELECT l.id, substring(trim(u) FROM '/storage/v1/object/public/' || bucket || '/(.*)$') AS ruta, trim(u) AS url
    FROM lote l, regexp_split_to_table(coalesce(l.imagen_url, ''), E'\n') AS u
    WHERE trim(u) LIKE '%/storage/v1/object/public/' || bucket || '/%'
  ),
  cola AS (
    SELECT trim(u) AS url
    FROM publicaciones_redes q, regexp_split_to_table(coalesce(q.imagen_url, ''), E'\n') AS u
    WHERE q.estado NOT IN ('publicada', 'descartada', 'error')
  )
  SELECT u.id, u.ruta,
         CASE WHEN EXISTS (SELECT 1 FROM cola c WHERE c.url = u.url) THEN 'esperar' ELSE 'borrar' END
  FROM urls u;
$$;

REVOKE ALL ON FUNCTION public.archivos_redes_limpiables(integer, text) FROM public, anon, authenticated;
