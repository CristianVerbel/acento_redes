#!/usr/bin/env python3
"""Kit para editar reels a mano en CapCut con el mismo diseño que arma
reel.py: capas PNG transparentes en 1080x1920, pauta (si la marca o el
pedido la trae) lista para encima, portada, cierre, fuentes, música y la guía.

La marca sale de marca/<nombre>/marca.json (MARCA=<carpeta>, por defecto canal1).

Uso:  python3 kit_capcut.py carpeta_de_salida [pauta.mp4]
"""
import os, shutil, subprocess, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel as R  # noqa: E402
M = R.M

W, H = R.W, R.H


def guardar(im, ruta):
    im.save(ruta)
    print("  ", os.path.basename(ruta))


def capa_logo(out):
    """Logo centrado arriba con su degradado. Va en todos los reels."""
    # Sin crédito: el equipo lo escribe en CapCut bajo el logo.
    im = R.capa({}, " ", completa=True)
    guardar(im, os.path.join(out, "01_logo_arriba.png"))


def capa_texto_abajo(out):
    """Degradado del color de fondo abajo y barra del titular, para cuando el
    reel lleva antetítulo y titular."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(255 * min(0.92, max(0, (y - 1000) / 450) * 0.92)))
    im.paste(Image.new("RGBA", (W, H), R.FONDO + (255,)), (0, 0), grad.resize((W, H)))
    d = ImageDraw.Draw(im)
    d.rectangle((64, R.TEXTO_Y + 76, 72, R.TEXTO_Y + 76 + 3 * 65), fill=R.ACENTO)
    guardar(im, os.path.join(out, "02_degradado_y_barra_titular.png"))


def fondo_horizontal(out):
    """Velo del color de fondo para el fondo desenfocado de los videos horizontales."""
    im = Image.new("RGBA", (W, H), R.FONDO + (153,))
    guardar(im, os.path.join(out, "03_velo_fondo_horizontal.png"))


def guia_zonas(out):
    """Capa de guía: lo rojo es lo que tapa Instagram. Se borra antes de
    exportar."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rojo = (230, 30, 30, 110)
    d.rectangle((0, 0, W, 170), fill=rojo)
    d.rectangle((0, 1600, W, H), fill=rojo)
    d.rectangle((940, 1100, W, 1600), fill=rojo)
    linea = (255, 225, 0, 255)
    for y, t in ((R.MEDIA_Y, "video horizontal (arriba)"), (R.MEDIA_Y + R.MEDIA_H, "video horizontal (abajo)"),
                 (R.SUB_Y, "subtítulos"), (R.TEXTO_Y, "antetítulo / titular"), (1400, "pauta: franja (y 1400)"),
                 (1595, "límite inferior")):
        d.line((0, y, W, y), fill=linea, width=3)
        d.text((20 if "subtítulos" not in t else 560, y + 6), t, font=R.fuente("entrada", 30), fill=linea)
    d.line((R.SEGURO_X, 1100, R.SEGURO_X, 1600), fill=linea, width=3)
    f = R.fuente("titular", 44)
    d.text((40, 60), "ZONA DE INSTAGRAM: NADA AQUÍ", font=f, fill="white")
    d.text((40, 1700), "ZONA DE INSTAGRAM: NADA AQUÍ", font=f, fill="white")
    d.text((40, 1760), "Borre esta capa antes de exportar", font=R.fuente("credito", 36), fill="white")
    guardar(im, os.path.join(out, "00_GUIA_zonas_seguras_BORRAR.png"))


def portada_plantilla(out):
    """Portada con el hueco de la foto transparente: se pone la foto debajo
    y el titular encima con la fuente de titular de la marca."""
    top = (H - 1350) // 2
    im = Image.new("RGBA", (W, H), R.PANEL + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, top, W, top + 690), fill=(0, 0, 0, 0))
    d.rectangle((0, top + 690, W, top + 1350), fill=R.PANEL + (255,))
    lg = M.logo("color")
    lg = lg.resize((211, int(lg.height * 211 / lg.width)), Image.LANCZOS)
    im.alpha_composite(lg, (817, top + 1264))
    guardar(im, os.path.join(out, "04_portada_marco.png"))


def cierre(out):
    png = os.path.join(out, "_cierre.png")
    R.tarjeta_cierre({}).save(png)
    R.ffmpeg("-loop", "1", "-t", "3", "-i", png, "-vf", "fps=30,format=yuv420p,fade=t=in:st=0:d=0.3",
             "-c:v", "libx264", "-crf", "20", os.path.join(out, "05_cierre_3s.mp4"))
    os.remove(png)
    print("   05_cierre_3s.mp4")


