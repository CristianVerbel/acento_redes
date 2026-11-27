// Publicación en Instagram, Facebook y X con las APIs oficiales.
//
// Copiado del motor de Acento Colombia (publicador-co/redes.ts), para las
// cuentas de Canal 1. Va en su propio proyecto de Supabase, así que los
// secretos no llevan sufijo.
//
// Cada red se enciende sola cuando sus credenciales están en los secretos de
// Edge Functions; si faltan, sus publicaciones se quedan en la cola
// (`publicaciones_redes`, estado «pendiente») y la vuelta sigue.
//
// Secretos:
//   META_PAGE_ID, META_PAGE_TOKEN → Facebook (página). Token de página de larga duración.
//   META_IG_USER_ID               → Instagram (cuenta profesional vinculada a esa página;
//                                   usa el mismo META_PAGE_TOKEN).
//   X_API_KEY, X_API_SECRET,
//   X_ACCESS_TOKEN, X_ACCESS_SECRET → X, OAuth 1.0a de la cuenta que publica.
//   META_GRAPH_VERSION (opcional) → p. ej. v23.0

export type Red = "instagram" | "facebook" | "x";

export interface Resultado {
  ok: boolean;
  idExterno?: string;
  error?: string;
  /** El error no se arregla reintentando (credenciales, contenido rechazado). */
  definitivo?: boolean;
  /** Credenciales inválidas o sin permiso: nada de esta red saldrá hasta arreglarlas. */
  credenciales?: boolean;
  /**
   * Reel que Instagram sigue procesando (un vídeo tarda uno o dos minutos):
   * la fila vuelve a la cola con este contenedor y la siguiente vuelta lo
   * publica cuando esté listo, sin crearlo otra vez.
   */
  contenedor?: string;
}

export interface Opciones {
  /** Reel de prueba de Instagram: solo lo ve gente que no sigue la cuenta. */
  prueba?: boolean;
  /** Contenedor de un reel que una vuelta anterior dejó procesándose. */
  contenedor?: string | null;
  /** Cuentas de Instagram invitadas a colaborar (sin @, hasta 3). Cada una
   *  recibe la invitación y, si la acepta, la publicación sale también en su
   *  perfil. Solo para Instagram. */
  colaboradores?: string[] | null;
}

/** Campo `collaborators` de la API: hasta 3 usuarios, sin @. */
function camposColaboradores(op: Opciones): Record<string, string> {
  const lista = (op.colaboradores || []).map((u) => u.trim().replace(/^@/, "")).filter(Boolean).slice(0, 3);
  return lista.length ? { collaborators: JSON.stringify(lista) } : {};
}

/** Un reel: la URL apunta a un vídeo y no a una imagen. */
export function esVideo(url: string): boolean {
  return /\.(mp4|mov)(\?|$)/i.test(url);
}

const env = (k: string) => Deno.env.get(k) || "";

export function redConfigurada(red: Red): boolean {
  if (red === "facebook") return !!(env("META_PAGE_ID") && env("META_PAGE_TOKEN"));
  if (red === "instagram") return !!(env("META_IG_USER_ID") && env("META_PAGE_TOKEN"));
  return !!(env("X_API_KEY") && env("X_API_SECRET") && env("X_ACCESS_TOKEN") && env("X_ACCESS_SECRET"));
}

// ── Meta ────────────────────────────────────────────────────────────────────

function graph(ruta: string): string {
  return `https://graph.facebook.com/${env("META_GRAPH_VERSION") || "v23.0"}/${ruta}`;
}

async function postGraph(ruta: string, campos: Record<string, string>) {
  return await postGraphConToken(env("META_PAGE_TOKEN"), ruta, campos);
}

async function postGraphConToken(token: string, ruta: string, campos: Record<string, string>) {
  const cuerpo = new URLSearchParams({ ...campos, access_token: token });
  const resp = await fetch(graph(ruta), { method: "POST", body: cuerpo, signal: AbortSignal.timeout(25_000) });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.error) {
    const e = data.error || {};
    // 190 = token inválido o vencido; 10 / 200-299 = permisos.
    const credenciales = e.code === 190 || e.code === 10 || (e.code >= 200 && e.code < 300);
    throw Object.assign(
      new Error(`Meta ${resp.status} (código ${e.code ?? "?"}/${e.error_subcode ?? "-"}): ${e.message || JSON.stringify(data)}`),
      { definitivo: credenciales, credenciales },
    );
  }
  return data;
}

