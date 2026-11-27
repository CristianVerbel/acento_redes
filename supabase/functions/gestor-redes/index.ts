// Gestor de redes de Canal 1
// ==========================
//
// Copiado del motor de redes de Acento Colombia (`publicador-co`): la misma
// cola (`publicaciones_redes`), el mismo ritmo por red y las mismas
// protecciones contra posts duplicados, sin la parte que redacta notas.
// Aquí las filas las pone el equipo (o `encolar`), y este motor las envía.
//
// Cuerpo (POST):
//   {}                       → VUELTA: envía a Instagram, Facebook y X lo que
//                              toca de la cola (cron cada 15 minutos).
//   { metricas: true }       → guarda los números de Instagram de los últimos
//                              14 días en `metricas_redes` (cron diario).
//   { limpiar_redes: true }  → borra del bucket «redes» los archivos de
//                              publicaciones ya terminadas (cron diario).
//   { encolar: {...} }       → crea las filas de una publicación, una por red:
//       texto, imagen_url (texto con una URL por línea, o lista), redes
//       (["instagram","facebook","x"]), textos ({ x: "…" } por red, opcional),
//       enlace, destacada, prueba, colaboradores, programada_para.
//
// Acceso: header X-Cron-Secret = secreto CRON_SECRET (pg_cron), o el JWT de
// un usuario que esté en `equipo_redes`.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import { metricasInstagram, publicarEnRed, type Red, redConfigurada } from "./redes.ts";

const SITIO = Deno.env.get("SITIO") || "canal1";
const BUCKET = Deno.env.get("BUCKET_REDES") || "redes";
const REDES: Red[] = ["x", "facebook", "instagram"];

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-cron-secret",
};

/**
 * Ritmo de cada red, aplicado al ENVIAR (no al encolar, así dos piezas que se
 * encolan a la vez no salen juntas). Lo destacado sale siempre en la vuelta
 * en que le toca. De lo demás, una por red y por vuelta, y solo si desde la
 * última publicación en esa red pasaron `HUECO_MIN` minutos. `TOPE_DIARIO`
 * cuenta las últimas 24 h (la API de Instagram permite 100 publicaciones en
 * 24 h; se deja margen). Lo que lleva más de `CADUCA_MIN` esperando se
 * descarta: ya no es noticia. Se ajustan con variables de entorno.
 */
const num = (k: string, d: number) => Number(Deno.env.get(k) || d);
const HUECO_MIN: Record<Red, number> = { x: num("HUECO_MIN_X", 20), facebook: num("HUECO_MIN_FACEBOOK", 14), instagram: num("HUECO_MIN_INSTAGRAM", 29) };
const NORMALES_POR_VUELTA: Record<Red, number> = { x: 1, facebook: 1, instagram: 1 };
const TOPE_DIARIO: Record<Red, number> = { x: num("TOPE_DIARIO_X", 60), facebook: num("TOPE_DIARIO_FACEBOOK", 80), instagram: num("TOPE_DIARIO_INSTAGRAM", 90) };
/** Límite duro en 24 h que nada pasa, ni lo destacado ni lo hecho a mano. */
const LIMITE_24H: Record<Red, number> = { x: 90, facebook: 150, instagram: 95 };
const CADUCA_MIN = num("CADUCA_MIN", 6 * 60);
/** Margen de reloj de la vuelta (el límite de Supabase es 150 s). */
const PLAZO_VUELTA_MS = 120_000;

function json(cuerpo: unknown, status = 200) {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json", ...CORS } });
}

// ── Acceso ──────────────────────────────────────────────────────────────────

function esCron(req: Request): boolean {
  const esperado = Deno.env.get("CRON_SECRET");
  if (!esperado) return false;
  const llegado = req.headers.get("x-cron-secret") ?? "";
  if (llegado.length !== esperado.length) return false;
  let diff = 0;
  for (let i = 0; i < llegado.length; i++) diff |= llegado.charCodeAt(i) ^ esperado.charCodeAt(i);
  return diff === 0;
}

