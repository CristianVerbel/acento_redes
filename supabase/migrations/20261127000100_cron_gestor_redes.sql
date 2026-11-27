-- Tareas programadas del gestor de redes
-- ======================================
--
-- Igual que en Acento: pg_cron llama a la función con pg_net, con el secreto
-- del cron guardado en el Vault. Antes de aplicar, guardar en el Vault:
--
--   select vault.create_secret('https://<ref>.supabase.co', 'url_proyecto');
--   select vault.create_secret('<clave anon del proyecto>', 'clave_anon');
--   select vault.create_secret('<el mismo valor que CRON_SECRET>', 'cron_secret');
--
-- y poner CRON_SECRET en los secretos de Edge Functions.
--
--   · cada 15 minutos (2, 17, 32, 47): una vuelta de la cola.
--   · cada día 6:05 (hora de Colombia, 11:05 UTC): métricas de Instagram.
--   · cada día 4:20 (9:20 UTC): limpieza de archivos ya publicados.
--
-- Se puede aplicar más de una vez.

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

CREATE OR REPLACE FUNCTION public.llamar_gestor_redes(cuerpo jsonb)
RETURNS bigint LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = 'url_proyecto' LIMIT 1)
           || '/functions/v1/gestor-redes',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || COALESCE((SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = 'clave_anon' LIMIT 1), ''),
      'X-Cron-Secret', COALESCE((SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = 'cron_secret' LIMIT 1), '')
    ),
    body := cuerpo,
    timeout_milliseconds := 150000
  );
$$;
REVOKE ALL ON FUNCTION public.llamar_gestor_redes(jsonb) FROM public, anon, authenticated;

SELECT cron.unschedule(jobname) FROM cron.job
 WHERE jobname IN ('gestor-redes', 'gestor-redes-metricas', 'gestor-redes-limpieza');

SELECT cron.schedule('gestor-redes', '2,17,32,47 * * * *',
  $$ SELECT public.llamar_gestor_redes('{"triggered_by":"cron"}'::jsonb) $$);
SELECT cron.schedule('gestor-redes-metricas', '5 11 * * *',
  $$ SELECT public.llamar_gestor_redes('{"metricas":true}'::jsonb) $$);
SELECT cron.schedule('gestor-redes-limpieza', '20 9 * * *',
  $$ SELECT public.llamar_gestor_redes('{"limpiar_redes":true}'::jsonb) $$);
