"""Piloto do Claude: joga o Ultimo Sobrevivente sozinho, de verdade (sem modo dono).

Ele so usa o que um jogador usa: anda (WASD), mira e atira com o mouse, aperta E, come, bebe e se cura
com o que achar. Para abrir:  pythonw jogo.py --piloto
"""
import heapq
import math

import numpy as np
import pygame

from config import *

PRIORIDADE_ARMAS = ["fuzil", "smg", "espingarda", "revolver", "pistola", "besta", "rifle"]


class Piloto:
    def __init__(self, jogo):
        self.j = jogo
        self.tarefas = []
        self.caminho = []
        self.alvo_caminho = None
        self.t_parado = 0.0
        self.ult_pos = (0.0, 0.0)
        self.espera = 0.0
        self.status = "Começando..."
        self.t_necess = 0.0
        self.grade = None
        self.t_grade = 0.0
        self.mouse = (W / 2 + 100, H / 2)
        self.montar_tarefas()

    # ------------------------------------------------------------------ mapa para andar
    def montar_grade(self):
        m = self.j.mundo
        t = np.frombuffer(bytes(m.t), dtype=np.uint8).reshape(N, N)
        livre = ~np.isin(t, list(SOLIDO))
        for lst in m.col.values():  # cada obstaculo tapa os quadradinhos que o corpo do jogador nao passa
            for (ox, oy, r) in lst:
                alc = r + 13
                for ty in range(int((oy - alc) // T), int((oy + alc) // T) + 1):
                    for tx in range(int((ox - alc) // T), int((ox + alc) // T) + 1):
                        if 0 <= tx < N and 0 <= ty < N:
                            if (tx * T + 16 - ox) ** 2 + (ty * T + 16 - oy) ** 2 < alc * alc:
                                livre[ty, tx] = False
        livre[0, :] = livre[-1, :] = livre[:, 0] = livre[:, -1] = False
        self.grade = livre
        custo = np.ones((N, N), np.float32)
        custo[np.isin(t, [ASFALTO, TERRA, PONTE])] = 0.45   # estrada: rapido e aberto
        custo[t == MATO] = 1.6                               # mato fechado: evita
        custo[t == AREIA] = 1.3                              # beira de rio: evita
        self.custo = custo

    def perto_livre(self, tx, ty):
        g = self.grade
        for r in range(0, 8):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    x, y = tx + dx, ty + dy
                    if 0 <= x < N and 0 <= y < N and g[y, x]:
                        return x, y
        return tx, ty

    def achar_caminho(self, x0, y0, x1, y1):
        g = self.grade
        a = self.perto_livre(int(x0 // T), int(y0 // T))
        b = self.perto_livre(int(x1 // T), int(y1 // T))
        aberto = [(0, 0, a)]
        veio = {a: None}
        custo = {a: 0}
        n = 0
        while aberto and n < 600000:
            n += 1
            _, c, atual = heapq.heappop(aberto)
            if atual == b:
                break
            cx, cy = atual
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < N and 0 <= ny < N) or not g[ny, nx]:
                    continue
                if dx and dy and not (g[cy, nx] and g[ny, cx]):  # nao corta quina
                    continue
                nc = c + (1.414 if dx and dy else 1.0) * float(self.custo[ny, nx])
                if nc < custo.get((nx, ny), 1e9):
                    custo[(nx, ny)] = nc
                    veio[(nx, ny)] = atual
                    h = max(abs(b[0] - nx), abs(b[1] - ny)) + 0.414 * min(abs(b[0] - nx), abs(b[1] - ny))
                    heapq.heappush(aberto, (nc + h * 0.7, nc, (nx, ny)))
        if b not in veio:
            return []
        pts = []
        no = b
        while no is not None:
            pts.append((no[0] * T + 16, no[1] * T + 16))
            no = veio[no]
        pts.reverse()
        return pts[1:] + [(x1, y1)]

    # ------------------------------------------------------------------ o plano do jogo
    def montar_tarefas(self):
        j = self.j
        m = j.mundo
        tf = []
        if j.cao and not j.cao["amigo"]:
            tf.append(("cao", None, "Fazendo carinho no Thor"))
        for i, b in enumerate(m.bunkers):
            caixa = next((mv for mv in m.moveis if mv.get("predio") is b and "revela" in mv), None)
            if caixa:
                tf.append(("revistar", caixa, f"Indo pela estrada pegar a peça do bunker {i + 1}"))
            for tipo in ("arsenal", "despensa"):
                mv = next((mv for mv in m.moveis if mv.get("predio") is b and mv["tipo"] == tipo), None)
                if mv:
                    tf.append(("revistar", mv, f"Pegando as coisas do {tipo} do bunker {i + 1}"))
        tf.append(("torre", m.torre, "Indo para a TORRE DE RÁDIO chamar o resgate"))
        tf.append(("resgate", None, "Aguentando os zumbis até o helicóptero chegar"))
        self.tarefas = tf

    def ponto_do_movel(self, mv):
        m = self.j.mundo
        for ox, oy in ((0, 30), (0, -30), (30, 0), (-30, 0), (24, 24), (-24, 24)):
            x, y = mv["x"] + ox, mv["y"] + oy
            if not m.bloqueado(x, y, 12):
                return x, y
        return mv["x"], mv["y"] + 30

    # ------------------------------------------------------------------ cada quadro
    def quadro(self, dt):
        j = self.j
        if j.estado == "morto":
            j.renascer()
            self.caminho = []
            self.status = "Morri... voltando para pegar a mochila e continuar"
            return
        if j.estado != "jogo":
            return
        if self.grade is None:
            self.montar_grade()
        p = j.p
        mv, corre, mira, tiro = (0.0, 0.0), False, False, False
        self.cuidar_da_vida(dt)
        luta = self.lutar()
        if j.cao and j.cao["amigo"]:  # o piloto manda o Thor atacar so quando esta lutando
            j.cao["modo"] = "ataque" if luta is not None else "quieto"
        if luta is not None:
            mv, mira, tiro = luta
        elif j.acao:
            pass  # revistando / consertando: fica parado
        elif self.espera > 0:
            self.espera -= dt
        elif self.tarefas:
            mv, corre = self.fazer_tarefa(dt)
        j.fake = dict(mv=mv, corre=corre, mira=mira, tiro=tiro, mouse=self.mouse)

    def cuidar_da_vida(self, dt):
        j = self.j
        p = j.p
        self.t_necess -= dt
        if self.t_necess > 0 or j.acao:
            return
        self.t_necess = 1.0
        inv = j.inv
        if p.sangrando and inv.get("bandagem", 0) > 0:
            j.usar("bandagem")
        elif (p.perna or p.braco or p.vida < 40) and inv.get("kit", 0) > 0:
            j.usar("kit")
        elif p.vida < 55 and inv.get("bandagem", 0) > 0:
            j.usar("bandagem")
        if p.fome < 40 and inv.get("comida", 0) > 0:
            j.usar("comida")
        if p.sede < 40 and inv.get("agua", 0) > 0:
            j.usar("agua")
        if p.vida < 30 and inv.get("seringa", 0) > 0:
            j.usar("seringa")

    def melhor_arma(self, d):
        j = self.j
        for ida in PRIORIDADE_ARMAS:
            if ida not in j.armas:
                continue
            a = j.arma_melhorada(ida)
            if j.pente.get(ida, 0) <= 0 and j.inv.get(a["mun"], 0) <= 0:
                continue
            if ida == "espingarda" and d > 300:
                continue
            return ida
        for ida in ("facao", "machado", "taco", "faca"):
            if ida in j.armas:
                return ida
        return j.armas[0]

    def lutar(self):
        j = self.j
        p = j.p
        m = j.mundo
        perigo = [z for z in j.zumbis if (z.estado == "perseguir" and (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 430 ** 2)
                  or (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 110 ** 2]
        if not perigo:
            return None
        z = min(perigo, key=lambda z: (z.x - p.x) ** 2 + (z.y - p.y) ** 2)
        d = math.hypot(z.x - p.x, z.y - p.y)
        arma = self.melhor_arma(d)
        if arma != j.arma:
            j.trocar_arma(arma)
        a = j.arma_atual()
        self.mouse = (z.x - j.cam[0] + W / 2, z.y - j.cam[1] + H / 2)
        dx, dy = (z.x - p.x) / max(d, 1), (z.y - p.y) / max(d, 1)
        self.status = f"Lutando com um zumbi ({a['nome']})"
        livre = m.linha_livre(p.x, p.y, z.x, z.y)
        if not livre and d > 70:  # tem parede no meio: nao fica empurrando a parede, segue o caminho
            return None
        if a["melee"]:
            if d > a["alcance"] + z.r - 6:
                return (dx, dy), False, False
            return (0.0, 0.0), False, True
        if d < 70:  # perto demais: anda para tras atirando
            return (-dx, -dy), False, True
        return (0.0, 0.0), True, True

    def fazer_tarefa(self, dt):
        j = self.j
        p = j.p
        tipo, obj, txt = self.tarefas[0]
        self.status = txt
        if tipo == "cao":
            alvo = (j.cao["x"], j.cao["y"])
            if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 50:
                j.interagir()
                self.tarefas.pop(0)
                self.espera = 1.0
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), False
        if tipo == "revistar":
            if obj["aberto"]:
                self.tarefas.pop(0)
                self.caminho = []
                return (0.0, 0.0), False
            alvo = self.ponto_do_movel(obj)
            if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 14:
                al = j.alvo_interacao()
                if al and al[1] is obj:
                    j.interagir()
                else:  # outro movel mais perto: revista ele tambem
                    j.interagir()
                self.espera = 0.3
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), True
        if tipo == "passar":
            if math.hypot(obj[0] - p.x, obj[1] - p.y) < 90:
                self.tarefas.pop(0)
                self.caminho = []
                return (0.0, 0.0), False
            return self.ir_para(obj, dt), True
        if tipo == "torre":
            if j.inv.get("peca", 0) < PECAS_RADIO:  # ainda falta peca: volta a procurar
                self.montar_tarefas()
                return (0.0, 0.0), False
            alvo = ((obj["x"] + obj["w"] / 2) * T, (obj["y"] + obj["h"] / 2) * T + 70)
            if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 20:
                j.interagir()
                if j.acao or j.resgate is not None:
                    self.tarefas.pop(0)
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), True
        if tipo == "resgate":
            if j.heli is not None:
                self.status = "O HELICÓPTERO CHEGOU! Esperando ele pousar..."
            elif j.resgate is not None:
                self.status = f"Aguentando os zumbis: helicóptero em {int(j.resgate)} segundos"
            return (0.0, 0.0), False
        return (0.0, 0.0), False

    def ir_para(self, alvo, dt):
        j = self.j
        p = j.p
        if self.alvo_caminho != alvo or not self.caminho:
            self.caminho = self.achar_caminho(p.x, p.y, alvo[0], alvo[1]) or [alvo]
            self.alvo_caminho = alvo
            self.t_parado = 0.0
        # preso? recalcula
        if math.hypot(p.x - self.ult_pos[0], p.y - self.ult_pos[1]) < 1.0:
            self.t_parado += dt
            if self.t_parado > 1.0:
                # o proximo ponto esta tapado: marca ele e procura outro caminho
                if self.caminho:
                    wx, wy = self.caminho[0]
                    self.grade[int(wy // T), int(wx // T)] = False
                self.caminho = self.achar_caminho(p.x, p.y, alvo[0], alvo[1]) or [alvo]
                self.t_parado = 0.0
        else:
            self.t_parado = 0.0
        self.ult_pos = (p.x, p.y)
        while len(self.caminho) > 1 and math.hypot(self.caminho[0][0] - p.x, self.caminho[0][1] - p.y) < 12:
            self.caminho.pop(0)
        wx, wy = self.caminho[0]
        dx, dy = wx - p.x, wy - p.y
        d = math.hypot(dx, dy)
        if d < 2:
            return (0.0, 0.0)
        self.mouse = (W / 2 + dx / d * 150, H / 2 + dy / d * 150)
        return (dx / d, dy / d)

    # ------------------------------------------------------------------ o que aparece na tela
    def desenhar(self, tela, fonte, fonte_peq):
        j = self.j
        caixa = pygame.Surface((560, 64), pygame.SRCALPHA)
        caixa.fill((10, 10, 14, 200))
        tela.blit(caixa, (W // 2 - 280, H - 168))
        t1 = fonte.render("PILOTO DO CLAUDE jogando ao vivo", True, (255, 200, 90))
        t2 = fonte_peq.render(self.status, True, (235, 230, 220))
        pecas = fonte_peq.render(f"Peças do rádio: {j.inv.get('peca', 0)}/{PECAS_RADIO}", True, (160, 230, 160))
        tela.blit(t1, t1.get_rect(center=(W // 2, H - 150)))
        tela.blit(t2, t2.get_rect(center=(W // 2, H - 126)))
        tela.blit(pecas, (W // 2 + 150, H - 160))
