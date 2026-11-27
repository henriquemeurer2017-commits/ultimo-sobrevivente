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
        self.rota = []
        self.alvo_caminho = None
        self.t_parado = 0.0
        self.ult_pos = (0.0, 0.0)
        self.espera = 0.0
        self.status = "Começando..."
        self.t_necess = 0.0
        self.grade = None
        self.t_grade = 0.0
        self.mouse = (W / 2 + 100, H / 2)
        self.quer_metro = False
        self.metro_feito = False
        self.carro_feito = False
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
        self.grade_base = livre.copy()  # o mapa limpo (as marcas de "enroscou aqui" sao apagadas de tempos em tempos)
        self.t_limpa_marcas = 25.0
        q = 4  # mapa grosso: cada celula = 4x4 quadradinhos (para planejar a rota longa rapido)
        self.grosso = livre.reshape(N // q, q, N // q, q).mean(axis=(1, 3)) >= 0.45
        self.custo_g = np.asarray(custo, dtype=np.float32).reshape(N // q, q, N // q, q).mean(axis=(1, 3))

    def perto_livre(self, tx, ty):
        g = self.grade
        for r in range(0, 8):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    x, y = tx + dx, ty + dy
                    if 0 <= x < N and 0 <= y < N and g[y, x]:
                        return x, y
        return tx, ty

    def achar_caminho(self, x0, y0, x1, y1, limite=600000):
        g = self.grade
        a = self.perto_livre(int(x0 // T), int(y0 // T))
        b = self.perto_livre(int(x1 // T), int(y1 // T))
        aberto = [(0, 0, a)]
        veio = {a: None}
        custo = {a: 0}
        n = 0
        melhor, melhor_h = a, 1e18
        while aberto and n < limite:
            n += 1
            _, c, atual = heapq.heappop(aberto)
            if atual == b:
                break
            cx, cy = atual
            hh = abs(b[0] - cx) + abs(b[1] - cy)
            if hh < melhor_h:  # o ponto mais perto do destino que ja deu para alcancar
                melhor, melhor_h = atual, hh
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
                    heapq.heappush(aberto, (nc + h * 1.6, nc, (nx, ny)))
        chegou = b in veio
        if not chegou:  # nao achou o caminho inteiro: vai ate o ponto mais perto e calcula de novo de la
            if melhor == a:
                return []
            b = melhor
        pts = []
        no = b
        while no is not None:
            pts.append((no[0] * T + 16, no[1] * T + 16))
            no = veio[no]
        pts.reverse()
        return pts[1:] + ([(x1, y1)] if chegou else [])

    def rota_grossa(self, x0, y0, x1, y1):
        """Rota no mapa grosso (rapida): lista de pontos no mundo, um a cada 4 quadradinhos."""
        g, cg, Q = self.grosso, self.custo_g, 4 * T
        n = g.shape[0]

        def livre_perto(cx, cy):
            for r in range(0, 6):
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        x, y = cx + dx, cy + dy
                        if 0 <= x < n and 0 <= y < n and g[y, x]:
                            return x, y
            return cx, cy
        a = livre_perto(int(x0 // Q), int(y0 // Q))
        b = livre_perto(int(x1 // Q), int(y1 // Q))
        aberto = [(0, 0, a)]
        veio = {a: None}
        custo = {a: 0}
        while aberto:
            _, c, atual = heapq.heappop(aberto)
            if atual == b:
                break
            cx, cy = atual
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < n and 0 <= ny < n) or not g[ny, nx]:
                    continue
                nc = c + (1.414 if dx and dy else 1.0) * float(cg[ny, nx])
                if nc < custo.get((nx, ny), 1e9):
                    custo[(nx, ny)] = nc
                    veio[(nx, ny)] = atual
                    h = max(abs(b[0] - nx), abs(b[1] - ny))
                    heapq.heappush(aberto, (nc + h, nc, (nx, ny)))
        if b not in veio:
            return []
        pts = []
        no = b
        while no is not None:
            pts.append((no[0] * Q + Q / 2, no[1] * Q + Q / 2))
            no = veio[no]
        pts.reverse()
        return pts

    # ------------------------------------------------------------------ o plano do jogo
    def montar_tarefas(self):
        j = self.j
        m = j.mundo
        tf = []
        if j.cao and not j.cao["amigo"]:
            tf.append(("cao", None, "Fazendo carinho no Thor"))
        for mv in m.moveis[j.n_moveis_base:]:  # a mochila que caiu quando morreu
            if mv["tipo"] == "mochila" and not mv["aberto"]:
                tf.append(("revistar", mv, "Buscando a mochila que caiu quando morri"))
        if not self.metro_feito and getattr(m, "metros", None):
            p = j.p
            mt = min(m.metros, key=lambda mt: (mt["ent"][0] - p.x) ** 2 + (mt["ent"][1] - p.y) ** 2)
            tf.append(("metro", mt, f"Indo para o METRÔ da estação {mt['cidade']}"))
        if not self.carro_feito:
            tf.append(("carro", None, "Procurando um CARRO com gasolina para ir dirigindo"))
        tem_radio = j.__dict__.get("radio_consertado")
        for i, b in enumerate(m.bunkers):
            if j.inv.get("peca", 0) >= PECAS_RADIO or tem_radio:  # ja tem as pecas: direto para a torre
                break
            caixa = next((mv for mv in m.moveis if mv.get("predio") is b and "revela" in mv), None)
            if caixa and caixa["aberto"]:  # bunker que ja foi revistado: nao volta nele
                continue
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
        self.relogio_luta = self.__dict__.get("relogio_luta", 0.0) + dt
        if j.estado == "morto":
            j.renascer()
            self.caminho = []
            self.status = "Morri... voltando para pegar a mochila e continuar"
            return
        if j.estado != "jogo":
            return
        j.teclas = set()  # quem joga e o piloto: teclado e rodinha do mouse nao trocam a arma dele
        j.roda = 0
        if j.dono:  # o piloto joga honesto: sem modo dono
            j.dono = False
            j.mochila_infinita = False
            j.console_ativo = False
        if self.grade is None:
            self.montar_grade()
        p = j.p
        mv, corre, mira, tiro = (0.0, 0.0), False, False, False
        self.cuidar_da_vida(dt)
        luta = None if j.dirigindo else self.lutar()
        if j.cao and j.cao["amigo"]:  # o piloto manda o Thor atacar so quando esta lutando
            j.cao["modo"] = "ataque" if luta is not None else "quieto"
        if luta is not None:
            mv, mira, tiro, corre = luta
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
        if j.espaco_usado() > j.capacidade() - 25:  # mochila cheia: larga o que o piloto nao usa
            for item in ("tabua", "sucata", "ferramentas"):
                if inv.get(item, 0) > 0:
                    inv[item] = 0
                    j.msg(f"Piloto largou {ITENS[item].lower()} para caber munição.", (200, 200, 190))
        if p.sangrando:  # sangrando: para o sangue com o que tiver
            for remedio in ("bandagem", "kit", "seringa"):
                if inv.get(remedio, 0) > 0:
                    j.usar(remedio)
                    break
        sem_remedio = not any(inv.get(r, 0) for r in ("bandagem", "kit", "seringa"))
        if (p.vida < 45 or p.sangrando) and sem_remedio and j.resgate is None                 and not any(t[0] == "cama" for t in self.tarefas):
            m = j.mundo
            camas = [c for c in m.camas if c.get("hospital")]
            if camas:  # sem nada para curar: corre para o hospital mais perto
                cama = min(camas, key=lambda c: (c["x"] - p.x) ** 2 + (c["y"] - p.y) ** 2)
                self.tarefas.insert(0, ("cama", cama, "Machucado e sem remédio: indo ao HOSPITAL se curar"))
                self.caminho = []
        if p.sangrando and inv.get("bandagem", 0) > 0:
            j.usar("bandagem")
        elif (p.perna or p.braco or p.vida < (65 if j.resgate is not None else 40)) and inv.get("kit", 0) > 0:
            j.usar("kit")
        elif p.vida < 55 and inv.get("bandagem", 0) > 0:
            j.usar("bandagem")
        cao = j.cao
        if cao and cao["amigo"] and not cao.get("morto") and math.hypot(cao["x"] - p.x, cao["y"] - p.y) < 90:
            precisa = j.cuidado_cao()
            if precisa:
                j.cuidar_thor(*precisa)
        if p.fome < 40 and inv.get("comida", 0) > 0:
            j.usar("comida")
        if p.sede < 40 and inv.get("agua", 0) > 0:
            j.usar("agua")
        if p.vida < 30 and inv.get("seringa", 0) > 0:
            j.usar("seringa")

    def melhor_arma(self, d, z=None):
        """Escolhe a arma pela distancia e varia: cada zumbi novo pode ser com uma arma diferente."""
        j = self.j
        if d < 75:
            lista = ["katana", "facao", "machado", "taco", "faca"]
        elif d < 200:
            lista = ["dragao", "espingarda", "smg", "revolver", "pistola", "minigun"]
        elif d < 320:
            lista = ["fuzil", "smg", "revolver", "besta", "minigun", "pistola"]
        else:
            lista = ["dourado", "rifle", "besta", "fuzil"]

        def tem(ida):
            if ida not in j.armas:
                return False
            a = j.arma_melhorada(ida)
            return a["melee"] or j.pente.get(ida, 0) > 0 or j.inv.get(a["mun"], 0) > 0

        boas = [i for i in lista if tem(i)]
        if z is not None and getattr(self, "zumbi_da_vez", None) is z and getattr(self, "arma_da_vez", None) in boas:
            return self.arma_da_vez  # continua com a mesma arma ate acabar com esse zumbi
        if boas:
            import random
            escolha = random.choice(boas[:3])
        else:
            outras = [i for i in ("fuzil", "smg", "espingarda", "revolver", "pistola", "besta", "rifle") if tem(i)]
            escolha = outras[0] if outras else next((i for i in ("facao", "machado", "taco", "faca") if i in j.armas),
                                                    j.armas[0])
        self.zumbi_da_vez, self.arma_da_vez = z, escolha
        return escolha

    def lutar(self):
        """Luta como um jogador bom: recua atirando, desvia de parede e foge do grupo."""
        j = self.j
        p = j.p
        m = j.mundo
        ign = self.__dict__.setdefault("ignorar", {})
        agora = self.__dict__.get("relogio_luta", 0.0)
        perigo = [z for z in j.zumbis if ((z.estado == "perseguir" and (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 450 ** 2)
                  or (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 120 ** 2)
                  and (ign.get(id(z), -1) < agora or (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 55 ** 2)]
        if not perigo:
            self.t_luta_parado = 0.0
            return None
        # lutando sem conseguir sair do lugar (zumbi atras de arvore/agua): desiste dele por um tempo
        if math.hypot(p.x - self.__dict__.get("pos_luta", (0, 0))[0], p.y - self.__dict__.get("pos_luta", (0, 0))[1]) < 1.5                 and not j.fake.get("tiro"):
            self.t_luta_parado = self.__dict__.get("t_luta_parado", 0.0) + 1 / 60
        else:
            self.t_luta_parado = 0.0
        self.pos_luta = (p.x, p.y)
        if self.t_luta_parado > 1.5:
            for q in perigo:
                if (q.x - p.x) ** 2 + (q.y - p.y) ** 2 >= 55 ** 2:
                    ign[id(q)] = agora + 10.0
            self.t_luta_parado = 0.0
            return None
        z = min(perigo, key=lambda z: (z.x - p.x) ** 2 + (z.y - p.y) ** 2)
        d = math.hypot(z.x - p.x, z.y - p.y)
        if j.resgate is not None and not j.telhado_b and d > 90 and self.tarefas and self.tarefas[0][0] == "resgate":
            return None  # correndo para o telhado: so luta se o zumbi estiver colado
        arma = self.melhor_arma(d, z)
        if arma != j.arma:
            j.trocar_arma(arma)
        a = j.arma_atual()
        self.mouse = (z.x - j.cam[0] + W / 2, z.y - j.cam[1] + H / 2)
        self.status = f"Lutando com {len(perigo)} zumbi(s) ({a['nome']})"
        livre = m.linha_livre(p.x, p.y, z.x, z.y)
        if not livre and d > 90:  # parede no meio: segue o caminho
            return None
        # para onde fugir: o lado contrario do grupo
        cx = sum(q.x for q in perigo) / len(perigo)
        cy = sum(q.y for q in perigo) / len(perigo)
        fx, fy = p.x - cx, p.y - cy
        n = math.hypot(fx, fy) or 1.0
        fx, fy = fx / n, fy / n
        fuga = self.direcao_livre(fx, fy)
        perto = sum(1 for q in perigo if (q.x - p.x) ** 2 + (q.y - p.y) ** 2 < 160 ** 2)
        if a["melee"]:
            if perto >= 2 or p.vida < 35:  # muita gente em volta so com faca: corre
                return fuga, False, False, True
            if d > a["alcance"] + z.r - 6:
                ax, ay = (z.x - p.x) / max(d, 1), (z.y - p.y) / max(d, 1)
                return (ax, ay), False, False, False
            return (0.0, 0.0), False, True, False
        if j.telhado_b:  # no telhado: fica parado atirando la de cima
            return (0.0, 0.0), True, True, False
        if d < 240 or perto >= 2:  # perto: anda para tras ATIRANDO, sem parar
            correr = d < 110 and p.folego > 15
            return fuga, False, True, correr
        return (0.0, 0.0), True, True, False  # longe: para e mira com calma

    def direcao_livre(self, fx, fy):
        """Tenta fugir reto; se tem parede, gira para os lados ate achar caminho."""
        m = self.j.mundo
        p = self.j.p
        base = math.atan2(fy, fx)
        for giro in (0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.5, -2.5):
            a = base + giro
            dx, dy = math.cos(a), math.sin(a)
            if not m.bloqueado(p.x + dx * 34, p.y + dy * 34, 13) and not m.bloqueado(p.x + dx * 70, p.y + dy * 70, 13):
                return (dx, dy)
        return (math.cos(base + 1.57), math.sin(base + 1.57))

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
            tent = self.__dict__.setdefault("tentativas", {})
            if obj["aberto"] or tent.get(id(obj), 0) >= 2:  # aberto, ou mochila cheia: segue em frente
                self.tarefas.pop(0)
                self.caminho = []
                return (0.0, 0.0), False
            alvo = self.ponto_do_movel(obj)
            if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 14:
                al = j.alvo_interacao()
                tent[id(obj)] = tent.get(id(obj), 0) + 1
                if al and al[1] is obj:
                    j.interagir()
                else:  # outro movel mais perto: revista ele tambem
                    j.interagir()
                self.espera = 0.3
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), True
        if tipo == "metro":
            if j.metro is None:  # ainda na rua: vai ate a entrada e desce
                self.quer_metro = True
                alvo = (obj["ent"][0], obj["ent"][1] + 64)
                self.status = txt
                if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 24:
                    al = j.alvo_interacao()
                    if al and al[0] == "descer_metro":
                        j.interagir()
                        self.caminho = []
                        self.espera = 1.0
                    return (0.0, 0.0), False
                return self.ir_para(alvo, dt), True
            # chegou la embaixo: revista a estacao, atravessa ate a outra escada e sobe
            self.tarefas.pop(0)
            sobra = j.capacidade() - j.espaco_usado()
            novas = [] if sobra < 60 else [("revistar", mv, f"Revistando a estação de metrô {obj['cidade']}")
                     for mv in sorted((mv for mv in j.mundo.moveis if mv.get("metro") == obj["idx"] and not mv["aberto"]),
                                      key=lambda mv: mv["x"])]
            novas.append(("sair_metro", obj, "Atravessando a estação até a outra escada" if novas else
                          "Mochila pequena: só atravessando a estação até a outra escada"))
            self.tarefas[0:0] = novas
            self.caminho = []
            return (0.0, 0.0), False
        if tipo == "sair_metro":
            if j.metro is None:
                self.tarefas.pop(0)
                self.quer_metro = False
                self.metro_feito = True
                self.caminho = []
                return (0.0, 0.0), False
            alvo = obj["saidas"][-1]
            if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 30:
                j.interagir()
                self.caminho = []
                self.espera = 1.0
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), True
        if tipo == "carro":
            return self.tarefa_carro(dt)
        if tipo == "cama":
            if p.vida >= 95 and not p.sangrando:
                self.tarefas.pop(0)
                self.caminho = []
                return (0.0, 0.0), False
            if math.hypot(obj["x"] - p.x, obj["y"] - p.y) < 34:
                j.interagir()  # deita na cama do hospital (cura tudo)
                self.espera = 0.5
                return (0.0, 0.0), False
            return self.ir_para((obj["x"], obj["y"]), dt), True
        if tipo == "passar":
            if math.hypot(obj[0] - p.x, obj[1] - p.y) < 90:
                self.tarefas.pop(0)
                self.caminho = []
                return (0.0, 0.0), False
            return self.ir_para(obj, dt), True
        if tipo == "torre":
            if j.inv.get("peca", 0) < PECAS_RADIO and not j.__dict__.get("radio_consertado"):  # falta peca
                self.montar_tarefas()
                return (0.0, 0.0), False
            centro = ((obj["x"] + obj["w"] / 2) * T, (obj["y"] + obj["h"] / 2) * T)
            alvo = (centro[0], centro[1] + 70)
            if math.hypot(centro[0] - p.x, centro[1] - p.y) < 100:  # o radio funciona de perto, nao precisa ponto exato
                j.interagir()
                if j.acao or j.resgate is not None:
                    self.tarefas.pop(0)
                return (0.0, 0.0), False
            return self.ir_para(alvo, dt), True
        if tipo == "resgate" and j.resgate is not None and not j.telhado_b:
            # no resgate: sobe no telhado mais perto (zumbi nao alcanca e o helicoptero busca la em cima)
            m = j.mundo
            alvo_b = self.__dict__.get("predio_resgate")
            if alvo_b is None:
                com_escada = [b for b in m.construcoes if b.get("escada")]
                if com_escada:
                    alvo_b = min(com_escada, key=lambda b: (b["escada"]["fora"][0] - p.x) ** 2
                                 + (b["escada"]["fora"][1] - p.y) ** 2)
                    self.predio_resgate = alvo_b
            if alvo_b is not None:
                fora = alvo_b["escada"]["fora"]
                self.status = "Resgate chamado! Subindo no TELHADO para esperar o helicóptero"
                if math.hypot(fora[0] - p.x, fora[1] - p.y) < 30:
                    j.interagir()
                    self.caminho = []
                    return (0.0, 0.0), False
                return self.ir_para(fora, dt), True
        if tipo == "resgate":
            if j.resgate is None and j.heli is None:  # morreu no resgate: volta e chama de novo
                self.montar_tarefas()
                return (0.0, 0.0), False
            if j.heli is not None:
                self.status = "O HELICÓPTERO CHEGOU! Esperando ele pousar..."
            elif j.resgate is not None:
                self.status = f"Aguentando os zumbis: helicóptero em {int(j.resgate)} segundos"
            return (0.0, 0.0), False
        return (0.0, 0.0), False

    def destino_da_viagem(self):
        """Para onde ir de carro: o lugar da proxima tarefa."""
        for tipo, obj, _ in self.tarefas[1:]:
            if tipo == "revistar":
                return self.ponto_do_movel(obj)
            if tipo == "torre":
                return ((obj["x"] + obj["w"] / 2) * self.T_, (obj["y"] + obj["h"] + 3) * self.T_)
        return None

    T_ = T

    def tarefa_carro(self, dt):
        j = self.j
        p = j.p
        m = j.mundo

        def acabou(txt=None):
            self.tarefas.pop(0)
            self.carro_feito = True
            self.caminho = []
            self.carro_alvo = None
            if txt:
                j.msg(txt, (200, 220, 255))
            return (0.0, 0.0), False

        destino = self.destino_da_viagem()
        if destino is None:
            return acabou()
        if not j.dirigindo:
            c = self.__dict__.get("carro_alvo")
            if c is None:
                bons = [c for c in m.carros if c.get("gas", 0) >= 15 and (c["x"] - p.x) ** 2 + (c["y"] - p.y) ** 2 < 1600 ** 2]
                if not bons:
                    return acabou("Piloto: nenhum carro com gasolina por perto, vou a pé.")
                c = self.carro_alvo = min(bons, key=lambda c: (c["x"] - p.x) ** 2 + (c["y"] - p.y) ** 2)
                self.t_carro = 0.0
            if self.__dict__.get("ja_dirigiu"):  # ja chegou de carro: desceu, segue a pe
                return acabou()
            self.status = "Indo até um CARRO com gasolina"
            self.t_carro = self.__dict__.get("t_carro", 0.0) + dt
            if self.t_carro > 60:  # nao conseguiu chegar no carro
                return acabou()
            if math.hypot(c["x"] - p.x, c["y"] - p.y) < 44:
                al = j.alvo_interacao()
                if al and al[0] == "carro":
                    j.interagir()
                    self.caminho = []
                    self.t_dirigindo = 0.0
                    self.t_preso_carro = 0.0
                    self.re = 0.0
                return (0.0, 0.0), False
            alvo = None
            for k in range(8):
                ax, ay = c["x"] + math.cos(k * 0.785) * 40, c["y"] + math.sin(k * 0.785) * 40
                if not m.bloqueado(ax, ay, 12):
                    alvo = (ax, ay)
                    break
            return self.ir_para(alvo or (c["x"], c["y"] + 40), dt), True
        # DIRIGINDO
        c = j.dirigindo
        self.ja_dirigiu = True
        self.t_dirigindo = self.__dict__.get("t_dirigindo", 0.0) + dt
        dist = math.hypot(destino[0] - p.x, destino[1] - p.y)
        self.status = f"Dirigindo o carro! Faltam {int(dist / 32)} metros  ·  gasolina {int(c.get('gas', 0))}%"
        if dist < 340 or self.t_dirigindo > 150 or c.get("gas", 0) <= 0:
            if abs(j.vel_carro) > 25:  # freia antes de descer
                return (0.0, 1.0), False
            j.interagir()  # sai do carro
            return acabou()
        # direcao: segue o caminho (o mesmo do andar a pe)
        self.ir_para(destino, dt)  # calcula o caminho (o mesmo do andar a pe)
        # carro nao faz curva fechada: mira num ponto do caminho la na frente
        while len(self.caminho) > 1 and math.hypot(self.caminho[0][0] - p.x, self.caminho[0][1] - p.y) < 80:
            self.caminho.pop(0)
        mira_pt = self.caminho[-1] if self.caminho else destino
        for wx, wy in self.caminho:
            if math.hypot(wx - p.x, wy - p.y) > 130:
                mira_pt = (wx, wy)
                break
        dx, dy = mira_pt[0] - p.x, mira_pt[1] - p.y
        quer = math.degrees(math.atan2(-dy, dx))
        dif = (quer - c["ang"] + 180) % 360 - 180
        vira = -max(-1.0, min(1.0, dif / 25))
        # preso? da re um pouquinho
        if self.__dict__.get("re", 0) > 0:
            self.re -= dt
            return (-vira, 1.0), False
        if abs(j.vel_carro) < 15:
            self.t_preso_carro = self.__dict__.get("t_preso_carro", 0.0) + dt
            if self.t_preso_carro > 1.2:
                self.t_preso_carro = 0.0
                self.re = 0.8
        else:
            self.t_preso_carro = 0.0
        if abs(dif) > 70 and j.vel_carro > 120:
            return (vira, 1.0), False  # curva fechada: freia
        acel = -1.0 if abs(dif) < 80 or j.vel_carro < 60 else 0.0
        return (vira, acel), False

    def sub_alvo(self, alvo):
        """O proximo pedaco da viagem: um ponto da rota grossa uns 25 quadradinhos a frente (ou o destino)."""
        p = self.j.p
        if math.hypot(alvo[0] - p.x, alvo[1] - p.y) < 30 * T or not self.rota:
            return alvo
        # joga fora o que ja ficou para tras: segue a partir do ponto da rota mais perto de voce
        perto = min(range(len(self.rota)), key=lambda i: (self.rota[i][0] - p.x) ** 2 + (self.rota[i][1] - p.y) ** 2)
        self.rota = self.rota[perto:]
        k = min(len(self.rota) - 1, 6)
        return self.rota[k]

    def ir_para(self, alvo, dt):
        j = self.j
        p = j.p
        if self.alvo_caminho != alvo:
            self.alvo_caminho = alvo
            self.rota = self.rota_grossa(p.x, p.y, alvo[0], alvo[1]) if math.hypot(alvo[0] - p.x, alvo[1] - p.y) > 30 * T else []
            self.caminho = []
            self.t_parado = 0.0
        # chegou no fim do pedaco (ou nao tem): calcula o proximo pedaco curto
        if not self.caminho or (len(self.caminho) == 1 and math.hypot(self.caminho[0][0] - p.x, self.caminho[0][1] - p.y) < 14):
            sub = self.sub_alvo(alvo)
            self.caminho = self.achar_caminho(p.x, p.y, sub[0], sub[1], 60000) or [sub]
        # de tempos em tempos esquece as marcas de "enroscou aqui" (para nao se trancar sozinho)
        self.t_limpa_marcas -= dt
        if self.t_limpa_marcas <= 0:
            self.t_limpa_marcas = 25.0
            self.grade = self.grade_base.copy()
        # mexidinha para o lado depois de enroscar
        if self.__dict__.get("t_mexida", 0) > 0:
            self.t_mexida -= dt
            return self.dir_mexida
        # preso? marca o ponto tapado, da uma mexidinha e calcula de novo
        if math.hypot(p.x - self.ult_pos[0], p.y - self.ult_pos[1]) < 1.0:
            self.t_parado += dt
            if self.t_parado > 0.8:
                if self.caminho:
                    wx, wy = self.caminho[0]
                    tx_, ty_ = int(wx // T), int(wy // T)
                    if (tx_, ty_) != (int(p.x // T), int(p.y // T)):
                        self.grade[ty_, tx_] = False
                # mexidinha para uma direcao LIVRE (a mais parecida com para onde quer ir)
                m_ = j.mundo
                quer = math.atan2(alvo[1] - p.y, alvo[0] - p.x)
                livres = [k_ * 0.785 for k_ in range(8)
                          if not m_.bloqueado(p.x + math.cos(k_ * 0.785) * 10, p.y + math.sin(k_ * 0.785) * 10, 12)]
                if livres:
                    a_ = min(livres, key=lambda a: abs((a - quer + math.pi) % (2 * math.pi) - math.pi))
                else:
                    a_ = quer + math.pi
                self.dir_mexida = (math.cos(a_), math.sin(a_))
                self.t_mexida = 0.35
                sub = self.sub_alvo(alvo)
                self.caminho = self.achar_caminho(p.x, p.y, sub[0], sub[1], 60000)
                if not self.caminho:  # nao achou: limpa as marcas e tenta de novo
                    self.grade = self.grade_base.copy()
                    self.caminho = self.achar_caminho(p.x, p.y, sub[0], sub[1], 60000) or [sub]
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