async function autorizado(req: Request, supabase: SupabaseClient): Promise<boolean> {
  if (esCron(req)) return true;
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!token) return false;
  const { data } = await supabase.auth.getUser(token);
  if (!data?.user) return false;
  const { data: fila } = await supabase.from("equipo_redes").select("rol").eq("user_id", data.user.id).maybeSingle();
  return !!fila;
}

// ── Enviar con ritmo ────────────────────────────────────────────────────────

async function vaciarCola(supabase: SupabaseClient, hasta: number) {
  const ahora = Date.now();
  // Lo que lleva demasiado esperando ya no es noticia.
  await supabase.from("publicaciones_redes")
    .update({ estado: "descartada", error: "Caducó en la cola" })
    .eq("sitio", SITIO)
    .eq("estado", "pendiente")
    .eq("destacada", false)
    .lt("programada_para", new Date(ahora - CADUCA_MIN * 60_000).toISOString());

  const informe: Record<string, { enviadas: number; errores: number; sinCredenciales?: boolean; limite?: boolean }> = {};
  for (const red of REDES) {
    informe[red] = { enviadas: 0, errores: 0 };
    if (!redConfigurada(red)) {
      informe[red].sinCredenciales = true;
      continue;
    }

    const hace24h = new Date(ahora - 24 * 3600_000).toISOString();
    const { count: hoy } = await supabase.from("publicaciones_redes")
      .select("id", { count: "exact", head: true })
      .eq("sitio", SITIO).eq("red", red).eq("estado", "publicada").gte("publicada_at", hace24h);
    const { data: ultima } = await supabase.from("publicaciones_redes")
      .select("publicada_at")
      .eq("sitio", SITIO).eq("red", red).eq("estado", "publicada")
      .order("publicada_at", { ascending: false }).limit(1).maybeSingle();
    const desdeUltima = ultima?.publicada_at ? ahora - new Date(ultima.publicada_at).getTime() : Infinity;
    let normalesLibres = (hoy || 0) >= TOPE_DIARIO[red] || desdeUltima < HUECO_MIN[red] * 60_000
      ? 0
      : NORMALES_POR_VUELTA[red];

    const { data: pendientes } = await supabase.from("publicaciones_redes")
      .select("id, texto, imagen_url, intentos, destacada, prueba, id_externo, colaboradores")
      .eq("sitio", SITIO).eq("red", red).eq("estado", "pendiente")
      .lte("programada_para", new Date().toISOString())
      .order("destacada", { ascending: false })
      .order("programada_para", { ascending: true })
      .limit(10);

    let usadas = hoy || 0;
    for (const fila of pendientes || []) {
      if (Date.now() > hasta) break;
      if (usadas >= LIMITE_24H[red]) {
        informe[red].limite = true;
        break;
      }
      if (!fila.destacada) {
        if (normalesLibres <= 0) break;
        normalesLibres--;
      }
      // Se toma solo si sigue pendiente: dos vueltas a la vez no la envían dos veces.
      const { data: tomada } = await supabase.from("publicaciones_redes")
        .update({ estado: "publicando", intentos: fila.intentos + 1, tomada_at: new Date().toISOString() })
        .eq("id", fila.id).eq("estado", "pendiente")
        .select("id").maybeSingle();
      if (!tomada) continue;

      const enProceso = typeof fila.id_externo === "string" && fila.id_externo.startsWith("contenedor:")
        ? fila.id_externo.slice("contenedor:".length)
        : null;
      const r = await publicarEnRed(red, fila.texto, fila.imagen_url, { prueba: fila.prueba === true, contenedor: enProceso, colaboradores: fila.colaboradores });
      if (r.contenedor) {
        // Reel que Instagram sigue procesando: vuelve a la cola con su
        // contenedor, sin gastar un intento, y se revisa en dos minutos.
        await supabase.from("publicaciones_redes")
          .update({
            estado: "pendiente",
            intentos: fila.intentos,
            id_externo: `contenedor:${r.contenedor}`,
            error: r.error?.slice(0, 1000),
            programada_para: new Date(Date.now() + 2 * 60_000).toISOString(),
          })
          .eq("id", fila.id);
        continue;
      }
      if (r.ok) {
        informe[red].enviadas++;
        usadas++;
        await supabase.from("publicaciones_redes")
          .update({ estado: "publicada", id_externo: r.idExterno, publicada_at: new Date().toISOString(), error: null })
          .eq("id", fila.id);
      } else {
        informe[red].errores++;
        console.error(`${red}: ${r.error}`);
        const reintentar = !r.definitivo && fila.intentos + 1 < 3;
        await supabase.from("publicaciones_redes")
          .update({
            estado: reintentar ? "pendiente" : "error",
            error: r.error?.slice(0, 1000),
            programada_para: new Date(Date.now() + 10 * 60_000).toISOString(),
          })
          .eq("id", fila.id);
        // Credenciales malas: no tiene sentido seguir con esta red en esta vuelta.
        if (r.credenciales) break;
      }
    }
  }
  return informe;
}