async function estadoContenedor(id: string): Promise<string> {
  const url = `${graph(id)}?fields=status_code&access_token=${encodeURIComponent(env("META_PAGE_TOKEN"))}`;
  const resp = await fetch(url, { signal: AbortSignal.timeout(15_000) });
  const data = await resp.json().catch(() => ({}));
  return data?.status_code || "DESCONOCIDO";
}

/**
 * Token de la página. Si el secreto guardado es el del usuario del sistema (y
 * no el de la página), Facebook rechaza la publicación («publish_actions»):
 * se pide a Meta el token de la página con el que haya y se usa ese.
 */
let tokenPaginaCache: string | null = null;
async function tokenPagina(): Promise<string> {
  if (tokenPaginaCache) return tokenPaginaCache;
  const base = env("META_PAGE_TOKEN");
  try {
    const url = `${graph(env("META_PAGE_ID"))}?fields=access_token&access_token=${encodeURIComponent(base)}`;
    const data = await (await fetch(url, { signal: AbortSignal.timeout(15_000) })).json();
    tokenPaginaCache = typeof data?.access_token === "string" && data.access_token ? data.access_token : base;
  } catch {
    tokenPaginaCache = base;
  }
  return tokenPaginaCache ?? base;
}

async function publicarFacebook(texto: string, imagenUrl: string): Promise<Resultado> {
  // Foto con texto: en el feed rinde mucho más que un enlace, y no depende de
  // que la página tenga su vista previa (OG) lista en el momento.
  const data = await postGraphConToken(await tokenPagina(), `${env("META_PAGE_ID")}/photos`, { url: imagenUrl, message: texto });
  return { ok: true, idExterno: data.post_id || data.id };
}

/**
 * Publica un contenedor ya listo. Instagram a veces publica el post y aun así
 * responde con error (p. ej. 9007, «Media ID is not available»). Si la fila
 * se reintentara, saldría un post duplicado: antes de dar el fallo se mira si
 * el contenedor quedó PUBLISHED y, si es así, se toma el post más reciente.
 */
async function publicarContenedorIG(igId: string, creacion: string): Promise<string> {
  try {
    return (await postGraph(`${igId}/media_publish`, { creation_id: creacion })).id;
  } catch (e) {
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      if (await estadoContenedor(creacion) === "PUBLISHED") {
        const url = `${graph(`${igId}/media`)}?fields=id&limit=1&access_token=${encodeURIComponent(env("META_PAGE_TOKEN"))}`;
        const data = await (await fetch(url, { signal: AbortSignal.timeout(15_000) })).json().catch(() => ({}));
        return data?.data?.[0]?.id || `publicado:${creacion}`;
      }
    }
    throw e;
  }
}

/** Espera a que Instagram termine de procesar un contenedor. null si quedó listo; si no, el estado. */
async function esperarContenedor(id: string): Promise<string | null> {
  let estado = "";
  for (let intento = 0; intento < 8; intento++) {
    estado = await estadoContenedor(id);
    if (estado === "FINISHED") return null;
    if (estado === "ERROR" || estado === "EXPIRED") return estado;
    await new Promise((r) => setTimeout(r, 2500));
  }
  return null; // Sin respuesta clara: se intenta publicar igual, como antes.
}

/**
 * Instagram solo acepta JPEG por API: las diapositivas ya salen en JPEG. Con
 * una imagen, post simple; con 2 a 10, carrusel: un contenedor hijo por
 * imagen (is_carousel_item), uno padre CAROUSEL con los hijos y el texto, y
 * se publica el padre cuando está listo.
 *
 * Ocultar el número de «me gusta»: la API de publicación no lo permite (ni al
 * crear el contenedor ni después: en un medio publicado solo se puede cambiar
 * comment_enabled). Se hace a mano en la app, o con el ajuste de la cuenta.
 */
