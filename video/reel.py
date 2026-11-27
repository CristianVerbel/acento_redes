#!/usr/bin/env python3
"""Generador de reels: video vertical 1080x1920 con la marca del medio.

Copiado del generador de reels de Acento y separado de su marca: colores,
fuentes, logos, música y textos salen de `marca/<nombre>/marca.json`
(por defecto `marca/l1bre`; otra con MARCA=<carpeta>).

Combina videos y fotos en escenas, cada una con su texto: logo arriba,
degradado del color de fondo abajo, titular con barra de color, subtítulos
sincronizados con la voz, crédito bajo el logo y cierre con la marca.

Uso:  python3 reel.py guion.json salida.mp4

guion.json:
{
  "credito": "Video: @cuenta",
  "transcripcion": "tr.json",          # opcional: palabras con tiempos (faster-whisper)
  "portada": {"titular": "...", "foto": "foto.jpg"},
  "escenas": [
    {"tipo": "foto",  "src": "a.jpg", "dur": 3, "antetitulo": "BOGOTÁ", "texto": "Titular de la escena"},
    {"tipo": "video", "src": "v.mp4", "desde": 0, "hasta": 18.3, "texto": "«Cita»", "subtitulos": true},
    {"tipo": "cierre", "dur": 3}
  ],
  "publicidad": {"src": "pauta.mp4", "primera": 7, "cada": 20}   # opcional
}
"""
import json, os, subprocess, sys, tempfile, textwrap
from PIL import Image, ImageDraw, ImageFilter
from marca import Marca

AQUI = os.path.dirname(os.path.abspath(__file__))
M = Marca()
W, H, FPS = 1080, 1920, 30
FONDO, ACENTO, PANEL, TINTA = M.FONDO, M.ACENTO, M.PANEL, M.TINTA
ROLES = {"800ExtraBold": "titular", "700Bold": "entrada", "600SemiBold": "credito", "400Regular": "texto"}


def fuente(peso, tam):
    """`peso` es el rol de la marca (titular, entrada, credito, texto); se
    aceptan también los nombres de peso de Newsreader del original."""
    return M.fuente(ROLES.get(peso, peso), tam)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


# Zonas seguras de Instagram: arriba (~120 px) va el encabezado, desde ~1600
# el nombre de la cuenta y el texto del post, y a la derecha (x > 940, desde
# y ~1100) los botones. Todo lo nuestro va entre LOGO_Y y SEGURO_Y, y los
# textos de abajo no pasan de SEGURO_X.
LOGO_Y = 200   # logo centrado arriba, justo debajo del encabezado de Instagram
LOGO_W = 360
MEDIA_Y, MEDIA_H, MEDIA_W = 450, 600, 1040
SUB_Y = 1062
TEXTO_Y = 1150
SEGURO_X, SEGURO_Y = 920, 1595