/**
 * «publicando» colgado (una vuelta cortada a medias): pudo salir o no. Se
 * marca error (no se reintenta) para no arriesgar un post duplicado; queda a
 * la vista en la tabla.
 */
async function limpiarColgadas(supabase: SupabaseClient) {
  await supabase.from("publicaciones_redes")
    .update({ estado: "error", error: "Envío interrumpido: revisar si salió" })
    .eq("sitio", SITIO).eq("estado", "publicando")
    .lt("tomada_at", new Date(Date.now() - 15 * 60_000).toISOString());
}

// ── Encolar ─────────────────────────────────────────────────────────────────

interface PedidoEncolar {
  texto: string;
  imagen_url?: string | string[] | null;
  redes?: Red[];
  textos?: Partial<Record<Red, string>>;
  enlace?: string | null;
  destacada?: boolean;
  prueba?: boolean;
  colaboradores?: string[] | null;
  programada_para?: string | null;
}

async function encolar(supabase: SupabaseClient, p: PedidoEncolar) {
  if (!p?.texto?.trim()) throw new Error("Falta el texto");
  const redes = (p.redes?.length ? p.redes : ["instagram", "facebook"] as Red[]).filter((r): r is Red => REDES.includes(r));
  if (!redes.length) throw new Error("Ninguna red válida (instagram, facebook, x)");
  const imagen = Array.isArray(p.imagen_url) ? p.imagen_url.join("\n") : p.imagen_url || null;
  const grupo = crypto.randomUUID();
  const filas = redes.map((red) => ({
    sitio: SITIO,
    grupo,
    red,
    texto: p.textos?.[red] || p.texto,
    imagen_url: imagen,
    enlace: p.enlace || null,
    destacada: !!p.destacada,
    prueba: red === "instagram" && !!p.prueba,
    colaboradores: red === "instagram" ? p.colaboradores || null : null,
    programada_para: p.programada_para || new Date().toISOString(),
  }));
  const { data, error } = await supabase.from("publicaciones_redes").insert(filas).select("id, red");
  if (error) throw new Error(error.message);
  return { grupo, filas: data };
}

// ── Métricas y limpieza ─────────────────────────────────────────────────────

/**
 * Mide lo publicado en Instagram en los últimos 14 días (vistas, alcance,
 * guardados, compartidos y, en los reels, tiempo medio y % que se va en los
 * 3 primeros segundos). Una fila por publicación y día en `metricas_redes`.
 */
async function medirInstagram(supabase: SupabaseClient) {
  const desde = new Date(Date.now() - 14 * 24 * 3600_000).toISOString();
  const { data: filas } = await supabase.from("publicaciones_redes")
    .select("id, id_externo")
    .eq("sitio", SITIO).eq("red", "instagram").eq("estado", "publicada")
    .gte("publicada_at", desde).not("id_externo", "is", null)
    .order("publicada_at", { ascending: false }).limit(400);
  const fecha = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
  let medidas = 0;
  const errores: string[] = [];
  const lista = filas || [];
  for (let i = 0; i < lista.length; i += 6) {
    await Promise.all(lista.slice(i, i + 6).map(async (f) => {
      try {
        const m = await metricasInstagram(String(f.id_externo));
        const { error } = await supabase.from("metricas_redes").upsert({
          publicacion_id: f.id, sitio: SITIO, red: "instagram", fecha, tipo: m.tipo,
          vistas: m.vistas, alcance: m.alcance, guardados: m.guardados, compartidos: m.compartidos,
          tiempo_medio_ms: m.tiempoMedioMs, salto_3s: m.salto3s, datos: m.datos, medido_at: new Date().toISOString(),
        }, { onConflict: "publicacion_id,fecha" });
        if (error) throw new Error(error.message);
        medidas++;
      } catch (e) {
        if (errores.length < 5) errores.push(`${f.id_externo}: ${(e as Error).message.slice(0, 200)}`);
      }
    }));
  }
  return { publicaciones: lista.length, medidas, errores };
}