async function publicarInstagram(texto: string, imagenes: string[], op: Opciones = {}): Promise<Resultado> {
  const igId = env("META_IG_USER_ID");
  let creacion: string;
  if (imagenes.length === 1) {
    creacion = (await postGraph(`${igId}/media`, { image_url: imagenes[0], caption: texto, ...camposColaboradores(op) })).id;
  } else {
    const hijos: string[] = [];
    for (const url of imagenes.slice(0, 10)) {
      hijos.push((await postGraph(`${igId}/media`, { image_url: url, is_carousel_item: "true" })).id);
    }
    for (const hijo of hijos) {
      const fallo = await esperarContenedor(hijo);
      if (fallo) return { ok: false, error: `Instagram rechazó una imagen del carrusel (${fallo})`, definitivo: true };
    }
    creacion = (await postGraph(`${igId}/media`, { media_type: "CAROUSEL", children: hijos.join(","), caption: texto, ...camposColaboradores(op) })).id;
  }
  const fallo = await esperarContenedor(creacion);
  if (fallo) return { ok: false, error: `Instagram rechazó la publicación (${fallo})`, definitivo: true };
  return { ok: true, idExterno: await publicarContenedorIG(igId, creacion) };
}

/**
 * Historia: un contenedor STORIES con una imagen 9:16 (sin texto: las
 * historias no llevan pie). Se marca poniendo «[HISTORIA]» al comienzo del
 * texto de la fila de Instagram.
 */
async function publicarHistoria(imagen: string): Promise<Resultado> {
  const igId = env("META_IG_USER_ID");
  const creacion = (await postGraph(`${igId}/media`, { image_url: imagen, media_type: "STORIES" })).id;
  const fallo = await esperarContenedor(creacion);
  if (fallo) return { ok: false, error: `Instagram rechazó la historia (${fallo})`, definitivo: true };
  return { ok: true, idExterno: await publicarContenedorIG(igId, creacion) };
}

/**
 * Reel: un contenedor REELS con el vídeo (Instagram lo descarga de la URL),
 * y se publica cuando termina de procesarlo. Un vídeo tarda más que una
 * imagen: si a los ~40 s no está, la fila vuelve a la cola con el contenedor
 * (`Resultado.contenedor`) y la siguiente vuelta lo publica.
 *
 * Reel de prueba (`prueba`): `trial_params` con graduación manual y sin pasar
 * al feed. Instagram lo enseña solo a quien no sigue la cuenta; sirve para
 * probar arranques distintos del mismo vídeo y comparar cuántos se quedan.
 */
