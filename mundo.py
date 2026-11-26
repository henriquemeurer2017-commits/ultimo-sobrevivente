"""Geracao do mundo aberto (mato, lagos, estradas, cidades, hospitais, bunkers) e desenho dos pedacos do chao."""
import math
import random

import numpy as np
import pygame

import graficos as G
from config import *


def ruido(rng, n, cell):
    g = n // cell + 2
    grid = rng.random((g, g))
    c = np.arange(n) / cell
    i = c.astype(int)
    f = c - i
    f = f * f * (3 - 2 * f)
    a = grid[i][:, i]
    b = grid[i][:, i + 1]
    cc = grid[i + 1][:, i]
    d = grid[i + 1][:, i + 1]
    top = a + (b - a) * f[None, :]
    bot = cc + (d - cc) * f[None, :]
    return top + (bot - top) * f[:, None]


def fbm(rng, n, camadas):
    return sum(w * ruido(rng, n, c) for c, w in camadas)


def sortear(rnd, tabela, n):
    itens = []
    total = sum(p for _, p, _, _ in tabela)
    for _ in range(n):
        r = rnd.uniform(0, total)
        for item, p, a, b in tabela:
            r -= p
            if r <= 0:
                itens.append([item, rnd.randint(a, b)])
                break
    return itens


COR_NAT = {
    GRAMA: (88, 124, 58), MATO: (62, 98, 46), AREIA: (194, 176, 128), AGUA: (44, 92, 128),
    TERRA: (138, 114, 82), PONTE: (44, 92, 128), ASFALTO: (66, 68, 72),
}
COR_MAPA = {
    PISO_MAD: (150, 120, 90), PISO_HOSP: (225, 225, 228), PISO_CONC: (140, 140, 132),
    PAREDE: (60, 54, 50), PAREDE_CONC: (80, 82, 78), PORTA: (150, 120, 90), PONTE: (130, 100, 66),
}


