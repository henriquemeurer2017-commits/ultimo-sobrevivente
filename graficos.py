"""Desenhos (sprites) gerados por codigo, luzes e sons do Ultimo Sobrevivente."""
import math
import random

import numpy as np
import pygame

from config import W, H


def vivo(s, sat=1.3, contraste=1.08, brilho=3):
    """Cores mais vivas e fortes (ideia do Rua dos Zumbis). So mexe nas cores, nunca na transparencia."""
    if s is None:
        return s
    arr = pygame.surfarray.pixels3d(s)
    f = arr.astype(np.float32)
    cinza = f.mean(axis=2, keepdims=True)
    f = cinza + (f - cinza) * sat
    f = (f - 128.0) * contraste + 128.0 + brilho
    arr[:] = np.clip(f, 0, 255).astype(np.uint8)
    del arr
    return s


def contorno(s, cor=(16, 12, 10), esp=2):
    """Contorno escuro em volta do desenho, para o personagem aparecer bem."""
    mask = pygame.mask.from_surface(s, 60)
    sil = mask.to_surface(setcolor=cor + (255,), unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    for dx in range(-esp, esp + 1):
        for dy in range(-esp, esp + 1):
            if dx * dx + dy * dy <= esp * esp and (dx or dy):
                out.blit(sil, (dx, dy))
    out.blit(s, (0, 0))
    return out


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def tom(c, d):
    """Clareia (d>0) ou escurece (d<0) uma cor."""
    return (clamp(int(c[0] + d), 0, 255), clamp(int(c[1] + d), 0, 255), clamp(int(c[2] + d), 0, 255))


def mistura(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


# ------------------------------------------------------------------ texturas
def textura_chao(seed, s):
    """Mapa de brilho (s x s) com granulado fino + manchas, para dar cara de chao de verdade."""
    rng = np.random.default_rng(seed)
    fino = rng.normal(1.0, 0.045, (s, s))

    def manchas(cell, amp):
        # repete sem emenda (as bordas casam com o pedaco vizinho)
        g = s // cell
        grid = rng.random((g, g))
        c = np.arange(s) / cell
        i = c.astype(int) % g
        j = (i + 1) % g
        f = c - np.floor(c)
        f = f * f * (3 - 2 * f)
        a = grid[i][:, i]
        b = grid[i][:, j]
        cc = grid[j][:, i]
        d = grid[j][:, j]
        top = a + (b - a) * f[None, :]
        bot = cc + (d - cc) * f[None, :]
        return (top + (bot - top) * f[:, None] - 0.5) * amp

    tex = fino + manchas(128, 0.12) + manchas(32, 0.10) + manchas(8, 0.07) + manchas(4, 0.04)
    return np.clip(tex, 0.72, 1.25).astype(np.float32)


def sombra_suave(rx, ry, alpha=90):
    s = pygame.Surface((rx * 2 + 8, ry * 2 + 8), pygame.SRCALPHA)
    passos = 6
    for i in range(passos):
        k = 1 - i / passos
        a = int(alpha * (i + 1) / passos * 0.45)
        pygame.draw.ellipse(s, (0, 0, 0, a), (4 + rx * (1 - k), 4 + ry * (1 - k), rx * 2 * k, ry * 2 * k))
    return s


# ------------------------------------------------------------------ arvores
def copa_folhosa(rnd, r):
    s = pygame.Surface((r * 2 + 12, r * 2 + 12), pygame.SRCALPHA)
    c = r + 6
    base = (rnd.randint(40, 60), rnd.randint(84, 110), rnd.randint(36, 50))
    escuro = tom(base, -28)
    pygame.draw.circle(s, escuro, (c, c), r)
    for _ in range(16):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(r * 0.45, r * 0.8)
        pygame.draw.circle(s, escuro, (c + math.cos(a) * d, c + math.sin(a) * d), r * rnd.uniform(0.28, 0.42))
    for _ in range(14):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(0, r * 0.62)
        pygame.draw.circle(s, tom(base, rnd.randint(-8, 6)), (c + math.cos(a) * d, c + math.sin(a) * d),
                           r * rnd.uniform(0.3, 0.45))
    for _ in range(10):
        a = rnd.uniform(3.4, 5.2)
        d = rnd.uniform(r * 0.1, r * 0.55)
        pygame.draw.circle(s, tom(base, rnd.randint(14, 26)), (c + math.cos(a) * d, c + math.sin(a) * d),
                           r * rnd.uniform(0.14, 0.26))
    for _ in range(30):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(0, r * 0.85)
        pygame.draw.circle(s, tom(base, rnd.randint(18, 40)), (c + math.cos(a) * d, c + math.sin(a) * d), 1.5)
    return s


def copa_pinheiro(rnd, r):
    s = pygame.Surface((r * 2 + 12, r * 2 + 12), pygame.SRCALPHA)
    c = r + 6
    base = (rnd.randint(28, 40), rnd.randint(66, 84), rnd.randint(44, 58))
    camadas = 5
    rot = rnd.uniform(0, 1)
    for k in range(camadas):
        rr = r * (1 - k / (camadas + 0.6))
        pts = []
        npts = 18
        for i in range(npts * 2):
            ang = rot + k * 0.31 + i * math.pi / npts
            d = rr if i % 2 == 0 else rr * 0.72
            pts.append((c + math.cos(ang) * d, c + math.sin(ang) * d))
        pygame.draw.polygon(s, tom(base, -18 + k * 9), pts)
    pygame.draw.circle(s, tom(base, 30), (c - 1, c - 1), max(2, r // 8))
    return s


def pedra(rnd, r):
    s = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
    c = r + 4
    pts = []
    for i in range(9):
        a = i / 9 * 6.283
        d = r * rnd.uniform(0.75, 1.0)
        pts.append((c + math.cos(a) * d, c + math.sin(a) * d))
    cinza = rnd.randint(105, 135)
    pygame.draw.polygon(s, (cinza - 25, cinza - 25, cinza - 28), pts)
    pts2 = [(c + (x - c) * 0.8 - 2, c + (y - c) * 0.8 - 2) for x, y in pts]
    pygame.draw.polygon(s, (cinza, cinza, cinza - 4), pts2)
    pts3 = [(c + (x - c) * 0.4 - 4, c + (y - c) * 0.4 - 4) for x, y in pts]
    pygame.draw.polygon(s, (cinza + 22, cinza + 22, cinza + 18), pts3)
    return s


def arbusto(rnd, r):
    s = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
    c = r + 4
    base = (rnd.randint(52, 70), rnd.randint(96, 120), rnd.randint(40, 52))
    for _ in range(9):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(0, r * 0.5)
        pygame.draw.circle(s, tom(base, rnd.randint(-22, 8)), (c + math.cos(a) * d, c + math.sin(a) * d),
                           r * rnd.uniform(0.4, 0.55))
    for _ in range(6):
        pygame.draw.circle(s, tom(base, 25), (c + rnd.uniform(-r * .5, r * .3), c + rnd.uniform(-r * .5, r * .3)), 2)
    if rnd.random() < 0.35:  # frutinhas
        for _ in range(5):
            pygame.draw.circle(s, (190, 50, 60), (c + rnd.uniform(-r * .6, r * .6), c + rnd.uniform(-r * .6, r * .6)), 2)
    return s


def capim(rnd, tamanho):
    """Moita de capim vista de cima: folhas compridas saindo do centro. tamanho = raio em px."""
    r = tamanho
    s = pygame.Surface((r * 2 + 10, r * 2 + 10), pygame.SRCALPHA)
    c = r + 5
    base = (rnd.randint(78, 104), rnd.randint(118, 146), rnd.randint(46, 62))
    seco = rnd.random() < 0.3
    if seco:
        base = (rnd.randint(140, 165), rnd.randint(132, 150), rnd.randint(70, 86))
    nfolhas = int(14 + r * 1.3)
    folhas = []
    for _ in range(nfolhas):
        a = rnd.uniform(0, 6.283)
        L = r * rnd.uniform(0.55, 1.0)
        curva = rnd.uniform(-0.5, 0.5)
        folhas.append((L, a, curva))
    folhas.sort()  # curtas por cima ficam mais claras
    for L, a, curva in sorted(folhas, key=lambda f: -f[0]):
        pts = []
        for k in range(6):
            t = k / 5
            aa = a + curva * t * t
            pts.append((c + math.cos(aa) * L * t, c + math.sin(aa) * L * t))
        brilho = rnd.randint(-30, 24)
        cor = tom(base, brilho)
        larg = max(2, int(r / 9))
        pygame.draw.lines(s, tom(cor, -25), False, pts, larg + 1)
        pygame.draw.lines(s, cor, False, pts, larg)
        pygame.draw.circle(s, tom(cor, 30), (int(pts[-1][0]), int(pts[-1][1])), 1)
    pygame.draw.circle(s, tom(base, -40), (c, c), max(3, r // 5))
    return s


def tufo(rnd):
    s = pygame.Surface((14, 14), pygame.SRCALPHA)
    base = (rnd.randint(70, 100), rnd.randint(110, 140), rnd.randint(44, 60))
    for _ in range(5):
        a = rnd.uniform(0, 6.283)
        L = rnd.uniform(3, 6)
        pygame.draw.line(s, tom(base, rnd.randint(-20, 20)), (7, 7), (7 + math.cos(a) * L, 7 + math.sin(a) * L), 2)
    return s


# ------------------------------------------------------------------ carros
CORES_CARRO = [(150, 40, 36), (40, 70, 120), (200, 200, 196), (60, 62, 66), (170, 150, 60), (54, 96, 70),
               (110, 80, 60), (140, 140, 150)]


def carro(rnd, cor):
    """Carro abandonado (comprido no eixo x, frente para a direita)."""
    w, h = 64, 32
    s = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
    o = 2
    pygame.draw.rect(s, tom(cor, -40), (o, o, w, h), border_radius=9)
    pygame.draw.rect(s, cor, (o + 1, o + 1, w - 2, h - 2), border_radius=8)
    pygame.draw.rect(s, tom(cor, 18), (o + 4, o + 3, w - 8, 6), border_radius=3)
    # vidros
    vidro = (46, 60, 70)
    pygame.draw.rect(s, vidro, (o + 40, o + 5, 9, h - 10), border_radius=3)  # para-brisa
    pygame.draw.rect(s, vidro, (o + 12, o + 6, 7, h - 12), border_radius=2)  # traseiro
    pygame.draw.rect(s, tom(cor, -12), (o + 19, o + 5, 21, h - 10), border_radius=3)  # teto
    # rachaduras
    for _ in range(3):
        x = o + 41 + rnd.randint(0, 6)
        y = o + 6 + rnd.randint(0, h - 14)
        pygame.draw.line(s, (150, 170, 180), (x, y), (x + rnd.randint(-4, 4), y + rnd.randint(-5, 5)), 1)
    # farois
    pygame.draw.rect(s, (230, 220, 160), (o + w - 4, o + 4, 3, 6))
    pygame.draw.rect(s, (230, 220, 160), (o + w - 4, o + h - 10, 3, 6))
    pygame.draw.rect(s, (150, 30, 30), (o + 1, o + 4, 3, 6))
    pygame.draw.rect(s, (150, 30, 30), (o + 1, o + h - 10, 3, 6))
    # ferrugem / sujeira
    for _ in range(14):
        pygame.draw.circle(s, (120, 80, 50, 150), (o + rnd.randint(4, w - 4), o + rnd.randint(3, h - 3)),
                           rnd.randint(1, 3))
    return s


# ------------------------------------------------------------------ gente e zumbis
def _boneco(corpo, pele, cabelo, arma=None, zumbi=False, rnd=None, ombro=13):
    """Personagem visto de cima, virado para a direita."""
    S = 72
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S // 2
    if zumbi:
        # bracos esticados para a frente
        for lado in (-1, 1):
            y = c + lado * (ombro - 3)
            pygame.draw.line(s, tom(pele, -30), (c, y), (c + 21, y + lado * -2), 7)
            pygame.draw.line(s, pele, (c, y), (c + 20, y + lado * -2), 5)
            pygame.draw.circle(s, tom(pele, -10), (c + 21, y + lado * -2), 3)
    else:
        if arma == "maos":  # sem nada na mao: bracos soltos do lado do corpo
            for lado in (-1, 1):
                y = c + lado * (ombro - 2)
                pygame.draw.line(s, tom(pele, -25), (c, y), (c + 9, y + lado * 2), 6)
                pygame.draw.line(s, pele, (c, y), (c + 8, y + lado * 2), 4)
                pygame.draw.circle(s, pele, (c + 10, y + lado * 2), 3)
        elif arma in ("faca", "machado", "facao", "katana", "taco"):
            pygame.draw.line(s, tom(pele, -25), (c, c + ombro - 3), (c + 14, c + ombro - 6), 6)
            pygame.draw.line(s, pele, (c, c + ombro - 3), (c + 13, c + ombro - 6), 4)
            pygame.draw.line(s, tom(pele, -25), (c, c - ombro + 3), (c + 6, c - ombro + 7), 6)
            if arma == "faca":
                pygame.draw.line(s, (90, 70, 50), (c + 13, c + ombro - 6), (c + 18, c + ombro - 6), 4)
                pygame.draw.line(s, (200, 205, 210), (c + 18, c + ombro - 6), (c + 29, c + ombro - 7), 3)
            elif arma == "taco":
                pygame.draw.line(s, (90, 60, 34), (c + 8, c + ombro - 3), (c + 40, c + ombro - 12), 5)
                pygame.draw.line(s, (160, 116, 66), (c + 8, c + ombro - 4), (c + 40, c + ombro - 13), 3)
                for px in (30, 34, 38):
                    py = c + ombro - 4 - (px - 8) * 9 // 32
                    pygame.draw.line(s, (200, 200, 210), (c + px, py - 5), (c + px, py + 3), 1)
            elif arma == "katana":
                pygame.draw.line(s, (30, 30, 34), (c + 12, c + ombro - 6), (c + 19, c + ombro - 6), 5)
                pygame.draw.line(s, (215, 220, 230), (c + 19, c + ombro - 6), (c + 46, c + ombro - 10), 3)
            elif arma == "facao":
                pygame.draw.line(s, (60, 44, 30), (c + 12, c + ombro - 6), (c + 18, c + ombro - 6), 5)
                pygame.draw.polygon(s, (190, 196, 202), [(c + 18, c + ombro - 9), (c + 38, c + ombro - 11),
                                                          (c + 40, c + ombro - 7), (c + 18, c + ombro - 3)])
            else:
                pygame.draw.line(s, (120, 86, 54), (c + 6, c + ombro - 2), (c + 32, c + ombro - 8), 4)
                pygame.draw.polygon(s, (170, 175, 182), [(c + 27, c + ombro - 15), (c + 35, c + ombro - 14),
                                                          (c + 33, c + ombro - 4), (c + 27, c + ombro - 6)])
        else:
            comp = COMP_ARMA.get(arma, 16)
            larg = {"pistola": 4, "espingarda": 5, "fuzil": 5, "rifle": 4, "smg": 5, "besta": 4, "minigun": 8,
                    "dragao": 7, "dourado": 5, "rpg": 9}.get(arma, 4)
            # bracos segurando a arma
            pygame.draw.line(s, tom(pele, -25), (c, c + ombro - 3), (c + 15, c + 3), 6)
            pygame.draw.line(s, tom(pele, -25), (c, c - ombro + 3), (c + 12 if comp < 20 else c + 20, c), 6)
            pygame.draw.line(s, pele, (c, c + ombro - 3), (c + 14, c + 3), 4)
            pygame.draw.line(s, pele, (c, c - ombro + 3), (c + 11 if comp < 20 else c + 19, c), 4)
            desenha_arma(s, arma, c + 4, c + 1, 1.0)
    # mochila
    if not zumbi:
        pygame.draw.rect(s, (70, 56, 36), (c - 16, c - 9, 10, 18), border_radius=3)
        pygame.draw.rect(s, (92, 74, 48), (c - 15, c - 7, 7, 14), border_radius=2)
    # ombros/corpo
    pygame.draw.ellipse(s, tom(corpo, -35), (c - 10, c - ombro - 1, 20, ombro * 2 + 2))
    pygame.draw.ellipse(s, corpo, (c - 9, c - ombro, 18, ombro * 2))
    pygame.draw.ellipse(s, tom(corpo, 16), (c - 6, c - ombro + 3, 8, ombro * 2 - 8))
    if zumbi and rnd is not None:
        for _ in range(rnd.randint(2, 5)):
            pygame.draw.circle(s, (100, 20, 20), (c + rnd.randint(-7, 7), c + rnd.randint(-ombro + 2, ombro - 2)),
                               rnd.randint(2, 4))
        for _ in range(2):  # rasgos
            x = c + rnd.randint(-6, 6)
            y = c + rnd.randint(-ombro + 3, ombro - 3)
            pygame.draw.line(s, tom(pele, -20), (x, y), (x + rnd.randint(-4, 4), y + rnd.randint(-4, 4)), 2)
    # cabeca
    hx = c + 2
    pygame.draw.circle(s, tom(pele, -35), (hx, c), 8)
    pygame.draw.circle(s, pele, (hx, c), 7)
    pygame.draw.circle(s, cabelo, (hx - 2, c), 6)
    pygame.draw.circle(s, pele, (hx + 2, c), 4)
    if zumbi:
        pygame.draw.circle(s, (220, 40, 30), (hx + 5, c - 2), 2)
        pygame.draw.circle(s, (220, 40, 30), (hx + 5, c + 2), 2)
    return contorno(vivo(s, 1.35, 1.06))


def sprite_jogador(arma):
    return _boneco((70, 86, 58), (214, 168, 128), (58, 42, 30), arma=arma, ombro=12)


ROUPAS_ZUMBI = [(70, 80, 110), (110, 84, 62), (90, 90, 94), (120, 50, 46), (60, 90, 80), (140, 130, 110),
                (50, 50, 56), (100, 110, 70)]


def sprite_zumbi(rnd, tipo):
    roupa = rnd.choice(ROUPAS_ZUMBI)
    pele = (rnd.randint(118, 140), rnd.randint(138, 156), rnd.randint(104, 120))
    cabelo = rnd.choice([(40, 36, 30), (70, 60, 44), (120, 110, 90), (30, 30, 30), (110, 70, 40)])
    if tipo == "gigante":
        base = _boneco((90, 40, 36), (120, 136, 100), (30, 30, 30), zumbi=True, rnd=rnd, ombro=17)
        return pygame.transform.smoothscale(base, (122, 122))
    if tipo == "gordo":
        return _boneco(tom(roupa, 10), pele, cabelo, zumbi=True, rnd=rnd, ombro=17)
    if tipo == "corredor":
        pele = (rnd.randint(140, 160), rnd.randint(120, 136), rnd.randint(110, 122))
        return _boneco(roupa, pele, cabelo, zumbi=True, rnd=rnd, ombro=11)
    return _boneco(roupa, pele, cabelo, zumbi=True, rnd=rnd, ombro=13)


def sangue(rnd, r):
    s = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
    c = r * 2
    cor = (rnd.randint(90, 120), 10, 12, 200)
    pygame.draw.circle(s, cor, (c, c), r)
    for _ in range(10):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(r * 0.6, r * 1.8)
        pygame.draw.circle(s, cor, (c + math.cos(a) * d, c + math.sin(a) * d), rnd.uniform(1.5, r * 0.45))
    return s


# ------------------------------------------------------------------ itens
_CACHE_ICONE = {}


def desenha_icone(s, item, x, y, k=1.0):
    """Desenha o icone do item. Guarda o desenho pronto para reaproveitar."""
    chave = (item, round(k, 2))
    img = _CACHE_ICONE.get(chave)
    if img is None:
        tam = int(64 * k) + 8
        img = pygame.Surface((tam, tam), pygame.SRCALPHA)
        _desenha_icone_bruto(img, item, tam // 2, tam // 2, k)
        _CACHE_ICONE[chave] = img
    s.blit(img, (int(x) - img.get_width() // 2, int(y) - img.get_height() // 2))


def _desenha_icone_bruto(s, item, x, y, k=1.0):
    x = int(x)
    y = int(y)

    def R(a, b, w, h):
        return pygame.Rect(x + a * k, y + b * k, max(1, w * k), max(1, h * k))

    if item == "comida":
        pygame.draw.rect(s, (150, 150, 158), R(-7, -8, 14, 16), border_radius=3)
        pygame.draw.rect(s, (190, 60, 40), R(-7, -3, 14, 7))
        pygame.draw.rect(s, (230, 200, 80), R(-3, -2, 6, 4))
    elif item == "agua":
        pygame.draw.rect(s, (130, 190, 235), R(-5, -7, 10, 15), border_radius=4)
        pygame.draw.rect(s, (40, 100, 190), R(-3, -10, 6, 4))
        pygame.draw.rect(s, (230, 240, 255), R(-3, -4, 2, 8))
    elif item == "bandagem":
        pygame.draw.rect(s, (238, 236, 228), R(-8, -6, 16, 12), border_radius=3)
        pygame.draw.rect(s, (200, 40, 40), R(-1, -4, 3, 8))
        pygame.draw.rect(s, (200, 40, 40), R(-4, -1, 9, 3))
    elif item == "kit":
        pygame.draw.rect(s, (200, 40, 40), R(-9, -7, 18, 14), border_radius=3)
        pygame.draw.rect(s, (250, 250, 250), R(-2, -5, 4, 10))
        pygame.draw.rect(s, (250, 250, 250), R(-5, -2, 10, 4))
    elif item in ("9mm", "12", "556", "308", "38"):
        cor = {"9mm": (220, 190, 70), "12": (200, 60, 50), "556": (200, 170, 90), "308": (230, 150, 60)}[item]
        n = 3 if item != "556" else 4
        for i in range(n):
            pygame.draw.rect(s, cor, R(-7 + i * 4, -6, 3, 12))
            pygame.draw.rect(s, (160, 120, 60), R(-7 + i * 4, -6, 3, 3))
    elif item == "silenciador":
        pygame.draw.rect(s, (40, 40, 44), R(-10, -3, 20, 7), border_radius=3)
        pygame.draw.rect(s, (90, 90, 96), R(-9, -2, 18, 2))
    elif item == "tabua":
        for i in range(3):
            pygame.draw.rect(s, (150 - i * 10, 104, 60), R(-9, -7 + i * 5, 18, 4))
    elif item == "sucata":
        pygame.draw.polygon(s, (130, 132, 138), [(x - 8 * k, y + 5 * k), (x - 3 * k, y - 7 * k), (x + 8 * k, y - 2 * k),
                                                 (x + 4 * k, y + 7 * k)])
        pygame.draw.circle(s, (160, 100, 60), (x, y), 3 * k)
    elif item == "ferramentas":
        pygame.draw.rect(s, (190, 40, 30), R(-9, -5, 18, 11), border_radius=2)
        pygame.draw.rect(s, (60, 60, 60), R(-4, -8, 8, 3))
    elif item == "peca":
        pygame.draw.rect(s, (40, 110, 60), R(-8, -6, 16, 12), border_radius=2)
        for i in range(3):
            pygame.draw.rect(s, (220, 190, 80), R(-6 + i * 5, -4, 3, 3))
        pygame.draw.rect(s, (30, 30, 30), R(-5, 2, 10, 2))
    elif item == "flecha":
        for i in (-3, 0, 3):
            pygame.draw.line(s, (150, 110, 70), (x - 9 * k, y + i * k), (x + 7 * k, y + i * k), max(1, int(1.5 * k)))
            pygame.draw.polygon(s, (190, 190, 200), [(x + 7 * k, y + (i - 2) * k), (x + 11 * k, y + i * k),
                                                     (x + 7 * k, y + (i + 2) * k)])
    elif item == "foguete":
        pygame.draw.rect(s, (90, 110, 70), R(-9, -3, 14, 6), border_radius=2)
        pygame.draw.polygon(s, (170, 170, 160), [(x + 5 * k, y - 4 * k), (x + 11 * k, y), (x + 5 * k, y + 4 * k)])
        pygame.draw.rect(s, (200, 90, 40), R(-12, -2, 3, 4))
    elif item == "mira":
        pygame.draw.rect(s, (20, 20, 24), R(-11, -4, 22, 8), border_radius=3)
        pygame.draw.rect(s, (90, 96, 106), R(-10, -3, 20, 6), border_radius=3)
        pygame.draw.circle(s, (120, 200, 255), (x + int(9 * k), y), max(2, int(3 * k)))
        pygame.draw.rect(s, (60, 64, 72), R(-4, 3, 3, 4))
        pygame.draw.rect(s, (60, 64, 72), R(3, 3, 3, 4))
    elif item == "maos":
        pygame.draw.circle(s, (214, 168, 128), (x, y), max(3, int(6 * k)))
        pygame.draw.circle(s, (170, 128, 96), (x, y), max(3, int(6 * k)), 1)
    elif item == "galao":
        pygame.draw.rect(s, (20, 20, 24), R(-8, -8, 16, 17), border_radius=2)
        pygame.draw.rect(s, (200, 40, 30), R(-7, -7, 14, 15), border_radius=2)
        pygame.draw.rect(s, (40, 40, 44), R(1, -11, 5, 4))
        pygame.draw.line(s, (240, 200, 60), (x - 4 * k, y + 4 * k), (x + 4 * k, y - 4 * k), max(1, int(2 * k)))
    elif item.startswith("lanterna") and item[8:].isdigit():
        n = int(item[8:])
        corpo = [(70, 70, 76), (40, 44, 52), (50, 64, 44), (30, 32, 34)][n]
        comp = 14 + n * 2
        pygame.draw.rect(s, (14, 14, 16), R(-comp // 2 - 1, -4, comp + 2, 8), border_radius=2)
        pygame.draw.rect(s, corpo, R(-comp // 2, -3, comp, 6), border_radius=2)
        pygame.draw.rect(s, (14, 14, 16), R(comp // 2 - 3, -6 - n, 7, 12 + 2 * n), border_radius=2)
        pygame.draw.rect(s, (255, 240, 150), R(comp // 2 + 1, -5 - n, 3, 10 + 2 * n))
        for i in range(n + 1):
            pygame.draw.line(s, (255, 240, 150), (x + (comp // 2 + 6) * k, y), (x + (comp // 2 + 12 + i * 3) * k,
                             y + (i - n / 2) * 4 * k), 1)
    elif item == "colete":
        pygame.draw.polygon(s, (14, 14, 16), [(x - 10 * k, y - 10 * k), (x + 10 * k, y - 10 * k), (x + 11 * k, y + 11 * k),
                                              (x - 11 * k, y + 11 * k)])
        pygame.draw.polygon(s, (70, 84, 56), [(x - 9 * k, y - 9 * k), (x + 9 * k, y - 9 * k), (x + 10 * k, y + 10 * k),
                                              (x - 10 * k, y + 10 * k)])
        pygame.draw.rect(s, (14, 14, 16), R(-3, -10, 6, 6))
        for yy in (-2, 4):
            pygame.draw.rect(s, (50, 60, 40), R(-8, yy, 16, 3))
    elif item == "capacete":
        pygame.draw.circle(s, (14, 14, 16), (x, y), int(11 * k))
        pygame.draw.circle(s, (78, 92, 60), (x, y), int(10 * k))
        pygame.draw.circle(s, (110, 126, 86), (x - int(3 * k), y - int(3 * k)), int(4 * k))
        pygame.draw.rect(s, (40, 46, 32), R(-11, 3, 22, 3))
    elif item == "calca":
        for lado in (-1, 1):
            pygame.draw.polygon(s, (14, 14, 16), [(x, y - 10 * k), (x + lado * 10 * k, y - 10 * k),
                                                  (x + lado * 9 * k, y + 12 * k), (x + lado * 2 * k, y + 12 * k)])
            pygame.draw.polygon(s, (60, 70, 90), [(x, y - 9 * k), (x + lado * 9 * k, y - 9 * k),
                                                  (x + lado * 8 * k, y + 11 * k), (x + lado * 3 * k, y + 11 * k)])
            pygame.draw.rect(s, (90, 100, 70), R(lado * 6 - 3, 1, 6, 4))
        pygame.draw.rect(s, (40, 30, 24), R(-10, -10, 20, 3))
    elif item == "seringa":
        pygame.draw.line(s, (200, 200, 210), (x - 11 * k, y + 8 * k), (x + 6 * k, y - 9 * k), max(1, int(6 * k)))
        pygame.draw.line(s, (240, 60, 70), (x - 8 * k, y + 5 * k), (x + 3 * k, y - 6 * k), max(1, int(3 * k)))
        pygame.draw.line(s, (150, 150, 160), (x + 6 * k, y - 9 * k), (x + 11 * k, y - 14 * k), max(1, int(1.5 * k)))
        pygame.draw.line(s, (90, 90, 100), (x - 14 * k, y + 5 * k), (x - 8 * k, y + 11 * k), max(1, int(3 * k)))
    elif item == "saco":
        pygame.draw.rect(s, (40, 70, 120), R(-12, -6, 24, 12), border_radius=6)
        pygame.draw.rect(s, (70, 110, 170), R(-12, -6, 9, 12), border_radius=5)
        for i in (-2, 3, 8):
            pygame.draw.line(s, (30, 50, 90), (x + i * k, y - 6 * k), (x + i * k, y + 6 * k), 1)
    elif item == "mochila":
        pygame.draw.rect(s, (90, 70, 44), R(-8, -9, 16, 18), border_radius=4)
        pygame.draw.rect(s, (120, 94, 60), R(-6, -2, 12, 8), border_radius=2)
    elif item.startswith("mochila"):
        from config import MOCHILAS
        n = int(item[7:])
        c = MOCHILAS[n][2]
        g = 1 + n * 0.12
        pygame.draw.rect(s, tom(c, -30), R(-9 * g, -10 * g, 18 * g, 20 * g), border_radius=5)
        pygame.draw.rect(s, c, R(-8 * g, -9 * g, 16 * g, 18 * g), border_radius=5)
        pygame.draw.rect(s, tom(c, 30), R(-6 * g, -1 * g, 12 * g, 8 * g), border_radius=2)
        pygame.draw.rect(s, (30, 30, 30), R(-4, -12 * g, 8, 3), border_radius=1)
    else:  # armas
        L = {"faca": 14, "machado": 18, "pistola": 12, "espingarda": 22, "fuzil": 22, "rifle": 24, "smg": 16, "minigun": 24,
             "dragao": 22, "dourado": 26}.get(item, 16)
        if item == "machado":
            pygame.draw.line(s, (120, 86, 54), (x - 9 * k, y + 5 * k), (x + 7 * k, y - 5 * k), max(2, int(3 * k)))
            pygame.draw.polygon(s, (175, 180, 186), [(x + 4 * k, y - 10 * k), (x + 11 * k, y - 6 * k),
                                                     (x + 7 * k, y + 1 * k), (x + 2 * k, y - 4 * k)])
        elif item == "katana":
            pygame.draw.rect(s, (30, 30, 34), R(-13, -2, 7, 4))
            pygame.draw.line(s, (220, 224, 232), (x - 6 * k, y), (x + 14 * k, y - 4 * k), max(2, int(2.5 * k)))
        elif item == "rpg":
            pygame.draw.rect(s, (20, 24, 18), R(-13, -4, 22, 8))
            pygame.draw.rect(s, (90, 116, 70), R(-12, -3, 20, 6))
            pygame.draw.polygon(s, (150, 150, 140), [(x + 8 * k, y - 5 * k), (x + 15 * k, y), (x + 8 * k, y + 5 * k)])
            pygame.draw.rect(s, (60, 64, 50), R(-4, 2, 4, 6))
        elif item == "facao":
            pygame.draw.rect(s, (60, 44, 30), R(-11, -2, 6, 4))
            pygame.draw.polygon(s, (200, 205, 212), [(x - 5 * k, y - 3 * k), (x + 12 * k, y - 4 * k),
                                                     (x + 13 * k, y), (x - 5 * k, y + 2 * k)])
        elif item == "besta":
            pygame.draw.rect(s, (110, 80, 50), R(-10, -2, 20, 4))
            pygame.draw.line(s, (120, 90, 60), (x + 4 * k, y - 9 * k), (x + 4 * k, y + 9 * k), max(2, int(3 * k)))
            pygame.draw.line(s, (220, 220, 210), (x + 4 * k, y - 9 * k), (x - 6 * k, y), 1)
            pygame.draw.line(s, (220, 220, 210), (x + 4 * k, y + 9 * k), (x - 6 * k, y), 1)
        elif item == "faca":
            pygame.draw.rect(s, (80, 60, 40), R(-8, -2, 6, 4))
            pygame.draw.polygon(s, (205, 210, 215), [(x - 2 * k, y - 2 * k), (x + 8 * k, y - 1 * k), (x - 2 * k, y + 2 * k)])
        elif item == "taco":
            pygame.draw.line(s, (90, 60, 34), (x - 12 * k, y + 4 * k), (x + 12 * k, y - 4 * k), max(3, int(5 * k)))
            pygame.draw.line(s, (170, 124, 72), (x - 12 * k, y + 3 * k), (x + 12 * k, y - 5 * k), max(1, int(3 * k)))
            for px in (4, 8, 11):
                pygame.draw.line(s, (210, 210, 220), (x + px * k, y - (px / 3 + 4) * k), (x + px * k, y - (px / 3 - 2) * k), 1)
        elif item in COMP_ARMA:
            kk = k * 0.78
            desenha_arma(s, item, x - COMP_ARMA[item] * kk / 2, y, kk)
        else:
            corpo = {"dourado": (232, 186, 60), "dragao": (196, 60, 44), "minigun": (150, 154, 164)}.get(item, (120, 124, 134))
            pygame.draw.rect(s, (20, 20, 24), R(-L // 2 - 1, -3, L + 2, 6))
            pygame.draw.rect(s, corpo, R(-L // 2, -2, L, 4))
            pygame.draw.rect(s, (190, 194, 204), R(-L // 2, -2, L, 1))
            pygame.draw.rect(s, (20, 20, 24), R(-L // 2 + 1, 0, 6, 9))
            pygame.draw.rect(s, corpo, R(-L // 2 + 2, 0, 4, 8))
            if item in ("espingarda", "rifle"):
                pygame.draw.rect(s, (150, 104, 62), R(-L // 2 - 4, -2, 8, 6))
            if item in ("fuzil", "smg"):
                pygame.draw.rect(s, corpo, R(1, 1, 3, 8))
            if item == "rifle":
                pygame.draw.rect(s, (60, 62, 70), R(-2, -5, 8, 3))


# ------------------------------------------------------------------ armas de fogo (desenho detalhado)
COMP_ARMA = {"pistola": 17, "revolver": 21, "smg": 23, "espingarda": 35, "fuzil": 35, "rifle": 40, "besta": 26,
             "minigun": 38, "dragao": 34, "dourado": 42, "rpg": 40}


def desenha_arma(s, arma, x, y, k=1.0):
    """Arma deitada, coronha na esquerda (x) e cano na direita, no meio da altura y."""
    def R(a, b, w, h):
        return pygame.Rect(int(x + a * k), int(y + b * k), max(1, int(round(w * k))), max(1, int(round(h * k))))

    def P(pts):
        return [(x + a * k, y + b * k) for a, b in pts]

    preto = (18, 18, 22)
    aco = (58, 62, 70)
    aco_claro = (120, 126, 138)
    madeira = (138, 88, 48)
    madeira_e = (96, 60, 32)

    def peca(r, cor, brilho=True):
        pygame.draw.rect(s, preto, r.inflate(2, 2))
        pygame.draw.rect(s, cor, r)
        if brilho and r.h >= 3:
            pygame.draw.line(s, tom(cor, 45), r.topleft, (r.right - 1, r.top), 1)

    if arma == "pistola":
        peca(R(1, 1, 5, 8), (34, 34, 38), False)
        peca(R(0, -3, 17, 5), aco)
        pygame.draw.rect(s, preto, R(6, 2, 4, 3), 1)
        pygame.draw.rect(s, preto, R(15, -2, 2, 2))
    elif arma == "revolver":
        peca(R(0, 0, 6, 8), madeira)
        peca(R(4, -3, 7, 5), aco_claro)
        pygame.draw.circle(s, preto, (int(x + 9 * k), int(y)), int(4.5 * k))
        pygame.draw.circle(s, (150, 156, 168), (int(x + 9 * k), int(y)), int(3.5 * k))
        pygame.draw.circle(s, preto, (int(x + 9 * k), int(y)), max(1, int(1 * k)))
        peca(R(12, -2, 9, 3), aco_claro)
    elif arma == "smg":
        pygame.draw.line(s, aco, (x, y - 1 * k), (x + 4 * k, y - 1 * k), max(1, int(2 * k)))
        peca(R(3, -3, 15, 6), (48, 52, 58))
        peca(R(9, 2, 4, 10), preto, False)
        peca(R(4, 2, 3, 5), (34, 34, 38), False)
        peca(R(18, -1, 5, 2), aco)
    elif arma in ("espingarda", "dragao"):
        corpo = (160, 44, 34) if arma == "dragao" else (52, 54, 60)
        peca(R(0, -3, 11, 6), madeira if arma == "espingarda" else (110, 30, 24))
        pygame.draw.line(s, madeira_e, (x + 2 * k, y + 2 * k), (x + 9 * k, y + 2 * k), 1)
        peca(R(10, -3, 7, 6), corpo)
        peca(R(17, -2, 17, 3), (78, 82, 90) if arma == "espingarda" else (200, 160, 60))
        peca(R(19, 1, 9, 4), (156, 108, 64) if arma == "espingarda" else (60, 60, 64))
        if arma == "dragao":
            pygame.draw.circle(s, preto, (int(x + 13 * k), int(y + 6 * k)), int(4 * k))
            pygame.draw.circle(s, (200, 160, 60), (int(x + 13 * k), int(y + 6 * k)), int(3 * k))
    elif arma == "fuzil":
        peca(R(0, -3, 10, 6), madeira)
        peca(R(10, -3, 12, 6), (56, 58, 62))
        pygame.draw.polygon(s, preto, P([(14, 2), (19, 2), (22, 12), (16, 13)]))
        pygame.draw.polygon(s, (60, 54, 44), P([(15, 3), (18, 3), (20, 11), (17, 12)]))
        peca(R(22, -2, 7, 5), madeira)
        peca(R(29, -1, 6, 2), aco)
        pygame.draw.rect(s, preto, R(30, -4, 1, 3))
    elif arma in ("rifle", "dourado"):
        dourado = arma == "dourado"
        corpo = (214, 172, 60) if dourado else (64, 74, 52)
        peca(R(0, -3, 12, 6), corpo)
        peca(R(12, -2, 14, 5), (150, 118, 40) if dourado else (44, 48, 42))
        peca(R(26, -1, 16 if dourado else 14, 2), (190, 150, 50) if dourado else (40, 40, 42))
        peca(R(13, -8, 14, 4), (28, 28, 32))
        pygame.draw.rect(s, (110, 200, 255), R(26, -8, 2, 4))
        pygame.draw.line(s, preto, (x + 18 * k, y + 3 * k), (x + 22 * k, y + 9 * k), 1)
        pygame.draw.line(s, preto, (x + 22 * k, y + 3 * k), (x + 18 * k, y + 9 * k), 1)
    elif arma == "minigun":
        peca(R(0, -5, 14, 10), (74, 76, 84))
        peca(R(2, 5, 9, 7), (80, 90, 60))
        for yy in (-3, 0, 3):
            peca(R(14, yy - 1, 24, 2), (150, 154, 164), False)
        pygame.draw.rect(s, preto, R(14, -5, 2, 10))
        pygame.draw.rect(s, preto, R(30, -5, 2, 10))
    elif arma == "rpg":
        peca(R(0, -4, 30, 8), (76, 98, 60))
        peca(R(8, 4, 4, 6), (50, 54, 44), False)
        peca(R(18, 4, 3, 5), (50, 54, 44), False)
        pygame.draw.polygon(s, preto, P([(29, -6), (40, 0), (29, 6)]))
        pygame.draw.polygon(s, (150, 150, 138), P([(30, -5), (38, 0), (30, 5)]))
    elif arma == "besta":
        peca(R(0, -2, 20, 4), (110, 80, 50))
        pygame.draw.line(s, (120, 90, 60), (x + 18 * k, y - 11 * k), (x + 18 * k, y + 11 * k), max(2, int(3 * k)))
        pygame.draw.line(s, (220, 220, 210), (x + 18 * k, y - 11 * k), (x + 8 * k, y), 1)
        pygame.draw.line(s, (220, 220, 210), (x + 18 * k, y + 11 * k), (x + 8 * k, y), 1)
        pygame.draw.line(s, (200, 200, 210), (x + 8 * k, y), (x + 26 * k, y), 1)
    else:
        peca(R(0, -2, COMP_ARMA.get(arma, 16), 4), aco)
    return COMP_ARMA.get(arma, 16)



# ------------------------------------------------------------------ construcoes
def sprite_barricada():
    s = pygame.Surface((76, 26), pygame.SRCALPHA)
    for i in range(3):
        y = 3 + i * 7
        pygame.draw.rect(s, (96, 66, 40), (2 + i * 2, y, 70, 7), border_radius=2)
        pygame.draw.rect(s, (138, 98, 60), (3 + i * 2, y + 1, 68, 4), border_radius=2)
        for px in (10, 36, 62):
            pygame.draw.circle(s, (60, 60, 60), (px + i * 2, y + 3), 1)
    pygame.draw.line(s, (80, 54, 32), (8, 2), (66, 24), 5)
    return s


def sprite_arame():
    s = pygame.Surface((80, 30), pygame.SRCALPHA)
    for px in (6, 40, 74):
        pygame.draw.rect(s, (90, 70, 46), (px - 2, 4, 5, 22), border_radius=1)
    for k, yy in enumerate((9, 15, 21)):
        pts = [(2 + i * 4, yy + (2 if (i + k) % 2 else -2)) for i in range(20)]
        pygame.draw.lines(s, (150, 150, 158), False, pts, 1)
        for i in range(2, 20, 3):
            pygame.draw.line(s, (190, 190, 196), (pts[i][0] - 2, pts[i][1] - 2), (pts[i][0] + 2, pts[i][1] + 2), 1)
    return s


def sprite_ponte():
    s = pygame.Surface((96, 96), pygame.SRCALPHA)
    for i in range(8):
        pygame.draw.rect(s, (110, 80, 50), (0, i * 12, 96, 11))
        pygame.draw.rect(s, (150, 112, 70), (0, i * 12 + 1, 96, 7))
    return s


def sprite_cachorro(passo=0):
    """Cachorro visto de cima, virado para a direita. passo 0/1 mexe as patas e o rabo."""
    s = pygame.Surface((56, 40), pygame.SRCALPHA)
    pelo, escuro = (150, 100, 52), (98, 62, 30)
    d = 3 if passo else -3
    for px, py in ((16, 11 + d), (16, 29 - d), (34, 11 - d), (34, 29 + d)):  # patas
        pygame.draw.ellipse(s, escuro, (px - 3, py - 3, 7, 6))
    pygame.draw.line(s, escuro, (12, 20), (3, 20 + d * 2), 4)  # rabo
    pygame.draw.ellipse(s, escuro, (11, 11, 30, 18))
    pygame.draw.ellipse(s, pelo, (12, 12, 28, 16))
    pygame.draw.ellipse(s, (180, 130, 76), (18, 15, 14, 9))
    pygame.draw.circle(s, escuro, (42, 20), 9)
    pygame.draw.circle(s, pelo, (42, 20), 8)
    pygame.draw.ellipse(s, escuro, (36, 9, 8, 7))     # orelhas
    pygame.draw.ellipse(s, escuro, (36, 24, 8, 7))
    pygame.draw.ellipse(s, (60, 40, 24), (47, 17, 6, 6))  # focinho
    pygame.draw.circle(s, (20, 14, 10), (44, 16), 1)
    pygame.draw.circle(s, (20, 14, 10), (44, 24), 1)
    pygame.draw.rect(s, (200, 40, 40), (32, 14, 3, 12))   # coleira
    return contorno(vivo(s, 1.2, 1.05))


def sprite_bancada():
    s = pygame.Surface((64, 40), pygame.SRCALPHA)
    pygame.draw.rect(s, (70, 48, 30), (2, 6, 60, 30), border_radius=3)
    pygame.draw.rect(s, (140, 100, 62), (4, 8, 56, 22), border_radius=2)
    for x in (12, 26, 40):
        pygame.draw.line(s, (110, 78, 48), (x, 8), (x, 30), 1)
    pygame.draw.rect(s, (120, 124, 134), (8, 12, 14, 6))      # morsa
    pygame.draw.rect(s, (70, 72, 80), (12, 18, 6, 6))
    pygame.draw.line(s, (150, 104, 62), (34, 14), (52, 22), 3)  # martelo
    pygame.draw.rect(s, (110, 114, 124), (49, 17, 8, 7))
    pygame.draw.circle(s, (180, 184, 194), (28, 24), 3)        # parafusos
    pygame.draw.circle(s, (180, 184, 194), (36, 26), 2)
    return s


def sprite_muro():
    s = pygame.Surface((100, 22), pygame.SRCALPHA)
    pygame.draw.rect(s, (60, 46, 34), (0, 2, 100, 18), border_radius=3)
    for i in range(6):
        pygame.draw.rect(s, (128, 96, 62), (2 + i * 16, 4, 14, 14), border_radius=2)
        pygame.draw.line(s, (90, 66, 42), (4 + i * 16, 8), (14 + i * 16, 8), 1)
    pygame.draw.rect(s, (120, 124, 134), (0, 9, 100, 3))
    for x in (8, 50, 92):
        pygame.draw.circle(s, (170, 174, 184), (x, 10), 2)
    return s


def sprite_portao(aberto=False):
    s = pygame.Surface((100, 22), pygame.SRCALPHA)
    if aberto:  # aberto: so os postes
        for x in (0, 90):
            pygame.draw.rect(s, (70, 52, 36), (x, 0, 10, 22), border_radius=2)
        return s
    for x in (0, 90):
        pygame.draw.rect(s, (70, 52, 36), (x, 0, 10, 22), border_radius=2)
    pygame.draw.rect(s, (150, 110, 66), (10, 4, 80, 14))
    for x in range(12, 90, 10):
        pygame.draw.line(s, (110, 80, 50), (x, 4), (x, 17), 1)
    pygame.draw.rect(s, (110, 114, 124), (10, 6, 80, 2))
    pygame.draw.rect(s, (110, 114, 124), (10, 14, 80, 2))
    pygame.draw.circle(s, (220, 200, 90), (50, 11), 3)
    return s


def sprite_bau():
    s = pygame.Surface((40, 30), pygame.SRCALPHA)
    pygame.draw.rect(s, (70, 48, 28), (2, 4, 36, 24), border_radius=4)
    pygame.draw.rect(s, (146, 100, 56), (4, 6, 32, 20), border_radius=3)
    pygame.draw.rect(s, (110, 74, 40), (4, 12, 32, 3))
    pygame.draw.rect(s, (200, 170, 80), (17, 11, 6, 7), border_radius=1)
    return s


def sprite_escada():
    """Escada de pe, encostada (vista de cima, comprida na vertical)."""
    s = pygame.Surface((20, 46), pygame.SRCALPHA)
    for x in (3, 15):
        pygame.draw.rect(s, (70, 48, 28), (x - 1, 0, 4, 46))
        pygame.draw.rect(s, (150, 104, 58), (x, 0, 2, 46))
    for y in range(4, 44, 7):
        pygame.draw.rect(s, (70, 48, 28), (3, y - 1, 14, 4))
        pygame.draw.rect(s, (170, 122, 70), (3, y, 14, 2))
    return s


def luneta_mascara(raio):
    """Tela preta com um buraco redondo e a cruz da mira (visao pela luneta)."""
    s = pygame.Surface((raio * 2 + 2 * 1400, raio * 2 + 2 * 800), pygame.SRCALPHA)
    s.fill((0, 0, 0, 255))
    cx, cy = s.get_width() // 2, s.get_height() // 2
    pygame.draw.circle(s, (0, 0, 0, 0), (cx, cy), raio)
    pygame.draw.circle(s, (10, 10, 10, 255), (cx, cy), raio, 10)
    for d in (-1, 1):
        pygame.draw.line(s, (10, 10, 10, 230), (cx + d * 18, cy), (cx + d * raio, cy), 2)
        pygame.draw.line(s, (10, 10, 10, 230), (cx, cy + d * 18), (cx, cy + d * raio), 2)
    pygame.draw.circle(s, (220, 30, 30, 255), (cx, cy), 3)
    return s


def sprite_fogueira():
    s = pygame.Surface((40, 40), pygame.SRCALPHA)
    for i in range(10):
        a = i / 10 * 6.283
        pygame.draw.circle(s, (110, 108, 104), (20 + math.cos(a) * 14, 20 + math.sin(a) * 14), 5)
        pygame.draw.circle(s, (140, 138, 132), (19 + math.cos(a) * 14, 19 + math.sin(a) * 14), 3)
    for a in (0.3, 1.9, 3.6, 5.0):
        pygame.draw.line(s, (90, 60, 36), (20 - math.cos(a) * 9, 20 - math.sin(a) * 9),
                         (20 + math.cos(a) * 9, 20 + math.sin(a) * 9), 4)
    pygame.draw.circle(s, (40, 30, 26), (20, 20), 5)
    return s


def sprite_abrigo():
    s = pygame.Surface((112, 112), pygame.SRCALPHA)
    c = 56
    for i in range(22):  # anel de sacos de areia
        a = i / 22 * 6.283
        x = c + math.cos(a) * 46
        y = c + math.sin(a) * 46
        pygame.draw.ellipse(s, (130, 116, 80), (x - 9, y - 6, 18, 12))
        pygame.draw.ellipse(s, (160, 146, 104), (x - 7, y - 5, 13, 8))
    pygame.draw.circle(s, (88, 84, 74), (c, c), 30)
    pygame.draw.circle(s, (70, 76, 70), (c, c), 17)
    pygame.draw.circle(s, (96, 104, 96), (c, c), 15)
    pygame.draw.circle(s, (60, 64, 60), (c, c), 6, 2)
    pygame.draw.line(s, (60, 64, 60), (c - 12, c), (c + 12, c), 2)
    return s


def sprite_torre():
    s = pygame.Surface((150, 150), pygame.SRCALPHA)
    c = 75
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        pygame.draw.line(s, (150, 40, 36), (c, c), (c + math.cos(a) * 66, c + math.sin(a) * 66), 3)
    for r in (20, 38, 56):
        pygame.draw.rect(s, (190, 190, 190), (c - r * 0.7, c - r * 0.7, r * 1.4, r * 1.4), 2)
    pygame.draw.rect(s, (220, 60, 50), (c - 14, c - 14, 28, 28))
    pygame.draw.rect(s, (240, 240, 240), (c - 8, c - 8, 16, 16))
    pygame.draw.circle(s, (255, 60, 50), (c, c), 4)
    return s


def sprite_cama(hospital):
    s = pygame.Surface((26, 52), pygame.SRCALPHA)
    pygame.draw.rect(s, (90, 90, 96) if hospital else (70, 80, 60), (0, 0, 26, 52), border_radius=3)
    pygame.draw.rect(s, (232, 234, 236) if hospital else (150, 140, 110), (2, 2, 22, 48), border_radius=3)
    pygame.draw.rect(s, (250, 250, 250) if hospital else (190, 182, 150), (4, 3, 18, 10), border_radius=4)
    pygame.draw.rect(s, (130, 170, 210) if hospital else (90, 100, 70), (2, 18, 22, 32), border_radius=3)
    return s


def desenha_movel(s, tipo, aberto, x, y):
    x = int(x)
    y = int(y)
    if tipo == "geladeira":
        pygame.draw.rect(s, (120, 124, 128), (x - 11, y - 13, 22, 26), border_radius=3)
        pygame.draw.rect(s, (214, 218, 222), (x - 10, y - 12, 20, 24), border_radius=3)
        pygame.draw.line(s, (150, 150, 155), (x - 10, y - 2), (x + 10, y - 2), 2)
    elif tipo == "armario":
        pygame.draw.rect(s, (70, 48, 30), (x - 15, y - 9, 30, 18), border_radius=2)
        pygame.draw.rect(s, (116, 82, 52), (x - 14, y - 8, 28, 16), border_radius=2)
        pygame.draw.line(s, (70, 48, 30), (x, y - 8), (x, y + 8), 2)
    elif tipo == "gaveta":
        pygame.draw.rect(s, (80, 56, 36), (x - 11, y - 9, 22, 18), border_radius=2)
        pygame.draw.rect(s, (138, 100, 64), (x - 10, y - 8, 20, 16), border_radius=2)
        for yy in (-4, 2):
            pygame.draw.line(s, (90, 64, 40), (x - 10, y + yy), (x + 10, y + yy), 1)
            pygame.draw.circle(s, (200, 180, 120), (x, y + yy - 2), 1)
    elif tipo == "medico":
        pygame.draw.rect(s, (150, 154, 160), (x - 12, y - 10, 24, 20), border_radius=2)
        pygame.draw.rect(s, (236, 238, 240), (x - 11, y - 9, 22, 18), border_radius=2)
        pygame.draw.rect(s, (210, 40, 40), (x - 2, y - 6, 4, 12))
        pygame.draw.rect(s, (210, 40, 40), (x - 6, y - 2, 12, 4))
    elif tipo == "militar":
        pygame.draw.rect(s, (46, 56, 36), (x - 15, y - 10, 30, 20), border_radius=2)
        pygame.draw.rect(s, (76, 90, 56), (x - 14, y - 9, 28, 18), border_radius=2)
        pygame.draw.rect(s, (46, 56, 36), (x - 14, y - 2, 28, 3))
        pygame.draw.rect(s, (200, 190, 120), (x - 4, y - 7, 8, 3))
    elif tipo == "prateleira":
        pygame.draw.rect(s, (70, 74, 80), (x - 26, y - 9, 52, 18), border_radius=2)
        pygame.draw.rect(s, (130, 136, 146), (x - 25, y - 8, 50, 16), border_radius=2)
        pygame.draw.line(s, (80, 84, 92), (x - 25, y), (x + 25, y), 2)
        if not aberto:
            cores = [(200, 60, 50), (60, 140, 210), (230, 190, 60), (90, 170, 90), (220, 120, 40)]
            for k in range(6):
                pygame.draw.rect(s, cores[(k + x // 7) % 5], (x - 23 + k * 8, y - 7, 6, 6))
                pygame.draw.rect(s, cores[(k + y // 5) % 5], (x - 23 + k * 8, y + 2, 6, 5))
    elif tipo == "vitrine":
        pygame.draw.rect(s, (60, 46, 34), (x - 24, y - 11, 48, 22), border_radius=2)
        pygame.draw.rect(s, (150, 196, 220), (x - 22, y - 9, 44, 18), border_radius=2)
        if not aberto:
            pygame.draw.rect(s, (40, 40, 44), (x - 14, y - 2, 22, 4))
            pygame.draw.rect(s, (40, 40, 44), (x - 12, y + 1, 4, 5))
        pygame.draw.line(s, (230, 245, 255), (x - 20, y - 8), (x - 8, y - 8), 2)
    elif tipo == "despensa":
        pygame.draw.rect(s, (60, 62, 58), (x - 26, y - 12, 52, 24), border_radius=2)
        pygame.draw.rect(s, (110, 112, 104), (x - 25, y - 11, 50, 22), border_radius=2)
        pygame.draw.line(s, (60, 62, 58), (x - 25, y), (x + 25, y), 2)
        if not aberto:
            for k in range(5):
                desenha_icone(s, "comida", x - 20 + k * 10, y - 6, 0.5)
                desenha_icone(s, "agua", x - 20 + k * 10, y + 6, 0.5)
    elif tipo == "arsenal":
        pygame.draw.rect(s, (40, 44, 36), (x - 26, y - 12, 52, 24), border_radius=2)
        pygame.draw.rect(s, (70, 78, 60), (x - 25, y - 11, 50, 22), border_radius=2)
        if not aberto:
            for k, arma in enumerate(("fuzil", "rifle")):
                desenha_icone(s, arma, x, y - 5 + k * 10, 0.9)
        pygame.draw.rect(s, (200, 190, 120), (x - 3, y - 11, 6, 3))
    elif tipo == "mochila":
        desenha_icone(s, "mochila", x, y, 1.3)
    elif tipo == "porta_malas":
        return
    else:  # caixa
        pygame.draw.rect(s, (110, 84, 50), (x - 11, y - 11, 22, 22), border_radius=2)
        pygame.draw.rect(s, (168, 132, 84), (x - 10, y - 10, 20, 20), border_radius=2)
        pygame.draw.line(s, (110, 84, 50), (x - 9, y - 9), (x + 9, y + 9), 2)
        pygame.draw.line(s, (110, 84, 50), (x + 9, y - 9), (x - 9, y + 9), 2)
    if aberto:
        sombra = pygame.Surface((24, 18), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 90))
        s.blit(sombra, (x - 12, y - 9))


# ------------------------------------------------------------------ luzes
def luz_redonda(R, forca=1.0, expo=1.6):
    s = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    yy, xx = np.mgrid[0:R * 2, 0:R * 2]
    d = np.sqrt((xx - R + 0.5) ** 2 + (yy - R + 0.5) ** 2) / R
    a = np.clip(1 - d, 0, 1) ** expo * 255 * forca
    alfa = pygame.surfarray.pixels_alpha(s)
    alfa[:] = a.T.astype(np.uint8)
    del alfa
    return s


def luz_cone(L, meio_ang=0.42):
    s = pygame.Surface((L * 2, L * 2), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    yy, xx = np.mgrid[0:L * 2, 0:L * 2]
    dx = xx - L + 0.5
    dy = yy - L + 0.5
    d = np.sqrt(dx * dx + dy * dy) / L
    ang = np.abs(np.arctan2(dy, dx))
    ang_f = np.clip(1 - (ang / meio_ang) ** 2, 0, 1)
    rad = np.clip(1 - d, 0, 1) ** 0.7
    a = np.clip(rad * ang_f * 1.25, 0, 1) * 255
    alfa = pygame.surfarray.pixels_alpha(s)
    alfa[:] = a.T.astype(np.uint8)
    del alfa
    return s


def vinheta():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((d - 0.55) / 0.85, 0, 1) ** 1.5 * 170
    alfa = pygame.surfarray.pixels_alpha(s)
    alfa[:] = a.T.astype(np.uint8)
    del alfa
    return s


def vinheta_vermelha():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    s.fill((170, 0, 0, 0))
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((d - 0.35) / 0.8, 0, 1) * 255
    alfa = pygame.surfarray.pixels_alpha(s)
    alfa[:] = a.T.astype(np.uint8)
    del alfa
    return s


# ------------------------------------------------------------------ sons
def criar_sons():
    sons = {}
    try:
        if not pygame.mixer.get_init():
            return sons
        freq, _, canais = pygame.mixer.get_init()
        rng = np.random.default_rng(3)

        def fazer(onda, vol=0.6):
            onda = onda / (np.max(np.abs(onda)) + 1e-9) * vol
            arr = (onda * 32767).astype(np.int16)
            if canais == 2:
                arr = np.column_stack([arr, arr])
            return pygame.sndarray.make_sound(np.ascontiguousarray(arr))

        def t_(seg):
            return np.arange(int(freq * seg)) / freq

        def ruido(n):
            return rng.uniform(-1, 1, n)

        def passa_baixa(x, k):
            y = np.copy(x)
            for _ in range(k):
                y = np.convolve(y, np.ones(5) / 5, mode="same")
            return y

        t = t_(0.45)
        sons["pistola"] = fazer(passa_baixa(ruido(len(t)), 1) * np.exp(-t * 16) + 0.7 * np.sin(2 * np.pi * 110 * t) * np.exp(-t * 20), 0.55)
        t = t_(0.8)
        sons["espingarda"] = fazer(passa_baixa(ruido(len(t)), 3) * np.exp(-t * 7) + 0.9 * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 9), 0.8)
        t = t_(0.35)
        sons["fuzil"] = fazer(passa_baixa(ruido(len(t)), 1) * np.exp(-t * 20) + 0.6 * np.sin(2 * np.pi * 95 * t) * np.exp(-t * 18), 0.5)
        t = t_(1.0)
        sons["rifle"] = fazer(passa_baixa(ruido(len(t)), 2) * np.exp(-t * 6) + 1.0 * np.sin(2 * np.pi * 60 * t) * np.exp(-t * 7), 0.85)
        t = t_(0.18)
        sons["silencioso"] = fazer(passa_baixa(ruido(len(t)), 6) * np.exp(-t * 30), 0.35)
        t = t_(0.2)
        sons["faca"] = fazer(ruido(len(t)) * np.sin(np.pi * t / 0.2) * 0.5, 0.25)
        t = t_(0.25)
        sons["golpe"] = fazer(passa_baixa(ruido(len(t)), 4) * np.exp(-t * 25) + np.sin(2 * np.pi * 80 * t) * np.exp(-t * 30), 0.5)
        t = t_(0.12)
        sons["clique"] = fazer(np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 60), 0.3)
        t = t_(0.5)
        sons["recarga"] = fazer(np.where((t % 0.25) < 0.03, np.sin(2 * np.pi * 1200 * t), 0) * np.exp(-t * 2), 0.3)
        t = t_(0.25)
        sons["pegar"] = fazer(np.sin(2 * np.pi * (600 + 600 * t / 0.25) * t) * np.exp(-t * 10), 0.25)
        t = t_(0.35)
        sons["dor"] = fazer(passa_baixa(ruido(len(t)), 5) * np.exp(-t * 12) + 0.6 * np.sin(2 * np.pi * 140 * t) * np.exp(-t * 10), 0.55)
        for i, base in enumerate((70, 85, 100)):
            t = t_(1.3)
            vib = np.sin(2 * np.pi * 5.5 * t) * 6
            onda = np.sign(np.sin(2 * np.pi * (base + vib) * t)) * 0.4 + passa_baixa(ruido(len(t)), 3)
            env = np.sin(np.pi * t / 1.3) ** 1.5
            sons[f"gemido{i}"] = fazer(passa_baixa(onda, 4) * env, 0.32)
        t = t_(2.0)
        sons["chuva"] = fazer(passa_baixa(ruido(len(t)), 2), 0.12)
        t = t_(1.0)
        sons["fogo"] = fazer(passa_baixa(ruido(len(t)), 8) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 3 * t))), 0.12)
        t = t_(1.2)
        sons["comer"] = fazer(passa_baixa(ruido(len(t)), 3) * (np.sin(2 * np.pi * 4 * t) > 0.3), 0.2)
        t = t_(1.6)
        sons["helicoptero"] = fazer(passa_baixa(ruido(len(t)), 3) * (0.5 + 0.5 * (np.sin(2 * np.pi * 9 * t) > 0)), 0.5)
    except Exception:
        return {}
    return sons