async function publicarReel(texto: string, video: string, portada: string | undefined, op: Opciones): Promise<Resultado> {
  const igId = env("META_IG_USER_ID");
  let contenedor = op.contenedor || "";
  if (!contenedor) {
    const campos: Record<string, string> = { media_type: "REELS", video_url: video, caption: texto, ...camposColaboradores(op) };
    if (portada) campos.cover_url = portada;
    if (op.prueba) {
      campos.share_to_feed = "false";
      campos.trial_params = JSON.stringify({ graduation_strategy: "MANUAL" });
    } else {
      campos.share_to_feed = "true";
    }
    contenedor = (await postGraph(`${igId}/media`, campos)).id;
  }
  let estado = "";
  for (let intento = 0; intento < 8; intento++) {
    estado = await estadoContenedor(contenedor);
    if (estado === "FINISHED") {
      return { ok: true, idExterno: await publicarContenedorIG(igId, contenedor) };
    }
    if (estado === "ERROR" || estado === "EXPIRED") {
      return { ok: false, error: `Instagram rechazó el vídeo (${estado}): MP4 o MOV, H.264 y AAC, vertical 9:16, de 3 s a 15 min`, definitivo: true };
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
  return { ok: false, error: `Instagram sigue procesando el vídeo (${estado || "sin estado"})`, contenedor };
}

/** Vídeo en la página de Facebook: Facebook lo descarga de la URL y lo procesa por su cuenta. */
async function publicarVideoFacebook(texto: string, video: string): Promise<Resultado> {
  const data = await postGraphConToken(await tokenPagina(), `${env("META_PAGE_ID")}/videos`, { file_url: video, description: texto });
  return { ok: true, idExterno: data.id };
}

// ── Métricas ────────────────────────────────────────────────────────────────

export interface Metricas {
  tipo: string | null;
  vistas: number | null;
  alcance: number | null;
  guardados: number | null;
  compartidos: number | null;
  tiempoMedioMs: number | null;
  salto3s: number | null;
  datos: Record<string, unknown>;
}

async function getGraph(ruta: string, params: Record<string, string>) {
  const q = new URLSearchParams({ ...params, access_token: env("META_PAGE_TOKEN") });
  const resp = await fetch(`${graph(ruta)}?${q}`, { signal: AbortSignal.timeout(15_000) });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.error) {
    const e = data.error || {};
    throw new Error(`Meta ${resp.status} (código ${e.code ?? "?"}): ${e.message || JSON.stringify(data)}`);
  }
  return data;
}

/**
 * Números de una publicación de Instagram. A los reels se les piden además
 * el tiempo medio de visualización y el % que se va en los 3 primeros
 * segundos (la nota del arranque). Si Meta no reconoce alguna métrica, se
 * vuelve a pedir sin ella en vez de perder todas.
 */
export async function metricasInstagram(mediaId: string): Promise<Metricas> {
  const media = await getGraph(mediaId, { fields: "media_product_type,media_type" });
  const tipo = media.media_product_type || media.media_type || null;
  const base = ["views", "reach", "saved", "shares"];
  const reel = tipo === "REELS" ? ["ig_reels_avg_watch_time", "reels_skip_rate"] : [];
  let pedidas = [...base, ...reel];
  let data: { data?: { name: string; values?: { value: number }[]; total_value?: { value: number } }[] } = {};
  for (let intento = 0; intento < 3; intento++) {
    try {
      data = await getGraph(`${mediaId}/insights`, { metric: pedidas.join(",") });
      break;
    } catch (e) {
      const sobra = pedidas.find((m) => (e as Error).message.includes(m));
      if (!sobra) throw e;
      pedidas = pedidas.filter((m) => m !== sobra);
    }
  }
  const valor = (nombre: string): number | null => {
    const m = data.data?.find((x) => x.name === nombre);
    const v = m?.total_value?.value ?? m?.values?.[0]?.value;
    return typeof v === "number" ? v : null;
  };
  return {
    tipo,
    vistas: valor("views"),
    alcance: valor("reach"),
    guardados: valor("saved"),
    compartidos: valor("shares"),
    tiempoMedioMs: valor("ig_reels_avg_watch_time"),
    salto3s: valor("reels_skip_rate"),
    datos: data as Record<string, unknown>,
  };
}

// ── X (OAuth 1.0a) ──────────────────────────────────────────────────────────

function pct(s: string): string {
  return encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
}

async function hmacSha1(clave: string, texto: string): Promise<string> {
  const k = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(clave), { name: "HMAC", hash: "SHA-1" }, false, ["sign"],
  );
  const firma = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(texto));
  return btoa(String.fromCharCode(...new Uint8Array(firma)));
}

/** Encabezado Authorization OAuth 1.0a. El cuerpo JSON o multipart no se firma. */
async function cabeceraOAuth(metodo: string, url: string): Promise<string> {
  const u = new URL(url);
  const oauth: Record<string, string> = {
    oauth_consumer_key: env("X_API_KEY"),
    oauth_nonce: crypto.randomUUID().replace(/-/g, ""),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
    oauth_token: env("X_ACCESS_TOKEN"),
    oauth_version: "1.0",
  };
  const params: [string, string][] = [...Object.entries(oauth), ...u.searchParams.entries()];
  const normalizados = params
    .map(([k, v]) => [pct(k), pct(v)])
    .sort(([a, x], [b, y]) => (a === b ? (x < y ? -1 : 1) : a < b ? -1 : 1))
    .map(([k, v]) => `${k}=${v}`)
    .join("&");
  const base = `${metodo.toUpperCase()}&${pct(u.origin + u.pathname)}&${pct(normalizados)}`;
  const clave = `${pct(env("X_API_SECRET"))}&${pct(env("X_ACCESS_SECRET"))}`;
  oauth.oauth_signature = await hmacSha1(clave, base);
  return "OAuth " + Object.entries(oauth).map(([k, v]) => `${pct(k)}="${pct(v)}"`).join(", ");
}

