"""Saca el logo L1BRE (sin el lema) de la imagen original sobre fondo azul y
lo deja en PNG transparente: logo-blanco.png (letras blancas, para encima del
video) y logo-color.png (letras azul L1BRE, para fondos claros).

Uso:  python3 extraer_logo.py   (requiere numpy, scipy y Pillow)
"""
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
from scipy.spatial import ConvexHull

AQUI = os.path.dirname(os.path.abspath(__file__))
FONDO = np.array([9, 42, 113], float)          # azul L1BRE del fondo
BLANCO = np.array([255, 255, 255], float)

im = np.asarray(Image.open(os.path.join(AQUI, "l1bre-con-lema.png")).convert("RGB")).astype(float)
y0, y1, x0, x1 = 215, 535, 180, 1480           # solo la palabra, sin el lema
c = im[y0:y1, x0:x1]

# Letras blancas: cuánto del blanco hay en cada píxel (proyección fondo→blanco).
# Se mide con el canal más bajo: así el amarillo y el azul del ícono no
# cuentan como blanco.
a_letras = np.clip((c.min(2) - FONDO.min()) / (255 - FONDO.min()), 0, 1)
a_letras[a_letras < 0.04] = 0

# Ícono del 1: su parte oscura casi no se distingue del fondo. La forma es
# convexa (paralelogramo redondeado): se toma el contorno convexo de la parte
# clara (amarillo, blanco, azul), que marca bien los bordes de la derecha y de
# abajo, más la esquina oscura de arriba a la izquierda, que sale de la
# diferencia suavizada con el fondo, recortada a la izquierda del amarillo y arriba del azul.
d = np.sqrt(((c - FONDO) ** 2).sum(2))
ix0, ix1, corte = 390 - x0, 700 - x0, 575 - x0
claro = d > 40
claro[:, :ix0] = False
claro[:, ix1:] = False
etq, n = nd.label(claro)
tam = nd.sum(claro, etq, range(1, n + 1))
claro = etq == (1 + int(np.argmax(tam)))
oscuro = nd.gaussian_filter(d, 2.2) > 5.5
oscuro[:, :ix0] = False
oscuro[:, corte:] = False
oscuro[330 - y0:, :] = False   # la esquina oscura es solo la de arriba
oscuro = nd.binary_opening(nd.binary_fill_holes(nd.binary_closing(oscuro, iterations=4)), iterations=3)
oscuro = nd.binary_erosion(oscuro, iterations=2)
puntos = np.argwhere(claro | oscuro)
casco = ConvexHull(puntos)
lienzo = Image.new("L", (c.shape[1], c.shape[0]), 0)
ImageDraw.Draw(lienzo).polygon([(int(p[1]), int(p[0])) for p in puntos[casco.vertices]], fill=255)
icono = np.asarray(lienzo) > 0
a_icono = nd.gaussian_filter(icono.astype(float), 0.8).clip(0, 1)

def guardar(color_letras, nombre):
    alfa = np.maximum(a_letras, a_icono)
    rgb = np.where(a_icono[..., None] > 0, c, color_letras)
    # Dentro del ícono se dejan sus colores (el 1 sigue blanco en las dos).
    out = np.dstack([rgb, alfa * 255]).clip(0, 255).astype("uint8")
    img = Image.fromarray(out, "RGBA")
    img = img.crop(img.getbbox())
    img.save(os.path.join(os.path.dirname(AQUI), nombre))
    print(nombre, img.size)

guardar(BLANCO, "logo-blanco.png")
guardar(FONDO, "logo-color.png")