/**
 * Lo que solo se usó en redes no se guarda: las redes ya tienen su copia.
 * Dos días después de que una publicación termina, se borran del bucket sus
 * archivos, salvo los que usa una publicación que sigue en cola. Ver la
 * función SQL `archivos_redes_limpiables`.
 */
async function limpiarArchivosRedes(supabase: SupabaseClient) {
  const inicio = Date.now();
  let borrados = 0, revisadas = 0;
  while (Date.now() - inicio < 100_000) {
    const { data, error } = await supabase.rpc("archivos_redes_limpiables", { lim: 300, bucket: BUCKET });
    if (error) throw new Error(`archivos_redes_limpiables: ${error.message}`);
    const filas = (data || []) as Array<{ publicacion_id: string; ruta: string; accion: string }>;
    if (!filas.length) break;
    const borrar = [...new Set(filas.filter((f) => f.accion === "borrar").map((f) => f.ruta))];
    for (let i = 0; i < borrar.length; i += 100) {
      const { error: e } = await supabase.storage.from(BUCKET).remove(borrar.slice(i, i + 100));
      if (e) throw new Error(`No se pudieron borrar archivos: ${e.message}`);
    }
    borrados += borrar.length;
    const esperan = new Set(filas.filter((f) => f.accion === "esperar").map((f) => f.publicacion_id));
    const listas = [...new Set(filas.map((f) => f.publicacion_id))].filter((id) => !esperan.has(id));
    for (let i = 0; i < listas.length; i += 200) {
      await supabase.from("publicaciones_redes").update({ archivos_borrados: true }).in("id", listas.slice(i, i + 200));
    }
    revisadas += listas.length;
    if (!listas.length) break; // solo quedan archivos que esperan a la cola
  }
  // Las terminadas sin archivos en el bucket (enlaces externos) también se
  // marcan, para no revisarlas otra vez.
  const hace2d = new Date(Date.now() - 2 * 86400_000).toISOString();
  await supabase.from("publicaciones_redes").update({ archivos_borrados: true })
    .eq("archivos_borrados", false).in("estado", ["publicada", "descartada", "error"])
    .lt("created_at", hace2d).not("imagen_url", "like", `%/object/public/${BUCKET}/%`);
  return { borrados, revisadas };
}

// ── Entrada ─────────────────────────────────────────────────────────────────

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const inicio = Date.now();
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  if (!(await autorizado(req, supabase))) return json({ error: "No autorizado" }, 401);

  let cuerpo: Record<string, unknown> = {};
  try {
    cuerpo = await req.json();
  } catch { /* sin cuerpo: vuelta normal */ }

  try {
    if (cuerpo.encolar && typeof cuerpo.encolar === "object") {
      return json({ success: true, ...(await encolar(supabase, cuerpo.encolar as PedidoEncolar)) });
    }
    if (cuerpo.metricas === true) return json({ success: true, ...(await medirInstagram(supabase)) });
    if (cuerpo.limpiar_redes === true) return json({ success: true, ...(await limpiarArchivosRedes(supabase)) });

    await limpiarColgadas(supabase);
    const redes = await vaciarCola(supabase, inicio + PLAZO_VUELTA_MS);
    return json({ success: true, redes });
  } catch (e) {
    console.error((e as Error).message);
    return json({ success: false, error: (e as Error).message }, 500);
  }
});