async function subirImagenX(imagenUrl: string): Promise<string | null> {
  try {
    const img = await fetch(imagenUrl, { signal: AbortSignal.timeout(15_000) });
    if (!img.ok) return null;
    const bytes = new Uint8Array(await img.arrayBuffer());
    const url = "https://api.x.com/2/media/upload";
    const form = new FormData();
    form.append("media", new Blob([bytes], { type: "image/jpeg" }), "tarjeta.jpg");
    form.append("media_category", "tweet_image");
    const resp = await fetch(url, {
      method: "POST",
      headers: { Authorization: await cabeceraOAuth("POST", url) },
      body: form,
      signal: AbortSignal.timeout(25_000),
    });
    const data = await resp.json().catch(() => ({}));
    const id = data?.data?.id || data?.media_id_string;
    if (!resp.ok || !id) {
      console.warn("X: no se pudo subir la imagen, se publica sin ella:", resp.status, JSON.stringify(data).slice(0, 300));
      return null;
    }
    return String(id);
  } catch (e) {
    console.warn("X: error subiendo imagen:", (e as Error).message);
    return null;
  }
}

async function publicarX(texto: string, imagenUrl: string | null): Promise<Resultado> {
  const mediaId = imagenUrl ? await subirImagenX(imagenUrl) : null;
  const url = "https://api.x.com/2/tweets";
  const resp = await fetch(url, {
    method: "POST",
    headers: { Authorization: await cabeceraOAuth("POST", url), "Content-Type": "application/json" },
    body: JSON.stringify(mediaId ? { text: texto, media: { media_ids: [mediaId] } } : { text: texto }),
    signal: AbortSignal.timeout(20_000),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data?.data?.id) {
    // 401: credenciales. 403: plan sin escritura o contenido rechazado
    // (p. ej. texto duplicado): no se reintenta. 429: límite, sí.
    return {
      ok: false,
      error: `X ${resp.status}: ${JSON.stringify(data).slice(0, 400)}`,
      definitivo: resp.status === 401 || resp.status === 403,
      credenciales: resp.status === 401,
    };
  }
  return { ok: true, idExterno: data.data.id };
}

// ── Entrada única ───────────────────────────────────────────────────────────

/**
 * `imagenUrl` puede traer varias URL, una por línea (las diapositivas del
 * carrusel, en orden; así se guardan en `publicaciones_redes.imagen_url` sin
 * cambiar la tabla). Instagram las publica como carrusel; Facebook y X, solo
 * la primera (la portada).
 */
export async function publicarEnRed(red: Red, texto: string, imagenUrl: string | null, op: Opciones = {}): Promise<Resultado> {
  const imagenes = (imagenUrl || "").split(/\s+/).filter(Boolean);
  try {
    // Reel: el vídeo va primero; una segunda URL (imagen), si la hay, es la portada.
    if (imagenes.length && esVideo(imagenes[0])) {
      if (red === "instagram") return await publicarReel(texto, imagenes[0], imagenes.find((u) => !esVideo(u)), op);
      if (red === "facebook") return await publicarVideoFacebook(texto, imagenes[0]);
      return { ok: false, error: "Los vídeos no se publican en X desde el motor", definitivo: true };
    }
    if (red === "x") return await publicarX(texto, imagenes[0] || null);
    if (!imagenes.length) return { ok: false, error: "Falta la imagen", definitivo: true };  // solo esta fila
    if (red === "facebook") return await publicarFacebook(texto, imagenes[0]);
    if (texto.trim().startsWith("[HISTORIA]")) return await publicarHistoria(imagenes[0]);
    return await publicarInstagram(texto, imagenes, op);
  } catch (e) {
    const err = e as Error & { definitivo?: boolean; credenciales?: boolean };
    return { ok: false, error: err.message, definitivo: !!err.definitivo, credenciales: !!err.credenciales };
  }
}