def pauta(out, src):
    """La pauta ya reducida y en su sitio, a pantalla completa:
    se pone encima del video y no hay que moverla. Dos alturas: baja (bajo
    el titular) y alta (para videos verticales con subtítulos propios)."""
    # Transparente, solo la franja (pesa poco): se pega a la izquierda con su
    # borde de arriba en la línea «pauta» de la guía.
    R.ffmpeg("-i", src, "-vf", f"crop={W}:260:0:1340,colorkey=0x000000:0.10:0.12,scale=iw*0.86:-2,format=yuva444p10le",
             "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "8",
             os.path.join(out, "06_pauta_franja_transparente.mov"))
    for nombre, y in (("baja", 1400), ("alta", 1150)):
        px = int(40 - 55 * 0.86)
        # Versión en verde por si CapCut no lee la transparencia: se usa con
        # «Eliminar fondo > Croma» sobre el verde.
        fc2 = (f"[0:v]crop={W}:260:0:1340,colorkey=0x000000:0.10:0.12,scale=iw*0.86:-2[p];"
               f"color=c=0x00FF00:s={W}x{H}:r=30:d=6[f];[f][p]overlay={px}:{y}:shortest=1,format=yuv420p[v]")
        R.ffmpeg("-i", src, "-filter_complex", fc2, "-map", "[v]", "-c:v", "libx264", "-crf", "18",
                 os.path.join(out, f"06_pauta_{nombre}_verde.mp4"))
        print(f"   06_pauta_{nombre}_verde.mp4")


def main(out, pauta_src=None):
    os.makedirs(out, exist_ok=True)
    guia_zonas(out)
    capa_logo(out)
    capa_texto_abajo(out)
    fondo_horizontal(out)
    portada_plantilla(out)
    cierre(out)
    if pauta_src:
        pauta(out, pauta_src)
    fu = os.path.join(out, "fuentes")
    os.makedirs(fu, exist_ok=True)
    for rol in ("titular", "entrada", "credito", "texto"):
        p = M.archivo(M.cfg["fuentes"][rol])
        if p:
            shutil.copy(p, fu)
    if M.musica:
        shutil.copy(M.musica, os.path.join(out, "07_musica" + os.path.splitext(M.musica)[1]))
    for v in ("blanco", "color"):
        M.logo(v).save(os.path.join(out, f"logo-{v}.png"))
    guia = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GUIA_CAPCUT.md")
    shutil.copy(guia, out)
    guia_pdf(guia, os.path.join(out, "GUIA_CAPCUT.pdf"))


def guia_pdf(md, salida):
    """La guía en PDF para leerla en el celular (Markdown -> HTML -> Chromium)."""
    import html as H_, re
    lineas, out, tabla = open(md).read().splitlines(), [], []

    def inline(t):
        t = H_.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return re.sub(r"`(.+?)`", r"<code>\1</code>", t)

    def cerrar_tabla():
        if tabla:
            filas = [r for r in tabla if not set(r.replace("|", "").strip()) <= {"-"}]
            out.append("<table>" + "".join(
                "<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{inline(c.strip())}</{'th' if i == 0 else 'td'}>"
                                 for c in r.strip().strip("|").split("|")) + "</tr>" for i, r in enumerate(filas)) + "</table>")
            tabla.clear()
    for ln in lineas:
        if ln.startswith("|"):
            tabla.append(ln); continue
        cerrar_tabla()
        if ln.startswith("# "): out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "): out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif re.match(r"^\s*(- |\d+\. )", ln): out.append(f"<p class=li>{inline(ln.strip())}</p>")
        elif ln.startswith("  ") and out: out[-1] = out[-1][:-4] + " " + inline(ln.strip()) + "</p>"
        elif ln.strip(): out.append(f"<p>{inline(ln)}</p>")
    cerrar_tabla()
    css = ("body{font-family:Georgia,serif;color:#131313;margin:36px;font-size:15px;line-height:1.45}"
           "h1{color:#"+M.hex(M.FONDO)+";border-bottom:6px solid #"+M.hex(M.ACENTO)+";padding-bottom:8px}h2{color:#"+M.hex(M.FONDO)+";margin-top:26px}"
           "table{border-collapse:collapse;width:100%;margin:10px 0}td,th{border:1px solid #ccd;padding:6px;text-align:left;vertical-align:top}"
           "th{background:#"+M.hex(M.FONDO)+";color:#fff}code{background:#eef;padding:1px 4px}p.li{margin:4px 0 4px 14px}")
    tmp = salida + ".html"
    open(tmp, "w").write(f"<html><head><meta charset=utf-8><style>{css}</style></head><body>{''.join(out)}</body></html>")
    subprocess.run(["node", "-e", f"""const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage();
await p.goto('file://{tmp}');await p.pdf({{path:'{salida}',format:'A4',printBackground:true}});await b.close();}})()"""], check=True)
    os.remove(tmp)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