def capa(escena, credito, completa=False):
    """PNG transparente con todo lo que va encima de la escena. Con
    `completa` (video vertical a pantalla completa) no hay velo arriba: solo
    una sombra suave para el logo y el degradado de abajo para el texto."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    grad = Image.new("L", (1, H))
    for y in range(H):
        if completa and not escena.get("texto"):
            # Video con sus propios textos: solo sombra arriba para el logo.
            t = 0.4 * max(0, 1 - y / 520)
        elif completa:
            t = 0.35 * max(0, 1 - y / 420) if y < 420 else min(0.92, max(0, (y - 1000) / 450) * 0.92)
        else:
            # El velo azul del fondo desenfocado se pone en ffmpeg, solo al
            # fondo: el video del recuadro se ve limpio. Aquí, solo el
            # oscurecimiento de abajo para que el texto se lea.
            t = 0 if y < MEDIA_Y + MEDIA_H else min(0.8, (y - MEDIA_Y - MEDIA_H) / 260 * 0.8)
        # Degradado corto arriba para que el logo no se pierda en ningún video.
        t = max(t, 0.62 * max(0.0, 1 - y / 420) ** 1.3)
        grad.putpixel((0, y), int(255 * t))
    im.paste(Image.new("RGBA", (W, H), FONDO + (255,)), (0, 0), grad.resize((W, H)))
    logo = M.logo("blanco")
    logo = logo.resize((LOGO_W, int(logo.height * LOGO_W / logo.width)), Image.LANCZOS)
    logo_y = escena.get("logo_y", LOGO_Y)
    im.alpha_composite(logo, ((W - LOGO_W) // 2, logo_y))
    y = TEXTO_Y
    if escena.get("antetitulo"):
        f = fuente("700Bold", 34)
        txt = escena["antetitulo"].upper()
        tw = d.textlength(txt, font=f)
        d.rectangle((64, y, 64 + tw + 36, y + 54), fill=ACENTO)
        d.text((82, y + 6), txt, font=f, fill=M.TEXTO_ACENTO)
        y += 76
    if escena.get("texto"):
        tam = escena.get("tam", 58)
        f = fuente("800ExtraBold", tam)
        # Que ninguna línea entre en la columna de botones de Instagram.
        ancho = 34
        while ancho > 12 and any(d.textlength(l, font=f) > SEGURO_X - 96 for l in textwrap.wrap(escena["texto"], ancho)):
            ancho -= 1
        lineas = textwrap.wrap(escena["texto"], ancho)
        d.rectangle((64, y, 72, y + len(lineas) * int(tam * 1.12)), fill=ACENTO)
        for ln in lineas:
            d.text((96, y - 6), ln, font=f, fill="white")
            y += int(tam * 1.12)
    if escena.get("bajada"):
        f = fuente("400Regular", 36)
        y += 14
        for ln in textwrap.wrap(escena["bajada"], 42):
            d.text((96, y), ln, font=f, fill=M.BAJADA)
            y += 46
    if y > 1400:
        print(f"aviso: el texto termina en y={y} y choca con la pauta (y=1400); acórtelo", flush=True)
    # Crédito pequeño y centrado pegado al logo, dentro del degradado: abajo
    # lo taparía el nombre de la cuenta y más abajo caería en los rostros.
    f = fuente("600SemiBold", 26)
    pie = credito or M.dominio
    d.text(((W - d.textlength(pie, font=f)) / 2, logo_y + logo.height + 10), pie, font=f, fill="white",
           stroke_width=2, stroke_fill=(0, 0, 0))
    return im


def portada(titular, foto, salida):
    """Portada del reel con el diseño de la portada de los carruseles (foto
    arriba, titular sobre el panel gris y logo de la marca), en
    1080x1920 para que la cuadrícula del perfil (recorte 4:5 al centro) se vea
    igual que la de los carruseles. Nunca queda en negro."""
    # Fondo del color del panel del slide: arriba y abajo de la tarjeta 4:5
    # no quedan franjas oscuras, y la miniatura se ve como un slide.
    im = Image.new("RGB", (W, H), PANEL)
    top = (H - 1350) // 2
    ph = Image.open(foto).convert("RGB")
    # La foto completa en 1080x690 (recorte suave al centro, sin deformar).
    r = max(1080 / ph.width, 690 / ph.height)
    ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1), Image.LANCZOS)
    x0 = (ph.width - 1080) // 2
    y0 = max(0, int((ph.height - 690) * 0.3))
    im.paste(ph.crop((x0, y0, x0 + 1080, y0 + 690)), (0, top))
    d = ImageDraw.Draw(im)
    d.rectangle((0, top + 690, W, top + 1350), fill=PANEL)
    for tam in range(80, 50, -2):
        f = fuente("800ExtraBold", tam)
        ln = textwrap.wrap(titular, max(10, int(920 / (tam * 0.5))))
        if len(ln) <= 5 and all(d.textlength(x, font=f) <= 920 for x in ln):
            break
    alto = len(ln) * tam * 1.15
    y = top + 690 + (574 - alto) / 2
    for x in ln:
        d.text(((W - d.textlength(x, font=f)) / 2, y), x, font=f, fill=TINTA)
        y += tam * 1.15
    lg = M.logo("color")
    lg = lg.resize((211, int(lg.height * 211 / lg.width)), Image.LANCZOS)
    im.paste(lg, (817, top + 1264), lg)
    im.save(salida, quality=92)
    return salida


def tarjeta_cierre(escena):
    im = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(im)
    logo = M.logo("blanco")
    logo = logo.resize((760, int(logo.height * 760 / logo.width)), Image.LANCZOS)
    im.paste(logo, ((W - logo.width) // 2, 720), logo)
    d.rectangle((0, 0, W, 14), fill=ACENTO)
    d.rectangle((0, H - 14, W, H), fill=ACENTO)
    f = fuente("700Bold", 52)
    y = 1000
    for ln in textwrap.wrap(escena.get("texto", M.cfg["cierre"]["texto"]), 30):
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill="white")
        y += 66
    f2 = fuente("600SemiBold", 40)
    t = escena.get("bajada", M.cfg["cierre"]["bajada"])
    d.text(((W - d.textlength(t, font=f2)) / 2, y + 30), t, font=f2, fill=(200, 206, 220))
    return im


def ass_subtitulos(palabras, desde, hasta, ruta):
    def ts(t):
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    ws = [w for w in palabras if w[0] >= desde - 0.05 and w[1] <= hasta + 0.2]
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: S,%s,58,%s,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,1,8,64,180,%d,1" % (M.cfg["fuentes"]["familia_subtitulos"], M.ass_color(M.SUBTITULOS), SUB_Y),
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i in range(0, len(ws), 4):
        ch = ws[i:i + 4]
        s = ch[0][0] - desde
        e = (ws[i + 4][0] if i + 4 < len(ws) else ch[-1][1]) - desde
        out.append(f"Dialogue: 0,{ts(max(0, s))},{ts(min(e, hasta - desde))},S,,0,0,0,,{' '.join(w[2].strip() for w in ch)}")
    open(ruta, "w").write("\n".join(out) + "\n")


def es_completa(e):
    """Pantalla completa si la escena lo pide o si el video ya es vertical
    (proporción cercana a 9:16): así no se reduce ni se recorta."""
    if e.get("pantalla") in ("completa", "recuadro"):
        return e["pantalla"] == "completa"
    if e["tipo"] != "video":
        return False
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", e["src"]], capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(r[0]), int(r[1])
    return h / w >= 1.6


def escena_a_clip(i, e, credito, palabras, tmp):
    out = os.path.join(tmp, f"e{i:02d}.mp4")
    if e["tipo"] == "cierre":
        png = os.path.join(tmp, f"c{i}.png")
        tarjeta_cierre(e).save(png)
        dur = e.get("dur", 3)
        ffmpeg("-loop", "1", "-t", str(dur), "-i", png, "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo",
               "-vf", f"fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.3", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-c:a", "aac", "-shortest", out)
        return out
    png = os.path.join(tmp, f"o{i}.png")
    completa = es_completa(e)
    capa(e, credito, completa).save(png)
    fade = "fade=t=in:st=0:d=0.25"
    # Nunca se recorta ni se deforma la imagen: va completa en el recuadro
    # central y el resto de la pantalla lo llena la misma imagen desenfocada.
    fondo = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,"
             f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{M.hex(FONDO)}@0.6:t=fill")
    frente = f"scale={MEDIA_W}:{MEDIA_H}:force_original_aspect_ratio=decrease"
    pos = f"x=(W-w)/2:y={MEDIA_Y}+({MEDIA_H}-h)/2"
    if e["tipo"] == "foto":
        dur = e.get("dur", 3.5)
        vf = (f"[0:v]split[a][b];[a]{fondo}[bg];[b]{frente}[fg];[bg][fg]overlay={pos}[m];"
              f"[m][1:v]overlay=0:0,fps={FPS},{fade},format=yuv420p[v]")
        ffmpeg("-loop", "1", "-t", str(dur), "-i", e["src"], "-loop", "1", "-t", str(dur), "-i", png,
               "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo",
               "-filter_complex", vf, "-map", "[v]", "-map", "2:a", "-t", str(dur),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", out)
        return out
    desde, hasta = e.get("desde", 0), e["hasta"]
    if completa:
        # Vertical: el video va en su ancho y alto normal, a pantalla completa,
        # y encima solo los elementos de marca y la pauta.
        vf = (f"[0:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[m];"
              f"[m][1:v]overlay=0:0:shortest=1")
    else:
        vf = (f"[0:v]fps={FPS},split[a][b];[a]{fondo}[bg];[b]{frente}[fg];[bg][fg]overlay={pos}[m];"
              f"[m][1:v]overlay=0:0:shortest=1")
    if e.get("subtitulos") and palabras:
        ass = os.path.join(tmp, f"s{i}.ass")
        ass_subtitulos(palabras, desde, hasta, ass)
        vf += f",subtitles={ass}:fontsdir={M.dirs_fuentes()[0]}"
    vf += f",{fade},format=yuv420p[v]"
    ffmpeg("-ss", str(desde), "-t", str(hasta - desde), "-i", e["src"], "-loop", "1", "-i", png,
           "-filter_complex", vf, "-map", "[v]", "-map", "0:a", "-t", str(hasta - desde),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "2", out)
    return out


def publicidad(entrada, salida, dur, cfg):
    """Pone la franja de publicidad (video 1080x1920 con fondo negro) varias
    veces a lo largo del reel, justo debajo del texto, sin tapar rostros."""
    src = cfg["src"]
    if not os.path.isabs(src):
        src = M.archivo(src) or os.path.join(cfg.get("_base", "."), src)
    largo = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                                 capture_output=True, text=True).stdout)
    fin_util = dur - cfg.get("sin_final", 3.5)
    t, momentos = cfg.get("primera", 6), []
    while t + largo <= fin_util:
        momentos.append(t)
        t += cfg.get("cada", 18)
    if not momentos:
        os.rename(entrada, salida)
        return
    franja_y, franja_h = cfg.get("franja_y", 1340), cfg.get("franja_h", 260)
    # La tarjeta va reducida y pegada a la izquierda para no meterse bajo
    # los botones de Instagram; `y` es la parte de arriba de la franja.
    escala = cfg.get("escala", 0.86)
    destino = cfg.get("y", 1400)
    px = int(40 - 55 * escala)
    ins = ["-i", entrada]
    fc, prev = "", "0:v"
    for k, m in enumerate(momentos):
        ins += ["-itsoffset", str(m), "-i", src]
        fc += (f"[{k+1}:v]crop={W}:{franja_h}:0:{franja_y},colorkey=0x000000:0.10:0.12,scale=iw*{escala}:-2,format=yuva420p[p{k}];"
               f"[{prev}][p{k}]overlay={px}:{destino}:eof_action=pass:enable='between(t,{m},{m + largo})'[o{k}];")
        prev = f"o{k}"
    fc = fc.rstrip(";")
    ffmpeg(*ins, "-filter_complex", fc, "-map", f"[{prev}]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", salida)


def main(guion, salida):
    g = json.load(open(guion))
    base = os.path.dirname(os.path.abspath(guion))
    palabras = []
    if g.get("transcripcion"):
        tr = json.load(open(os.path.join(base, g["transcripcion"])))
        palabras = [w for s in tr for w in s["w"]]
    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        if g.get("portada"):
            pt = g["portada"]
            foto = pt["foto"] if os.path.isabs(pt["foto"]) else os.path.join(base, pt["foto"])
            jpg = portada(pt["titular"], foto, os.path.splitext(salida)[0] + "-portada.jpg")
            pc = os.path.join(tmp, "portada.mp4")
            ffmpeg("-loop", "1", "-t", "0.6", "-i", jpg, "-f", "lavfi", "-t", "0.6", "-i", "anullsrc=r=44100:cl=stereo",
                   "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest", pc)
            clips.append(pc)
        for i, e in enumerate(g["escenas"]):
            if e.get("src") and not os.path.isabs(e["src"]):
                e["src"] = os.path.join(base, e["src"])
            clips.append(escena_a_clip(i, e, g.get("credito", ""), palabras, tmp))
        lista = os.path.join(tmp, "lista.txt")
        open(lista, "w").write("".join(f"file '{c}'\n" for c in clips))
        unido = os.path.join(tmp, "unido.mp4")
        ffmpeg("-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", unido)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", unido],
                                   capture_output=True, text=True).stdout)
        if g.get("publicidad"):
            con_pub = os.path.join(tmp, "pub.mp4")
            publicidad(unido, con_pub, dur, {**g["publicidad"], "_base": base})
            unido = con_pub
        # Música de la marca en bucle, baja bajo la voz y con salida suave.
        # Sin música en la marca, el audio sale tal cual.
        if not M.musica:
            ffmpeg("-i", unido, "-c", "copy", "-movflags", "+faststart", salida)
            return
        vol = g.get("volumen_musica", 0.16)
        ffmpeg("-i", unido, "-stream_loop", "-1", "-i", M.musica,
               "-filter_complex", f"[1:a]volume={vol},afade=t=out:st={max(0, dur - 2)}:d=2[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", str(dur), salida)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