class Mundo:
    def __init__(self, seed, aviso=None):
        aviso = aviso or (lambda txt: None)
        for txt in self.gerar(seed):
            aviso(txt)

    def gerar(self, seed):
        """Monta o mundo em passos. A cada passo devolve um texto (assim o navegador nao trava)."""
        self.seed = seed
        rnd = random.Random(seed)
        rng = np.random.default_rng(seed)
        self.rnd = rnd

        yield ("Criando o terreno, os lagos e as matas...")
        elev = fbm(rng, N, [(80, .55), (30, .3), (11, .15)])
        yy, xx = np.mgrid[0:N, 0:N]
        borda = np.minimum(np.minimum(xx, yy), np.minimum(N - 1 - xx, N - 1 - yy))
        elev = elev - np.clip((22 - borda) * 0.025, 0, None)
        mata = fbm(rng, N, [(64, .6), (22, .3), (8, .1)])
        self.mata = mata
        qa = np.quantile(elev, .11)
        qr = np.quantile(elev, .135)
        q_ralo, q_mata, q_densa = np.quantile(mata, [.38, .52, .72])
        t = np.full((N, N), GRAMA, np.uint8)
        t[mata > q_mata] = MATO
        t[elev < qr] = AREIA
        t[elev < qa] = AGUA
        t[borda < 4] = AGUA
        self.res = np.zeros((N, N), bool)      # sem arvore
        self.ocup = np.zeros((N, N), bool)     # ocupado por predio
        self.construcoes = []
        self.moveis = []
        self.camas = []
        self.carros = []
        self.ruas = []
        self.vias = []
        self._t = t

        yield ("Erguendo cidades e vilas abandonadas...")
        self.cidades = []
        nomes = NOMES_CIDADES[:]
        rnd.shuffle(nomes)
        # uma cidade grande (metropole), 5 cidades e 22 vilas
        plano = [("metropole", 46)] + [("cidade", 30)] * 5 + [("vila", 17)] * 22
        for tipo, raio in plano:
            for _ in range(3000):
                x = rnd.randint(50, N - 51)
                y = rnd.randint(50, N - 51)
                if any(math.hypot(x - c["x"], y - c["y"]) < raio + c["raio"] + 30 for c in self.cidades):
                    continue
                sub = t[y - raio:y + raio + 1, x - raio:x + raio + 1]
                if (sub == AGUA).mean() > 0.01:
                    continue
                nome = NOME_METROPOLE if tipo == "metropole" else nomes.pop()
                self.cidades.append(dict(nome=nome, x=x, y=y, raio=raio, tipo=tipo))
                break

        # estradas ligando tudo (arvore minima)
        cs = self.cidades
        ligados = [0]
        resto = list(range(1, len(cs)))
        pares = []
        while resto:
            i, j = min(((i, j) for i in ligados for j in resto),
                       key=lambda p: math.hypot(cs[p[0]]["x"] - cs[p[1]]["x"], cs[p[0]]["y"] - cs[p[1]]["y"]))
            pares.append((i, j))
            ligados.append(j)
            resto.remove(j)
        for _ in range(3):
            i, j = rnd.sample(range(len(cs)), 2)
            pares.append((i, j))
        for i, j in pares:
            tipo = ASFALTO if cs[i]["tipo"] != "vila" and cs[j]["tipo"] != "vila" else TERRA
            self._estrada((cs[i]["x"], cs[i]["y"]), (cs[j]["x"], cs[j]["y"]), tipo)

        for c in cs:
            if c["tipo"] == "metropole":  # o SHOPPING fica no meio da cidade grande
                for _ in range(800):
                    x = c["x"] + rnd.randint(-10, 10) - 13
                    y = c["y"] + rnd.randint(-10, 10) - 9
                    sub = self._t[y - 2:y + 20, x - 2:x + 28]
                    if not np.isin(sub, [AGUA, PONTE]).any() and not self.ocup[y - 2:y + 20, x - 2:x + 28].any():
                        self._predio("shopping", x, y, 26, 18, c)  # pode ficar em cima da estrada
                        break
            if c["tipo"] != "vila":
                r = c["raio"]
                for _ in range(600):
                    x = c["x"] + rnd.randint(-r // 2, r // 2) - 8
                    y = c["y"] + rnd.randint(-r // 2, r // 2) - 6
                    if self._livre(x, y, 16, 12):
                        self._predio("hospital", x, y, 16, 12, c)
                        break
                for _ in range(2 if c["tipo"] == "metropole" else 1):  # mercados
                    for _ in range(600):
                        x = c["x"] + rnd.randint(-r + 6, r - 6) - 6
                        y = c["y"] + rnd.randint(-r + 6, r - 6) - 5
                        if self._livre(x, y, 13, 10):
                            self._predio("mercado", x, y, 13, 10, c)
                            break
        for c in cs:
            if c["tipo"] != "vila":
                for k in range(-3, 4) if c["tipo"] == "metropole" else range(-2, 3):
                    yy_ = c["y"] + k * 15
                    xx_ = c["x"] + k * 15
                    for x in range(c["x"] - c["raio"], c["x"] + c["raio"] + 1):
                        self._pincel(x, yy_, 1, ASFALTO)
                    for y in range(c["y"] - c["raio"], c["y"] + c["raio"] + 1):
                        self._pincel(xx_, y, 1, ASFALTO)
                    self.ruas.append((c["x"] - c["raio"], yy_, c["x"] + c["raio"], yy_))
                    self.ruas.append((xx_, c["y"] - c["raio"], xx_, c["y"] + c["raio"]))
            else:
                for x in range(c["x"] - c["raio"], c["x"] + c["raio"] + 1):
                    self._pincel(x, c["y"], 1, TERRA)
                for y in range(c["y"] - c["raio"], c["y"] + c["raio"] + 1):
                    self._pincel(c["x"], y, 1, TERRA)

        for c in cs:
            r = c["raio"]
            if c["tipo"] == "vila" and rnd.random() < 0.6:
                for _ in range(300):
                    x = c["x"] + rnd.randint(-r, r) - 5
                    y = c["y"] + rnd.randint(-r, r) - 4
                    if self._livre(x, y, 10, 8):
                        self._predio("posto", x, y, 10, 8, c)
                        break
            # posto de gasolina na beira da cidade (e em metade das vilas)
            if c["tipo"] != "vila" or rnd.random() < 0.5:
                for _ in range(400):
                    a = rnd.uniform(0, 6.283)
                    x = int(c["x"] + math.cos(a) * (r + 3)) - 5
                    y = int(c["y"] + math.sin(a) * (r + 3)) - 4
                    if self._livre(x, y, 10, 8):
                        self._predio("gas", x, y, 10, 8, c)
                        break
            alvo = {"metropole": 70, "cidade": 30}.get(c["tipo"], 9)
            feitas = 0
            for _ in range(alvo * 40):
                if feitas >= alvo:
                    break
                if c["tipo"] != "vila":
                    w = rnd.randint(6, 10)
                    h = rnd.randint(6, 9)
                else:
                    w = rnd.randint(7, 11)
                    h = rnd.randint(6, 9)
                x = c["x"] + rnd.randint(-r, r) - w // 2
                y = c["y"] + rnd.randint(-r, r) - h // 2
                if self._livre(x, y, w, h):
                    self._predio("casa", x, y, w, h, c)
                    feitas += 1

        # inicio: uma vila
        vilas = [c for c in cs if c["tipo"] == "vila"] or cs
        vila0 = min(vilas, key=lambda c: math.hypot(c["x"] - N / 2, c["y"] - N / 2) + rnd.uniform(0, 80))
        self.vila_inicio = vila0

        yield ("Escondendo bunkers militares na floresta...")
        cabanas = 0
        for _ in range(4000):
            if cabanas >= 60:
                break
            w = rnd.randint(6, 8)
            h = rnd.randint(5, 7)
            x = rnd.randint(10, N - 20)
            y = rnd.randint(10, N - 20)
            if any(math.hypot(x - c["x"], y - c["y"]) < c["raio"] + 12 for c in cs):
                continue
            if self._livre(x, y, w, h):
                self._predio("casa", x, y, w, h, None)
                cabanas += 1

        self.bunkers = []
        sx, sy = vila0["x"], vila0["y"]
        for _ in range(20000):
            if len(self.bunkers) >= PECAS_RADIO:
                break
            x = rnd.randint(25, N - 36)
            y = rnd.randint(25, N - 34)
            if any(math.hypot(x - c["x"], y - c["y"]) < c["raio"] + 30 for c in cs):
                continue
            if any(math.hypot(x - b["x"], y - b["y"]) < 95 for b in self.bunkers):
                continue
            if math.hypot(x - sx, y - sy) < 60:
                continue
            if self._livre(x, y, 11, 9, margem=3):
                b = self._predio("militar", x, y, 11, 9, None)
                self.bunkers.append(b)
        self.bunkers.sort(key=lambda b: math.hypot(b["x"] - sx, b["y"] - sy))
        for i, b in enumerate(self.bunkers):
            b["indice"] = i

        self.torre = None
        melhor = -1
        for _ in range(4000):
            x = rnd.randint(20, N - 30)
            y = rnd.randint(20, N - 30)
            d = math.hypot(x - sx, y - sy)
            if d < melhor or any(math.hypot(x - c["x"], y - c["y"]) < c["raio"] + 15 for c in cs):
                continue
            if self._livre(x, y, 9, 9, margem=2):
                melhor = d
                self.torre = (x, y)
        if self.torre:
            b = self._predio("torre", self.torre[0], self.torre[1], 9, 9, None)
            self.torre = b

        # pecas do radio: uma em cada bunker, e o bilhete do proximo
        for b in self.bunkers:
            caixas = [m for m in self.moveis if m.get("predio") is b and m["tipo"] == "militar"]
            if caixas:
                caixas[0]["itens"].insert(0, ["peca", 1])
                caixas[0]["revela"] = b["indice"] + 1

        yield ("Plantando arvores e capim alto...")
        self.tn = t
        self.t = bytearray(t.tobytes())
        self.col = {}
        self.arvores = {}
        self.pedras = {}
        self.arbustos = {}
        self.capim_p = {}
        self.capim_g = {}
        nat = (t == GRAMA) | (t == MATO)
        livre = nat & ~self.res
        prob = np.where(mata > q_densa, 0.42, np.where(mata > q_mata, 0.24, np.where(mata > q_ralo, 0.06, 0.012)))
        r1 = rng.random((N, N))
        r2 = rng.random((N, N))
        m_arv = livre & (r1 < prob)
        m_ped = livre & ~m_arv & (r2 < 0.004)
        m_arb = nat & ~m_arv & ~m_ped & (r2 > 0.004) & (r2 < 0.035)
        p_cap = np.where(t == GRAMA, np.where(mata < q_ralo, 0.16, 0.09), 0.05)
        r3 = rng.random((N, N))
        m_cap = nat & ~m_arv & ~m_ped & (r3 < p_cap) & ~self.ocup
        for ty, tx in zip(*np.nonzero(m_arv)):
            x = tx * T + 16 + rnd.uniform(-7, 7)
            y = ty * T + 16 + rnd.uniform(-7, 7)
            tipo = "pinheiro" if (t[ty, tx] == MATO and rnd.random() < 0.6) else "folhosa"
            i = ty * N + tx
            self.arvores[i] = (x, y, tipo, rnd.randrange(12))
            self.col.setdefault(i, []).append((x, y, 9))
        for ty, tx in zip(*np.nonzero(m_ped)):
            x = tx * T + 16 + rnd.uniform(-5, 5)
            y = ty * T + 16 + rnd.uniform(-5, 5)
            v = rnd.randrange(8)
            i = ty * N + tx
            self.pedras[i] = (x, y, v)
            self.col.setdefault(i, []).append((x, y, 9 + (v % 4) * 2))
        for ty, tx in zip(*np.nonzero(m_arb)):
            self.arbustos[ty * N + tx] = (tx * T + rnd.uniform(4, 28), ty * T + rnd.uniform(4, 28), rnd.randrange(10))
        for ty, tx in zip(*np.nonzero(m_cap)):
            x = tx * T + rnd.uniform(6, 26)
            y = ty * T + rnd.uniform(6, 26)
            if rnd.random() < 0.35:
                self.capim_g[ty * N + tx] = (x, y, rnd.randrange(12))
            else:
                self.capim_p[ty * N + tx] = (x, y, rnd.randrange(12))

        yield ("Abandonando carros nas estradas...")
        vias = self.vias
        rnd.shuffle(vias)
        for (tx, ty) in vias:
            if len(self.carros) > 600:
                break
            if rnd.random() > 0.05 or self.t[ty * N + tx] == PONTE:
                continue
            x = tx * T + 16
            y = ty * T + 16
            if any(abs(c["x"] - x) < 160 and abs(c["y"] - y) < 160 for c in self.carros[-30:]):
                continue
            hor = sum(1 for d in (-2, -1, 1, 2) if 0 <= tx + d < N and self.t[ty * N + tx + d] in (ASFALTO, TERRA))
            ver = sum(1 for d in (-2, -1, 1, 2) if 0 <= ty + d < N and self.t[(ty + d) * N + tx] in (ASFALTO, TERRA))
            ang = (0 if hor >= ver else 90) + rnd.uniform(-18, 18) + (180 if rnd.random() < .5 else 0)
            a = math.radians(ang)
            pontos = [(x + math.cos(a) * k, y - math.sin(a) * k) for k in (-16, 0, 16)]
            if any(self.bloqueado(px, py, 14) for px, py in pontos):
                continue
            car = dict(x=x, y=y, ang=ang, cor=rnd.randrange(len(G.CORES_CARRO)))
            self.carros.append(car)
            for px, py in pontos:
                self.add_colisor(px, py, 13)
            bx = x - math.cos(a) * 36
            by = y + math.sin(a) * 36
            car["mala"] = len(self.moveis)
            self.moveis.append(dict(id=len(self.moveis), x=bx, y=by, tipo="porta_malas", aberto=False,
                                    itens=sortear(rnd, LOOT["porta_malas"], rnd.choice([0, 1, 1, 2, 2, 3]))))

        yield ("Espalhando armas e suprimentos pelo chao...")
        self.itens_chao = []
        tent = 0
        while len(self.itens_chao) < 3800 and tent < 90000:
            tent += 1
            if len(self.itens_chao) < 2250:
                tx = rnd.randint(5, N - 6)
                ty = rnd.randint(5, N - 6)
            else:
                c = rnd.choice(cs)
                tx = c["x"] + rnd.randint(-c["raio"], c["raio"])
                ty = c["y"] + rnd.randint(-c["raio"], c["raio"])
            v = self.t[ty * N + tx]
            if v in SOLIDO or v in (PAREDE, PAREDE_CONC):
                continue
            x = tx * T + rnd.uniform(8, 24)
            y = ty * T + rnd.uniform(8, 24)
            if self.bloqueado(x, y, 8):
                continue
            item, q = sortear(rnd, LOOT["chao"], 1)[0]
            self.itens_chao.append(dict(id=len(self.itens_chao), x=x, y=y, item=item, q=q))

        # ponto de partida
        self.inicio = (vila0["x"] * T, vila0["y"] * T)
        for _ in range(3000):
            a = rnd.uniform(0, 6.283)
            d = (vila0["raio"] + rnd.uniform(4, 9)) * T
            x = vila0["x"] * T + math.cos(a) * d
            y = vila0["y"] * T + math.sin(a) * d
            if 0 < x < N * T and 0 < y < N * T and not self.bloqueado(x, y, 16) and self.tile_px(x, y) in (GRAMA, MATO, TERRA):
                self.inicio = (x, y)
                break
        # uma pistola garantida na casa mais perto do inicio
        casas = [b for b in self.construcoes if b["tipo"] == "casa"]
        if casas:
            perto = min(casas, key=lambda b: math.hypot(b["x"] * T - self.inicio[0], b["y"] * T - self.inicio[1]))
            for m in self.moveis:
                if m.get("predio") is perto:
                    m["itens"] = [["pistola", 1], ["9mm", 12], ["agua", 1]]
                    break

        yield ("Espalhando campos de capim alto...")
        self._campos_e_zonas()
        yield "Escondendo mochilas, armas e materiais..."
        self._mochilas_e_materiais()
        self._escadas()

        yield ("Preparando o desenho...")
        self._indexar()
        yield "Pintando o mundo..."
        self._preparar_desenho(rng)

    # ---------------------------------------------------------------- geracao
    def _campos_e_zonas(self):
        """Campos grandes de capim alto e o mapa de onde tem (ou nao tem) zumbi.
        Usa um sorteio separado para o resto do mundo continuar igual nos jogos salvos."""
        rng = np.random.default_rng(self.seed + 4242)
        rnd = random.Random(self.seed + 4242)
        tn = self.tn
        nat = (tn == GRAMA) | (tn == MATO)
        # campos de capim alto (uns 9% do mapa, longe da floresta fechada)
        cam = fbm(rng, N, [(40, .7), (14, .3)])
        aberto = self.mata < np.quantile(self.mata, 0.42)
        campo = (cam > np.quantile(cam, 0.82)) & nat & aberto & ~self.ocup
        self.campo = campo
        r = rng.random((N, N))
        for ty, tx in zip(*np.nonzero(campo)):
            i = ty * N + tx
            if i in self.arvores or i in self.pedras:
                continue
            x = tx * T + rnd.uniform(6, 26)
            y = ty * T + rnd.uniform(6, 26)
            if r[ty, tx] < 0.82:
                self.capim_p.pop(i, None)
                self.capim_g[i] = (x, y, rnd.randrange(12))
            elif i not in self.capim_g:
                self.capim_p[i] = (x, y, rnd.randrange(12))
        # zumbis: 0 = regiao calma (nenhum zumbi), 1 = infestado
        inf = fbm(rng, N, [(90, .7), (30, .3)])
        q0, q1 = np.quantile(inf, 0.42), np.quantile(inf, 0.95)
        dens = np.clip((inf - q0) / (q1 - q0), 0, 1)
        dens = np.where(dens > 0, 0.25 + 0.75 * dens, 0)
        yy, xx = np.mgrid[0:N, 0:N]
        for c in self.cidades:
            dc = np.hypot(xx - c["x"], yy - c["y"])
            dens = np.where(dc < c["raio"] * 1.2, np.maximum(dens, {"metropole": 1.0, "cidade": 0.7}.get(c["tipo"], 0.45)), dens)
        # perto de onde voce comeca e calmo
        ix, iy = self.inicio[0] / T, self.inicio[1] / T
        dens = np.where(np.hypot(xx - ix, yy - iy) < 45, 0, dens)
        self.dens = dens.astype(np.float32)

    def _mochilas_e_materiais(self):
        """Mochilas (cada vez melhores) e mais material de construcao. Sorteio separado."""
        self.bancadas = []
        rnd = random.Random(self.seed + 5151)
        casa = [mv for mv in self.moveis if mv["tipo"] in ("armario", "gaveta", "caixa")]
        malas = [mv for mv in self.moveis if mv["tipo"] == "porta_malas"]
        rnd.shuffle(casa)
        rnd.shuffle(malas)
        # cada armario/gaveta sorteia: mochila (quase metade tem), ferramentas e saco de dormir
        for mv in casa:
            r = rnd.random()
            if r < 0.22:
                mv["itens"].append(["mochila1", 1])
            elif r < 0.38:
                mv["itens"].append(["mochila2", 1])
            elif r < 0.45:
                mv["itens"].append(["mochila3", 1])
            elif r < 0.47:
                mv["itens"].append(["mochila4", 1])
            if rnd.random() < 0.12:
                mv["itens"].append(["ferramentas", 1])
            if rnd.random() < 0.10:
                mv["itens"].append(["saco", 1])
        for mv in malas[:45]:
            mv["itens"].append(["mochila2" if rnd.random() < 0.75 else "mochila3", 1])
        for mv in malas[45:]:
            if rnd.random() < 0.4:
                mv["itens"].append(["sucata", rnd.randint(2, 4)])
        # armas novas (facao, submetralhadora, besta) e flechas: sorteio separado
        for mv in casa:
            r = rnd.random()
            if r < 0.06:
                mv["itens"].append(["facao", 1])
            elif r < 0.09:
                mv["itens"].append(["smg", 1])
            elif r < 0.12:
                mv["itens"].append(["besta", 1])
            if rnd.random() < 0.12:
                mv["itens"].append(["flecha", rnd.randint(3, 8)])
        for mv in self.moveis:
            if mv["tipo"] == "militar":
                if rnd.random() < 0.25:
                    mv["itens"].append(["smg" if rnd.random() < 0.55 else "besta", 1])
                if rnd.random() < 0.4:
                    mv["itens"].append(["flecha", rnd.randint(6, 14)])
        # taco com pregos, revolver e balas .38
        for mv in casa:
            r = rnd.random()
            if r < 0.05:
                mv["itens"].append(["taco", 1])
            elif r < 0.08:
                mv["itens"].append(["revolver", 1])
            if rnd.random() < 0.10:
                mv["itens"].append(["38", rnd.randint(4, 10)])
        for mv in malas:
            if rnd.random() < 0.06:
                mv["itens"].append(["taco", 1])
        # miras (lunetas): raras nas casas, mais comuns nas caixas militares, algumas no chao
        for mv in casa:
            if rnd.random() < 0.035:
                mv["itens"].append(["mira", 1])
        for mv in self.moveis:
            if mv["tipo"] == "militar" and rnd.random() < 0.22:
                mv["itens"].append(["mira", 1])
        # galoes de gasolina para os carros
        for mv in self.moveis:
            if mv["tipo"] == "prateleira" and (mv.get("predio") or {}).get("tipo") == "gas" and rnd.random() < 0.5:
                mv["itens"].append(["galao", 1])
            elif mv["tipo"] == "porta_malas" and rnd.random() < 0.08:
                mv["itens"].append(["galao", 1])
        for i, c in enumerate(self.carros):  # cada carro tem um pouco de gasolina
            c["gas"] = round(random.Random(self.seed * 31 + i).uniform(0, 60))
        # lanternas: a boa nas casas e carros, a tatica nas caixas militares, o holofote nos ultimos bunkers
        for mv in self.moveis:
            r = rnd.random()
            if mv["tipo"] in ("armario", "gaveta", "caixa") and r < 0.07:
                mv["itens"].append(["lanterna1", 1])
            elif mv["tipo"] == "porta_malas" and r < 0.05:
                mv["itens"].append(["lanterna1", 1])
            elif mv["tipo"] == "militar" and r < 0.25:
                mv["itens"].append(["lanterna2", 1])
            elif mv["tipo"] == "vitrine" and r < 0.5:
                mv["itens"].append(["lanterna2", 1])
        # seringas rarissimas nos hospitais
        medicos = [mv for mv in self.moveis if mv["tipo"] == "medico" and (mv.get("predio") or {}).get("tipo") != "militar"]
        rnd.shuffle(medicos)
        for mv in medicos[:3]:
            mv["itens"].append(["seringa", 1])
        for b in self.bunkers:
            caixas = [mv for mv in self.moveis if mv.get("predio") is b and mv["tipo"] == "militar"]
            if caixas:
                caixas[-1]["itens"].append(["mochila4" if b["indice"] in (2, 4) else "mochila3", 1])
            # despensa (muita comida e agua) e arsenal (armas melhores) dentro de cada bunker
            i = b["indice"]
            x, y, w, h = b["x"], b["y"], b["w"], b["h"]
            # tamanho: o primeiro fica normal; os outros podem ser grandes (mais coisas) ou pequenos (menos)
            r = rnd.random()
            b["porte"] = "normal" if i == 0 else ("grande" if r < 0.45 else ("pequeno" if r < 0.75 else "normal"))
            # segunda porta, do lado oposto, para achar a entrada mais facil
            pts = b.get("portas", [])
            if pts:
                if all(py == y for _, py in pts):
                    novas = [(x + w // 2 - 1, y + h - 1), (x + w // 2, y + h - 1)]
                elif all(py == y + h - 1 for _, py in pts):
                    novas = [(x + w // 2 - 1, y), (x + w // 2, y)]
                elif all(px == x for px, _ in pts):
                    novas = [(x + w - 1, y + h // 2 - 1), (x + w - 1, y + h // 2)]
                else:
                    novas = [(x, y + h // 2 - 1), (x, y + h // 2)]
                for px, py in novas:
                    self.t[py * N + px] = PORTA
                    self.tn[py, px] = PORTA
                b["portas"] = list(pts) + novas
            porte = b["porte"]
            q = {"pequeno": (3, 5), "normal": (8, 12), "grande": (14, 20)}[porte]
            self.moveis.append(dict(
                id=len(self.moveis), x=(x + 6) * T + 30, y=(y + 1) * T + 18, tipo="despensa", aberto=False, predio=b,
                itens=[["comida", rnd.randint(*q)], ["agua", rnd.randint(*q)], ["bandagem", 4 if porte != "pequeno" else 1],
                       ["kit", {"pequeno": 1, "normal": 2, "grande": 4}[porte]]]))
            if porte == "pequeno":
                arsenal = [["pistola", 1], ["9mm", 30]]
            else:
                arsenal = [["fuzil" if i >= 1 else "espingarda", 1], ["556", 90], ["12", 18], ["silenciador", 1], ["saco", 1]]
                if i >= 2 or porte == "grande":
                    arsenal += [["rifle", 1], ["308", 25]]
            if porte == "grande" or rnd.random() < 0.3:
                arsenal.append(["seringa", 1])
            arsenal.append(["mochila2" if i == 0 else ("mochila3" if i in (1, 3) else "mochila4"), 1])
            if i >= 3:  # o HOLOFOTE MILITAR fica nos ultimos bunkers
                arsenal.append(["lanterna3", 1])
            self.moveis.append(dict(
                id=len(self.moveis), x=(x + 6) * T + 30, y=(y + h - 2) * T + 14, tipo="arsenal", aberto=False, predio=b,
                itens=arsenal))
            if porte == "grande":
                self._aumentar_bunker(b, rnd)
            # cada bunker tem uma bancada pronta para melhorar armas e mochila
            bx = (b["x"] + (3 if b.get("porte") == "grande" else 2)) * T + 18
            by = (b["y"] + b["h"] // 2) * T + 16
            self.bancadas.append(dict(x=bx, y=by, bunker=b["indice"]))
            self.add_colisor(bx, by, 16)

        self._liberar_portas()
        # mochilas extras (sorteio separado, para nao mudar o resto do mundo)
        rx = random.Random(self.seed + 6161)
        for mv in casa:
            if rx.random() < 0.18:
                mv["itens"].append([rx.choice(["mochila1", "mochila2", "mochila2", "mochila3"]), 1])
        for mv in malas:
            if rx.random() < 0.15:
                mv["itens"].append([rx.choice(["mochila2", "mochila3"]), 1])

        # pilhas de tabuas e sucata nas cidades e vilas, e mochilas pelo chao
        def solta(item, q, cx, cy, raio):
            for _ in range(30):
                a = rnd.uniform(0, 6.283)
                d = rnd.uniform(0, raio)
                x = (cx + math.cos(a) * d) * T
                y = (cy + math.sin(a) * d) * T
                if 0 < x < N * T and 0 < y < N * T and not self.bloqueado(x, y, 10) and \
                        self.tile_px(x, y) in (GRAMA, MATO, TERRA, ASFALTO, AREIA):
                    self.itens_chao.append(dict(id=len(self.itens_chao), x=x, y=y, item=item, q=q))
                    return
        for c in self.cidades:
            pilhas = {"metropole": 70, "cidade": 40}.get(c["tipo"], 14)
            for _ in range(pilhas):
                if rnd.random() < 0.6:
                    solta("tabua", rnd.randint(3, 6), c["x"], c["y"], c["raio"] * 1.3)
                else:
                    solta("sucata", rnd.randint(2, 5), c["x"], c["y"], c["raio"] * 1.3)
            for _ in range(1 if c["tipo"] == "vila" else 3):
                solta(rnd.choice(["mochila1", "mochila2", "mochila2", "mochila3"]), 1, c["x"], c["y"], c["raio"] * 1.2)
        # uma mochila escolar perto de onde voce comeca
        solta("mochila1", 1, self.inicio[0] / T, self.inicio[1] / T, 4)
        for _ in range(70):
            solta(rnd.choice(["mochila1", "mochila2", "mochila2", "mochila3"]), 1, rnd.uniform(20, N - 20),
                  rnd.uniform(20, N - 20), 3)

    def _aumentar_bunker(self, b, rnd):
        """Bunker grande: cresce 2 quadradinhos para cada lado, com mais caixas e camas."""
        x, y, w, h = b["x"] - 2, b["y"] - 2, b["w"] + 4, b["h"] + 4
        if x < 4 or y < 4 or x + w > N - 5 or y + h > N - 5:
            b["porte"] = "normal"
            return
        for o in self.construcoes:
            if o is b:
                continue
            if x - 2 < o["x"] + o["w"] and o["x"] < x + w + 2 and y - 2 < o["y"] + o["h"] and o["y"] < y + h + 2:
                b["porte"] = "normal"
                return
        anel = self.tn[y:y + h, x:x + w].copy()
        anel[2:-2, 2:-2] = GRAMA
        if not np.all(np.isin(anel, [GRAMA, MATO, AREIA])):
            b["porte"] = "normal"
            return
        # limpa arvores, pedras e capim do terreno novo
        for ty in range(y - 1, y + h + 1):
            for tx in range(x - 1, x + w + 1):
                i = ty * N + tx
                for d in (self.arvores, self.pedras, self.arbustos, self.capim_g, self.capim_p):
                    d.pop(i, None)
                self.col.pop(i, None)
        piso, parede = PISO_CONC, PAREDE_CONC
        for ty in range(y, y + h):
            for tx in range(x, x + w):
                borda = tx in (x, x + w - 1) or ty in (y, y + h - 1)
                v = parede if borda else piso
                self.t[ty * N + tx] = v
                self.tn[ty, tx] = v
        portas = [(x + w // 2 - 1, y), (x + w // 2, y), (x + w // 2 - 1, y + h - 1), (x + w // 2, y + h - 1)]
        for px, py in portas:
            self.t[py * N + px] = PORTA
            self.tn[py, px] = PORTA
        self.ocup[y - 1:y + h + 1, x - 1:x + w + 1] = True
        self.res[y - 2:y + h + 2, x - 2:x + w + 2] = True
        b.update(x=x, y=y, w=w, h=h, portas=portas)
        # mais caixas militares e camas no espaco novo
        for bx, by in ((x + 1, y + h // 2), (x + w - 2, y + h // 2), (x + 2, y + h - 2)):
            self.moveis.append(dict(id=len(self.moveis), x=bx * T + 16, y=by * T + 16, tipo="militar", aberto=False,
                                    predio=b, itens=sortear(rnd, LOOT["militar"], rnd.randint(3, 5))))
        for bx in (x + w - 4, x + w - 2):
            self.camas.append(dict(x=bx * T + 16, y=(y + 1) * T + 28, hospital=False, bunker=b["id"]))

    def _liberar_portas(self):
        """Tira carros e arvores que ficaram bloqueando a porta de algum predio."""
        frentes = []
        for b in self.construcoes:
            for px, py in b.get("portas", []):
                lado = "N" if py == b["y"] else "S" if py == b["y"] + b["h"] - 1 else "O" if px == b["x"] else "L"
                dx, dy = {"N": (0, -1), "S": (0, 1), "O": (-1, 0), "L": (1, 0)}[lado]
                for k in (0.5, 1.5, 2.5):
                    frentes.append((px * T + 16 + dx * k * T, py * T + 16 + dy * k * T))
        # separa as frentes das portas por quadradinho: assim cada arvore so olha as portas do lado dela
        grade = {}
        for fx, fy in frentes:
            grade.setdefault((int(fx // T), int(fy // T)), []).append((fx, fy))

        def perto(x, y, r):
            tx, ty = int(x // T), int(y // T)
            for gy in range(ty - 3, ty + 4):
                for gx in range(tx - 3, tx + 4):
                    for fx, fy in grade.get((gx, gy), ()):
                        if (x - fx) ** 2 + (y - fy) ** 2 < r * r:
                            return True
            return False
        ficam = []
        for c in self.carros:
            if perto(c["x"], c["y"], 64):
                a = math.radians(c["ang"])
                for k in (-16, 0, 16):
                    qx, qy = c["x"] + math.cos(a) * k, c["y"] - math.sin(a) * k
                    i = int(qy // T) * N + int(qx // T)
                    self.col[i] = [q for q in self.col.get(i, []) if abs(q[0] - qx) > 0.01 or abs(q[1] - qy) > 0.01]
                tx, ty = c["x"] - math.cos(a) * 36, c["y"] + math.sin(a) * 36
                for mv in self.moveis:
                    if mv["tipo"] == "porta_malas" and abs(mv["x"] - tx) < 1 and abs(mv["y"] - ty) < 1:
                        mv["aberto"] = True
                        mv["itens"] = []
            else:
                ficam.append(c)
        self.carros = ficam
        for i, a in list(self.arvores.items()):
            if perto(a[0], a[1], 40):
                self.arvores.pop(i)
                self.col[i] = [q for q in self.col.get(i, []) if abs(q[0] - a[0]) > 0.01 or abs(q[1] - a[1]) > 0.01]

    def _escadas(self):
        """Escada encostada na parede de muitas casas, mercados e postos: da para subir no telhado."""
        rnd = random.Random(self.seed + 7373)
        for b in self.construcoes:
            if b["tipo"] not in ("casa", "mercado", "gas", "hospital", "posto", "shopping"):
                continue
            x, y, w, h = b["x"], b["y"], b["w"], b["h"]
            lados_porta = set()
            for px, py in b.get("portas", []):
                lados_porta.add("N" if py == y else "S" if py == y + h - 1 else "O" if px == x else "L")
            opcoes = [l for l in "NSLO" if l not in lados_porta]
            rnd.shuffle(opcoes)
            for lado in opcoes:
                if lado == "N":
                    fora, dentro = ((x + w / 2) * T, y * T - 14), ((x + w / 2) * T, y * T + 26)
                elif lado == "S":
                    fora, dentro = ((x + w / 2) * T, (y + h) * T + 14), ((x + w / 2) * T, (y + h) * T - 26)
                elif lado == "O":
                    fora, dentro = (x * T - 14, (y + h / 2) * T), (x * T + 26, (y + h / 2) * T)
                else:
                    fora, dentro = ((x + w) * T + 14, (y + h / 2) * T), ((x + w) * T - 26, (y + h / 2) * T)
                if not self.bloqueado(fora[0], fora[1], 12) and self.tile_px(*fora) not in (AGUA, PONTE):
                    b["escada"] = dict(lado=lado, fora=fora, dentro=dentro)
                    break

    def densidade(self, x, y):
        tx = min(N - 1, max(0, int(x // T)))
        ty = min(N - 1, max(0, int(y // T)))
        return float(self.dens[ty, tx])

    def _pincel(self, x, y, larg, tipo):
        t = self._t
        for yy in range(y - larg, y + larg + 1):
            for xx in range(x - larg, x + larg + 1):
                if 1 <= xx < N - 1 and 1 <= yy < N - 1:
                    if self.ocup[yy, xx]:
                        continue
                    v = t[yy, xx]
                    if v == AGUA or v == PONTE:
                        t[yy, xx] = PONTE
                    elif tipo == TERRA and v == ASFALTO:
                        pass
                    else:
                        if v != tipo:
                            self.vias.append((xx, yy))
                        t[yy, xx] = tipo
        self.res[max(0, y - larg - 1):y + larg + 2, max(0, x - larg - 1):x + larg + 2] = True

    def _estrada(self, a, b, tipo):
        rnd = self.rnd
        x, y = a
        bx, by = b
        larg = 2 if tipo == ASFALTO else 1
        ultimo = None
        while (x, y) != (bx, by):
            dx = bx - x
            dy = by - y
            if ultimo == "x" and dx != 0 and rnd.random() < 0.8:
                x += 1 if dx > 0 else -1
            elif ultimo == "y" and dy != 0 and rnd.random() < 0.8:
                y += 1 if dy > 0 else -1
            elif dx != 0 and (dy == 0 or rnd.random() < abs(dx) / (abs(dx) + abs(dy))):
                x += 1 if dx > 0 else -1
                ultimo = "x"
            else:
                y += 1 if dy > 0 else -1
                ultimo = "y"
            self._pincel(x, y, larg, tipo)

    def _livre(self, x, y, w, h, margem=1):
        if x < 4 or y < 4 or x + w > N - 5 or y + h > N - 5:
            return False
        sub = self._t[y - margem:y + h + margem, x - margem:x + w + margem]
        if not np.all((sub == GRAMA) | (sub == MATO) | (sub == AREIA)):
            return False
        return not self.ocup[y - margem:y + h + margem, x - margem:x + w + margem].any()

    def _lado_porta(self, x, y, w, h, cidade):
        t = self._t
        opcoes = []
        for lado, (px, py) in (("N", (x + w // 2, y - 2)), ("S", (x + w // 2, y + h + 1)),
                               ("O", (x - 2, y + h // 2)), ("L", (x + w + 1, y + h // 2))):
            for k in range(0, 4):
                qx = px + (0 if lado in "NS" else (-k if lado == "O" else k))
                qy = py + (0 if lado in "OL" else (-k if lado == "N" else k))
                if 0 <= qx < N and 0 <= qy < N and t[qy, qx] in (TERRA, ASFALTO):
                    opcoes.append((k, lado))
                    break
        if opcoes:
            return min(opcoes)[1]
        if cidade:
            dx = cidade["x"] - (x + w / 2)
            dy = cidade["y"] - (y + h / 2)
            if abs(dx) > abs(dy):
                return "L" if dx > 0 else "O"
            return "S" if dy > 0 else "N"
        return self.rnd.choice("NSLO")

    def _predio(self, tipo, x, y, w, h, cidade):
        rnd = self.rnd
        t = self._t
        piso = {"casa": PISO_MAD, "hospital": PISO_HOSP, "posto": PISO_HOSP, "militar": PISO_CONC, "torre": PISO_CONC,
                "mercado": PISO_HOSP, "shopping": PISO_HOSP, "gas": PISO_CONC}[tipo]
        parede = PAREDE_CONC if tipo == "militar" else PAREDE
        b = dict(tipo=tipo, x=x, y=y, w=w, h=h, cidade=cidade["nome"] if cidade else None, id=len(self.construcoes))
        self.construcoes.append(b)
        self.ocup[y - 1:y + h + 1, x - 1:x + w + 1] = True
        self.res[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2] = True
        if tipo == "torre":
            t[y:y + h, x:x + w] = piso
            return b
        t[y:y + h, x:x + w] = parede
        t[y + 1:y + h - 1, x + 1:x + w - 1] = piso
        lado = self._lado_porta(x, y, w, h, cidade) if tipo != "hospital" else "S"
        portas = []

        def porta(lado):
            if lado == "N":
                c = x + w // 2 - 1
                portas.extend([(c, y), (c + 1, y)])
            elif lado == "S":
                c = x + w // 2 - 1
                portas.extend([(c, y + h - 1), (c + 1, y + h - 1)])
            elif lado == "O":
                c = y + h // 2 - 1
                portas.extend([(x, c), (x, c + 1)])
            else:
                c = y + h // 2 - 1
                portas.extend([(x + w - 1, c), (x + w - 1, c + 1)])

        porta(lado)
        if tipo == "hospital":
            porta("N")
        if tipo == "shopping":  # o shopping tem entrada dos dois lados
            porta({"N": "S", "S": "N", "O": "L", "L": "O"}[lado])
        for px, py in portas:
            t[py, px] = PORTA
        b["portas"] = portas

        bloqueados = set()
        for px, py in portas:
            for d in range(-1, 3):
                for e in range(-1, 3):
                    bloqueados.add((px + d, py + e))
                    bloqueados.add((px - d, py - e))

        if tipo == "casa" and w >= 9:
            col = x + w // 2 + (2 if lado in "NS" else 0)
            if col < x + w - 2:
                t[y + 1:y + h - 1, col] = parede
                gy = rnd.randint(y + 1, y + h - 3)
                t[gy:gy + 2, col] = piso
                for yy in range(y + 1, y + h - 1):
                    bloqueados.add((col, yy))
                    bloqueados.add((col - 1, yy))
                    bloqueados.add((col + 1, yy))
        if tipo == "hospital":
            meio = y + h // 2
            t[meio, x + 1:x + w - 1] = parede
            for gx in (x + 3, x + w - 5, x + w // 2 - 1):
                t[meio, gx:gx + 2] = piso
            for bx in range(x + 2, x + w - 2, 3):
                self.camas.append(dict(x=bx * T + 16, y=(y + 1) * T + 28, hospital=True))
            for bx in (x + 2, x + 5, x + w - 4, x + w - 7):
                self.moveis.append(dict(id=len(self.moveis), x=bx * T + 16, y=(y + h - 2) * T + 22, tipo="medico",
                                        aberto=False, predio=b, itens=sortear(rnd, LOOT["medico"], rnd.randint(1, 3))))
            return b
        if tipo in ("mercado", "shopping", "gas"):
            # prateleiras em fileiras (e vitrines de armas no shopping)
            loot = {"mercado": "mercado", "shopping": "mercado", "gas": "conveniencia"}[tipo]
            passo_x = 4
            for yy in range(y + 2, y + h - 2, 3):
                for xx in range(x + 3, x + w - 3, passo_x):
                    if any((xx + d, yy) in bloqueados for d in (-1, 0, 1, 2)):
                        continue
                    if tipo == "shopping" and yy == y + 2 and (xx - x) % 8 == 3:
                        self.moveis.append(dict(id=len(self.moveis), x=xx * T + 16, y=yy * T + 16, tipo="vitrine",
                                                aberto=False, predio=b, itens=sortear(rnd, LOOT["loja_armas"], 2)))
                        continue
                    self.moveis.append(dict(id=len(self.moveis), x=xx * T + 16, y=yy * T + 16, tipo="prateleira",
                                            aberto=False, predio=b, itens=sortear(rnd, LOOT[loot], rnd.randint(1, 3))))
            if tipo == "shopping":
                for bx in (x + 2, x + w - 3):
                    self.moveis.append(dict(id=len(self.moveis), x=bx * T + 16, y=(y + h - 2) * T + 16, tipo="medico",
                                            aberto=False, predio=b, itens=sortear(rnd, LOOT["medico"], 3)))
            return b
        if tipo == "posto":
            for bx in (x + 2, x + 5):
                self.camas.append(dict(x=bx * T + 16, y=(y + 1) * T + 28, hospital=True))
            for bx in (x + 2, x + w - 3):
                self.moveis.append(dict(id=len(self.moveis), x=bx * T + 16, y=(y + h - 2) * T + 22, tipo="medico",
                                        aberto=False, predio=b, itens=sortear(rnd, LOOT["medico"], rnd.randint(1, 3))))
            return b
        if tipo == "militar":
            self.camas.append(dict(x=(x + 2) * T + 16, y=(y + 1) * T + 28, hospital=False, bunker=b["id"]))
            self.camas.append(dict(x=(x + 4) * T + 16, y=(y + 1) * T + 28, hospital=False, bunker=b["id"]))
            for k, (bx, by) in enumerate([(x + w - 3, y + 1), (x + w - 3, y + 3), (x + 2, y + h - 2)]):
                self.moveis.append(dict(id=len(self.moveis), x=bx * T + 16, y=by * T + 16, tipo="militar",
                                        aberto=False, predio=b, itens=sortear(rnd, LOOT["militar"], rnd.randint(2, 4))))
            self.moveis.append(dict(id=len(self.moveis), x=(x + w - 3) * T + 16, y=(y + h - 2) * T + 16,
                                    tipo="medico", aberto=False, predio=b, itens=sortear(rnd, LOOT["medico"], 2)))
            return b
        # casa: moveis encostados nas paredes
        cand = []
        for yy in range(y + 1, y + h - 1):
            for xx in range(x + 1, x + w - 1):
                if (xx, yy) in bloqueados or t[yy, xx] != piso:
                    continue
                enc = []
                if yy == y + 1:
                    enc.append((0, -8))
                if yy == y + h - 2:
                    enc.append((0, 8))
                if xx == x + 1:
                    enc.append((-8, 0))
                if xx == x + w - 2:
                    enc.append((8, 0))
                if enc:
                    cand.append((xx, yy, enc[0]))
        rnd.shuffle(cand)
        usados = []
        for xx, yy, (ox, oy) in cand:
            if len(usados) >= rnd.randint(2, 4):
                break
            if any(abs(xx - a) + abs(yy - b_) < 2 for a, b_ in usados):
                continue
            usados.append((xx, yy))
            tipo_m = rnd.choice(["armario", "geladeira", "gaveta", "caixa", "armario", "gaveta"])
            self.moveis.append(dict(id=len(self.moveis), x=xx * T + 16 + ox, y=yy * T + 16 + oy, tipo=tipo_m,
                                    aberto=False, predio=b,
                                    itens=sortear(rnd, LOOT["casa"], rnd.choice([0, 1, 1, 2, 2, 2, 3]))))
        return b

    # ---------------------------------------------------------------- consultas
    def _indexar(self):
        self.moveis_ch = {}
        for m in self.moveis:
            self.moveis_ch.setdefault((int(m["x"] // CHPX), int(m["y"] // CHPX)), []).append(m)
        self.itens_ch = {}
        for it in self.itens_chao:
            self.itens_ch.setdefault((int(it["x"] // CHPX), int(it["y"] // CHPX)), []).append(it)
        self.camas_ch = {}
        for c in self.camas:
            self.camas_ch.setdefault((int(c["x"] // CHPX), int(c["y"] // CHPX)), []).append(c)
        self.pred_ch = {}
        for b in self.construcoes:
            for cy in range(b["y"] // CH, (b["y"] + b["h"]) // CH + 1):
                for cx in range(b["x"] // CH, (b["x"] + b["w"]) // CH + 1):
                    self.pred_ch.setdefault((cx, cy), []).append(b)
        self.carros_ch = {}
        for c in self.carros:
            self.carros_ch.setdefault((int(c["x"] // CHPX), int(c["y"] // CHPX)), []).append(c)

    def add_item_chao(self, it):
        self.itens_chao.append(it)
        self.itens_ch.setdefault((int(it["x"] // CHPX), int(it["y"] // CHPX)), []).append(it)

    def add_movel(self, m):
        self.moveis.append(m)
        self.moveis_ch.setdefault((int(m["x"] // CHPX), int(m["y"] // CHPX)), []).append(m)

    def perto(self, indice, x, y, raio=1):
        cx = int(x // CHPX)
        cy = int(y // CHPX)
        for yy in range(cy - raio, cy + raio + 1):
            for xx in range(cx - raio, cx + raio + 1):
                yield from indice.get((xx, yy), ())

    def tile(self, tx, ty):
        if 0 <= tx < N and 0 <= ty < N:
            return self.t[ty * N + tx]
        return AGUA

    def tile_px(self, x, y):
        return self.tile(int(x // T), int(y // T))

    def add_colisor(self, x, y, r):
        self.col.setdefault(int(y // T) * N + int(x // T), []).append((x, y, r))

    def bloqueado(self, x, y, r):
        t = self.t
        tx0 = int((x - r) // T)
        tx1 = int((x + r) // T)
        ty0 = int((y - r) // T)
        ty1 = int((y + r) // T)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if not (0 <= tx < N and 0 <= ty < N):
                    return True
                if t[ty * N + tx] in SOLIDO:
                    nx = min(max(x, tx * T), tx * T + T)
                    ny = min(max(y, ty * T), ty * T + T)
                    if (x - nx) ** 2 + (y - ny) ** 2 < r * r:
                        return True
        ctx = int(x // T)
        cty = int(y // T)
        col = self.col
        for ty in (cty - 1, cty, cty + 1):
            base = ty * N
            for tx in (ctx - 1, ctx, ctx + 1):
                lst = col.get(base + tx)
                if lst:
                    for (ox, oy, orr) in lst:
                        rr = r + orr
                        if (x - ox) ** 2 + (y - oy) ** 2 < rr * rr:
                            return True
        return False

    def linha_livre(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = int(d / 16) + 1
        t = self.t
        for i in range(1, n):
            k = i / n
            tx = int((x0 + (x1 - x0) * k) // T)
            ty = int((y0 + (y1 - y0) * k) // T)
            if 0 <= tx < N and 0 <= ty < N and t[ty * N + tx] in BLOQ_TIRO:
                return False
        return True

    def bala_para(self, x, y, ang, alcance):
        """Distancia que o tiro anda ate bater numa parede, arvore, pedra ou carro."""
        dx = math.cos(ang)
        dy = math.sin(ang)
        d = 0.0
        t = self.t
        col = self.col
        while d < alcance:
            d += 8
            px = x + dx * d
            py = y + dy * d
            tx = int(px // T)
            ty = int(py // T)
            if not (0 <= tx < N and 0 <= ty < N):
                return d
            if t[ty * N + tx] in BLOQ_TIRO:
                return d
            lst = col.get(ty * N + tx)
            if lst and d > 20:
                for (ox, oy, orr) in lst:
                    if (px - ox) ** 2 + (py - oy) ** 2 < orr * orr:
                        return d
        return alcance

    def predio_em(self, x, y):
        tx = int(x // T)
        ty = int(y // T)
        for b in self.pred_ch.get((tx // CH, ty // CH), ()):
            if b["x"] <= tx < b["x"] + b["w"] and b["y"] <= ty < b["y"] + b["h"]:
                return b
        return None

    def no_capim(self, x, y):
        tx = int(x // T)
        ty = int(y // T)
        for yy in (ty - 1, ty, ty + 1):
            for xx in (tx - 1, tx, tx + 1):
                c = self.capim_g.get(yy * N + xx)
                if c and (c[0] - x) ** 2 + (c[1] - y) ** 2 < 26 * 26:
                    return True
        return False

    def cidade_perto(self, x, y, folga=1.3):
        tx = x / T
        ty = y / T
        for c in self.cidades:
            if math.hypot(c["x"] - tx, c["y"] - ty) < c["raio"] * folga:
                return c
        return None

    # ---------------------------------------------------------------- desenho
    def _preparar_desenho(self, rng):
        rnd = random.Random(self.seed + 5)
        pad = np.pad(self.tn, 1, constant_values=AGUA)
        self.tpad = pad
        pal = np.zeros((16, 3), np.float32)
        for k, v in COR_NAT.items():
            pal[k] = v
        for k in (PISO_MAD, PISO_HOSP, PISO_CONC, PAREDE, PAREDE_CONC, PORTA):
            pal[k] = COR_NAT[GRAMA]
        cores = pal[pad].copy()
        # agua funda mais escura
        prof = np.pad(self.tn == AGUA, 1, constant_values=True).astype(np.float32)
        viz = prof.copy()
        for _ in range(3):
            viz = (np.roll(viz, 1, 0) + np.roll(viz, -1, 0) + np.roll(viz, 1, 1) + np.roll(viz, -1, 1) + viz) / 5
        cores *= (1 - 0.35 * np.clip(viz - 0.6, 0, 1) / 0.4 * prof)[:, :, None]
        # mato mais escuro onde a floresta e densa
        m = np.pad(self.mata, 1, mode="edge")
        som = np.clip((m - m.mean()) * 1.4, -0.12, 0.12)
        nat = np.isin(pad, [GRAMA, MATO])[:, :, None]
        cores = np.where(nat, cores * (1 - som[:, :, None]), cores)
        self.cores = np.clip(cores, 0, 255).astype(np.uint8)

        self.texturas = [G.textura_chao(self.seed, CHPX)]
        self.spr_folhosa = [G.copa_folhosa(rnd, rnd.randint(24, 36)) for _ in range(12)]
        self.spr_pinheiro = [G.copa_pinheiro(rnd, rnd.randint(22, 32)) for _ in range(12)]
        self.spr_pedra = [G.pedra(rnd, 10 + (i % 4) * 2) for i in range(8)]
        self.spr_arbusto = [G.arbusto(rnd, rnd.randint(9, 14)) for _ in range(10)]
        self.spr_capim_p = [G.capim(rnd, rnd.randint(9, 14)) for _ in range(12)]
        self.spr_capim_g = [G.capim(rnd, rnd.randint(22, 34)) for _ in range(12)]
        self.spr_tufo = [G.tufo(rnd) for _ in range(16)]
        self.spr_carro = []
        self.base_carro = []
        for c in self.carros:
            base = G.carro(rnd, G.CORES_CARRO[c["cor"]])
            self.base_carro.append(base)
            self.spr_carro.append(pygame.transform.rotate(base, c["ang"]))
        for i, c in enumerate(self.carros):
            c["spr"] = i

        # mapa geral (1 pixel por quadradinho)
        mp = self.cores[1:-1, 1:-1].astype(np.float32)
        for k, v in COR_MAPA.items():
            mp[self.tn == k] = v
        arv = np.zeros((N, N), bool)
        for i in self.arvores:
            arv[i // N, i % N] = True
        mp[arv] *= 0.68
        mp[self.campo & ~arv] = mp[self.campo & ~arv] * 0.45 + np.array([168, 166, 78], np.float32) * 0.55
        self.mapa = pygame.surfarray.make_surface(np.ascontiguousarray(np.clip(mp, 0, 255).astype(np.uint8).transpose(1, 0, 2)))

    def assar_chao(self, cx, cy):
        x0 = cx * CH
        y0 = cy * CH
        small = pygame.surfarray.make_surface(np.ascontiguousarray(self.cores[y0:y0 + CH + 2, x0:x0 + CH + 2].transpose(1, 0, 2)))
        big = pygame.transform.smoothscale(small, ((CH + 2) * T, (CH + 2) * T))
        s = big.subsurface((T, T, CHPX, CHPX)).copy()
        arr = pygame.surfarray.pixels3d(s)
        tex = self.texturas[(cx * 7 + cy * 13) % len(self.texturas)]
        arr[:] = np.clip(arr * tex[:, :, None], 0, 255).astype(np.uint8)
        del arr

        r = random.Random(self.seed * 1000003 + cx * 7919 + cy)
        t = self.t
        ox = x0 * T
        oy = y0 * T
        for ly in range(CH):
            ty = y0 + ly
            for lx in range(CH):
                tx = x0 + lx
                v = t[ty * N + tx]
                px = lx * T
                py = ly * T
                if v == GRAMA or v == MATO:
                    for _ in range(3 if v == GRAMA else 2):
                        s.blit(self.spr_tufo[r.randrange(16)], (px + r.randint(-4, 24), py + r.randint(-4, 24)))
                    if r.random() < 0.05:
                        cor = r.choice([(240, 240, 230), (240, 210, 70), (180, 120, 200), (230, 120, 60)])
                        for _ in range(r.randint(2, 5)):
                            pygame.draw.circle(s, cor, (px + r.randint(2, 30), py + r.randint(2, 30)), 2)
                    if v == MATO and r.random() < 0.35:
                        for _ in range(r.randint(1, 4)):
                            pygame.draw.ellipse(s, r.choice([(110, 80, 40), (130, 96, 46), (90, 70, 40)]),
                                                (px + r.randint(0, 28), py + r.randint(0, 28), 5, 3))
                elif v == AREIA:
                    for _ in range(4):
                        pygame.draw.circle(s, (170, 156, 116), (px + r.randint(0, 31), py + r.randint(0, 31)), 1)
                elif v == AGUA:
                    if r.random() < 0.12:
                        x = px + r.randint(0, 20)
                        y = py + r.randint(4, 28)
                        pygame.draw.line(s, (90, 140, 170), (x, y), (x + r.randint(6, 14), y), 1)
                    if r.random() < 0.015:
                        pygame.draw.circle(s, (60, 120, 60), (px + 16, py + 16), 5)
                        pygame.draw.circle(s, (230, 200, 220), (px + 17, py + 15), 2)
                elif v == TERRA:
                    for _ in range(5):
                        pygame.draw.circle(s, (112, 92, 64), (px + r.randint(0, 31), py + r.randint(0, 31)), 1)
                elif v == ASFALTO:
                    if r.random() < 0.12:
                        x = px + r.randint(0, 31)
                        y = py + r.randint(0, 31)
                        pygame.draw.lines(s, (44, 46, 48), False, [(x, y), (x + r.randint(-8, 8), y + r.randint(-8, 8)),
                                                                   (x + r.randint(-14, 14), y + r.randint(-14, 14))], 1)
                    if r.random() < 0.03:
                        pygame.draw.circle(s, (90, 120, 60), (px + r.randint(4, 28), py + r.randint(4, 28)), 3)
                c = self.capim_p.get(ty * N + tx)
                if c:
                    sp = self.spr_capim_p[c[2]]
                    s.blit(sp, (c[0] - ox - sp.get_width() // 2, c[1] - oy - sp.get_height() // 2))
                c = self.arbustos.get(ty * N + tx)
                if c:
                    sp = self.spr_arbusto[c[2]]
                    s.blit(sp, (c[0] - ox - sp.get_width() // 2, c[1] - oy - sp.get_height() // 2))

        # sombras
        sombra = pygame.Surface((CHPX, CHPX), pygame.SRCALPHA)
        for ty in range(y0 - 2, y0 + CH + 2):
            for tx in range(x0 - 2, x0 + CH + 2):
                a = self.arvores.get(ty * N + tx)
                if a:
                    rr = 30 if a[2] == "folhosa" else 26
                    pygame.draw.ellipse(sombra, (0, 0, 0, 55), (a[0] - ox - rr + 10, a[1] - oy - rr * 0.8 + 12, rr * 2, rr * 1.6))
                    pygame.draw.ellipse(sombra, (0, 0, 0, 40), (a[0] - ox - rr * 0.6 + 9, a[1] - oy - rr * 0.5 + 10, rr * 1.2, rr))
        for b in self.pred_ch.get((cx, cy), ()):
            if b["tipo"] != "torre":
                pygame.draw.rect(sombra, (0, 0, 0, 70), (b["x"] * T - ox + 12, b["y"] * T - oy + 14, b["w"] * T, b["h"] * T),
                                 border_radius=4)
        for yy in (cy - 1, cy, cy + 1):
            for xx in (cx - 1, cx, cx + 1):
                for c in self.carros_ch.get((xx, yy), ()):
                    pygame.draw.ellipse(sombra, (0, 0, 0, 70), (c["x"] - ox - 30 + 6, c["y"] - oy - 30 + 8, 60, 60))
        s.blit(sombra, (0, 0))

        # pisos, paredes, pontes (bem definidos)
        for ly in range(CH):
            ty = y0 + ly
            for lx in range(CH):
                tx = x0 + lx
                v = t[ty * N + tx]
                if v not in ESTRUTURA:
                    continue
                px = lx * T
                py = ly * T
                h = ((tx * 73856093) ^ (ty * 19349663)) & 255
                if v == PISO_MAD:
                    base = (126 + h % 12, 94 + h % 9, 62 + h % 7)
                    pygame.draw.rect(s, base, (px, py, T, T))
                    for k in range(4):
                        cor = G.tom(base, ((h >> k) & 7) - 4)
                        pygame.draw.rect(s, cor, (px, py + k * 8, T, 7))
                        pygame.draw.line(s, G.tom(base, -26), (px, py + k * 8 + 7), (px + T, py + k * 8 + 7), 1)
                        j = (h * (k + 3)) % T
                        pygame.draw.line(s, G.tom(base, -22), (px + j, py + k * 8), (px + j, py + k * 8 + 7), 1)
                elif v == PISO_HOSP:
                    pygame.draw.rect(s, (208, 212, 210), (px, py, T, T))
                    pygame.draw.line(s, (178, 184, 182), (px, py), (px + T, py), 1)
                    pygame.draw.line(s, (178, 184, 182), (px, py + 16), (px + T, py + 16), 1)
                    pygame.draw.line(s, (178, 184, 182), (px, py), (px, py + T), 1)
                    pygame.draw.line(s, (178, 184, 182), (px + 16, py), (px + 16, py + T), 1)
                    if h < 20:
                        pygame.draw.circle(s, (120, 30, 30), (px + h % 30, py + h % 26), 3)
                elif v == PISO_CONC:
                    pygame.draw.rect(s, (124 + h % 8, 124 + h % 8, 118 + h % 6), (px, py, T, T))
                    for k in range(5):
                        pygame.draw.circle(s, (104, 104, 100), (px + (h * (k + 1) * 7) % 30, py + (h * (k + 2) * 5) % 30), 1)
                    pygame.draw.rect(s, (110, 110, 104), (px, py, T, T), 1)
                elif v in (PAREDE, PAREDE_CONC):
                    base = (92, 80, 70) if v == PAREDE else (120, 120, 114)
                    pygame.draw.rect(s, G.tom(base, -30), (px, py, T, T))
                    pygame.draw.rect(s, base, (px + 2, py + 2, T - 4, T - 4))
                    pygame.draw.line(s, G.tom(base, 25), (px + 2, py + 2), (px + T - 3, py + 2), 2)
                elif v == PORTA:
                    pygame.draw.rect(s, (118, 88, 58), (px, py, T, T))
                    pygame.draw.rect(s, (90, 66, 42), (px, py, T, T), 2)
                elif v == PONTE:
                    pygame.draw.rect(s, (112, 84, 54), (px, py, T, T))
                    hor = t[ty * N + tx - 1] == PONTE and t[ty * N + tx + 1] == PONTE
                    for k in range(0, T, 6):
                        if hor:
                            pygame.draw.line(s, (84, 62, 40), (px + k, py), (px + k, py + T), 1)
                        else:
                            pygame.draw.line(s, (84, 62, 40), (px, py + k), (px + T, py + k), 1)
                    for (dx, dy, rect) in ((0, -1, (px, py, T, 3)), (0, 1, (px, py + T - 3, T, 3)),
                                           (-1, 0, (px, py, 3, T)), (1, 0, (px + T - 3, py, 3, T))):
                        if self.tile(tx + dx, ty + dy) == AGUA:
                            pygame.draw.rect(s, (70, 50, 32), rect)
        # faixas das ruas
        for (ax, ay, bx, by) in self.ruas:
            if bx < x0 - 1 or ax > x0 + CH + 1 or by < y0 - 1 or ay > y0 + CH + 1:
                continue
            if ay == by:
                y = ay * T + 16 - oy
                for x in range(ax * T, bx * T, 34):
                    if x0 * T - 40 < x < (x0 + CH) * T + 40 and self.tile_px(x + 8, ay * T + 16) == ASFALTO:
                        pygame.draw.line(s, (214, 186, 80), (x - ox, y), (x - ox + 16, y), 3)
            else:
                x = ax * T + 16 - ox
                for y in range(ay * T, by * T, 34):
                    if y0 * T - 40 < y < (y0 + CH) * T + 40 and self.tile_px(ax * T + 16, y + 8) == ASFALTO:
                        pygame.draw.line(s, (214, 186, 80), (x, y - oy), (x, y - oy + 16), 3)
        # pedras e carros
        for ty in range(y0 - 1, y0 + CH + 1):
            for tx in range(x0 - 1, x0 + CH + 1):
                p = self.pedras.get(ty * N + tx)
                if p:
                    sp = self.spr_pedra[p[2]]
                    s.blit(sp, (p[0] - ox - sp.get_width() // 2, p[1] - oy - sp.get_height() // 2))
        for yy in (cy - 1, cy, cy + 1):
            for xx in (cx - 1, cx, cx + 1):
                for c in self.carros_ch.get((xx, yy), ()):
                    sp = self.spr_carro[c["spr"]]
                    s.blit(sp, (c["x"] - ox - sp.get_width() // 2, c["y"] - oy - sp.get_height() // 2))
        return s.convert() if pygame.display.get_surface() else s

    def assar_copa(self, cx, cy):
        x0 = cx * CH
        y0 = cy * CH
        ox = x0 * T
        oy = y0 * T
        s = None
        for ty in range(y0 - 2, y0 + CH + 2):
            for tx in range(x0 - 2, x0 + CH + 2):
                c = self.capim_g.get(ty * N + tx)
                if c:
                    if s is None:
                        s = pygame.Surface((CHPX, CHPX), pygame.SRCALPHA)
                    sp = self.spr_capim_g[c[2]]
                    s.blit(sp, (c[0] - ox - sp.get_width() // 2, c[1] - oy - sp.get_height() // 2))
        for ty in range(y0 - 2, y0 + CH + 2):
            for tx in range(x0 - 2, x0 + CH + 2):
                a = self.arvores.get(ty * N + tx)
                if a:
                    if s is None:
                        s = pygame.Surface((CHPX, CHPX), pygame.SRCALPHA)
                    sp = (self.spr_folhosa if a[2] == "folhosa" else self.spr_pinheiro)[a[3]]
                    s.blit(sp, (a[0] - ox - sp.get_width() // 2, a[1] - oy - sp.get_height() // 2))
        return s
