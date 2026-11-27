"""Carga la marca (colores, fuentes, logos, música, textos) de `marca/<nombre>/marca.json`.

El generador de reels y el kit de CapCut no llevan ninguna marca escrita en el
código: todo sale de aquí. Por defecto se usa `marca/l1bre`; otra marca se
elige con la variable de entorno MARCA (nombre de carpeta o ruta).
"""
import json, os
from PIL import Image, ImageDraw, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
FUENTES_COMUNES = os.path.join(AQUI, "assets", "fuentes")


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Marca:
    def __init__(self, ruta=None):
        ruta = ruta or os.environ.get("MARCA") or "l1bre"
        if not os.path.isdir(ruta):
            ruta = os.path.join(RAIZ, "marca", ruta)
        self.dir = os.path.abspath(ruta)
        self.cfg = json.load(open(os.path.join(self.dir, "marca.json")))
        c = self.cfg["colores"]
        self.FONDO = _rgb(c["fondo"])
        self.ACENTO = _rgb(c["acento"])
        self.TEXTO_ACENTO = _rgb(c.get("texto_acento", "#FFFFFF"))
        self.PANEL = _rgb(c.get("panel", "#E1E2E3"))
        self.TINTA = _rgb(c.get("tinta", "#131313"))
        self.BAJADA = _rgb(c.get("bajada", "#E1E6F0"))
        self.SUBTITULOS = _rgb(c.get("subtitulos", "#FFE100"))
        self.nombre = self.cfg["nombre"]
        self.dominio = self.cfg["dominio"]
        self._logos = {}

    # ── Archivos ──
    def archivo(self, nombre):
        """Busca un archivo primero en la carpeta de la marca y luego en las fuentes comunes."""
        for d in (self.dir, os.path.join(self.dir, "fuentes"), FUENTES_COMUNES):
            p = os.path.join(d, nombre)
            if os.path.exists(p):
                return p
        return None

    def dirs_fuentes(self):
        return [d for d in (os.path.join(self.dir, "fuentes"), self.dir, FUENTES_COMUNES) if os.path.isdir(d)]

    def fuente(self, rol, tam):
        nombre = self.cfg["fuentes"][rol]
        p = self.archivo(nombre)
        if not p:
            raise FileNotFoundError(f"Falta la fuente «{nombre}» de la marca {self.nombre}")
        return ImageFont.truetype(p, tam)

    @property
    def musica(self):
        m = self.cfg.get("musica")
        return self.archivo(m) if m else None

    def logo(self, variante="blanco"):
        """Logo de la marca. Si aún no está el PNG, se pinta el nombre en
        texto para que el reel salga igual (provisional)."""
        if variante in self._logos:
            return self._logos[variante].copy()
        p = self.archivo(self.cfg["logos"][variante])
        if p:
            im = Image.open(p).convert("RGBA")
        else:
            f = self.fuente("titular", 160)
            tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            x0, y0, x1, y1 = tmp.textbbox((0, 0), self.nombre, font=f)
            im = Image.new("RGBA", (x1 - x0 + 40, y1 - y0 + 40), (0, 0, 0, 0))
            color = (255, 255, 255) if variante == "blanco" else self.FONDO
            ImageDraw.Draw(im).text((20 - x0, 20 - y0), self.nombre, font=f, fill=color)
            print(f"aviso: falta {self.cfg['logos'][variante]} en {self.dir}; se usa el nombre en texto", flush=True)
        self._logos[variante] = im
        return im.copy()

    def texto(self, clave, defecto=""):
        return self.cfg.get(clave, defecto)

    def ass_color(self, rgb):
        """Color en formato ASS (&H00BBGGRR) para los subtítulos de ffmpeg."""
        r, g, b = rgb
        return f"&H00{b:02X}{g:02X}{r:02X}"

    def hex(self, rgb):
        return "".join(f"{v:02X}" for v in rgb)
