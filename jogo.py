"""
ÚLTIMO SOBREVIVENTE
Jogo 2D (visto de cima) de sobrevivência num mundo aberto tomado por zumbis.

Controles:
    W A S D ............ andar               SHIFT ... correr (gasta fôlego)
    Mouse .............. mirar               Botão ESQUERDO ... atacar / atirar
    Botão DIREITO ...... mirar com calma (mais preciso)
    1 a 6 / rodinha .... trocar de arma      R ... recarregar
    E .................. revistar, beber água no lago, dormir, descansar, cortar árvore
    F comer   G beber   H bandagem   J kit médico
    B .................. construir (barricada, fogueira, bunker)
    L lanterna   M mapa   ESC pausa   F11 tela cheia
"""
import json
import math
import os
import random
import sys
import time
from collections import OrderedDict

TESTE = "--teste" in sys.argv
NAVEGADOR = sys.platform == "emscripten"
if TESTE:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
# em tela cheia, nao minimizar quando outra janela pega o foco
os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")

import numpy as np
import pygame
try:
    import pygame.mixer
    import pygame.sndarray
except Exception:
    pass

import graficos as G
from config import *
from mundo import Mundo, sortear

clamp = G.clamp


class Jogador:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.ang = 0.0
        self.vida = 100.0
        self.fome = 100.0
        self.sede = 100.0
        self.folego = 100.0
        self.r = 12
        self.sangrando = False
        self.perna = False  # perna quebrada
        self.braco = False  # braco quebrado

    def curar_tudo(self):
        self.sangrando = False
        self.perna = False
        self.braco = False


class Zumbi:
    def __init__(self, x, y, tipo, var, rnd):
        self.x = x
        self.y = y
        self.tipo = tipo
        self.var = var
        if tipo == "gigante":
            self.hp = 1100
            self.vel = rnd.uniform(48, 56)
            self.r = 22
            self.dano = 30
        elif tipo == "gordo":
            self.hp = 230
            self.vel = rnd.uniform(40, 50)
            self.r = 14
            self.dano = 16
        elif tipo == "corredor":
            self.hp = 80
            self.vel = rnd.uniform(150, 175)
            self.r = 11
            self.dano = 7
        else:
            self.hp = 100
            self.vel = rnd.uniform(52, 74)
            self.r = 12
            self.dano = 10
        self.ang = rnd.uniform(0, 6.283)
        self.ang_vis = self.ang
        self.estado = "vagar"
        self.alvo = None
        self.t_ataque = 0.0
        self.t_pensar = rnd.uniform(0, 0.3)
        self.t_gemido = rnd.uniform(3, 12)
        self.t_vagar = 0.0
        self.parado = False
        self.viu = 0.0
        self.flash = 0.0
        self.balanco = rnd.uniform(0, 6.28)


class Jogo:
    def __init__(self):
        try:
            pygame.mixer.pre_init(22050, -16, 2, 512)
        except Exception:
            pass
        pygame.init()
        pygame.display.set_caption("Último Sobrevivente")
        try:
            pygame.display.set_icon(pygame.image.load(os.path.join(HERE, "icone.png")))
        except Exception:
            pass
        flags = 0 if (TESTE or sys.platform == "emscripten") else (pygame.SCALED | pygame.FULLSCREEN)
        self.tela = pygame.display.set_mode((W, H), flags)
        self.relogio = pygame.time.Clock()
        self.f_peq = pygame.font.SysFont("segoeui", 15)
        self.f_med = pygame.font.SysFont("segoeui", 19, bold=True)
        self.f_med2 = pygame.font.SysFont("segoeui", 19)
        self.f_grande = pygame.font.SysFont("segoeui", 34, bold=True)
        self.f_titulo = pygame.font.SysFont("segoeui", 76, bold=True)
        self.f_morte = pygame.font.SysFont("impact,segoeuiblack,arialblack", 170)
        if NAVEGADOR:  # no navegador nao tem a letra Impact
            self.f_morte = pygame.font.Font(None, 210)
            self.f_morte.set_bold(True)
        self.sons = G.criar_sons()
        for novo, base in (("smg", "pistola"), ("besta", "clique"), ("facao", "faca"), ("katana", "faca"),
                           ("minigun", "fuzil"), ("dragao", "espingarda"), ("dourado", "rifle"), ("rpg", "espingarda")):
            if novo not in self.sons and base in self.sons:
                self.sons[novo] = self.sons[base]
        self.rnd = random.Random()
        r = random.Random(42)
        self.spr_z = {"normal": [G.sprite_zumbi(r, "normal") for _ in range(16)],
                      "gordo": [G.sprite_zumbi(r, "gordo") for _ in range(6)],
                      "corredor": [G.sprite_zumbi(r, "corredor") for _ in range(6)],
                      "gigante": [G.sprite_zumbi(r, "gigante") for _ in range(2)]}
        self.spr_morto = {}
        for tipo, lst in self.spr_z.items():
            self.spr_morto[tipo] = []
            for s in lst:
                m = s.copy()
                m.fill((120, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
                self.spr_morto[tipo].append(m)
        self.spr_j = {a["id"]: G.sprite_jogador(a["id"]) for a in ARMAS}
        self.spr_sangue = [G.sangue(r, r.randint(5, 10)) for _ in range(10)]
        self.spr_sombra = G.sombra_suave(15, 12)
        self.spr_sombra_g = G.sombra_suave(19, 15)
        self.spr_sombra_gg = G.sombra_suave(32, 26)
        self.spr_barricada = G.sprite_barricada()
        self.spr_fogueira = G.sprite_fogueira()
        self.spr_abrigo = G.sprite_abrigo()
        self.spr_bancada = G.sprite_bancada()
        self.spr_arame = G.sprite_arame()
        self.spr_ponte = G.sprite_ponte()
        self.spr_torre = G.sprite_torre()
        self.spr_cama_h = G.sprite_cama(True)
        self.spr_cama_m = G.sprite_cama(False)
        self.luz_jog = G.luz_redonda(130, 0.78)
        self.luz_fogo = G.luz_redonda(300, 1.0, 1.2)
        self.luz_flash = G.luz_redonda(240, 1.0, 1.3)
        self.luz_peq = G.luz_redonda(60, 0.7)
        self.cone = G.luz_cone(480)
        self.cone_cache = OrderedDict()
        self.vinheta = G.vinheta()
        self.vinheta_v = G.vinheta_vermelha()
        self.escuro = pygame.Surface((W, H), pygame.SRCALPHA)
        self.rot_cache = {}
        self.estado = "menu"
        self.mundo = None
        self.click = False
        self.click_dir = False
        self.teclas = set()
        self.roda = 0
        self.fake = None
        self.recorde = self.ler_recorde()
        self.t_menu = 0.0
        self.fundo_menu = self.criar_fundo_menu()
        self.canal_chuva = None

    # ================================================================ arquivos
    def ler_recorde(self):
        try:
            with open(RECORDE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"dias": 0, "zumbis": 0, "resgates": 0}

    def gravar_recorde(self):
        try:
            with open(RECORDE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.recorde, f)
        except Exception:
            pass

    def tem_save(self):
        return bool(self.listar_mundos())

    def caminho_save(self):
        return self.__dict__.get("arq") or SAVE_FILE

    def listar_mundos(self):
        """Todos os mundos salvos: [(arquivo, nome, dia, zumbis, quando)], o mais recente primeiro."""
        os.makedirs(MUNDOS_DIR, exist_ok=True)
        # o jogo salvo antigo (de antes dos mundos) vira "Meu mundo"
        if os.path.exists(SAVE_FILE) and os.path.dirname(os.path.abspath(SAVE_FILE)) == os.path.abspath(HERE):
            try:
                with open(SAVE_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                d.setdefault("nome", "Meu mundo")
                destino = os.path.join(MUNDOS_DIR, "mundo_1.json")
                k = 1
                while os.path.exists(destino):
                    k += 1
                    destino = os.path.join(MUNDOS_DIR, f"mundo_{k}.json")
                with open(destino, "w", encoding="utf-8") as f:
                    json.dump(d, f)
                os.remove(SAVE_FILE)
            except Exception:
                pass
        lista = []
        for nome in os.listdir(MUNDOS_DIR):
            if not nome.endswith(".json"):
                continue
            arq = os.path.join(MUNDOS_DIR, nome)
            try:
                with open(arq, encoding="utf-8") as f:
                    d = json.load(f)
                lista.append((arq, d.get("nome", "Mundo"), d.get("dia", 1), d.get("mortes", 0), os.path.getmtime(arq)))
            except Exception:
                continue
        lista.sort(key=lambda m: -m[4])
        return lista

    def arquivo_novo(self):
        os.makedirs(MUNDOS_DIR, exist_ok=True)
        k = 1
        while os.path.exists(os.path.join(MUNDOS_DIR, f"mundo_{k}.json")):
            k += 1
        return os.path.join(MUNDOS_DIR, f"mundo_{k}.json")

    # ================================================================ loop
    def rodar(self):
        while True:
            self.passo()

    def passo(self):
        """Um quadro do jogo (a versao de navegador chama isto a cada quadro)."""
        # no navegador quem segura a velocidade e o proprio navegador; aqui so mede o tempo
        dt = min(self.relogio.tick(0 if NAVEGADOR else FPS) / 1000.0, 0.05)
        self.eventos()
        getattr(self, "tela_" + self.estado)(dt)
        pygame.display.flip()

    def eventos(self):
        self.click = False
        self.click_dir = False
        self.teclas = set()
        self.roda = 0
        self.letras = ""
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.sair()
            elif e.type == pygame.KEYDOWN:
                self.teclas.add(e.key)
                if getattr(e, "unicode", ""):
                    self.digitado = (self.__dict__.get("digitado", "") + e.unicode)[-12:]
                    if e.unicode.isprintable():
                        self.letras += e.unicode
                if e.key == pygame.K_F11:
                    try:
                        pygame.display.toggle_fullscreen()
                    except Exception:
                        pass
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    self.click = True
                elif e.button == 3:
                    self.click_dir = True
            elif e.type == pygame.MOUSEWHEEL:
                self.roda = e.y

    def sair(self):
        if self.mundo is not None and self.estado in ("jogo", "pausa", "mapa", "construir"):
            self.salvar()
        pygame.quit()
        sys.exit(0)

    # ================================================================ menus
    def criar_fundo_menu(self):
        s = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            pygame.draw.line(s, G.mistura((10, 14, 26), (44, 38, 40), k), (0, y), (W, y))
        for k in range(6):
            pygame.draw.circle(s, G.mistura((10, 14, 26), (60, 60, 70), (k + 1) / 7), (1150, 300), 120 - k * 10)
        pygame.draw.circle(s, (230, 226, 200), (1150, 300), 56)
        pygame.draw.circle(s, (210, 206, 180), (1135, 288), 10)
        pygame.draw.circle(s, (210, 206, 180), (1166, 318), 7)
        r = random.Random(7)
        for camada, (cor, base, alt) in enumerate([((22, 30, 30), 560, 220), ((14, 20, 20), 640, 260)]):
            x = -40
            while x < W + 40:
                h = r.randint(alt // 2, alt)
                larg = r.randint(40, 80)
                pts = [(x, base + 40)]
                for k in range(6):
                    yk = base - h * (1 - k / 6)
                    pts.insert(0, (x - larg * (1 - k / 6) / 2, yk + 30))
                    pts.append((x + larg * (1 - k / 6) / 2, yk + 30))
                pygame.draw.polygon(s, cor, [(x, base - h)] + [(x - larg / 2, base + 40), (x + larg / 2, base + 40)])
                for k in range(5):
                    yk = base - h + h * k / 5
                    w_ = larg * (k + 1) / 5
                    pygame.draw.polygon(s, cor, [(x, yk - 10), (x - w_ / 2, yk + h / 5), (x + w_ / 2, yk + h / 5)])
                x += r.randint(30, 70)
            pygame.draw.rect(s, cor, (0, base + 30, W, H))
        return s

    def botao(self, texto, cx, y, w=320, ativo=True):
        rect = pygame.Rect(cx - w // 2, y, w, 50)
        mx, my = pygame.mouse.get_pos()
        hover = rect.collidepoint(mx, my) and ativo
        cor = (150, 40, 34) if hover else (60, 30, 28)
        if not ativo:
            cor = (40, 40, 40)
        pygame.draw.rect(self.tela, (0, 0, 0), rect.move(3, 4), border_radius=10)
        pygame.draw.rect(self.tela, cor, rect, border_radius=10)
        pygame.draw.rect(self.tela, (200, 80, 60) if hover else (110, 60, 50), rect, 2, border_radius=10)
        txt = self.f_med.render(texto, True, (240, 230, 220) if ativo else (120, 120, 120))
        self.tela.blit(txt, txt.get_rect(center=rect.center))
        return hover and self.click

    def texto(self, txt, pos, fonte=None, cor=(235, 230, 220), centro=False, sombra=True):
        fonte = fonte or self.f_med2
        # textos prontos ficam guardados: escrever letra por letra todo quadro pesa
        cache = self.__dict__.setdefault("cache_texto", {})
        k = (txt, id(fonte), cor, sombra)
        par = cache.get(k)
        if par is None:
            img = fonte.render(txt, True, cor)
            sh = fonte.render(txt, True, (0, 0, 0)) if sombra else None
            if len(cache) > 800:
                cache.clear()
            par = cache[k] = (img, sh)
        img, sh = par
        r = img.get_rect(center=pos) if centro else img.get_rect(topleft=pos)
        if sh is not None:
            self.tela.blit(sh, r.move(2, 2))
        self.tela.blit(img, r)
        return r

    def desenhar_fundo_menu(self, dt):
        self.t_menu += dt
        self.tela.blit(self.fundo_menu, (0, 0))
        nevoa = pygame.Surface((W, 200), pygame.SRCALPHA)
        for i in range(8):
            x = (i * 260 + self.t_menu * (12 + i * 3)) % (W + 400) - 200
            pygame.draw.ellipse(nevoa, (180, 190, 200, 18), (x, 60 + (i % 3) * 30, 420, 90))
        self.tela.blit(nevoa, (0, 480))
        self.tela.blit(self.vinheta, (0, 0))

    def tela_menu(self, dt):
        self.desenhar_fundo_menu(dt)
        self.texto("ÚLTIMO SOBREVIVENTE", (W // 2, 140), self.f_titulo, (225, 70, 55), centro=True)
        self.texto("um apocalipse zumbi em mundo aberto", (W // 2, 205), self.f_med2, (210, 200, 190), centro=True)
        y = 290
        if self.botao("Jogar", W // 2, y):
            self.estado = "mundos"
            self.nome_novo = ""
            self.apagar_qual = None
            return
        y += 64
        if self.botao("Como jogar", W // 2, y):
            self.estado = "como"
        y += 64
        if self.botao("Sair", W // 2, y):
            self.sair()
        rec = self.recorde
        self.texto(f"Recorde: {rec.get('dias', 0)} dias  ·  {rec.get('zumbis', 0)} zumbis  ·  resgates: {rec.get('resgates', 0)}",
                   (W // 2, H - 40), self.f_peq, (170, 160, 150), centro=True)

    def tela_mundos(self, dt):
        """Escolher o mundo para jogar, ou criar um mundo novo com nome."""
        self.desenhar_fundo_menu(dt)
        if pygame.K_ESCAPE in self.teclas:
            self.estado = "menu"
            return
        self.texto("SEUS MUNDOS", (W // 2, 54), self.f_titulo, (225, 70, 55), centro=True)
        mundos = self.listar_mundos()
        caixa = pygame.Rect(W // 2 - 380, 104, 760, 400)
        self.painel(caixa, 200)
        if not mundos:
            self.texto("Você ainda não tem nenhum mundo. Crie um aí embaixo!", (W // 2, caixa.centery), self.f_med2,
                       (210, 200, 190), centro=True)
        mouse = pygame.mouse.get_pos()
        for i, (arq, nome, dia, mortes, _) in enumerate(mundos[:6]):
            r = pygame.Rect(caixa.x + 16, caixa.y + 14 + i * 64, caixa.w - 32, 56)
            pygame.draw.rect(self.tela, (52, 40, 34) if r.collidepoint(mouse) else (34, 30, 28), r, border_radius=10)
            G.desenha_icone(self.tela, "mochila3", r.x + 30, r.centery, 1.3)
            self.texto(nome, (r.x + 60, r.y + 6), self.f_med, (240, 225, 200))
            self.texto(f"Dia {dia}   ·   {mortes} zumbis derrubados", (r.x + 60, r.y + 31), self.f_peq, (190, 180, 170))
            if self.botao_peq("Jogar", pygame.Rect(r.right - 230, r.y + 10, 110, 36), (60, 90, 50)):
                self.carregar(arq)
                return
            certeza = self.__dict__.get("apagar_qual") == arq
            if self.botao_peq("Certeza?" if certeza else "Apagar", pygame.Rect(r.right - 112, r.y + 10, 100, 36),
                              (130, 30, 26) if certeza else (60, 34, 30)):
                if certeza:
                    try:
                        os.remove(arq)
                    except Exception:
                        pass
                    self.apagar_qual = None
                else:
                    self.apagar_qual = arq
        if len(mundos) > 6:
            self.texto(f"(+{len(mundos) - 6} mundos mais antigos)", (W // 2, caixa.bottom - 16), self.f_peq,
                       (170, 160, 150), centro=True)
        # mundo novo com nome
        nome = self.__dict__.get("nome_novo", "")
        if pygame.K_BACKSPACE in self.teclas:
            nome = nome[:-1]
        elif self.letras and pygame.K_RETURN not in self.teclas:
            nome = (nome + self.letras)[:22]
        self.nome_novo = nome
        self.texto("MUNDO NOVO  ·  escreva o nome dele:", (W // 2 - 380, 524), self.f_med, (255, 220, 140))
        campo = pygame.Rect(W // 2 - 380, 556, 500, 50)
        pygame.draw.rect(self.tela, (20, 18, 18), campo, border_radius=8)
        pygame.draw.rect(self.tela, (200, 150, 90), campo, 2, border_radius=8)
        pisca = "|" if int(time.time() * 2) % 2 == 0 else ""
        self.texto((nome or "") + pisca if nome else "ex.: Mundo do Leandro" + pisca, (campo.x + 14, campo.y + 12),
                   self.f_med2, (240, 235, 225) if nome else (120, 115, 110))
        criar = self.botao_peq("Criar mundo", pygame.Rect(campo.right + 12, campo.y + 2, 248, 46), (60, 90, 50))
        if criar or (pygame.K_RETURN in self.teclas):
            nome_final = nome.strip() or f"Mundo {len(mundos) + 1}"
            self.arq = self.arquivo_novo()
            self.nome_mundo = nome_final
            self.novo_jogo()
            self.salvar()
            return
        if self.botao("Voltar", W // 2, 640, w=220):
            self.estado = "menu"

    def tela_confirmar(self, dt):
        self.desenhar_fundo_menu(dt)
        self.texto("Começar um mundo novo?", (W // 2, 230), self.f_grande, centro=True)
        self.texto("O jogo salvo atual será apagado.", (W // 2, 285), self.f_med2, (220, 180, 170), centro=True)
        if self.botao("Sim, mundo novo", W // 2, 350):
            try:
                os.remove(SAVE_FILE)
            except Exception:
                pass
            self.novo_jogo()
        if self.botao("Voltar", W // 2, 414) or pygame.K_ESCAPE in self.teclas:
            self.estado = "menu"

    def tela_como(self, dt):
        self.desenhar_fundo_menu(dt)
        self.texto("COMO JOGAR", (W // 2, 60), self.f_grande, centro=True)
        linhas = [
            "W A S D: andar   ·   SHIFT: correr   ·   Mouse: mirar   ·   Botão esquerdo: atacar/atirar",
            "Botão direito: mirar   ·   R: recarregar   ·   1 a 0: armas   ·   ESPAÇO: esquiva   ·   C: agachar",
            "E: revistar armários, carros e caixas  ·  beber água no lago  ·  dormir  ·  cortar árvore (com machado)",
            "F: comer   ·   G: beber água   ·   H: bandagem   ·   J: kit médico",
            "B: construir (BANCADA melhora armas)  ·  L: lanterna  ·  M: mapa  ·  V: MOCHILA  ·  K: LOJA",
            "",
            "Fique de olho nas barras de VIDA, FOME e SEDE. Se a fome ou a sede zerarem, você perde vida.",
            "Hospital cura. Bunker e SACO DE DORMIR servem para dormir e salvar. A SERINGA (rara, nos bunkers) cura tudo.",
            "Armas e munição ficam no chão, nas casas, nos carros e nos bunkers. O silenciador deixa o tiro baixinho.",
            "Zumbi só te persegue se te VER (de frente, sem nada no meio). O \"?\" mostra que ele desconfiou.",
            "Barulho atrai zumbis. Nos campos de capim alto (amarelos no mapa) eles quase não te enxergam.",
            "Tem regiões calmas sem nenhum zumbi. Cidades e algumas matas são infestadas. A noite é bem escura.",
            "",
            "OBJETIVO: achar as 5 peças do rádio nos bunkers militares e chamar o resgate na torre de rádio.",
            "Cada bunker tem um bilhete que mostra onde está o próximo. As estações mudam a cada 6 dias. O jogo salva sozinho.",
        ]
        y = 118
        for l in linhas:
            self.texto(l, (W // 2, y), self.f_med2 if l.isupper() is False else self.f_med, centro=True)
            y += 32 if l else 16
        if self.botao("Voltar", W // 2, H - 60) or pygame.K_ESCAPE in self.teclas:
            self.estado = "menu"

    def aviso_carregando(self, txt):
        self.desenhar_fundo_menu(0.016)
        self.texto("ÚLTIMO SOBREVIVENTE", (W // 2, 200), self.f_grande, (225, 70, 55), centro=True)
        self.texto(txt, (W // 2, 330), self.f_med2, centro=True)
        pygame.display.flip()
        pygame.event.pump()

    # ================================================================ novo / salvar / carregar
    def preparar(self, seed):
        self.mundo = Mundo(seed, self.aviso_carregando)
        self.n_itens_base = len(self.mundo.itens_chao)
        self.n_moveis_base = len(self.mundo.moveis)
        self.cache_chao = OrderedDict()
        self.cache_copa = OrderedDict()
        self.telhados = {}
        self.alfa_telhado = {}
        self.zumbis = []
        self.particulas = []
        self.rastros = []
        self.decalques = []
        self.msgs = []
        self.construidos = []
        self.cortadas = []
        self.flash_t = 0.0
        self.dano_t = 0.0
        self.cd = 0.0
        self.recarga_t = 0.0
        self.acao = None
        self.t_spawn = 0.0
        self.na_calma = False
        self.agachado = False
        self.console_ativo = False
        self.console_modo = "comando"
        self.console_txt = ""
        self.moedas = 0
        self.dono = False
        self.mochila_infinita = False
        self.digitado = ""
        self.niveis = {}
        self.miras = []
        self.reforco_mochila = 0
        self.tremor = 0.0
        self.numeros = []
        self.esquiva = 0.0
        self.t_esquiva = 0.0
        self.dir_esquiva = (1.0, 0.0)
        self.adrenalina = 0.0
        self.estacao_atual = None
        self.nivel_mochila = 0
        self.t_cheia = 0.0
        self.t_explo = 0.0
        self.t_auto = 0.0
        self.t_gemidos = 0.0
        self.modo_construir = None
        self.lanterna = True
        self.cam = [0.0, 0.0]
        self.chuva = False
        self.t_clima = 300.0
        self.gotas = [[random.uniform(0, W), random.uniform(0, H), random.uniform(0.6, 1.0)] for _ in range(220)]
        self.resgate = None
        self.heli = None
        self.fog = pygame.Surface((N, N), pygame.SRCALPHA)
        self.fog.fill((10, 12, 16, 255))
        self.explorado = bytearray(NE * NE)
        self.mapa_grande = None
        self.drop_id = 10 ** 7

    def novo_jogo(self, seed=None):
        seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        self.preparar(seed)
        m = self.mundo
        self.p = Jogador(*m.inicio)
        self.respawn = list(m.inicio)
        self.inv = {"comida": 1, "agua": 1, "bandagem": 1}
        self.moedas = self.recorde.get("moedas", 0)
        if self.recorde.get("dono"):
            self.dono = True
        self.armas = ["faca"]
        self.pente = {}
        self.silen = []
        self.arma = "faca"
        self.hora = 8.0
        self.dia = 1
        self.mortes = 0
        self.vezes_morto = 0
        self.revelados = [0] if m.bunkers else []
        self.cam = [self.p.x, self.p.y]
        self.estado = "jogo"
        self.msg("Você acordou sozinho. O mundo acabou.", (240, 220, 200))
        self.msg("Revista as casas (E). Ache água, comida e armas.", (200, 220, 240))
        self.msg("No seu bolso: um bilhete com a posição de um bunker militar (M).", (200, 240, 200))
        self.salvar()

    def salvar(self):
        if self.mundo is None or getattr(self, "p", None) is None:
            return
        if self.recorde.get("moedas") != self.moedas:  # moedas valem para todos os mundos
            self.recorde["moedas"] = self.moedas
            self.gravar_recorde()
        m = self.mundo
        extras = [dict(x=mv["x"], y=mv["y"], tipo=mv["tipo"], itens=mv["itens"], aberto=mv["aberto"])
                  for mv in m.moveis[self.n_moveis_base:] if mv["tipo"] == "mochila" and not mv["aberto"]]
        dados = dict(
            versao=1, seed=m.seed, x=self.p.x, y=self.p.y, vida=self.p.vida, fome=self.p.fome, sede=self.p.sede,
            inv=self.inv, armas=self.armas, pente=self.pente, silen=self.silen, arma=self.arma, hora=self.hora,
            dia=self.dia, mortes=self.mortes, vezes_morto=self.vezes_morto, revelados=self.revelados,
            respawn=self.respawn, abertos=[mv["id"] for mv in m.moveis[:self.n_moveis_base] if mv["aberto"]],
            pegos=[it["id"] for it in m.itens_chao[:self.n_itens_base] if it.get("pego")],
            cortadas=self.cortadas, construidos=self.construidos, mochilas=extras,
            explorado=self.explorado.hex(), lanterna=self.lanterna, nivel_mochila=self.nivel_mochila,
            feridas=[self.p.sangrando, self.p.perna, self.p.braco],
            niveis=self.niveis, miras=self.miras, reforco_mochila=self.reforco_mochila,
            moedas=self.moedas, dono=self.dono, mochila_infinita=self.mochila_infinita,
            nome=self.__dict__.get("nome_mundo", "Meu mundo"),
        )
        try:
            arq = self.caminho_save()
            os.makedirs(os.path.dirname(arq), exist_ok=True)
            tmp = arq + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f)
            os.replace(tmp, arq)
        except Exception as e:
            self.msg(f"Não consegui salvar: {e}", (255, 120, 100))

    def carregar(self, arq=None):
        if arq:
            self.arq = arq
        try:
            with open(self.caminho_save(), encoding="utf-8") as f:
                d = json.load(f)
            self.nome_mundo = d.get("nome", "Meu mundo")
        except Exception:
            self.msg("Save estragado, começando de novo.")
            self.novo_jogo()
            return
        self.preparar(d["seed"])
        m = self.mundo
        self.p = Jogador(d["x"], d["y"])
        self.p.vida, self.p.fome, self.p.sede = d["vida"], d["fome"], d["sede"]
        if m.bloqueado(self.p.x, self.p.y, self.p.r):  # o mundo mudou e voce ficou preso: procura um lugar livre
            for raio in range(16, 800, 16):
                livre = None
                for k in range(24):
                    ax = self.p.x + math.cos(k / 24 * 6.283) * raio
                    ay = self.p.y + math.sin(k / 24 * 6.283) * raio
                    if not m.bloqueado(ax, ay, self.p.r):
                        livre = (ax, ay)
                        break
                if livre:
                    self.p.x, self.p.y = livre
                    break
        self.inv = d["inv"]
        self.nivel_mochila = d.get("nivel_mochila", 0)
        self.niveis = d.get("niveis", {})
        self.miras = d.get("miras", [])
        self.reforco_mochila = d.get("reforco_mochila", 0)
        self.moedas = self.recorde.get("moedas", d.get("moedas", 0))
        self.dono = d.get("dono", False) or self.recorde.get("dono", False)
        self.mochila_infinita = d.get("mochila_infinita", False)
        self.p.sangrando, self.p.perna, self.p.braco = d.get("feridas", [False, False, False])
        self.armas = d["armas"]
        self.pente = d["pente"]
        self.silen = d["silen"]
        self.arma = d["arma"]
        self.hora = d["hora"]
        self.dia = d["dia"]
        self.mortes = d["mortes"]
        self.vezes_morto = d.get("vezes_morto", 0)
        self.revelados = d["revelados"]
        self.respawn = d["respawn"]
        self.lanterna = d.get("lanterna", True)
        for i in d["abertos"]:
            if i < len(m.moveis):
                m.moveis[i]["aberto"] = True
        for i in d["pegos"]:
            if i < len(m.itens_chao):
                m.itens_chao[i]["pego"] = True
        for idx in d["cortadas"]:
            self.cortar_arvore(idx, carregando=True)
        for c in d["construidos"]:
            self.construir(c, carregando=True)
        for mc in d["mochilas"]:
            mc["id"] = len(m.moveis)
            m.add_movel(mc)
        exp = bytes.fromhex(d["explorado"])
        for i, v in enumerate(exp):
            if v:
                self.explorado[i] = 1
                self.fog.fill((0, 0, 0, 0), ((i % NE) * EXPLO, (i // NE) * EXPLO, EXPLO, EXPLO))
        self.cam = [self.p.x, self.p.y]
        self.estado = "jogo"
        self.msg(f"Bem-vindo de volta. Dia {self.dia}.", (240, 220, 200))

    # ================================================================ utilidades
    def msg(self, txt, cor=(235, 230, 220)):
        self.msgs.append([txt, 5.0, cor])
        if len(self.msgs) > 7:
            self.msgs.pop(0)

    def som(self, nome, vol=1.0):
        s = self.sons.get(nome)
        if s:
            ch = s.play()
            if ch:
                ch.set_volume(clamp(vol, 0, 1))

    def escuridao(self):
        h = self.hora
        if 7 <= h < 18:
            return 0.0
        if 18 <= h < 21:
            return (h - 18) / 3
        if 5 <= h < 7:
            return (7 - h) / 2
        return 1.0

    def rot(self, chave, base, graus, passo=6):
        q = int(round(graus / passo)) % int(360 / passo)
        k = (chave, q)
        s = self.rot_cache.get(k)
        if s is None:
            if len(self.rot_cache) > 4000:
                self.rot_cache.clear()
            s = pygame.transform.rotate(base, -q * passo)
            self.rot_cache[k] = s
        return s

    def arma_atual(self):
        return self.arma_melhorada(self.arma)

    def arma_melhorada(self, ida):
        """A arma com as melhorias da bancada e a mira."""
        n = self.niveis.get(ida, 0)
        mira = ida in self.miras
        k = (ida, n, mira)
        cache = self.__dict__.setdefault("cache_arma", {})
        if k not in cache:
            a = dict(ARMAS[ARMA_IDX[ida]])
            a["dano"] = a["dano"] * (1 + 0.25 * n)
            a["cd"] = a["cd"] * (1 - 0.08 * n)
            if not a["melee"]:
                a["pente"] = a["pente"] + n if ida == "besta" else int(round(a["pente"] * (1 + 0.3 * n)))
                a["disp"] = a["disp"] * (1 - 0.15 * n) * (0.45 if mira else 1.0)
                a["alcance"] = a["alcance"] * (1 + 0.1 * n) * (1.25 if mira else 1.0)
            else:
                a["alcance"] = a["alcance"] + 4 * n
            cache[k] = a
        return cache[k]

    def custo_melhoria(self, n):
        c = {"sucata": 4 * (n + 1)}
        if n >= 1:
            c["ferramentas"] = 1
        if n >= 2:
            c["tabua"] = 6
        return c

    def custo_mochila(self, n):
        return {"tabua": 6 * (n + 1), "sucata": 4 * (n + 1), "ferramentas": 1}

    def pagar(self, custo):
        if not all(self.inv.get(k, 0) >= q for k, q in custo.items()):
            falta = ", ".join(f"{q - self.inv.get(k, 0)} {ITENS[k].lower()}" for k, q in custo.items()
                              if self.inv.get(k, 0) < q)
            self.msg("Falta: " + falta, (255, 170, 140))
            return False
        for k, q in custo.items():
            self.inv[k] -= q
        return True

    def dar(self, item, q, avisar=True):
        if item in ARMAS_IDS:
            a = ARMAS[ARMA_IDX[item]]
            if item in self.armas:
                if not a["melee"]:
                    self.inv[a["mun"]] = self.inv.get(a["mun"], 0) + max(3, a["pente"] // 2)
                    if avisar:
                        self.msg(f"Outra {a['nome']}: tirou a munição dela (+{max(3, a['pente'] // 2)})", (230, 220, 160))
                return
            self.armas.append(item)
            self.armas.sort(key=lambda i: ARMA_IDX[i])
            if not a["melee"]:
                self.pente[item] = self.rnd.randint(1, a["pente"])
            if avisar:
                self.msg(f"Achou uma arma: {a['nome']}!  (tecla {(self.armas.index(item) + 1) % 10})", (255, 220, 120))
            if self.arma == "faca":
                self.arma = item
                self.recarga_t = 0
            if self.inv.get("mira_guardada") and not a["melee"] and item not in self.miras:
                self.inv["mira_guardada"] -= 1
                self.miras.append(item)
                self.msg(f"Mira colocada na {a['nome']}.", (180, 230, 255))
            if "silenciador_guardado" in self.inv and a.get("silencia") and item not in self.silen:
                self.inv.pop("silenciador_guardado")
                self.silen.append(item)
                self.msg(f"Silenciador colocado na {a['nome']}.", (180, 230, 255))
            return
        if item == "mira":
            ordem = ["rifle", "fuzil", "besta", "smg", "espingarda", "pistola"]
            for a in sorted(ARMAS, key=lambda a: ordem.index(a["id"]) if a["id"] in ordem else 99):
                if a["id"] in self.armas and not a["melee"] and a["id"] not in self.miras:
                    self.miras.append(a["id"])
                    if avisar:
                        self.msg(f"Achou uma MIRA! Colocou na {a['nome']}: tiro bem mais certeiro.", (180, 230, 255))
                    return 0
            self.inv["mira_guardada"] = self.inv.get("mira_guardada", 0) + q
            if avisar:
                self.msg("Mira guardada: vai na próxima arma de fogo que você achar.", (180, 230, 255))
            return 0
        if item == "silenciador":
            for a in sorted(ARMAS, key=lambda a: -ARMA_IDX[a["id"]]):
                if a["id"] in self.armas and a.get("silencia") and a["id"] not in self.silen:
                    self.silen.append(a["id"])
                    if avisar:
                        self.msg(f"Silenciador! Colocou na {a['nome']}. Tiro bem baixinho.", (180, 230, 255))
                    return
            self.inv["silenciador_guardado"] = self.inv.get("silenciador_guardado", 0) + q
            if avisar:
                self.msg("Silenciador guardado: vai na próxima arma que você achar.", (180, 230, 255))
            return
        if item.startswith("mochila") and item[7:].isdigit():
            n = int(item[7:])
            if n > self.nivel_mochila:
                self.nivel_mochila = n
                self.msg(f"Nova mochila: {MOCHILAS[n][0]}! Agora cabe {MOCHILAS[n][1]} de espaço.", (255, 220, 120))
            elif avisar:
                self.msg(f"Achou uma {MOCHILAS[n][0]}, mas a sua já é igual ou melhor.", (190, 185, 175))
            return 0
        sobra = 0
        if item in ESPACO:
            livre = self.capacidade() - self.espaco_usado()
            cabe = max(0, int(livre / ESPACO[item] + 1e-6))
            if cabe < q:
                sobra = q - cabe
                q = cabe
                if time.time() - self.t_cheia > 3:
                    self.t_cheia = time.time()
                    self.msg("Mochila cheia! Ache uma mochila maior ou gaste umas coisas.", (255, 170, 120))
            if q <= 0:
                return sobra
        self.inv[item] = self.inv.get(item, 0) + q
        if avisar:
            extra = ""
            if item == "peca":
                extra = f"  ({self.inv['peca']}/{PECAS_RADIO})"
            self.msg(f"+{q} {ITENS.get(item, item)}{extra}", (255, 230, 120) if item == "peca" else (220, 235, 210))
        return sobra

    # ================================================================ mochila (tela de clicar)
    def abrir_mochila(self):
        self.modo_construir = None
        self.estado = "mochila"
        self.som("clique", 0.4)

    def mouse_no_hud(self, pos):
        for r, _ in getattr(self, "rects_rapidos", ()):
            if r.collidepoint(pos):
                return True
        rb = getattr(self, "rect_botao_mochila", None)
        if rb and rb.collidepoint(pos):
            return True
        for nome in ("rect_botao_loja", "rect_botao_dono", "rect_console", "rect_codigo"):
            rr = getattr(self, nome, None)
            if rr and rr.collidepoint(pos):
                return True
        rc = getattr(self, "rect_painel_construir", None)
        return bool(rc and self.modo_construir is not None and rc.collidepoint(pos))

    def cliques_hud(self):
        pos = pygame.mouse.get_pos() if self.fake is None else self.fake["mouse"]
        rb = getattr(self, "rect_botao_mochila", None)
        if rb and rb.collidepoint(pos):
            self.abrir_mochila()
            return True
        rl = getattr(self, "rect_botao_loja", None)
        if rl and rl.collidepoint(pos):
            self.estado = "loja"
            return True
        rd = getattr(self, "rect_botao_dono", None)
        if rd and rd.collidepoint(pos):
            self.tudo_do_melhor()
            return True
        rc = getattr(self, "rect_console", None)
        if rc and rc.collidepoint(pos):
            self.console_ativo = True
            self.console_modo = "comando"
            return True
        rk = getattr(self, "rect_codigo", None)
        if rk and rk.collidepoint(pos):
            self.console_ativo = True
            self.console_modo = "codigo"
            self.console_txt = ""
            return True
        for r, it in getattr(self, "rects_rapidos", ()):
            if r.collidepoint(pos):
                if it in ("comida", "agua", "bandagem", "kit"):
                    self.usar(it)
                elif it in ("tabua", "sucata", "ferramentas"):
                    self.modo_construir = 0
                    self.msg("Escolha o que construir no painel e clique no chão para colocar.", (200, 230, 255))
                else:
                    self.abrir_mochila()
                return True
        rc = getattr(self, "rect_painel_construir", None)
        if rc and self.modo_construir is not None and rc.collidepoint(pos):
            i = (pos[1] - rc.y - 40) // 32
            if 0 <= i < len(RECEITAS):
                self.modo_construir = i
            return True
        return False

    def machucar(self):
        p = self.p
        r = random.random()
        if r < 0.2 and not p.sangrando:
            p.sangrando = True
            self.msg("Você foi mordido e está SANGRANDO! Use uma bandagem (H).", (255, 110, 100))
        elif r < 0.26:
            if random.random() < 0.5 and not p.perna:
                p.perna = True
                self.msg("Sua PERNA quebrou! Você anda devagar. Use um kit médico (J).", (255, 180, 100))
            elif not p.braco:
                p.braco = True
                self.msg("Seu BRAÇO quebrou! A mira piora. Use um kit médico (J).", (255, 180, 100))

    def botao_peq(self, texto, rect, cor=(60, 30, 28), ativo=True):
        mx, my = pygame.mouse.get_pos()
        hover = rect.collidepoint(mx, my) and ativo
        c = (150, 40, 34) if hover else cor
        if not ativo:
            c = (44, 44, 46)
        pygame.draw.rect(self.tela, c, rect, border_radius=7)
        pygame.draw.rect(self.tela, (200, 80, 60) if hover else (100, 70, 60), rect, 1, border_radius=7)
        img = self.f_peq.render(texto, True, (240, 230, 220) if ativo else (120, 120, 120))
        self.tela.blit(img, img.get_rect(center=rect.center))
        return hover and self.click

    def largar(self, item):
        q = self.inv.get(item, 0)
        if q <= 0:
            return
        m = self.mundo
        p = self.p
        self.inv[item] = 0
        x = p.x - math.cos(p.ang) * 30
        y = p.y - math.sin(p.ang) * 30
        m.add_movel(dict(id=len(m.moveis), x=x, y=y, tipo="mochila", aberto=False, itens=[[item, q]]))
        self.msg(f"Largou {q} {ITENS[item].lower()} no chão (E para pegar de volta).", (200, 200, 190))

    def desenhar_corpo(self, cx, cy):
        p = self.p
        tela = self.tela
        pisca = 0.5 + 0.5 * math.sin(time.time() * 6)
        ok = (110, 180, 110)
        ruim = (230, 70, 60)
        quebrado = (240, 170, 60)
        tronco = G.mistura(ok, ruim, pisca) if p.sangrando else ok
        braco = quebrado if p.braco else ok
        perna = quebrado if p.perna else ok
        cabeca = ok if p.vida > 30 else G.mistura(ok, ruim, pisca)
        pygame.draw.circle(tela, cabeca, (cx, cy - 92), 22)
        pygame.draw.rect(tela, tronco, (cx - 30, cy - 66, 60, 84), border_radius=10)
        pygame.draw.rect(tela, braco, (cx - 52, cy - 62, 18, 74), border_radius=8)
        pygame.draw.rect(tela, braco, (cx + 34, cy - 62, 18, 74), border_radius=8)
        pygame.draw.rect(tela, perna, (cx - 28, cy + 22, 24, 86), border_radius=8)
        pygame.draw.rect(tela, perna, (cx + 4, cy + 22, 24, 86), border_radius=8)
        if p.sangrando:
            for k in range(3):
                pygame.draw.circle(tela, (150, 10, 12), (cx - 10 + k * 10, cy - 20 + k * 9), 4)

    def tela_mochila(self, dt):
        tc = self.teclas
        if pygame.K_ESCAPE in tc or pygame.K_v in tc or pygame.K_i in tc:
            self.estado = "jogo"
            return
        self.desenhar()
        tela = self.tela
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 175))
        tela.blit(sh, (0, 0))
        p = self.p
        # ---- corpo
        esq = pygame.Rect(30, 30, 380, 660)
        self.painel(esq, 225)
        self.texto("SEU CORPO", (esq.centerx, 58), self.f_grande, centro=True)
        self.desenhar_corpo(esq.centerx, 230)
        y = 360
        for nome, v, cor in (("Vida", p.vida, (220, 60, 60)), ("Fome", p.fome, (230, 160, 60)),
                             ("Sede", p.sede, (80, 150, 230))):
            self.texto(nome, (50, y), self.f_med2)
            pygame.draw.rect(tela, (30, 30, 34), (130, y + 8, 200, 12), border_radius=6)
            pygame.draw.rect(tela, cor, (130, y + 8, int(200 * max(0, v) / 100), 12), border_radius=6)
            self.texto(f"{v:.0f}", (342, y), self.f_med2)
            y += 34
        y += 8
        self.texto("O QUE ELE PRECISA:", (50, y), self.f_med, (255, 220, 140))
        y += 30
        precisa = []
        if p.sangrando:
            precisa.append(("Está sangrando: use Bandagem ou Kit médico.", (255, 130, 120)))
        if p.perna:
            precisa.append(("Perna quebrada (anda devagar): Kit médico.", (255, 190, 120)))
        if p.braco:
            precisa.append(("Braço quebrado (mira ruim): Kit médico.", (255, 190, 120)))
        if p.vida < 60:
            precisa.append(("Pouca vida: Kit médico, bandagem ou hospital.", (255, 160, 140)))
        if p.fome < 50:
            precisa.append(("Com fome: coma uma Comida enlatada.", (255, 210, 150)))
        if p.sede < 50:
            precisa.append(("Com sede: beba uma Garrafa de água.", (170, 210, 255)))
        if not precisa:
            precisa.append(("Está tudo bem. Nenhum machucado!", (160, 230, 160)))
        for txt, cor in precisa:
            self.texto(txt, (50, y), self.f_peq, cor)
            y += 24
        # ---- mochila
        dir_ = pygame.Rect(430, 30, 820, 660)
        self.painel(dir_, 225)
        cap = self.capacidade()
        uso = self.espaco_usado()
        self.texto(MOCHILAS[self.nivel_mochila][0].upper(), (450, 42), self.f_grande)
        pygame.draw.rect(tela, (30, 30, 34), (450, 92, 400, 12), border_radius=6)
        pygame.draw.rect(tela, (200, 180, 120), (450, 92, int(400 * min(1, uso / cap)), 12), border_radius=6)
        self.texto(f"Espaço: {uso:.0f} de {cap}", (866, 84), self.f_med2)
        if self.nivel_mochila < len(MOCHILAS) - 1:
            self.texto(f"Ache uma {MOCHILAS[self.nivel_mochila + 1][0]} para carregar mais.", (450, 112), self.f_peq,
                       (180, 175, 165))
        # itens
        acoes = {"comida": "Comer", "agua": "Beber", "bandagem": "Curar", "kit": "Curar", "seringa": "Injetar",
                 "saco": "Dormir"}
        lista = [k for k in ITENS if k in ESPACO or k == "peca"]
        lista = [k for k in lista if self.inv.get(k, 0) > 0]
        x0, y0 = 450, 146
        if not lista:
            self.texto("Sua mochila está vazia.", (x0, y0), self.f_med2, (170, 165, 160))
        compacto = len(lista) > 8  # muita coisa: 3 colunas menores para caber tudo
        cols = 3 if compacto else 2
        cw, ch = (256, 44) if compacto else (384, 62)
        for i, it in enumerate(lista[:18]):
            r = pygame.Rect(x0 + (i % cols) * (cw + 8), y0 + (i // cols) * (ch + 7), cw, ch)
            pygame.draw.rect(tela, (34, 36, 40), r, border_radius=8)
            if compacto:
                G.desenha_icone(tela, it, r.x + 18, r.centery, 1.0)
                self.texto(ITENS[it][:18], (r.x + 36, r.y + 3), self.f_peq)
                self.texto(f"x{self.inv[it]}", (r.x + 36, r.y + 22), self.f_peq, (200, 195, 180))
                bx = r.right - 54
                if it in acoes and self.botao_peq(acoes[it][:6], pygame.Rect(bx - 60, r.y + 8, 56, 28)):
                    self.usar(it)
                if it != "peca" and self.botao_peq("Largar", pygame.Rect(bx, r.y + 8, 50, 28), (44, 40, 38)):
                    self.largar(it)
                continue
            G.desenha_icone(tela, it, r.x + 28, r.centery, 1.4)
            self.texto(ITENS[it], (r.x + 52, r.y + 8), self.f_med2)
            self.texto(f"x{self.inv[it]}", (r.x + 52, r.y + 32), self.f_peq, (200, 195, 180))
            bx = r.right - 92
            if it in acoes:
                if self.botao_peq(acoes[it], pygame.Rect(bx - 84, r.y + 14, 80, 34)):
                    self.usar(it)
            if it != "peca" and self.botao_peq("Largar", pygame.Rect(bx, r.y + 14, 84, 34), (44, 40, 38)):
                self.largar(it)
        # armas
        ya = 486
        self.texto("ARMAS (clique para usar)", (450, ya), self.f_med, (255, 220, 140))
        minhas = [ARMAS[ARMA_IDX[k]] for k in self.armas]
        lw = min(88, 792 // max(1, len(minhas)))
        for i, a in enumerate(minhas):
            r = pygame.Rect(450 + i * lw, ya + 30, lw - 4, 70)
            tem = a["id"] in self.armas
            pygame.draw.rect(tela, (34, 36, 40), r, border_radius=8)
            if a["id"] == self.arma:
                pygame.draw.rect(tela, (230, 190, 90), r, 2, border_radius=8)
            if tem:
                G.desenha_icone(tela, a["id"], r.centerx, r.y + 22, 1.1 if lw >= 80 else 0.8)
                if lw >= 80:
                    self.texto(a["nome"].split(" ")[0][:11], (r.centerx, r.y + 44), self.f_peq, centro=True)
                else:  # muita arma: mostra so o numero da tecla
                    self.texto(str((i + 1) % 10) if i < 10 else "", (r.centerx, r.y + 44), self.f_peq, centro=True)
                if not a["melee"] and lw >= 80:
                    extra = f"{self.pente.get(a['id'], 0)}+{self.inv.get(a['mun'], 0)}"
                    if a["id"] in self.silen:
                        extra += " S"
                    if a["id"] in self.miras:
                        extra += " M"
                    self.texto(extra, (r.centerx, r.y + 60), self.f_peq, (200, 195, 180), centro=True)
                if self.niveis.get(a["id"]):
                    self.texto(f"+{self.niveis[a['id']]}", (r.right - 22, r.y + 2), self.f_peq, (255, 210, 90), sombra=False)
                if self.click and r.collidepoint(pygame.mouse.get_pos()):
                    self.trocar_arma(a["id"])
            else:
                self.texto("?", (r.centerx, r.centery), self.f_med, (90, 90, 90), centro=True)
        # construir
        yc = 598
        self.texto("CONSTRUIR", (450, yc - 4), self.f_med, (255, 220, 140))
        curto = {"tabua": "tábuas", "sucata": "sucata", "ferramentas": "ferram."}
        for i, rec in enumerate(RECEITAS):
            pode = all(self.inv.get(k, 0) >= q for k, q in rec["custo"].items())
            partes = [f"{q} {curto.get(k, k)}" for k, q in rec["custo"].items()]
            r = pygame.Rect(450 + i * 133, yc + 22, 128, 36)
            linhas = [", ".join(partes)] if len(partes) < 3 else [", ".join(partes[:2]), partes[2]]
            for k, txt in enumerate(linhas):
                self.texto(txt, (r.centerx, r.bottom + 11 + k * 16), self.f_peq,
                           (200, 195, 180) if pode else (150, 140, 140), centro=True, sombra=False)
            if self.botao_peq(rec["nome"], r, (40, 60, 40), pode):
                self.estado = "jogo"
                self.modo_construir = i
                self.msg("Clique no chão para colocar. B ou ESC cancela.", (200, 230, 255))
                return
        if self.botao_peq("Fechar (V)", pygame.Rect(1130, 40, 104, 36)):
            self.estado = "jogo"

    def estacao(self):
        return ((self.dia - 1) // DIAS_ESTACAO) % len(ESTACOES)

    def tingir(self, s, copa=False):
        """Pinta o chao (ou as copas) com a cor da estacao. So mexe nas cores, nunca na transparencia."""
        if s is None:
            return s
        _, mult, soma, _, _ = ESTACOES[self.estacao()]
        if mult == (1, 1, 1) and not any(soma):
            return s
        arr = pygame.surfarray.pixels3d(s)
        arr[:] = np.clip(arr * np.array(mult, np.float32) + np.array(soma, np.float32), 0, 255).astype(np.uint8)
        del arr
        return s

    # ================================================================ loja e modo dono
    def ativar_dono(self):
        self.dono = True
        self.digitado = ""
        self.recorde["dono"] = True
        self.gravar_recorde()
        self.msg("Bem-vindo, DONO! Lá em cima apareceu o lugar de escrever, e do lado do mapa o botão DONO.",
                 (255, 160, 230))
        self.salvar()

    def comando_dono(self, txt):
        """Comandos que so o dono pode escrever."""
        partes = txt.strip().lower().split()
        if not partes or not self.dono:
            return
        cmd, arg = partes[0], (partes[1] if len(partes) > 1 else "")
        num = int(arg) if arg.isdigit() else None
        p = self.p
        if cmd == "ajuda":
            for linha in ("tudo  ·  moedas 1000  ·  curar  ·  noite  ·  dia  ·  dia 10 (vai para o dia 10)",
                          "gigante  ·  zumbis 5  ·  bunker 2 (te leva no bunker 2)  ·  limpar (some com os zumbis)"):
                self.msg(linha, (255, 200, 240))
        elif cmd == "tudo":
            self.tudo_do_melhor()
        elif cmd == "moedas":
            self.moedas += num or 1000
            self.msg(f"Agora você tem {self.moedas} moedas.", (255, 220, 110))
        elif cmd == "curar":
            p.vida, p.fome, p.sede, p.folego = 100, 100, 100, 100
            p.curar_tudo()
            self.msg("Curado: vida, fome e sede cheias.", (160, 255, 160))
        elif cmd == "noite":
            self.hora = 22.0
        elif cmd == "dia" and num:
            self.dia = num
            self.msg(f"Agora é o dia {num}.", (255, 220, 160))
        elif cmd == "dia":
            self.hora = 9.0
        elif cmd in ("gigante", "zumbis"):
            tipo = "gigante" if cmd == "gigante" else None
            for k in range(1 if tipo else min(num or 5, 30)):
                a = random.uniform(0, 6.283)
                x, y = p.x + math.cos(a) * 420, p.y + math.sin(a) * 420
                t = tipo or random.choice(["normal", "normal", "gordo", "corredor"])
                self.zumbis.append(Zumbi(x, y, t, random.randrange(len(self.spr_z[t])), random))
            self.msg("Lá vem eles!", (255, 150, 130))
        elif cmd == "limpar":
            self.zumbis = []
            self.msg("Sumiu todo mundo.", (200, 230, 255))
        elif cmd == "bunker" and num and 1 <= num <= len(self.mundo.bunkers):
            b = self.mundo.bunkers[num - 1]
            px, py = b["portas"][-1]
            lado = 1 if py == b["y"] + b["h"] - 1 else (-1 if py == b["y"] else 0)
            p.x, p.y = px * T + 16, (py + lado * 2) * T + 16
            if not lado:
                p.x += 64 if px == b["x"] + b["w"] - 1 else -64
            if num - 1 not in self.revelados:
                self.revelados.append(num - 1)
            self.cam = [p.x, p.y]
            self.msg(f"Você foi para o bunker {num}.", (200, 255, 200))
        else:
            self.msg(f"Não conheço o comando \"{txt}\". Escreva: ajuda", (255, 170, 150))

    def tudo_do_melhor(self):
        """Botao do dono: mochila infinita e tudo do melhor."""
        self.dono = True
        self.mochila_infinita = True
        self.nivel_mochila = len(MOCHILAS) - 1
        self.reforco_mochila = NIVEL_MAX
        for a in ARMAS:
            if a["id"] not in self.armas:
                self.armas.append(a["id"])
            self.niveis[a["id"]] = NIVEL_MAX
            if not a["melee"]:
                self.pente[a["id"]] = self.arma_melhorada(a["id"])["pente"]
                if a["id"] not in self.miras:
                    self.miras.append(a["id"])
                if a.get("silencia") and a["id"] not in self.silen:
                    self.silen.append(a["id"])
        self.armas.sort(key=lambda i: ARMA_IDX[i])
        self.cache_arma = {}
        for k, q in (("9mm", 999), ("12", 999), ("556", 999), ("308", 999), ("flecha", 999), ("foguete", 999),
                     ("comida", 99), ("agua", 99), ("kit", 50), ("bandagem", 50), ("seringa", 20), ("saco", 1),
                     ("tabua", 300), ("sucata", 300), ("ferramentas", 30)):
            self.inv[k] = max(self.inv.get(k, 0), q)
        self.moedas = max(self.moedas, 999999)
        self.p.vida = 100
        self.p.curar_tudo()
        self.msg("MODO DONO: mochila infinita e tudo do melhor!", (255, 160, 230))
        self.som("golpe", 0.8)
        self.salvar()

    def tela_loja(self, dt):
        tc = self.teclas
        if pygame.K_ESCAPE in tc or pygame.K_k in tc:
            self.estado = "jogo"
            return
        # codigo secreto do dono
        if not self.dono and self.digitado.upper().endswith(CODIGO_DONO):
            self.dono = True
            self.digitado = ""
            self.recorde["dono"] = True
            self.gravar_recorde()
            self.msg("Bem-vindo, DONO do jogo! Clique no botão DONO para ter tudo.", (255, 160, 230))
            self.salvar()
        self.desenhar()
        tela = self.tela
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 185))
        tela.blit(sh, (0, 0))
        caixa = pygame.Rect(120, 22, 1040, 676)
        self.painel(caixa, 232)
        self.texto("LOJA", (caixa.x + 24, caixa.y + 10), self.f_grande, (255, 220, 110))
        pygame.draw.circle(tela, (120, 90, 20), (caixa.x + 150, caixa.y + 34), 13)
        pygame.draw.circle(tela, (240, 200, 70), (caixa.x + 150, caixa.y + 34), 11)
        self.texto("modo DONO: tudo de graça" if self.dono else f"{self.moedas} moedas", (caixa.x + 172, caixa.y + 20),
                   self.f_med, (255, 220, 110))
        self.texto(f"Moedas: ganhe {MOEDAS_ZERAR} cada vez que ZERAR o jogo (chamar o resgate na torre), ou compre.",
                   (caixa.x + 26, caixa.y + 62), self.f_peq, (200, 195, 180))
        rp = pygame.Rect(caixa.right - 420, caixa.y + 16, 286, 36)
        self.botao_peq("Comprar moedas com Pix: em breve", rp, (40, 40, 44), False)
        if self.botao_peq("Fechar (K)", pygame.Rect(caixa.right - 120, caixa.y + 16, 104, 36)):
            self.estado = "jogo"
            return
        self.texto("ARMAS LENDÁRIAS (só aqui na loja)", (caixa.x + 26, caixa.y + 92), self.f_med, (255, 200, 120))
        y = caixa.y + 122
        for a in [a for a in ARMAS if a.get("loja")]:
            r = pygame.Rect(caixa.x + 20, y, caixa.w - 40, 56)
            pygame.draw.rect(tela, (40, 34, 26), r, border_radius=8)
            G.desenha_icone(tela, a["id"], r.x + 40, r.centery, 1.5)
            self.texto(a["nome"], (r.x + 84, r.y + 5), self.f_med, (255, 230, 170))
            self.texto(a.get("desc", ""), (r.x + 84, r.y + 31), self.f_peq, (210, 200, 185))
            tem = a["id"] in self.armas
            if tem:
                self.texto("JÁ É SUA", (r.right - 130, r.y + 16), self.f_med2, (160, 230, 160))
            else:
                preco = 0 if self.dono else a["loja"]
                self.texto("grátis" if self.dono else f"{a['loja']} moedas", (r.right - 300, r.y + 17), self.f_med2,
                           (255, 220, 110))
                pode = self.moedas >= preco
                if self.botao_peq("Comprar", pygame.Rect(r.right - 140, r.y + 10, 124, 36), (70, 54, 20), pode):
                    if pode:
                        self.moedas -= preco
                        self.dar(a["id"], 1, avisar=False)
                        if not a["melee"]:
                            self.inv[a["mun"]] = self.inv.get(a["mun"], 0) + a["pente"] * 2
                        self.msg(f"Você comprou: {a['nome']}!", (255, 220, 120))
                        self.som("golpe", 0.6)
                        self.salvar()
            y += 62
        self.texto("MUNIÇÃO E CURA", (caixa.x + 26, y + 4), self.f_med, (255, 200, 120))
        y += 34
        for i, (nome, itens, preco) in enumerate(LOJA_PACOTES):
            r = pygame.Rect(caixa.x + 20 + (i % 3) * 336, y + (i // 3) * 52, 328, 46)
            pygame.draw.rect(tela, (34, 36, 40), r, border_radius=8)
            G.desenha_icone(tela, next(iter(itens)), r.x + 26, r.centery, 1.1)
            self.texto(nome, (r.x + 50, r.y + 4), self.f_peq, (235, 230, 220))
            p0 = 0 if self.dono else preco
            self.texto("grátis" if self.dono else f"{preco} moedas", (r.x + 50, r.y + 24), self.f_peq, (255, 220, 110))
            pode = self.moedas >= p0
            if self.botao_peq("Comprar", pygame.Rect(r.right - 104, r.y + 7, 94, 32), (70, 54, 20), pode):
                if pode:
                    self.moedas -= p0
                    for k, q in itens.items():
                        self.inv[k] = self.inv.get(k, 0) + q
                    self.msg(f"Comprou: {nome}", (255, 220, 120))
                    self.salvar()
        self.texto("A MIRA (luneta) não se compra: você acha no mapa, nas casas e nos bunkers.",
                   (caixa.x + 26, caixa.bottom - 30), self.f_peq, (170, 200, 230))

    # ================================================================ bancada
    def tela_bancada(self, dt):
        tc = self.teclas
        if pygame.K_ESCAPE in tc or pygame.K_e in tc or pygame.K_v in tc:
            self.estado = "jogo"
            return
        self.desenhar()
        tela = self.tela
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 180))
        tela.blit(sh, (0, 0))
        caixa = pygame.Rect(140, 24, 1000, 672)
        self.painel(caixa, 230)
        self.texto("BANCADA", (caixa.x + 24, caixa.y + 12), self.f_grande, (255, 220, 140))
        self.texto("Cada melhoria: mais dano, mais rápida; nas armas de fogo, pente maior e tiro mais certeiro.",
                   (caixa.x + 26, caixa.y + 62), self.f_peq, (200, 195, 180))
        mat = "   ".join(f"{ITENS[k]}: {self.inv.get(k, 0)}" for k in ("sucata", "ferramentas", "tabua"))
        self.texto("Você tem  ·  " + mat, (caixa.x + 26, caixa.y + 84), self.f_peq, (180, 230, 180))
        if self.botao_peq("Fechar (E)", pygame.Rect(caixa.right - 120, caixa.y + 16, 104, 36)):
            self.estado = "jogo"
            return
        y = caixa.y + 116
        passo = min(54, 440 // max(1, len(self.armas)))
        for ida in self.armas:
            a = ARMAS[ARMA_IDX[ida]]
            n = self.niveis.get(ida, 0)
            r = pygame.Rect(caixa.x + 20, y, caixa.w - 40, passo - 6)
            pygame.draw.rect(tela, (34, 36, 40), r, border_radius=8)
            G.desenha_icone(tela, ida, r.x + 34, r.centery, 1.3)
            self.texto(a["nome"], (r.x + 70, r.y + 4), self.f_med2)
            extras = [t for t, tem in (("silenciador", ida in self.silen), ("mira", ida in self.miras)) if tem]
            self.texto(f"nível {n} de {NIVEL_MAX}" + ("   ·   " + " + ".join(extras) if extras else ""),
                       (r.x + 70, r.y + 26), self.f_peq, (255, 210, 90))
            atual = self.arma_melhorada(ida)
            info = f"dano {atual['dano']:.0f}"
            if not a["melee"]:
                info += f"  ·  pente {atual['pente']}"
            self.texto(info, (r.x + 330, r.y + 14), self.f_peq, (210, 205, 195))
            if n < NIVEL_MAX:
                custo = self.custo_melhoria(n)
                txt = ", ".join(f"{q} {ITENS[k].split(' ')[0].lower()}" for k, q in custo.items())
                pode = all(self.inv.get(k, 0) >= q for k, q in custo.items())
                self.texto(txt, (r.x + 540, r.y + 14), self.f_peq, (200, 195, 180) if pode else (150, 140, 140))
                if self.botao_peq(f"Melhorar (+{n + 1})", pygame.Rect(r.right - 150, r.y + 7, 140, 34), (40, 60, 40), pode):
                    if self.pagar(custo):
                        self.niveis[ida] = n + 1
                        self.som("golpe", 0.6)
                        self.msg(f"{a['nome']} melhorada: agora é +{n + 1}!", (255, 220, 120))
                        self.salvar()
            else:
                self.texto("NO MÁXIMO", (r.right - 130, r.y + 14), self.f_med2, (255, 210, 90))
            y += passo
        # mochila
        y += 6
        r = pygame.Rect(caixa.x + 20, y, caixa.w - 40, 52)
        pygame.draw.rect(tela, (34, 40, 36), r, border_radius=8)
        G.desenha_icone(tela, f"mochila{self.nivel_mochila}" if self.nivel_mochila else "mochila", r.x + 34, r.centery, 1.3)
        n = self.reforco_mochila
        self.texto(f"Reforçar a mochila  (+{MOCHILA_EXTRA} de espaço)", (r.x + 70, r.y + 4), self.f_med2)
        self.texto(f"nível {n} de {NIVEL_MAX}   ·   cabe {self.capacidade()}", (r.x + 70, r.y + 28), self.f_peq,
                   (255, 210, 90))
        if n < NIVEL_MAX:
            custo = self.custo_mochila(n)
            txt = ", ".join(f"{q} {ITENS[k].split(' ')[0].lower()}" for k, q in custo.items())
            pode = all(self.inv.get(k, 0) >= q for k, q in custo.items())
            self.texto(txt, (r.x + 540, r.y + 16), self.f_peq, (200, 195, 180) if pode else (150, 140, 140))
            if self.botao_peq(f"Reforçar (+{n + 1})", pygame.Rect(r.right - 150, r.y + 9, 140, 34), (40, 60, 40), pode):
                if self.pagar(custo):
                    self.reforco_mochila = n + 1
                    self.som("golpe", 0.6)
                    self.msg(f"Mochila reforçada! Agora cabe {self.capacidade()}.", (255, 220, 120))
                    self.salvar()
        else:
            self.texto("NO MÁXIMO", (r.right - 130, r.y + 16), self.f_med2, (255, 210, 90))
        self.texto("Dica: a MIRA (luneta) você acha no mapa, nas casas e nas caixas militares. Ela encaixa sozinha na arma.",
                   (caixa.x + 26, caixa.bottom - 34), self.f_peq, (170, 200, 230))

    def capacidade(self):
        if self.mochila_infinita:
            return 999999
        return MOCHILAS[self.nivel_mochila][1] + MOCHILA_EXTRA * self.reforco_mochila

    def espaco_usado(self):
        return sum(ESPACO.get(k, 0) * v for k, v in self.inv.items())

    # ================================================================ mundo / cache
    def chunk_chao(self, cx, cy):
        k = (cx, cy)
        s = self.cache_chao.get(k)
        if s is None:
            s = G.vivo(self.tingir(self.mundo.assar_chao(cx, cy)), 1.25, 1.06)
            self.cache_chao[k] = s
            if len(self.cache_chao) > 48:
                self.cache_chao.popitem(last=False)
        else:
            self.cache_chao.move_to_end(k)
        return s

    def chunk_copa(self, cx, cy):
        k = (cx, cy)
        if k in self.cache_copa:
            self.cache_copa.move_to_end(k)
            return self.cache_copa[k]
        s = G.vivo(self.tingir(self.mundo.assar_copa(cx, cy), copa=True), 1.3, 1.05)
        if s is not None:
            # transparencia so por pixel (mais rapido) e compactada (RLE): quase tudo e vazio
            s.fill((255, 255, 255, 238), special_flags=pygame.BLEND_RGBA_MULT)
            s.set_alpha(255, pygame.RLEACCEL)
        self.cache_copa[k] = s
        if len(self.cache_copa) > 48:
            self.cache_copa.popitem(last=False)
        return s

    def invalidar(self, x, y):
        cx = int(x // CHPX)
        cy = int(y // CHPX)
        for yy in (cy - 1, cy, cy + 1):
            for xx in (cx - 1, cx, cx + 1):
                self.cache_chao.pop((xx, yy), None)
                self.cache_copa.pop((xx, yy), None)

    def cortar_arvore(self, idx, carregando=False):
        m = self.mundo
        a = m.arvores.pop(idx, None)
        if a is None:
            return
        lst = m.col.get(idx, [])
        m.col[idx] = [c for c in lst if not (abs(c[0] - a[0]) < 0.01 and abs(c[1] - a[1]) < 0.01)]
        if not carregando:
            self.cortadas.append(idx)
            self.invalidar(a[0], a[1])
            for _ in range(14):
                self.particula(a[0], a[1], random.uniform(-80, 80), random.uniform(-80, 80), 0.8, (110, 80, 50), 3)

    def construir(self, c, carregando=False):
        m = self.mundo
        tipo = c["tipo"]
        x, y = c["x"], c["y"]
        if tipo == "barricada":
            a = math.radians(c.get("ang", 0))
            for k in (-26, -9, 9, 26):
                m.add_colisor(x + math.cos(a) * k, y + math.sin(a) * k, 10)
        elif tipo == "fogueira":
            m.add_colisor(x, y, 13)
        elif tipo == "bancada":
            m.add_colisor(x, y, 16)
        elif tipo == "abrigo":
            m.add_colisor(x, y, 12)
        elif tipo == "ponte":
            if "tiles" not in c:
                tx0, ty0 = int(x // T), int(y // T)
                c["tiles"] = [[tx, ty] for ty in range(ty0 - 1, ty0 + 2) for tx in range(tx0 - 1, tx0 + 2)
                              if m.tile(tx, ty) == AGUA]
            for tx, ty in c["tiles"]:
                if 0 <= tx < N and 0 <= ty < N:
                    m.t[ty * N + tx] = PONTE
                    m.tn[ty, tx] = PONTE
            self.cache_chao.clear()
        if not carregando:
            self.construidos.append(c)
        elif c not in self.construidos:
            self.construidos.append(c)

    def pontos_colisor(self, c):
        x, y = c["x"], c["y"]
        if c["tipo"] == "barricada":
            a = math.radians(c.get("ang", 0))
            return [(x + math.cos(a) * k, y + math.sin(a) * k) for k in (-26, -9, 9, 26)]
        if c["tipo"] in ("fogueira", "abrigo", "bancada"):
            return [(x, y)]
        return []

    def desmontar(self, c):
        m = self.mundo
        for px, py in self.pontos_colisor(c):
            i = int(py // T) * N + int(px // T)
            lst = m.col.get(i, [])
            m.col[i] = [q for q in lst if abs(q[0] - px) > 0.01 or abs(q[1] - py) > 0.01]
        if c in self.construidos:
            self.construidos.remove(c)
        rec = next((r for r in RECEITAS if r["id"] == c["tipo"]), None)
        if rec:
            sobrou = []
            for k, q in rec["custo"].items():
                r = self.dar(k, q, avisar=False)
                if r:
                    sobrou.append([k, r])
            if sobrou:
                m.add_movel(dict(id=len(m.moveis), x=c["x"], y=c["y"], tipo="mochila", aberto=False, itens=sobrou))
                self.msg(f"Desmontou: {rec['nome']}. O que não coube ficou no chão (E para pegar).", (200, 230, 200))
            else:
                self.msg(f"Desmontou: {rec['nome']}. Os materiais voltaram para a mochila.", (200, 230, 200))
        self.som("golpe", 0.6)
        self.salvar()

    def zonas_seguras(self):
        for c in self.construidos:
            if c["tipo"] == "abrigo":
                yield c["x"], c["y"], RAIO_ABRIGO
        for b in self.mundo.bunkers:
            yield (b["x"] + b["w"] / 2) * T, (b["y"] + b["h"] / 2) * T, max(b["w"], b["h"]) * T * 0.75

    def em_zona_segura(self, x, y):
        for zx, zy, r in self.zonas_seguras():
            if (x - zx) ** 2 + (y - zy) ** 2 < r * r:
                return (zx, zy, r)
        return None

    # ================================================================ atualizar
    def entrada(self):
        if self.fake is not None:
            f = self.fake
            return f["mv"], f["corre"], f["mira"], f["tiro"], f["mouse"]
        if self.console_ativo:
            return (0, 0), False, False, False, pygame.mouse.get_pos()
        k = pygame.key.get_pressed()
        mx = (k[pygame.K_d] or k[pygame.K_RIGHT]) - (k[pygame.K_a] or k[pygame.K_LEFT])
        my = (k[pygame.K_s] or k[pygame.K_DOWN]) - (k[pygame.K_w] or k[pygame.K_UP])
        b = pygame.mouse.get_pressed()
        pos = pygame.mouse.get_pos()
        tiro = b[0] and not self.mouse_no_hud(pos)
        return (mx, my), (k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]), b[2], tiro, pos

    def tela_jogo(self, dt):
        self.teclas_jogo()
        if self.estado != "jogo":
            self.desenhar()
            return
        self.atualizar(dt)
        self.desenhar()

    def teclas_jogo(self):
        tc = self.teclas
        if self.console_ativo:
            if pygame.K_ESCAPE in tc:
                self.console_ativo = False
            elif pygame.K_RETURN in tc:
                if self.console_modo == "codigo":
                    if self.console_txt.strip().upper() == CODIGO_DONO:
                        self.ativar_dono()
                    else:
                        self.msg("Código errado.", (255, 150, 130))
                else:
                    self.comando_dono(self.console_txt)
                self.console_txt = ""
                self.console_ativo = False
            elif pygame.K_BACKSPACE in tc:
                self.console_txt = self.console_txt[:-1]
            elif self.letras:
                self.console_txt = (self.console_txt + self.letras)[:40]
            return
        if not self.dono and self.digitado.upper().endswith(CODIGO_DONO):
            self.ativar_dono()
        if pygame.K_c in tc:
            self.agachado = not self.agachado
            self.msg("Agachado: anda devagar, sem barulho, e os zumbis te veem menos." if self.agachado else "Levantou.",
                     (170, 220, 255))
        if pygame.K_ESCAPE in tc or pygame.K_p in tc:
            if self.modo_construir:
                self.modo_construir = None
            else:
                self.estado = "pausa"
            return
        if pygame.K_m in tc or pygame.K_TAB in tc:
            self.estado = "mapa"
            self.mapa_grande = None
            return
        if pygame.K_v in tc or pygame.K_i in tc:
            self.abrir_mochila()
            return
        if self.click and self.cliques_hud():
            self.click = False
            return
        if pygame.K_k in tc:
            self.estado = "loja"
            self.som("clique", 0.4)
            return
        for i, key in enumerate((pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6,
                                 pygame.K_7, pygame.K_8, pygame.K_9, pygame.K_0)):
            if key in tc:
                if self.modo_construir is not None:
                    if i < len(RECEITAS):
                        self.modo_construir = i
                elif i < len(self.armas):
                    self.trocar_arma(self.armas[i])
                else:
                    self.msg(f"Você tem {len(self.armas)} armas. Tecla {(i + 1) % 10} está vazia.", (200, 190, 180))
        if self.roda and self.modo_construir is None:
            i = self.armas.index(self.arma)
            self.trocar_arma(self.armas[(i - self.roda) % len(self.armas)])
        if pygame.K_r in tc:
            self.recarregar()
        if pygame.K_e in tc:
            self.interagir()
        if pygame.K_f in tc:
            self.usar("comida")
        if pygame.K_g in tc:
            self.usar("agua")
        if pygame.K_h in tc:
            self.usar("bandagem")
        if pygame.K_j in tc:
            self.usar("kit")
        if pygame.K_l in tc:
            self.lanterna = not self.lanterna
            self.som("clique", 0.5)
        if pygame.K_b in tc:
            self.modo_construir = None if self.modo_construir is not None else 0
            if self.modo_construir is not None:
                self.msg("Construir: 1 barricada · 2 fogueira · 3 bunker · 4 arame · 5 ponte. Clique para colocar.",
                         (200, 230, 255))

    def trocar_arma(self, ida):
        if ida != self.arma:
            self.arma = ida
            self.recarga_t = 0
            self.cd = 0.25
            self.som("clique", 0.4)

    def recarregar(self):
        a = self.arma_atual()
        if a["melee"] or self.recarga_t > 0:
            return
        if self.pente.get(self.arma, 0) >= a["pente"]:
            return
        if self.inv.get(a["mun"], 0) <= 0:
            self.msg(f"Sem {ITENS[a['mun']]}.", (230, 170, 150))
            return
        self.recarga_t = a["recarga"]
        self.som("recarga", 0.6)

    def usar(self, item):
        p = self.p
        if self.inv.get(item, 0) <= 0:
            self.msg(f"Você não tem {ITENS[item].lower()}.", (220, 170, 150))
            return
        if item == "comida":
            if p.fome > 95:
                self.msg("Você está sem fome.")
                return
            p.fome = min(100, p.fome + 32)
            self.som("comer", 0.7)
        elif item == "agua":
            if p.sede > 95:
                self.msg("Você está sem sede.")
                return
            p.sede = min(100, p.sede + 38)
            self.som("comer", 0.5)
        elif item == "bandagem":
            if p.vida >= 100 and not p.sangrando:
                self.msg("Sua vida está cheia.")
                return
            if p.sangrando:
                p.sangrando = False
                self.msg("O sangramento parou.", (170, 240, 170))
            p.vida = min(100, p.vida + 22)
        elif item == "seringa":
            p.curar_tudo()
            p.vida = 100
            p.folego = 100
            self.adrenalina = 60.0
            self.msg("ADRENALINA! Vida cheia, machucados curados e você corre mais por 1 minuto.", (255, 120, 140))
        elif item == "saco":
            if self.zumbi_perto(500):
                self.msg("Não dá para dormir com zumbi atrás de você!", (255, 150, 120))
                return
            if self.mundo.tile_px(p.x, p.y) in (AGUA, PONTE):
                self.msg("Não dá para dormir em cima da água.", (255, 150, 120))
                return
            self.msg("Você abriu o saco de dormir e deitou...", (180, 220, 255))
            self.dormir(None)
            return
        elif item == "kit":
            if p.vida >= 100 and not (p.sangrando or p.perna or p.braco):
                self.msg("Sua vida está cheia.")
                return
            if p.perna or p.braco:
                self.msg("Você imobilizou o osso quebrado com o kit médico.", (170, 240, 170))
            p.curar_tudo()
            p.vida = min(100, p.vida + 65)
        self.inv[item] -= 1
        self.msg(f"Usou: {ITENS[item]}", (200, 230, 200))

    # ---------------------------------------------------------------- interacao
    def alvo_interacao(self):
        p = self.p
        m = self.mundo
        melhor = None
        md = 999
        for mv in m.perto(m.moveis_ch, p.x, p.y):
            if mv["aberto"]:
                continue
            d = math.hypot(mv["x"] - p.x, mv["y"] - p.y)
            lim = 58 if mv["tipo"] == "porta_malas" else 46
            if d < lim and d < md:
                md = d
                melhor = ("movel", mv)
        for c in m.perto(m.camas_ch, p.x, p.y):
            d = math.hypot(c["x"] - p.x, c["y"] - p.y)
            if d < 44 and d < md:
                md = d
                melhor = ("cama", c)
        for c in self.construidos:
            if c["tipo"] == "abrigo":
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d < 60 and d < md:
                    md = d
                    melhor = ("abrigo", c)
            elif c["tipo"] == "bancada":
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d < 60 and d < md:
                    md = d
                    melhor = ("bancada", c)
            elif c["tipo"] in ("barricada", "fogueira", "arame"):
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d < 56 and d < md:
                    md = d
                    melhor = ("desmontar", c)
        for c in getattr(m, "bancadas", ()):  # bancadas prontas dentro dos bunkers
            d = math.hypot(c["x"] - p.x, c["y"] - p.y)
            if d < 60 and d < md:
                md = d
                melhor = ("bancada", c)
        tor = m.torre
        if tor:
            cx = (tor["x"] + tor["w"] / 2) * T
            cy = (tor["y"] + tor["h"] / 2) * T
            if math.hypot(cx - p.x, cy - p.y) < 110:
                return ("torre", tor)
        if melhor:
            return melhor
        if self.arma == "machado":
            tx = int(p.x // T)
            ty = int(p.y // T)
            for yy in (ty - 1, ty, ty + 1):
                for xx in (tx - 1, tx, tx + 1):
                    a = m.arvores.get(yy * N + xx)
                    if a and math.hypot(a[0] - p.x, a[1] - p.y) < 44:
                        return ("arvore", yy * N + xx)
        tx = int(p.x // T)
        ty = int(p.y // T)
        for yy in (ty - 1, ty, ty + 1):
            for xx in (tx - 1, tx, tx + 1):
                if m.tile(xx, yy) == AGUA:
                    return ("agua", None)
        return None

    def texto_interacao(self, alvo):
        tipo, obj = alvo
        if tipo == "movel":
            return f"[E] Revistar {NOMES_MOVEIS.get(obj['tipo'], 'móvel')}"
        if tipo == "cama":
            return "[E] Descansar e se curar" if obj.get("hospital") else "[E] Dormir no bunker (salva o jogo)"
        if tipo == "abrigo":
            return "[E] Dormir no seu bunker (salva o jogo)"
        if tipo == "bancada":
            return "[E] Usar a bancada (melhorar armas e mochila)"
        if tipo == "desmontar":
            nome = {"barricada": "a barricada", "fogueira": "a fogueira", "arame": "o arame farpado"}[obj["tipo"]]
            return f"[E] Desmontar {nome} (devolve o material)"
        if tipo == "arvore":
            return "[E] Cortar árvore (tábuas)"
        if tipo == "agua":
            return "[E] Beber água do lago"
        if tipo == "torre":
            if self.resgate:
                return "Aguente firme! O helicóptero está vindo."
            return f"[E] Usar o rádio da torre ({self.inv.get('peca', 0)}/{PECAS_RADIO} peças)"
        return ""

    def zumbi_perto(self, raio=380):
        p = self.p
        return any(z.estado == "perseguir" and math.hypot(z.x - p.x, z.y - p.y) < raio for z in self.zumbis)

    def interagir(self):
        if self.acao:
            return
        alvo = self.alvo_interacao()
        if not alvo:
            return
        tipo, obj = alvo
        if tipo == "movel":
            dur = 2.0 if obj["tipo"] == "militar" else 1.3
            self.acao = dict(tipo="movel", obj=obj, t=0.0, total=dur, txt="Revistando...")
        elif tipo == "desmontar":
            self.acao = dict(tipo="desmontar", obj=obj, t=0.0, total=1.2, txt="Desmontando...")
        elif tipo == "bancada":
            self.estado = "bancada"
            self.som("clique", 0.4)
        elif tipo == "cama":
            if self.zumbi_perto():
                self.msg("Não dá para descansar com zumbi atrás de você!", (255, 150, 120))
                return
            if obj.get("hospital"):
                self.acao = dict(tipo="hospital", obj=obj, t=0.0, total=4.0, txt="Cuidando dos ferimentos...")
            else:
                self.acao = dict(tipo="dormir", obj=obj, t=0.0, total=2.0, txt="Deitando...")
        elif tipo == "abrigo":
            if self.zumbi_perto():
                self.msg("Não dá para dormir com zumbi atrás de você!", (255, 150, 120))
                return
            self.acao = dict(tipo="dormir", obj=obj, t=0.0, total=2.0, txt="Entrando no bunker...")
        elif tipo == "arvore":
            self.acao = dict(tipo="arvore", obj=obj, t=0.0, total=3.0, txt="Cortando a árvore...")
        elif tipo == "agua":
            if self.p.sede >= 99:
                self.msg("Você está sem sede.")
                return
            self.acao = dict(tipo="agua", obj=None, t=0.0, total=1.5, txt="Bebendo água...")
        elif tipo == "torre":
            if self.resgate:
                return
            if self.inv.get("peca", 0) >= PECAS_RADIO:
                self.acao = dict(tipo="torre", obj=obj, t=0.0, total=3.0, txt="Consertando o rádio...")
            else:
                self.msg(f"O rádio está quebrado. Faltam {PECAS_RADIO - self.inv.get('peca', 0)} peças.", (255, 210, 150))

    def terminar_acao(self):
        a = self.acao
        self.acao = None
        p = self.p
        tipo = a["tipo"]
        if tipo == "movel":
            mv = a["obj"]
            mv["aberto"] = True
            if not mv["itens"]:
                self.msg(f"Nada na {NOMES_MOVEIS.get(mv['tipo'], 'móvel')}." if mv["tipo"] in ("geladeira", "caixa", "cômoda")
                         else "Não tinha nada aqui.", (180, 175, 170))
            ficou = []
            for item, q in mv["itens"]:
                r = self.dar(item, q)
                if r:
                    ficou.append([item, r])
            if mv["itens"]:
                self.som("pegar", 0.6)
            mv["itens"] = ficou
            if ficou:
                mv["aberto"] = False
            if "revela" in mv:
                i = mv["revela"]
                if i < len(self.mundo.bunkers):
                    if i not in self.revelados:
                        self.revelados.append(i)
                    self.msg("Achou um bilhete: marca outro bunker militar no mapa (M)!", (200, 255, 200))
                else:
                    self.msg("Bilhete: \"Com todas as peças, vá até a TORRE DE RÁDIO (marcada no mapa).\"", (200, 255, 200))
        elif tipo == "desmontar":
            self.desmontar(a["obj"])
        elif tipo == "hospital":
            p.vida = 100
            p.curar_tudo()
            self.passar_horas(2)
            self.msg("Você se tratou no hospital. Vida cheia!", (160, 255, 160))
        elif tipo == "dormir":
            self.dormir(a["obj"])
        elif tipo == "arvore":
            self.cortar_arvore(a["obj"])
            self.dar("tabua", 3)
            self.som("golpe", 0.7)
            self.fazer_barulho(p.x, p.y, 260)
        elif tipo == "agua":
            p.sede = 100
            self.msg("Você bebeu água do lago.", (160, 210, 255))
            self.som("comer", 0.5)
        elif tipo == "torre":
            self.inv["peca"] -= PECAS_RADIO
            self.resgate = TEMPO_RESGATE
            self.msg("RÁDIO: \"Recebido! Helicóptero a caminho. Aguente firme!\"", (255, 230, 120))
            self.msg("O barulho atraiu uma horda inteira...", (255, 140, 120))
            self.fazer_barulho(p.x, p.y, 3000)

    def passar_horas(self, h):
        self.p.fome = max(3, self.p.fome - h * 2.4)
        self.p.sede = max(3, self.p.sede - h * 3.6)
        self.hora += h
        while self.hora >= 24:
            self.hora -= 24
            self.dia += 1

    def dormir(self, obj):
        h = (24 - self.hora + 7) if self.hora >= 7 else (7 - self.hora)
        if h < 1:
            h = 1
        self.passar_horas(h)
        self.p.vida = min(100, self.p.vida + 50)
        self.respawn = [self.p.x, self.p.y]
        self.zumbis = [z for z in self.zumbis if math.hypot(z.x - self.p.x, z.y - self.p.y) > 900]
        self.msg(f"Você dormiu em segurança. Dia {self.dia}, {int(self.hora):02d}:00. Jogo salvo.", (180, 220, 255))
        self.msg("Você vai acordar aqui se morrer.", (180, 200, 220))
        self.salvar()

    # ---------------------------------------------------------------- combate
    def fazer_barulho(self, x, y, raio):
        if self.chuva:
            raio *= 0.8
        for z in self.zumbis:
            if z.estado != "perseguir" and (z.x - x) ** 2 + (z.y - y) ** 2 < raio * raio:
                z.estado = "investigar"
                z.alvo = (x + random.uniform(-60, 60), y + random.uniform(-60, 60))

    def particula(self, x, y, vx, vy, vida, cor, tam, tipo="p"):
        if len(self.particulas) < 500:
            self.particulas.append([x, y, vx, vy, vida, vida, cor, tam, tipo])

    def decalque(self, surf, x, y):
        self.decalques.append((surf, x, y))
        if len(self.decalques) > 320:
            self.decalques.pop(0)

    def explodir(self, x, y, dano):
        """Explosao do foguete da RPG: machuca todo zumbi perto (e voce, se estiver perto demais)."""
        p = self.p
        for z in list(self.zumbis):
            d = math.hypot(z.x - x, z.y - y)
            if d < 150:
                self.ferir_zumbi(z, dano * (1 - d / 190), math.atan2(z.y - y, z.x - x))
        dp = math.hypot(p.x - x, p.y - y)
        if dp < 90:
            p.vida -= 30 * (1 - dp / 90)
            self.dano_t = 0.45
        for _ in range(40):
            a = random.uniform(0, 6.283)
            v = random.uniform(60, 320)
            cor = random.choice([(255, 200, 60), (255, 120, 30), (240, 60, 20), (90, 80, 70)])
            self.particula(x, y, math.cos(a) * v, math.sin(a) * v, random.uniform(0.3, 0.8), cor, random.randint(3, 7), "f")
        self.decalque(random.choice(self.spr_sangue), x - 20, y - 20)
        self.flash_t = 0.12
        self.flash_pos = (x, y)
        self.tremor = max(self.tremor, 16)
        self.fazer_barulho(x, y, 2000)
        self.som("espingarda", 1.0)

    def ferir_zumbi(self, z, dano, ang):
        z.hp -= dano
        if len(self.numeros) < 40:
            self.numeros.append([z.x + random.uniform(-8, 8), z.y - 18, str(int(round(dano))), 0.7, dano >= 60])
        z.flash = 0.08
        z.estado = "perseguir"
        z.alvo = (self.p.x, self.p.y)
        nx = z.x + math.cos(ang) * 6
        ny = z.y + math.sin(ang) * 6
        if not self.mundo.bloqueado(nx, ny, z.r):
            z.x, z.y = nx, ny
        for _ in range(5):
            a = ang + random.uniform(-0.6, 0.6)
            v = random.uniform(60, 220)
            self.particula(z.x, z.y, math.cos(a) * v, math.sin(a) * v, random.uniform(0.25, 0.5), (140, 10, 12), 3)
        if random.random() < 0.35:
            s = random.choice(self.spr_sangue)
            self.decalque(s, z.x + math.cos(ang) * 14 - s.get_width() / 2, z.y + math.sin(ang) * 14 - s.get_height() / 2)
        if z.hp <= 0:
            self.matar(z, ang)

    def matar(self, z, ang):
        if z not in self.zumbis:
            return
        self.zumbis.remove(z)
        self.mortes += 1
        if z.tipo == "gigante":
            self.msg("Você derrubou um GIGANTE! Ele deixou coisas boas no chão.", (255, 220, 120))
            for item, q in (("kit", 2), ("556", 40), ("seringa" if random.random() < 0.3 else "comida", 1)):
                self.drop_id += 1
                self.mundo.add_item_chao(dict(id=self.drop_id, x=z.x + random.uniform(-30, 30),
                                              y=z.y + random.uniform(-30, 30), item=item, q=q))
        base = self.spr_morto[z.tipo][z.var]
        corpo = pygame.transform.rotate(base, -math.degrees(ang) + random.uniform(-30, 30))
        s = random.choice(self.spr_sangue)
        self.decalque(s, z.x - s.get_width() / 2, z.y - s.get_height() / 2)
        self.decalque(corpo, z.x - corpo.get_width() / 2, z.y - corpo.get_height() / 2)
        if random.random() < 0.12:
            item, q = sortear(random, LOOT_ZUMBI, 1)[0]
            self.drop_id += 1
            self.mundo.add_item_chao(dict(id=self.drop_id, x=z.x, y=z.y, item=item, q=q))

    def atirar(self, mira, movendo):
        a = self.arma_atual()
        p = self.p
        if a["melee"]:
            self.cd = a["cd"]
            self.som("faca", 0.6)
            acertos = 0
            for z in sorted(self.zumbis, key=lambda z: (z.x - p.x) ** 2 + (z.y - p.y) ** 2):
                d = math.hypot(z.x - p.x, z.y - p.y)
                if d > a["alcance"] + z.r:
                    break
                ang = math.atan2(z.y - p.y, z.x - p.x)
                dif = abs((ang - p.ang + math.pi) % (2 * math.pi) - math.pi)
                if dif < 0.95:
                    self.ferir_zumbi(z, a["dano"] * random.uniform(0.85, 1.15), ang)
                    self.som("golpe", 0.6)
                    acertos += 1
                    if acertos >= (2 if a["id"] == "machado" else 1):
                        break
            if a["ruido"]:
                self.fazer_barulho(p.x, p.y, a["ruido"])
            return
        if self.recarga_t > 0:
            return
        if self.pente.get(self.arma, 0) <= 0:
            if self.inv.get(a["mun"], 0) > 0:
                self.recarregar()
            else:
                self.som("clique", 0.5)
                self.msg(f"Sem munição! Procure {ITENS[a['mun']]}.", (230, 170, 150))
                self.cd = 0.4
            return
        self.pente[self.arma] -= 1
        self.cd = a["cd"]
        sil = self.arma in self.silen
        disp = a["disp"] * (0.35 if mira else 1.0) * (1.7 if movendo and not mira else 1.0) * (2.0 if p.braco else 1.0)
        ox = p.x + math.cos(p.ang) * 22
        oy = p.y + math.sin(p.ang) * 22
        for _ in range(a["balas"]):
            ang = p.ang + random.gauss(0, disp)
            fim = self.mundo.bala_para(ox, oy, ang, a["alcance"])
            dx = math.cos(ang)
            dy = math.sin(ang)
            alvos = []
            for z in self.zumbis:
                rx = z.x - ox
                ry = z.y - oy
                tt = rx * dx + ry * dy
                if 0 < tt < fim:
                    perp = abs(rx * dy - ry * dx)
                    if perp < z.r + 3:
                        alvos.append((tt, z))
            alvos.sort(key=lambda q: q[0])
            fim_vis = fim
            if a.get("explode"):
                t_imp = alvos[0][0] if alvos else fim
                ix, iy = ox + dx * t_imp, oy + dy * t_imp
                self.rastros.append([ox, oy, ix, iy, 0.12])
                self.explodir(ix, iy, a["dano"])
                continue
            for k, (tt, z) in enumerate(alvos[:a["fura"] + 1]):
                queda = 1.0 - 0.6 * (tt / a["alcance"]) if a["id"] == "espingarda" else 1.0
                self.ferir_zumbi(z, a["dano"] * queda * random.uniform(0.9, 1.1), ang)
                fim_vis = tt
            self.rastros.append([ox, oy, ox + dx * fim_vis, oy + dy * fim_vis, 0.06])
            if not alvos and fim < a["alcance"]:
                for _ in range(3):
                    self.particula(ox + dx * fim, oy + dy * fim, random.uniform(-60, 60), random.uniform(-60, 60), 0.25,
                                   (230, 220, 160), 2)
        # capsula
        pa = p.ang + math.pi / 2
        self.particula(p.x + math.cos(p.ang) * 10, p.y + math.sin(p.ang) * 10, math.cos(pa) * 90 + random.uniform(-20, 20),
                       math.sin(pa) * 90 + random.uniform(-20, 20), 0.6, (220, 180, 70), 2, "c")
        if sil:
            self.som("silencioso", 0.8)
            self.fazer_barulho(p.x, p.y, a["ruido"] * 0.22)
            self.flash_t = 0.02
        else:
            self.som(a["id"], 0.9)
            self.fazer_barulho(p.x, p.y, a["ruido"])
            self.tremor = max(self.tremor, TREMOR.get(a["id"], 2) * (0.5 if a["id"] in self.silen else 1.0))
            self.flash_t = 0.05
        self.flash_pos = (ox, oy)

    # ---------------------------------------------------------------- update
    def atualizar(self, dt):
        p = self.p
        m = self.mundo
        mv, corre, mira, tiro, mouse = self.entrada()
        if self.acao and self.acao["tipo"] in ("hospital", "dormir"):
            mv = (0, 0)
        mx, my = mv
        movendo = mx != 0 or my != 0
        # mira
        wx = mouse[0] + self.cam[0] - W / 2
        wy = mouse[1] + self.cam[1] - H / 2
        p.ang = math.atan2(wy - p.y, wx - p.x)
        # esquiva rapida (ESPACO)
        self.t_esquiva -= dt
        if pygame.K_SPACE in self.teclas and self.t_esquiva <= 0 and p.folego >= 20 and self.esquiva <= 0:
            if movendo:
                n = math.hypot(mx, my)
                self.dir_esquiva = (mx / n, my / n)
            else:
                self.dir_esquiva = (math.cos(p.ang), math.sin(p.ang))
            self.esquiva = 0.2
            self.t_esquiva = 0.9
            p.folego -= 20
            self.som("clique", 0.4)
        if self.esquiva > 0:
            self.esquiva -= dt
            ex, ey = self.dir_esquiva
            p.x, p.y = self.mover(p.x, p.y, ex * 560 * dt, ey * 560 * dt, p.r)
            if random.random() < 0.7:
                self.particula(p.x, p.y + 6, random.uniform(-30, 30), random.uniform(-30, 30), 0.4, (170, 150, 120), 3)
        # andar
        vel = 128.0
        correndo = False
        if mira:
            vel = 78
        elif corre and movendo and p.folego > 1:
            vel = 212
            correndo = True
        if self.adrenalina > 0:
            self.adrenalina -= dt
            vel *= 1.35
            p.folego = 100
        if self.agachado:
            vel = min(vel, 128) * 0.5
            correndo = False
        if p.perna:
            vel = min(vel, 128) * 0.62
            correndo = False
        if p.fome < 10 or p.sede < 10:
            vel *= 0.8
        if movendo:
            n = math.hypot(mx, my)
            dx = mx / n * vel * dt
            dy = my / n * vel * dt
            p.x, p.y = self.mover(p.x, p.y, dx, dy, p.r)
            if self.acao and self.acao["tipo"] not in ("hospital", "dormir"):
                self.acao = None
                self.msg("Cancelado (você se mexeu).", (180, 175, 170))
        if correndo:
            p.folego = max(0, p.folego - 17 * dt)
            if random.random() < 0.3:
                self.particula(p.x, p.y + 6, random.uniform(-20, 20), random.uniform(-20, 20), 0.5, (150, 130, 100), 3)
            self.fazer_barulho(p.x, p.y, 120)
        else:
            p.folego = min(100, p.folego + (14 if not movendo else 8) * dt)
        # fome e sede
        est = ESTACOES[self.estacao()]
        p.fome = max(0, p.fome - 100 / FOME_SEG * dt * est[3])
        p.sede = max(0, p.sede - 100 / SEDE_SEG * dt * (1.6 if correndo else 1.0) * est[4])
        if self.estacao() != self.estacao_atual:
            if self.estacao_atual is not None:
                dica = {"Verão": " Calor: você tem mais sede.", "Inverno": " Frio: você tem mais fome.",
                        "Outono": "", "Primavera": ""}[est[0]]
                self.msg(f"Chegou o {est[0].upper()}!{dica}", (255, 230, 160))
            self.estacao_atual = self.estacao()
            self.cache_chao.clear()
            self.cache_copa.clear()
        if p.sangrando:
            p.vida -= 0.45 * dt
            if random.random() < dt * 2:
                self.particula(p.x, p.y + 4, random.uniform(-15, 15), random.uniform(-15, 15), 0.6, (140, 10, 12), 3)
            if random.random() < dt / 15:
                self.msg("Você está sangrando! Use uma bandagem (H).", (255, 130, 120))
        if p.fome <= 0:
            p.vida -= 0.6 * dt
        if p.sede <= 0:
            p.vida -= 0.8 * dt
        if p.fome > 50 and p.sede > 50 and p.vida < 100:
            p.vida = min(100, p.vida + 0.1 * dt)
        if p.fome <= 0 and random.random() < dt / 12:
            self.msg("Você está morrendo de fome! Coma alguma coisa (F).", (255, 170, 120))
        if p.sede <= 0 and random.random() < dt / 12:
            self.msg("Você está morrendo de sede! Beba água (G ou num lago).", (150, 200, 255))
        # arma
        self.cd -= dt
        a = self.arma_atual()
        if self.recarga_t > 0:
            self.recarga_t -= dt
            if self.recarga_t <= 0:
                precisa = a["pente"] - self.pente.get(self.arma, 0)
                pega = min(precisa, self.inv.get(a["mun"], 0))
                self.pente[self.arma] = self.pente.get(self.arma, 0) + pega
                self.inv[a["mun"]] -= pega
        if self.modo_construir is not None:
            if self.click:
                self.colocar_construcao(wx, wy)
        elif tiro and self.cd <= 0 and not self.acao:
            pode = a["melee"] or a.get("auto") or self.click or self.fake is not None
            if pode:
                self.atirar(mira, movendo)
        # acao
        if self.acao:
            self.acao["t"] += dt
            if self.acao["t"] >= self.acao["total"]:
                self.terminar_acao()
        # pegar itens no chao
        for it in m.perto(m.itens_ch, p.x, p.y, 0):
            if not it.get("pego") and (it["x"] - p.x) ** 2 + (it["y"] - p.y) ** 2 < 24 * 24:
                r = self.dar(it["item"], it["q"])
                if r == it["q"]:
                    continue
                it["q"] = r
                if not r:
                    it["pego"] = True
                self.som("pegar", 0.5)
        # zumbis
        self.atualizar_zumbis(dt)
        self.tremor = max(0.0, self.tremor - 30 * dt)
        # numeros de dano subindo
        for nmr in self.numeros:
            nmr[1] -= 45 * dt
            nmr[3] -= dt
        self.numeros = [nmr for nmr in self.numeros if nmr[3] > 0]
        # efeitos
        for q in self.particulas:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[2] *= 0.9
            q[3] *= 0.9
            q[4] -= dt
        self.particulas = [q for q in self.particulas if q[4] > 0]
        for r in self.rastros:
            r[4] -= dt
        self.rastros = [r for r in self.rastros if r[4] > 0]
        self.flash_t -= dt
        self.dano_t = max(0, self.dano_t - dt)
        for msg in self.msgs:
            msg[1] -= dt
        self.msgs = [q for q in self.msgs if q[1] > 0]
        for c in self.construidos:
            if c["tipo"] == "fogueira" and random.random() < 0.5:
                self.particula(c["x"] + random.uniform(-6, 6), c["y"] + random.uniform(-6, 6), random.uniform(-10, 10),
                               random.uniform(-50, -20), random.uniform(0.3, 0.7), random.choice([(255, 180, 60), (255, 120, 40), (255, 220, 120)]), 3, "f")
        # tempo e clima
        self.hora += 24 / DIA_SEG * dt
        if self.hora >= 24:
            self.hora -= 24
            self.dia += 1
            self.msg(f"Dia {self.dia}. Os zumbis estão ficando mais numerosos...", (255, 200, 160))
            if self.dia > self.recorde.get("dias", 0):
                self.recorde["dias"] = self.dia
                self.gravar_recorde()
        self.t_clima -= dt
        if self.t_clima <= 0:
            self.chuva = (not self.chuva) and random.random() < 0.45
            self.t_clima = random.uniform(150, 420) if self.chuva else random.uniform(240, 600)
            if self.chuva:
                self.msg("Começou a chover. Os zumbis ouvem e enxergam menos.", (170, 200, 230))
        if self.chuva and self.canal_chuva is None and "chuva" in self.sons:
            self.canal_chuva = self.sons["chuva"].play(loops=-1)
            if self.canal_chuva:
                self.canal_chuva.set_volume(0.5)
        if not self.chuva and self.canal_chuva is not None:
            self.canal_chuva.stop()
            self.canal_chuva = None
        for g in self.gotas:
            g[1] += 900 * dt * g[2]
            g[0] -= 180 * dt * g[2]
            if g[1] > H:
                g[1] = random.uniform(-40, 0)
                g[0] = random.uniform(0, W + 200)
        # explorado
        self.t_explo -= dt
        if self.t_explo <= 0:
            self.t_explo = 0.4
            self.marcar_explorado()
        # resgate
        if self.resgate is not None:
            self.resgate -= dt
            if self.resgate <= 0 and self.heli is None:
                self.heli = [p.x - 1400, p.y - 500, 0.0]
                self.msg("O HELICÓPTERO CHEGOU! Fique parado onde está!", (255, 240, 150))
                self.som("helicoptero", 1.0)
        if self.heli is not None:
            hx, hy, ht = self.heli
            dx = p.x - hx
            dy = p.y - 60 - hy
            d = math.hypot(dx, dy)
            if d > 8:
                self.heli[0] += dx / d * min(d, 360 * dt)
                self.heli[1] += dy / d * min(d, 360 * dt)
            else:
                self.heli[2] += dt
                if self.heli[2] > 2.5:
                    self.vencer()
                    return
            if random.random() < dt * 2:
                self.som("helicoptero", 0.7)
        # salvar sozinho
        self.t_auto += dt
        if self.t_auto > 30:
            self.t_auto = 0
            self.salvar()
        # morte
        if p.vida <= 0:
            p.vida = 0
            self.estado = "morto"
            self.vezes_morto += 1
            self.morte_info = (self.dia, self.mortes)
        # camera
        alvo_x = p.x
        alvo_y = p.y
        k = (0.75 if self.arma in self.miras else 0.45) if mira else 0.12
        alvo_x += (mouse[0] - W / 2) * k
        alvo_y += (mouse[1] - H / 2) * k
        self.cam[0] += (alvo_x - self.cam[0]) * min(1, dt * 8)
        self.cam[1] += (alvo_y - self.cam[1]) * min(1, dt * 8)
        self.cam[0] = clamp(self.cam[0], W / 2, N * T - W / 2)
        self.cam[1] = clamp(self.cam[1], H / 2, N * T - H / 2)

    def mover(self, x, y, dx, dy, r):
        m = self.mundo
        if dx:
            if not m.bloqueado(x + dx, y, r):
                x += dx
            else:
                for s in (1, -1):
                    if not m.bloqueado(x + dx * 0.5, y + s * abs(dx), r):
                        x += dx * 0.5
                        y += s * abs(dx)
                        break
        if dy:
            if not m.bloqueado(x, y + dy, r):
                y += dy
            else:
                for s in (1, -1):
                    if not m.bloqueado(x + s * abs(dy), y + dy * 0.5, r):
                        x += s * abs(dy)
                        y += dy * 0.5
                        break
        return x, y

    def marcar_explorado(self):
        p = self.p
        cx = int(p.x // T) // EXPLO
        cy = int(p.y // T) // EXPLO
        raio = 6
        for yy in range(cy - raio, cy + raio + 1):
            for xx in range(cx - raio, cx + raio + 1):
                if 0 <= xx < NE and 0 <= yy < NE and (xx - cx) ** 2 + (yy - cy) ** 2 <= raio * raio:
                    i = yy * NE + xx
                    if not self.explorado[i]:
                        self.explorado[i] = 1
                        self.fog.fill((0, 0, 0, 0), (xx * EXPLO, yy * EXPLO, EXPLO, EXPLO))
        b = self.mundo.predio_em(p.x, p.y)
        if b and b["tipo"] == "militar" and b["indice"] not in self.revelados:
            self.revelados.append(b["indice"])
            self.msg("Você achou um BUNKER MILITAR! Revista as caixas verdes.", (200, 255, 200))

    def colocar_construcao(self, wx, wy):
        p = self.p
        rec = RECEITAS[self.modo_construir]
        d = math.hypot(wx - p.x, wy - p.y)
        if d > 110:
            ang = math.atan2(wy - p.y, wx - p.x)
            wx = p.x + math.cos(ang) * 110
            wy = p.y + math.sin(ang) * 110
        falta = [f"{q - self.inv.get(i, 0)} {ITENS[i].lower()}" for i, q in rec["custo"].items() if self.inv.get(i, 0) < q]
        if falta:
            self.msg("Falta: " + ", ".join(falta), (255, 170, 140))
            return
        if not self.lugar_ok(rec["id"], wx, wy):
            self.msg("Não dá para construir aí.", (255, 170, 140))
            return
        for i, q in rec["custo"].items():
            self.inv[i] -= q
        if rec["id"] == "ponte":
            wx = (int(wx // T)) * T + 16
            wy = (int(wy // T)) * T + 16
        c = dict(tipo=rec["id"], x=wx, y=wy, ang=math.degrees(p.ang) + 90)
        self.construir(c)
        self.som("golpe", 0.8)
        self.msg(f"Construiu: {rec['nome']}!", (200, 255, 200))
        if rec["id"] == "abrigo":
            self.msg("Zumbis não chegam perto do seu bunker. Durma nele com E.", (200, 230, 255))
        if rec["id"] == "arame":
            self.msg("Zumbi que passar no arame se machuca e fica lento.", (200, 230, 255))
        if rec["id"] == "bancada":
            self.msg("Bancada pronta! Chegue perto e aperte E para melhorar armas e a mochila.", (200, 230, 255))
        if rec["id"] == "ponte":
            self.msg("Ponte pronta! Construa mais pedaços para atravessar a água.", (200, 230, 255))
            return
        self.modo_construir = None
        self.salvar()

    def lugar_ok(self, tipo, x, y):
        m = self.mundo
        if tipo == "ponte":
            if m.tile_px(x, y) != AGUA:
                return False
            tx, ty = int(x // T), int(y // T)
            return any(m.tile(tx + dx, ty + dy) != AGUA for dy in range(-2, 3) for dx in range(-2, 3))
        r = {"barricada": 14, "fogueira": 14, "abrigo": 40, "arame": 10, "bancada": 20}[tipo]
        if m.bloqueado(x, y, r):
            return False
        if math.hypot(x - self.p.x, y - self.p.y) < (r + 14):
            return False
        if tipo == "abrigo" and m.predio_em(x, y):
            return False
        return m.tile_px(x, y) not in (AGUA, PAREDE, PAREDE_CONC)

    def atualizar_zumbis(self, dt):
        p = self.p
        m = self.mundo
        esc = self.escuridao()
        # quantos zumbis a regiao aguenta (regiao calma = nenhum)
        dl = self.dens_local()
        alvo = round((2 + min(self.dia * 0.4, 10) + 4 * esc) * dl)
        # cidades e vilas tem zumbi andando pelas ruas, de dia tambem (a regiao calma do comeco continua calma)
        cid = m.cidade_perto(p.x, p.y, 1.3)
        na_cidade = cid is not None and m.densidade(p.x, p.y) > 0
        if na_cidade:
            base = 7 if cid["tipo"] == "cidade" else 4
            alvo = max(alvo, round(base + min(self.dia * 0.4, 6) + 3 * esc))
        if self.resgate is not None:
            alvo = 75
        seguro = self.em_zona_segura(p.x, p.y)
        calma = dl < 0.05 and self.resgate is None
        if calma != self.na_calma:
            self.na_calma = calma
            if calma:
                self.msg("Região calma: por aqui não tem zumbi.", (170, 230, 170))
            else:
                self.msg("Saindo da região calma. Cuidado.", (240, 190, 140))
        self.t_spawn -= dt
        if self.t_spawn <= 0 and len(self.zumbis) < alvo:
            self.t_spawn = 0.12 if self.resgate is not None else (2.2 if na_cidade else 5.0)
            self.criar_zumbi(esc)
        visao = 190 * (1 - esc) + esc * (150 if self.lanterna else 95)
        if self.chuva:
            visao *= 0.8
        if m.no_capim(p.x, p.y):
            visao *= 0.35
        if self.agachado:
            visao *= 0.55
        zonas = list(self.zonas_seguras())
        self.arames = [c for c in self.construidos if c["tipo"] == "arame"]
        remover = []
        for z in self.zumbis:
            dx = p.x - z.x
            dy = p.y - z.y
            d = math.hypot(dx, dy)
            if d > 2000 or (d > 1700 and z.estado == "vagar" and self.resgate is None):
                remover.append(z)
                continue
            z.flash -= dt
            z.t_ataque -= dt
            z.t_pensar -= dt
            # zona segura: afasta
            fugir = None
            for zx, zy, zr in zonas:
                if (z.x - zx) ** 2 + (z.y - zy) ** 2 < zr * zr:
                    fugir = math.atan2(z.y - zy, z.x - zx)
                    break
            if fugir is not None:
                z.estado = "vagar"
                self.passo_zumbi(z, fugir, z.vel * 0.8 * dt)
                continue
            if z.t_pensar <= 0:
                z.t_pensar = 0.25
                if self.resgate is not None and d < 1600:
                    z.estado = "perseguir"
                    z.alvo = (p.x, p.y)
                elif self.zumbi_ve(z, d, visao, seguro):
                    z.viu += 0.25
                    if z.estado == "perseguir" or z.viu >= 1.0 or d < 75:
                        z.estado = "perseguir"
                        z.alvo = (p.x, p.y)
                    else:
                        # desconfiou: para e vira para olhar
                        z.parado = True
                        z.ang = math.atan2(p.y - z.y, p.x - z.x)
                        dif = (z.ang - z.ang_vis + math.pi) % (2 * math.pi) - math.pi
                        z.ang_vis += dif * 0.5
                elif z.estado == "perseguir":
                    z.viu = 0
                    z.estado = "investigar"
                elif z.estado == "vagar":
                    z.viu = max(0, z.viu - 0.25)
                    z.t_vagar -= 0.25
                    if z.t_vagar <= 0:
                        if na_cidade and d > 300 and random.random() < 0.45:
                            # na cidade eles andam pelas ruas, chegando aos poucos perto de voce
                            z.ang = math.atan2(p.y - z.y, p.x - z.x) + random.uniform(-0.8, 0.8)
                            z.parado = False
                        else:
                            z.ang = random.uniform(0, 6.283)
                            z.parado = random.random() < 0.4
                        z.t_vagar = random.uniform(2, 7)
            if z.estado == "perseguir":
                z.alvo = (p.x, p.y)
            if z.estado in ("perseguir", "investigar") and z.alvo:
                ax = z.alvo[0] - z.x
                ay = z.alvo[1] - z.y
                if z.estado == "investigar" and ax * ax + ay * ay < 30 * 30:
                    z.estado = "vagar"
                    z.t_vagar = 0
                else:
                    vel = z.vel if z.estado == "perseguir" else z.vel * 0.8
                    vel *= self.no_arame(z, dt)
                    self.passo_zumbi(z, math.atan2(ay, ax), vel * dt)
            elif not z.parado:
                self.passo_zumbi(z, z.ang, z.vel * 0.3 * dt * self.no_arame(z, dt), vagando=True)
            # ataque
            if d < z.r + p.r + 8 and z.t_ataque <= 0 and not seguro and self.esquiva <= 0:
                z.t_ataque = {"gordo": 1.4, "corredor": 0.7, "gigante": 1.7}.get(z.tipo, 1.0)
                p.vida -= z.dano
                self.tremor = max(self.tremor, 6 if z.tipo != "gigante" else 14)
                self.machucar()
                self.dano_t = 0.45
                self.som("dor", 0.7)
                if self.acao and self.acao["tipo"] != "torre":
                    self.acao = None
                for _ in range(4):
                    self.particula(p.x, p.y, random.uniform(-90, 90), random.uniform(-90, 90), 0.4, (150, 10, 12), 3)
            # gemidos
            z.t_gemido -= dt
            if z.t_gemido <= 0:
                z.t_gemido = random.uniform(6, 14)
                if d < 650:
                    self.som(f"gemido{random.randrange(3)}", (1 - d / 650) * 0.55)
        for z in remover:
            self.zumbis.remove(z)
        for z in [z for z in self.zumbis if z.hp <= 0]:
            self.matar(z, 0.0)
        # separacao
        zs = self.zumbis
        for i in range(len(zs)):
            a = zs[i]
            for j in range(i + 1, len(zs)):
                b = zs[j]
                dx = b.x - a.x
                dy = b.y - a.y
                rr = a.r + b.r
                if -rr < dx < rr and -rr < dy < rr:
                    d2 = dx * dx + dy * dy
                    if 0.01 < d2 < rr * rr:
                        d = math.sqrt(d2)
                        push = (rr - d) * 0.5
                        ux = dx / d * push
                        uy = dy / d * push
                        if not m.bloqueado(a.x - ux, a.y - uy, a.r):
                            a.x -= ux
                            a.y -= uy
                        if not m.bloqueado(b.x + ux, b.y + uy, b.r):
                            b.x += ux
                            b.y += uy

    def no_arame(self, z, dt):
        """Arame farpado: machuca e deixa o zumbi lento."""
        for c in self.arames:
            if (c["x"] - z.x) ** 2 + (c["y"] - z.y) ** 2 < 34 * 34:
                z.hp -= 18 * dt
                if random.random() < dt * 3:
                    self.particula(z.x, z.y, random.uniform(-30, 30), random.uniform(-30, 30), 0.4, (120, 20, 16), 3)
                return 0.3
        return 1.0

    def dens_local(self):
        m = self.mundo
        p = self.p
        tot = 0
        for ox, oy in ((0, 0), (700, 0), (-700, 0), (0, 700), (0, -700), (500, 500), (-500, 500), (500, -500), (-500, -500)):
            tot += m.densidade(p.x + ox, p.y + oy)
        return tot / 9

    def zumbi_ve(self, z, d, visao, seguro):
        """O zumbi so te ve se voce estiver na frente dele, perto e sem nada no meio."""
        if seguro or d > visao:
            return False
        if z.estado != "perseguir" and d > 70:
            olhar = math.atan2(self.p.y - z.y, self.p.x - z.x)
            dif = abs((olhar - z.ang_vis + math.pi) % (2 * math.pi) - math.pi)
            if dif > 1.1:  # fora do campo de visao (uns 125 graus na frente)
                return False
        return self.mundo.linha_livre(z.x, z.y, self.p.x, self.p.y)

    def passo_zumbi(self, z, ang, dist, vagando=False):
        m = self.mundo
        for off in (0, 0.6, -0.6, 1.2, -1.2, 1.9, -1.9):
            a = ang + off
            nx = z.x + math.cos(a) * dist
            ny = z.y + math.sin(a) * dist
            if not m.bloqueado(nx, ny, z.r):
                z.x = nx
                z.y = ny
                if vagando and off:
                    z.ang = a
                dif = (a - z.ang_vis + math.pi) % (2 * math.pi) - math.pi
                z.ang_vis += dif * 0.2
                z.balanco += dist * 0.12
                return
        if vagando:
            z.ang = random.uniform(0, 6.283)

    def criar_zumbi(self, esc):
        p = self.p
        m = self.mundo
        for _ in range(12):
            a = random.uniform(0, 6.283)
            if self.resgate is not None:
                d = random.uniform(700, 1000)
            elif m.cidade_perto(p.x, p.y, 1.3):  # na cidade nasce mais perto (mas fora da tela), dentro da cidade
                d = random.uniform(760, 1050)
            else:
                d = random.uniform(1150, 1500)
            x = p.x + math.cos(a) * d
            y = p.y + math.sin(a) * d
            if not (40 < x < N * T - 40 and 40 < y < N * T - 40):
                continue
            if m.tile_px(x, y) in SOLIDO or m.bloqueado(x, y, 14):
                continue
            if self.em_zona_segura(x, y):
                continue
            if self.resgate is None and random.random() > m.densidade(x, y):
                continue
            r = random.random()
            tem_gigante = any(z.tipo == "gigante" for z in self.zumbis)
            if self.resgate is None and esc > 0.5 and self.dia >= 2 and not tem_gigante and random.random() < 0.05:
                tipo = "gigante"
            elif r < 0.06 + 0.12 * esc + min(0.1, self.dia * 0.01):
                tipo = "corredor"
            elif r < 0.25 + 0.05 * esc:
                tipo = "gordo"
            else:
                tipo = "normal"
            z = Zumbi(x, y, tipo, random.randrange(len(self.spr_z[tipo])), random)
            if self.resgate is not None:
                z.estado = "perseguir"
                z.alvo = (p.x, p.y)
            self.zumbis.append(z)
            return

    # ================================================================ morte / vitoria
    def tela_morto(self, dt):
        self.desenhar()
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((60, 0, 0, 170))
        self.tela.blit(sh, (0, 0))
        # SE FUDEU: grandao, vermelho, pulsando e tremendo
        t = time.time()
        pulso = 1.0 + 0.06 * math.sin(t * 6)
        img = self.__dict__.get("img_morte")
        if img is None:
            img = self.img_morte = self.f_morte.render("SE FUDEU", True, (235, 20, 20))
            self.img_morte_sombra = self.f_morte.render("SE FUDEU", True, (40, 0, 0))
        big = pygame.transform.smoothscale(img, (int(img.get_width() * pulso), int(img.get_height() * pulso)))
        sbig = pygame.transform.smoothscale(self.img_morte_sombra, big.get_size())
        tx = random.uniform(-3, 3)
        ty = random.uniform(-3, 3)
        r = big.get_rect(center=(W // 2 + tx, 150 + ty))
        self.tela.blit(sbig, r.move(6, 7))
        self.tela.blit(big, r)
        self.texto(f"Dia {self.dia}  ·  {self.mortes} zumbis derrubados", (W // 2, 280), self.f_med2, centro=True)
        self.texto("Sua mochila ficou caída onde você morreu (marcada no mapa).", (W // 2, 330), self.f_med2,
                   (230, 210, 200), centro=True)
        self.texto("Você vai acordar no último lugar onde dormiu.", (W // 2, 362), self.f_med2, (230, 210, 200), centro=True)
        if self.botao("Acordar", W // 2, 430):
            self.renascer()
        if self.botao("Salvar e ir para o menu", W // 2, 494):
            self.renascer()
            self.salvar()
            self.estado = "menu"

    def renascer(self):
        p = self.p
        m = self.mundo
        itens = [[k, v] for k, v in self.inv.items() if v > 0 and k not in ("silenciador_guardado", "mira_guardada")]
        if self.inv.get("silenciador_guardado"):
            itens.append(["silenciador", self.inv["silenciador_guardado"]])
        for ida in self.armas:
            if ida != "faca":
                itens.append([ida, 1])
                a = ARMAS[ARMA_IDX[ida]]
                if self.pente.get(ida, 0) > 0:
                    itens.append([a["mun"], self.pente[ida]])
        for ida in self.silen:
            itens.append(["silenciador", 1])
        for ida in self.miras:
            itens.append(["mira", 1])
        if self.inv.get("mira_guardada"):
            itens.append(["mira", self.inv["mira_guardada"]])
        self.miras = []
        if itens:
            m.add_movel(dict(id=len(m.moveis), x=p.x, y=p.y, tipo="mochila", aberto=False, itens=itens))
            self.mochila_pos = (p.x, p.y)
        self.inv = {}
        p.curar_tudo()
        self.armas = ["faca"]
        self.pente = {}
        self.silen = []
        self.arma = "faca"
        p.x, p.y = self.respawn
        p.vida = 70
        p.fome = max(p.fome, 50)
        p.sede = max(p.sede, 50)
        self.zumbis = [z for z in self.zumbis if math.hypot(z.x - p.x, z.y - p.y) > 1000]
        self.acao = None
        self.resgate = None
        self.heli = None
        self.cam = [p.x, p.y]
        self.estado = "jogo"
        self.msg("Você acordou... sem suas coisas. Volte e pegue sua mochila.", (255, 200, 170))
        self.salvar()

    def vencer(self):
        self.estado = "vitoria"
        self.moedas += MOEDAS_ZERAR
        self.recorde["moedas"] = self.moedas
        self.recorde["resgates"] = self.recorde.get("resgates", 0) + 1
        self.recorde["dias"] = max(self.recorde.get("dias", 0), self.dia)
        self.recorde["zumbis"] = max(self.recorde.get("zumbis", 0), self.mortes)
        self.gravar_recorde()
        try:
            os.remove(self.caminho_save())
        except Exception:
            pass

    def tela_vitoria(self, dt):
        self.desenhar_fundo_menu(dt)
        self.texto("VOCÊ FOI RESGATADO!", (W // 2, 190), self.f_titulo, (120, 230, 140), centro=True)
        self.texto(f"Sobreviveu {self.dia} dias e derrubou {self.mortes} zumbis.", (W // 2, 280), self.f_med2, centro=True)
        self.texto("O helicóptero levou você para a zona segura. Parabéns, sobrevivente.", (W // 2, 320), self.f_med2,
                   centro=True)
        self.texto(f"+{MOEDAS_ZERAR} MOEDAS por zerar o jogo!  (agora você tem {self.moedas})", (W // 2, 366),
                   self.f_med, (255, 220, 110), centro=True)
        if self.botao("Menu", W // 2, 420):
            self.mundo = None
            self.estado = "menu"

    def tela_pausa(self, dt):
        self.desenhar()
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 160))
        self.tela.blit(sh, (0, 0))
        self.texto("PAUSA", (W // 2, 170), self.f_titulo, centro=True)
        if self.botao("Continuar", W // 2, 270) or pygame.K_ESCAPE in self.teclas:
            self.estado = "jogo"
        if self.botao("Salvar o jogo", W // 2, 334):
            self.salvar()
            self.msg("Jogo salvo.", (180, 230, 255))
            self.estado = "jogo"
        if self.botao("Como jogar", W // 2, 398):
            self.estado = "como_pausa"
        if self.botao("Salvar e ir para o menu", W // 2, 462):
            self.salvar()
            self.estado = "menu"
        if self.botao("Salvar e sair do jogo", W // 2, 526):
            self.sair()

    def tela_como_pausa(self, dt):
        self.tela_como(dt)
        if self.estado == "menu":
            self.estado = "pausa"

    # ================================================================ mapa
    def tela_mapa(self, dt):
        if pygame.K_m in self.teclas or pygame.K_ESCAPE in self.teclas or pygame.K_TAB in self.teclas:
            self.estado = "jogo"
            return
        m = self.mundo
        self.tela.fill((14, 16, 20))
        S = 660
        if self.mapa_grande is None:
            base = m.mapa.copy()
            base.blit(self.fog, (0, 0))
            self.mapa_grande = pygame.transform.smoothscale(base, (S, S))
        ox = (W - S) // 2 - 150
        oy = (H - S) // 2
        pygame.draw.rect(self.tela, (90, 80, 60), (ox - 6, oy - 6, S + 12, S + 12), border_radius=6)
        self.tela.blit(self.mapa_grande, (ox, oy))
        k = S / (N * T)

        def P(x, y):
            return int(ox + x * k), int(oy + y * k)

        def explorado(x, y):
            i = int(y // T) // EXPLO * NE + int(x // T) // EXPLO
            return 0 <= i < len(self.explorado) and self.explorado[i]

        for c in m.cidades:
            x, y = c["x"] * T, c["y"] * T
            if explorado(x, y):
                self.texto(c["nome"], P(x, y - c["raio"] * T - 30), self.f_peq, (240, 235, 220), centro=True)
        for b in m.construcoes:
            x = (b["x"] + b["w"] / 2) * T
            y = (b["y"] + b["h"] / 2) * T
            if b["tipo"] in ("hospital", "posto") and explorado(x, y):
                px, py = P(x, y)
                pygame.draw.rect(self.tela, (255, 255, 255), (px - 7, py - 7, 14, 14))
                pygame.draw.rect(self.tela, (220, 30, 30), (px - 2, py - 5, 4, 10))
                pygame.draw.rect(self.tela, (220, 30, 30), (px - 5, py - 2, 10, 4))
        for i, b in enumerate(m.bunkers):
            x = (b["x"] + b["w"] / 2) * T
            y = (b["y"] + b["h"] / 2) * T
            if i in self.revelados:
                px, py = P(x, y)
                pygame.draw.circle(self.tela, (30, 40, 20), (px, py), 10)
                pygame.draw.circle(self.tela, (120, 200, 90), (px, py), 8)
                self.texto(f"B{i + 1}", (px, py), self.f_peq, (20, 30, 10), centro=True, sombra=False)
        if m.torre:
            px, py = P((m.torre["x"] + 4.5) * T, (m.torre["y"] + 4.5) * T)
            pygame.draw.line(self.tela, (255, 80, 60), (px, py + 10), (px, py - 12), 3)
            pygame.draw.circle(self.tela, (255, 80, 60), (px, py - 12), 4)
            self.texto("Torre de rádio", (px, py + 22), self.f_peq, (255, 160, 140), centro=True)
        for c in self.construidos:
            if c["tipo"] == "abrigo":
                px, py = P(c["x"], c["y"])
                pygame.draw.circle(self.tela, (90, 170, 255), (px, py), 7)
                pygame.draw.circle(self.tela, (255, 255, 255), (px, py), 7, 2)
        for mv in m.moveis[self.n_moveis_base:]:
            if mv["tipo"] == "mochila" and not mv["aberto"]:
                px, py = P(mv["x"], mv["y"])
                pygame.draw.rect(self.tela, (255, 200, 60), (px - 5, py - 6, 10, 12), border_radius=2)
        px, py = P(*self.respawn)
        pygame.draw.circle(self.tela, (200, 200, 255), (px, py), 4, 1)
        p = self.p
        px, py = P(p.x, p.y)
        a = p.ang
        pts = [(px + math.cos(a) * 11, py + math.sin(a) * 11), (px + math.cos(a + 2.5) * 8, py + math.sin(a + 2.5) * 8),
               (px + math.cos(a - 2.5) * 8, py + math.sin(a - 2.5) * 8)]
        pygame.draw.polygon(self.tela, (255, 255, 255), pts)
        pygame.draw.polygon(self.tela, (0, 0, 0), pts, 2)
        # legenda
        lx = ox + S + 40
        self.texto("MAPA", (lx, oy), self.f_grande)
        y = oy + 60
        for desenho, txt in (("eu", "Você"), ("h", "Hospital / posto de saúde"), ("b", "Bunker militar (peça do rádio)"),
                             ("t", "Torre de rádio (resgate)"), ("a", "Seu bunker"), ("m", "Sua mochila"),
                             ("r", "Onde você acorda")):
            cx, cy = lx + 10, y + 11
            if desenho == "eu":
                pygame.draw.polygon(self.tela, (255, 255, 255), [(cx + 9, cy), (cx - 6, cy - 6), (cx - 6, cy + 6)])
            elif desenho == "h":
                pygame.draw.rect(self.tela, (255, 255, 255), (cx - 7, cy - 7, 14, 14))
                pygame.draw.rect(self.tela, (220, 30, 30), (cx - 2, cy - 5, 4, 10))
                pygame.draw.rect(self.tela, (220, 30, 30), (cx - 5, cy - 2, 10, 4))
            elif desenho == "b":
                pygame.draw.circle(self.tela, (120, 200, 90), (cx, cy), 8)
            elif desenho == "t":
                pygame.draw.line(self.tela, (255, 80, 60), (cx, cy + 8), (cx, cy - 8), 3)
            elif desenho == "a":
                pygame.draw.circle(self.tela, (90, 170, 255), (cx, cy), 7)
            elif desenho == "m":
                pygame.draw.rect(self.tela, (255, 200, 60), (cx - 5, cy - 6, 10, 12), border_radius=2)
            else:
                pygame.draw.circle(self.tela, (200, 200, 255), (cx, cy), 4, 1)
            self.texto(txt, (lx + 30, y), self.f_peq)
            y += 30
        y += 20
        pecas = self.inv.get("peca", 0)
        self.texto(f"Peças do rádio: {pecas}/{PECAS_RADIO}", (lx, y), self.f_med, (255, 220, 140))
        self.texto(f"Dia {self.dia}  ·  {self.mortes} zumbis", (lx, y + 34), self.f_med2)
        self.texto("Só aparece no mapa o que você já explorou.", (lx, y + 74), self.f_peq, (170, 170, 170))
        self.texto("M ou ESC para fechar", (lx, oy + S - 20), self.f_peq, (170, 170, 170))

    # ================================================================ desenho
    def telhado(self, b):
        s = self.telhados.get(b["id"])
        if s is not None:
            return s
        w = b["w"] * T
        h = b["h"] * T
        r = random.Random(b["id"] * 31 + 7)
        s = pygame.Surface((w, h))
        if b["tipo"] == "casa":
            cor = r.choice([(150, 70, 52), (126, 88, 66), (88, 92, 102), (140, 108, 78), (84, 96, 72), (110, 60, 50)])
            claro = G.tom(cor, 16)
            escuro = G.tom(cor, -22)
            if w >= h:
                pygame.draw.rect(s, claro, (0, 0, w, h // 2))
                pygame.draw.rect(s, escuro, (0, h // 2, w, h - h // 2))
                for y in range(4, h, 7):
                    pygame.draw.line(s, G.tom(claro if y < h // 2 else escuro, -18), (0, y), (w, y), 1)
                    off = (y // 7) % 2 * 6
                    for x in range(off, w, 12):
                        pygame.draw.line(s, G.tom(claro if y < h // 2 else escuro, -14), (x, y - 6), (x, y), 1)
                pygame.draw.rect(s, G.tom(cor, -40), (0, h // 2 - 3, w, 6))
                pygame.draw.line(s, G.tom(cor, 30), (0, h // 2 - 3), (w, h // 2 - 3), 1)
            else:
                pygame.draw.rect(s, claro, (0, 0, w // 2, h))
                pygame.draw.rect(s, escuro, (w // 2, 0, w - w // 2, h))
                for x in range(4, w, 7):
                    pygame.draw.line(s, G.tom(claro if x < w // 2 else escuro, -18), (x, 0), (x, h), 1)
                    off = (x // 7) % 2 * 6
                    for y in range(off, h, 12):
                        pygame.draw.line(s, G.tom(claro if x < w // 2 else escuro, -14), (x - 6, y), (x, y), 1)
                pygame.draw.rect(s, G.tom(cor, -40), (w // 2 - 3, 0, 6, h))
                pygame.draw.line(s, G.tom(cor, 30), (w // 2 - 3, 0), (w // 2 - 3, h), 1)
            for _ in range(r.randint(4, 14)):
                pygame.draw.circle(s, r.choice([(70, 90, 50), (90, 100, 60), (60, 56, 50)]),
                                   (r.randint(0, w), r.randint(0, h)), r.randint(2, 6))
            rm = random.Random(b["id"] * 97 + 3)
            if rm.random() < 0.45:  # casa velha com musgo
                for _ in range(rm.randint(5, 12)):
                    mx, my = rm.randint(0, w), rm.randint(0, h)
                    for _ in range(rm.randint(3, 7)):
                        pygame.draw.circle(s, rm.choice([(64, 96, 44), (78, 112, 52), (52, 80, 38)]),
                                           (mx + rm.randint(-12, 12), my + rm.randint(-8, 8)), rm.randint(4, 10))
            cx = r.randint(20, w - 30)
            cy = r.randint(8, h - 30)
            pygame.draw.rect(s, (80, 70, 66), (cx, cy, 16, 16))
            pygame.draw.rect(s, (40, 36, 34), (cx + 3, cy + 3, 10, 10))
            if r.random() < 0.3:  # buraco no telhado
                hx, hy = r.randint(20, w - 40), r.randint(20, h - 40)
                pygame.draw.circle(s, (30, 26, 24), (hx, hy), r.randint(8, 14))
            pygame.draw.rect(s, G.tom(cor, -50), (0, 0, w, h), 3)
        elif b["tipo"] in ("hospital", "posto"):
            s.fill((206, 208, 204))
            for x in range(0, w, 32):
                pygame.draw.line(s, (190, 192, 188), (x, 0), (x, h), 1)
            for _ in range(3 if b["tipo"] == "hospital" else 1):
                ax, ay = r.randint(10, w - 50), r.randint(10, h - 40)
                pygame.draw.rect(s, (150, 152, 150), (ax, ay, 40, 30))
                pygame.draw.circle(s, (90, 92, 90), (ax + 20, ay + 15), 11)
                pygame.draw.line(s, (60, 60, 60), (ax + 9, ay + 15), (ax + 31, ay + 15), 2)
            cx, cy = w // 2, h // 2
            rr = min(w, h) // 3
            pygame.draw.circle(s, (250, 250, 250), (cx, cy), rr)
            pygame.draw.rect(s, (210, 30, 30), (cx - rr // 4, cy - rr * 3 // 4, rr // 2, rr * 3 // 2))
            pygame.draw.rect(s, (210, 30, 30), (cx - rr * 3 // 4, cy - rr // 4, rr * 3 // 2, rr // 2))
            if b["tipo"] == "hospital":
                txt = self.f_med.render("HOSPITAL", True, (180, 30, 30))
                s.blit(txt, txt.get_rect(center=(cx, h - 20)))
            pygame.draw.rect(s, (150, 152, 148), (0, 0, w, h), 5)
            for _ in range(10):
                pygame.draw.circle(s, (150, 140, 120), (r.randint(0, w), r.randint(0, h)), r.randint(3, 9))
        elif b["tipo"] == "militar":
            s.fill((82, 92, 64))
            for _ in range(18):
                pygame.draw.ellipse(s, r.choice([(64, 72, 50), (104, 108, 76), (70, 64, 46)]),
                                    (r.randint(-20, w), r.randint(-20, h), r.randint(30, 80), r.randint(20, 50)))
            for k in range(3):
                vx = 20 + k * (w - 60) // 2
                pygame.draw.rect(s, (40, 44, 36), (vx, 16, 26, 16))
                for j in range(4):
                    pygame.draw.line(s, (90, 96, 80), (vx + 2, 19 + j * 4), (vx + 24, 19 + j * 4), 1)
            pygame.draw.circle(s, (60, 66, 50), (w // 2, h // 2 + 10), 22)
            pygame.draw.circle(s, (100, 108, 86), (w // 2, h // 2 + 10), 18, 3)
            txt = self.f_med.render("BUNKER", True, (210, 200, 140))
            s.blit(txt, txt.get_rect(center=(w // 2, h // 2 + 56)))
            pygame.draw.rect(s, (50, 56, 40), (0, 0, w, h), 5)
        G.vivo(s, 1.2, 1.05)
        for px, py in (b.get("portas", []) if b["tipo"] in ("casa", "militar") else []):
            lx = (px - b["x"]) * T
            ly = (py - b["y"]) * T
            pygame.draw.rect(s, (26, 24, 22), (lx, ly, T, T))
            pygame.draw.rect(s, (200, 170, 90), (lx, ly, T, T), 2)
        if b["tipo"] == "militar":
            fonte = self.f_peq
            vistos = set()
            for px, py in b.get("portas", []):
                lado = "N" if py == b["y"] else "S" if py == b["y"] + b["h"] - 1 else "O" if px == b["x"] else "L"
                if lado in vistos:
                    continue
                vistos.add(lado)
                lx = (px - b["x"]) * T + T
                ly = (py - b["y"]) * T + T // 2
                dy = {"N": 30, "S": -30, "O": 0, "L": 0}[lado]
                dx = {"O": 60, "L": -60, "N": 0, "S": 0}[lado]
                img = fonte.render("ENTRADA", True, (255, 220, 120))
                s.blit(img, img.get_rect(center=(lx + dx, ly + dy)))
        self.telhados[b["id"]] = s
        return s

    def desenhar(self):
        tela = self.tela
        m = self.mundo
        p = self.p
        camx = int(self.cam[0] - W / 2)
        camy = int(self.cam[1] - H / 2)
        if self.tremor > 0.3:  # a tela treme nos tiros fortes e quando voce apanha
            camx += int(random.uniform(-self.tremor, self.tremor))
            camy += int(random.uniform(-self.tremor, self.tremor))
        cx0 = camx // CHPX
        cy0 = camy // CHPX
        cx1 = (camx + W) // CHPX
        cy1 = (camy + H) // CHPX
        # chao
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                if 0 <= cx < N // CH and 0 <= cy < N // CH:
                    tela.blit(self.chunk_chao(cx, cy), (cx * CHPX - camx, cy * CHPX - camy))
                else:
                    pygame.draw.rect(tela, (30, 60, 90), (cx * CHPX - camx, cy * CHPX - camy, CHPX, CHPX))
        # adianta o desenho de um pedaco vizinho por quadro
        for cy in range(cy0 - 1, cy1 + 2):
            for cx in range(cx0 - 1, cx1 + 2):
                if 0 <= cx < N // CH and 0 <= cy < N // CH and (cx, cy) not in self.cache_chao:
                    self.chunk_chao(cx, cy)
                    break
            else:
                continue
            break
        vis = pygame.Rect(camx - 80, camy - 80, W + 160, H + 160)
        for s, x, y in self.decalques:
            if vis.collidepoint(x, y):
                tela.blit(s, (x - camx, y - camy))
        # objetos no chao
        ccx = int(self.cam[0])
        ccy = int(self.cam[1])
        for c in m.perto(m.camas_ch, ccx, ccy, 2):
            if vis.collidepoint(c["x"], c["y"]):
                spr = self.spr_cama_h if c.get("hospital") else self.spr_cama_m
                tela.blit(spr, (c["x"] - camx - 13, c["y"] - camy - 26))
        for mv in m.perto(m.moveis_ch, ccx, ccy, 2):
            if vis.collidepoint(mv["x"], mv["y"]):
                G.desenha_movel(tela, mv["tipo"], mv["aberto"], mv["x"] - camx, mv["y"] - camy)
        brilho = (math.sin(time.time() * 4) + 1) / 2
        for it in m.perto(m.itens_ch, ccx, ccy, 2):
            if not it.get("pego") and vis.collidepoint(it["x"], it["y"]):
                sx = it["x"] - camx
                sy = it["y"] - camy
                pygame.draw.circle(tela, (255, 255, 200), (int(sx), int(sy)), int(13 + brilho * 3), 1)
                G.desenha_icone(tela, it["item"], sx, sy)
        for c in self.construidos:
            if vis.collidepoint(c["x"], c["y"]):
                if c["tipo"] == "fogueira":
                    tela.blit(self.spr_fogueira, (c["x"] - camx - 20, c["y"] - camy - 20))
                elif c["tipo"] == "arame":
                    spr = self.rot(("arame",), self.spr_arame, c["ang"] - 90, 3)
                    tela.blit(spr, (c["x"] - camx - spr.get_width() / 2, c["y"] - camy - spr.get_height() / 2))
                elif c["tipo"] == "abrigo":
                    tela.blit(self.spr_abrigo, (c["x"] - camx - 56, c["y"] - camy - 56))
                elif c["tipo"] == "bancada":
                    tela.blit(self.spr_bancada, (c["x"] - camx - 32, c["y"] - camy - 20))
        for c in getattr(m, "bancadas", ()):
            if vis.collidepoint(c["x"], c["y"]):
                tela.blit(self.spr_bancada, (c["x"] - camx - 32, c["y"] - camy - 20))
        # zumbis e jogador
        for z in self.zumbis:
            if vis.collidepoint(z.x, z.y):
                sx = z.x - camx
                sy = z.y - camy
                sh = {"gordo": self.spr_sombra_g, "gigante": self.spr_sombra_gg}.get(z.tipo, self.spr_sombra)
                tela.blit(sh, (sx - sh.get_width() / 2 + 4, sy - sh.get_height() / 2 + 6))
                ang = math.degrees(z.ang_vis) + math.sin(z.balanco) * 6
                spr = self.rot((z.tipo, z.var), self.spr_z[z.tipo][z.var], ang)
                if z.flash > 0:
                    spr = spr.copy()
                    spr.fill((120, 120, 120, 0), special_flags=pygame.BLEND_RGBA_ADD)
                tela.blit(spr, (sx - spr.get_width() / 2, sy - spr.get_height() / 2))
                if z.viu > 0 and z.estado != "perseguir":
                    self.texto("?", (sx, sy - 30), self.f_med, (255, 220, 90), centro=True)
                if z.tipo == "gigante":  # barra de vida do gigante
                    fr = max(0, z.hp / 1100)
                    pygame.draw.rect(tela, (20, 10, 10), (sx - 32, sy - 52, 64, 8), border_radius=3)
                    pygame.draw.rect(tela, (220, 50, 40), (sx - 31, sy - 51, int(62 * fr), 6), border_radius=3)
                    self.texto("GIGANTE", (sx, sy - 64), self.f_peq, (255, 160, 140), centro=True)
        psx = p.x - camx
        psy = p.y - camy
        tela.blit(self.spr_sombra, (psx - self.spr_sombra.get_width() / 2 + 4, psy - self.spr_sombra.get_height() / 2 + 6))
        if self.agachado:
            agach = self.__dict__.setdefault("spr_agachado", {})
            if self.arma not in agach:
                b = self.spr_j[self.arma]
                agach[self.arma] = pygame.transform.smoothscale(b, (int(b.get_width() * 0.82), int(b.get_height() * 0.82)))
            spr = self.rot(("ja", self.arma), agach[self.arma], math.degrees(p.ang), 4)
        else:
            spr = self.rot(("j", self.arma), self.spr_j[self.arma], math.degrees(p.ang), 4)
        tela.blit(spr, (psx - spr.get_width() / 2, psy - spr.get_height() / 2))
        for c in self.construidos:
            if c["tipo"] == "barricada" and vis.collidepoint(c["x"], c["y"]):
                spr = self.rot(("bar",), self.spr_barricada, c["ang"] - 90, 3)
                tela.blit(spr, (c["x"] - camx - spr.get_width() / 2, c["y"] - camy - spr.get_height() / 2))
        # tiros e particulas
        for r in self.rastros:
            pygame.draw.line(tela, (255, 236, 170), (r[0] - camx, r[1] - camy), (r[2] - camx, r[3] - camy), 2)
        if self.flash_t > 0:
            fx, fy = self.flash_pos
            pygame.draw.circle(tela, (255, 230, 140), (int(fx - camx), int(fy - camy)), 9)
            pygame.draw.circle(tela, (255, 255, 230), (int(fx - camx), int(fy - camy)), 5)
        for q in self.particulas:
            k = q[4] / q[5]
            cor = q[6]
            if q[8] == "f":
                cor = G.mistura((80, 70, 60), cor, k)
            pygame.draw.circle(tela, cor, (int(q[0] - camx), int(q[1] - camy)), max(1, int(q[7] * (0.5 + k * 0.5))))
        for nmr in self.numeros:
            cor = (255, 210, 80) if nmr[4] else (255, 255, 255)
            self.texto(nmr[2], (nmr[0] - camx, nmr[1] - camy), self.f_med if nmr[4] else self.f_peq, cor, centro=True)
        # copas e capim alto
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                if 0 <= cx < N // CH and 0 <= cy < N // CH:
                    s = self.chunk_copa(cx, cy)
                    if s is not None:
                        tela.blit(s, (cx * CHPX - camx, cy * CHPX - camy))
        # telhados
        dentro = m.predio_em(p.x, p.y)
        vistos = set()
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                for b in m.pred_ch.get((cx, cy), ()):
                    if b["id"] in vistos or b["tipo"] == "torre":
                        continue
                    vistos.add(b["id"])
                    alvo = 0 if b is dentro else 255
                    a = self.alfa_telhado.get(b["id"], 255)
                    a += clamp(alvo - a, -40, 40)
                    self.alfa_telhado[b["id"]] = a
                    if a > 0:
                        s = self.telhado(b)
                        s.set_alpha(None if a >= 255 else a)
                        tela.blit(s, (b["x"] * T - camx, b["y"] * T - camy))
        if m.torre and vis.colliderect(pygame.Rect(m.torre["x"] * T, m.torre["y"] * T, 9 * T, 9 * T)):
            tela.blit(self.spr_torre, ((m.torre["x"] + 4.5) * T - camx - 75, (m.torre["y"] + 4.5) * T - camy - 75))
        # jogador debaixo de arvore/capim: contorno
        if m.no_capim(p.x, p.y) or self.debaixo_arvore():
            pygame.draw.circle(tela, (255, 255, 255), (int(psx), int(psy)), 15, 1)
        # fantasma da construcao
        if self.modo_construir is not None:
            self.desenhar_fantasma(camx, camy)
        if self.heli is not None:
            self.desenhar_heli(camx, camy)
        # chuva
        if self.chuva:
            camada = pygame.Surface((W, H), pygame.SRCALPHA)
            camada.fill((40, 50, 70, 50))
            for g in self.gotas:
                pygame.draw.line(camada, (180, 200, 230, 110), (g[0], g[1]), (g[0] - 5 * g[2], g[1] + 18 * g[2]), 1)
            tela.blit(camada, (0, 0))
        # luz e escuridao
        self.desenhar_luz(camx, camy, psx, psy)
        if not NAVEGADOR:  # a sombra das bordas pesa no navegador
            tela.blit(self.vinheta, (0, 0))
        if self.dano_t > 0:
            self.vinheta_v.set_alpha(int(255 * self.dano_t / 0.45))
            tela.blit(self.vinheta_v, (0, 0))
        if p.vida < 25:
            self.vinheta_v.set_alpha(int(80 + 60 * math.sin(time.time() * 5)))
            tela.blit(self.vinheta_v, (0, 0))
        self.desenhar_hud()

    def debaixo_arvore(self):
        p = self.p
        m = self.mundo
        tx = int(p.x // T)
        ty = int(p.y // T)
        for yy in (ty - 1, ty, ty + 1):
            for xx in (tx - 1, tx, tx + 1):
                a = m.arvores.get(yy * N + xx)
                if a and (a[0] - p.x) ** 2 + (a[1] - p.y) ** 2 < 30 * 30:
                    return True
        return False

    def desenhar_fantasma(self, camx, camy):
        rec = RECEITAS[self.modo_construir]
        mx, my = pygame.mouse.get_pos() if self.fake is None else self.fake["mouse"]
        wx = mx + camx
        wy = my + camy
        p = self.p
        d = math.hypot(wx - p.x, wy - p.y)
        if d > 110:
            ang = math.atan2(wy - p.y, wx - p.x)
            wx = p.x + math.cos(ang) * 110
            wy = p.y + math.sin(ang) * 110
        ok = self.lugar_ok(rec["id"], wx, wy) and all(self.inv.get(i, 0) >= q for i, q in rec["custo"].items())
        spr = {"barricada": self.rot(("bar",), self.spr_barricada, math.degrees(p.ang), 3), "fogueira": self.spr_fogueira,
               "abrigo": self.spr_abrigo, "arame": self.rot(("arame",), self.spr_arame, math.degrees(p.ang), 3),
               "ponte": self.spr_ponte, "bancada": self.spr_bancada}[rec["id"]].copy()
        if rec["id"] == "ponte":
            wx = (int(wx // T)) * T + 16
            wy = (int(wy // T)) * T + 16
        spr.fill((0, 255, 0, 0) if ok else (255, 0, 0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        spr.set_alpha(150)
        self.tela.blit(spr, (wx - camx - spr.get_width() / 2, wy - camy - spr.get_height() / 2))
        # painel
        y = 120
        self.rect_painel_construir = pygame.Rect(W // 2 - 165, y, 330, 40 + 34 * len(RECEITAS))
        painel = pygame.Surface((330, 40 + 34 * len(RECEITAS)), pygame.SRCALPHA)
        painel.fill((10, 12, 16, 200))
        self.tela.blit(painel, (W // 2 - 165, y))
        self.texto("CONSTRUIR (B ou ESC sai)", (W // 2, y + 18), self.f_med, centro=True)
        for i, r in enumerate(RECEITAS):
            custo = ", ".join(f"{q} {ITENS[k].lower()}" for k, q in r["custo"].items())
            pode = all(self.inv.get(k, 0) >= q for k, q in r["custo"].items())
            cor = (255, 240, 160) if i == self.modo_construir else ((210, 230, 210) if pode else (150, 140, 140))
            self.texto(f"{i + 1}. {r['nome']}: {custo}", (W // 2 - 150, y + 40 + i * 32), self.f_peq, cor)

    def desenhar_heli(self, camx, camy):
        hx, hy, _ = self.heli
        sx = hx - camx
        sy = hy - camy
        sh = pygame.Surface((160, 90), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), (0, 0, 160, 90))
        self.tela.blit(sh, (sx - 60, sy + 80))
        pygame.draw.ellipse(self.tela, (50, 64, 46), (sx - 50, sy - 22, 100, 44))
        pygame.draw.rect(self.tela, (50, 64, 46), (sx - 120, sy - 6, 80, 12))
        pygame.draw.ellipse(self.tela, (120, 170, 200), (sx + 14, sy - 14, 30, 28))
        a = time.time() * 30
        for k in range(2):
            aa = a + k * math.pi / 2
            pygame.draw.line(self.tela, (30, 30, 30), (sx - math.cos(aa) * 90, sy - math.sin(aa) * 90),
                             (sx + math.cos(aa) * 90, sy + math.sin(aa) * 90), 4)

    def desenhar_luz(self, camx, camy, psx, psy):
        esc = self.escuridao()
        if self.chuva:
            esc = max(esc, 0.18)
        if esc <= 0.01:
            # leve tom quente no fim da tarde
            if 16.5 <= self.hora < 18:
                t = pygame.Surface((W, H), pygame.SRCALPHA)
                t.fill((255, 150, 60, int((self.hora - 16.5) / 1.5 * 30)))
                self.tela.blit(t, (0, 0))
            return
        D = int(252 * esc)
        cor = (2, 4, 12) if esc > 0.6 else (24, 16, 34)
        self.escuro.fill((cor[0], cor[1], cor[2], D))
        sub = pygame.BLEND_RGBA_SUB
        self.escuro.blit(self.luz_jog, (psx - 130, psy - 130), special_flags=sub)
        if self.lanterna:
            q = int(round(math.degrees(self.p.ang) / 3)) % 120
            cone = self.cone_cache.get(q)
            if cone is None:
                cone = pygame.transform.rotate(self.cone, -q * 3)
                self.cone_cache[q] = cone
                if len(self.cone_cache) > 24:
                    self.cone_cache.popitem(last=False)
            self.escuro.blit(cone, (psx - cone.get_width() / 2, psy - cone.get_height() / 2), special_flags=sub)
        for c in self.construidos:
            if c["tipo"] == "fogueira":
                fx = c["x"] - camx
                fy = c["y"] - camy
                if -320 < fx < W + 320 and -320 < fy < H + 320:
                    k = 0.9 + 0.1 * math.sin(time.time() * 13 + c["x"])
                    sz = int(600 * k)
                    luz = pygame.transform.scale(self.luz_fogo, (sz, sz))
                    self.escuro.blit(luz, (fx - sz / 2, fy - sz / 2), special_flags=sub)
        if self.flash_t > 0:
            fx, fy = self.flash_pos
            self.escuro.blit(self.luz_flash, (fx - camx - 240, fy - camy - 240), special_flags=sub)
        for q in self.particulas:
            if q[8] == "f":
                self.escuro.blit(self.luz_peq, (q[0] - camx - 60, q[1] - camy - 60), special_flags=sub)
                break
        self.tela.blit(self.escuro, (0, 0))

    # ---------------------------------------------------------------- HUD
    def painel(self, rect, alpha=170):
        k = (rect.w, rect.h, alpha)
        cache = self.__dict__.setdefault("cache_painel", {})
        s = cache.get(k)
        if s is None:
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(s, (12, 14, 18, alpha), s.get_rect(), border_radius=12)
            pygame.draw.rect(s, (255, 255, 255, 30), s.get_rect(), 1, border_radius=12)
            if len(cache) > 60:
                cache.clear()
            cache[k] = s
        self.tela.blit(s, rect.topleft)

    def barra(self, x, y, valor, cor, icone, nome):
        tela = self.tela
        cx, cy = x + 12, y + 9
        if icone == "vida":
            pygame.draw.circle(tela, cor, (cx - 4, cy - 2), 5)
            pygame.draw.circle(tela, cor, (cx + 4, cy - 2), 5)
            pygame.draw.polygon(tela, cor, [(cx - 9, cy), (cx + 9, cy), (cx, cy + 9)])
        elif icone == "fome":
            G.desenha_icone(tela, "comida", cx, cy, 0.9)
        elif icone == "sede":
            pygame.draw.circle(tela, cor, (cx, cy + 3), 6)
            pygame.draw.polygon(tela, cor, [(cx - 6, cy + 2), (cx + 6, cy + 2), (cx, cy - 9)])
        else:
            for k in range(3):
                pygame.draw.line(tela, cor, (cx - 8, cy - 5 + k * 5), (cx + 6 - k * 3, cy - 5 + k * 5), 2)
        bx = x + 30
        w = 190
        pygame.draw.rect(tela, (30, 30, 34), (bx, y + 2, w, 14), border_radius=7)
        v = clamp(valor / 100, 0, 1)
        if v > 0:
            c = cor if v > 0.25 or icone == "folego" else G.mistura(cor, (255, 60, 40), 0.5 + 0.5 * math.sin(time.time() * 6))
            pygame.draw.rect(tela, c, (bx + 2, y + 4, int((w - 4) * v), 10), border_radius=5)
            pygame.draw.rect(tela, G.tom(c, 45), (bx + 4, y + 5, max(0, int((w - 8) * v)), 2), border_radius=2)
        self.texto(f"{nome} {int(valor)}", (bx + w + 10, y - 2), self.f_peq, (225, 225, 225))

    def desenhar_hud(self):
        tela = self.tela
        p = self.p
        # barras
        self.painel(pygame.Rect(14, H - 136, 330, 122))
        self.barra(24, H - 126, p.vida, (220, 60, 60), "vida", "Vida")
        self.barra(24, H - 98, p.fome, (230, 160, 60), "fome", "Fome")
        self.barra(24, H - 70, p.sede, (80, 160, 240), "sede", "Sede")
        self.barra(24, H - 42, p.folego, (200, 220, 200), "folego", "Fôlego")
        # arma
        a = self.arma_atual()
        self.painel(pygame.Rect(W - 330, H - 136, 316, 122))
        G.desenha_icone(tela, a["id"], W - 290, H - 104, 2.0)
        nv = self.niveis.get(self.arma, 0)
        self.texto(a["nome"] + (f"  +{nv}" if nv else ""), (W - 250, H - 128), self.f_med,
                   (255, 220, 120) if nv else (235, 230, 220))
        if a["melee"]:
            self.texto("corpo a corpo", (W - 250, H - 100), self.f_peq, (190, 190, 190))
        else:
            if self.recarga_t > 0:
                self.texto("recarregando...", (W - 250, H - 100), self.f_med2, (255, 220, 140))
            else:
                cor = (255, 120, 100) if self.pente.get(self.arma, 0) == 0 else (240, 240, 240)
                self.texto(f"{self.pente.get(self.arma, 0)} / {self.inv.get(a['mun'], 0)}", (W - 250, H - 102), self.f_grande, cor)
            extras = [n for n, tem in (("silenciador", self.arma in self.silen), ("mira", self.arma in self.miras)) if tem]
            if extras:
                self.texto(" + ".join(extras), (W - 120, H - 92), self.f_peq, (150, 210, 255))
        x = W - 320
        for i, aa in enumerate([ARMAS[ARMA_IDX[k]] for k in self.armas[:10]]):
            r = pygame.Rect(x + 4 + i * 31, H - 50, 28, 30)
            tem = aa["id"] in self.armas
            pygame.draw.rect(tela, (60, 50, 30) if aa["id"] == self.arma else (30, 32, 36), r, border_radius=6)
            pygame.draw.rect(tela, (230, 190, 90) if aa["id"] == self.arma else (70, 70, 76), r, 1, border_radius=6)
            if tem:
                G.desenha_icone(tela, aa["id"], r.centerx, r.centery + 1, 0.7)
            self.texto(str((i + 1) % 10), (r.x + 3, r.y - 2), self.f_peq, (200, 200, 200) if tem else (90, 90, 90), sombra=False)
        # itens rapidos
        itens = [("comida", "F"), ("agua", "G"), ("bandagem", "H"), ("kit", "J"), ("tabua", ""), ("sucata", ""),
                 ("ferramentas", ""), ("peca", "")]
        larg = 62
        x0 = W // 2 - len(itens) * larg // 2
        self.painel(pygame.Rect(x0 - 8, H - 72, len(itens) * larg + 16, 58))
        for i, (it, tecla) in enumerate(itens):
            cx = x0 + i * larg + larg // 2
            q = self.inv.get(it, 0)
            G.desenha_icone(tela, it, cx - 10, H - 46, 1.3)
            self.texto(f"{q}", (cx + 6, H - 58), self.f_med, (240, 240, 240) if q else (110, 110, 110))
            if tecla:
                self.texto(tecla, (cx - 26, H - 72), self.f_peq, (170, 170, 170), sombra=False)
        self.rects_rapidos = [(pygame.Rect(x0 + i * larg, H - 72, larg, 58), it) for i, (it, _) in enumerate(itens)]
        # botao da mochila (clique ou tecla V)
        cap = self.capacidade()
        uso = self.espaco_usado()
        rb = pygame.Rect(x0 - 8, H - 136, 60, 58)
        self.rect_botao_mochila = rb
        hover = rb.collidepoint(pygame.mouse.get_pos())
        self.painel(rb, 220 if hover else 170)
        if hover:
            pygame.draw.rect(tela, (230, 190, 90), rb, 2, border_radius=12)
        G.desenha_icone(tela, f"mochila{self.nivel_mochila}" if self.nivel_mochila else "mochila", rb.centerx, rb.centery - 2,
                        1.5)
        self.texto("V", (rb.x + 5, rb.y + 1), self.f_peq, (200, 200, 200), sombra=False)
        mouse = pygame.mouse.get_pos()
        rl = pygame.Rect(W - 290, 14, 64, 58)  # do lado do mapa
        self.rect_botao_loja = rl
        self.painel(rl, 220 if rl.collidepoint(mouse) else 170)
        pygame.draw.rect(tela, (230, 190, 90) if rl.collidepoint(mouse) else (150, 120, 60), rl, 2, border_radius=12)
        pygame.draw.circle(tela, (120, 90, 20), (rl.centerx, rl.y + 22), 11)
        pygame.draw.circle(tela, (240, 200, 70), (rl.centerx, rl.y + 22), 9)
        self.texto("LOJA", (rl.centerx, rl.y + 45), self.f_peq, (255, 220, 120), centro=True)
        self.texto("K", (rl.x + 5, rl.y + 1), self.f_peq, (200, 200, 200), sombra=False)
        self.rect_botao_dono = None
        if self.dono:
            rd = pygame.Rect(W - 290, 80, 64, 58)
            self.rect_botao_dono = rd
            self.painel(rd, 220 if rd.collidepoint(mouse) else 170)
            pygame.draw.rect(tela, (255, 120, 220) if rd.collidepoint(mouse) else (170, 80, 150), rd, 2, border_radius=12)
            G.desenha_icone(tela, "mochila4", rd.centerx, rd.y + 22, 1.0)
            self.texto("DONO", (rd.centerx, rd.y + 45), self.f_peq, (255, 160, 230), centro=True)
        self.rect_codigo = None
        if not self.dono:
            rk = pygame.Rect(W - 290, 78, 64, 22)
            self.rect_codigo = rk
            escrevendo = self.console_ativo and self.console_modo == "codigo"
            pygame.draw.rect(tela, (20, 18, 20), rk, border_radius=5)
            pygame.draw.rect(tela, (200, 170, 110) if escrevendo else (80, 74, 70), rk, 1, border_radius=5)
            if escrevendo:
                self.texto("*" * len(self.console_txt) + ("|" if int(time.time() * 2) % 2 == 0 else ""),
                           (rk.x + 5, rk.y + 2), self.f_peq, (240, 220, 180), sombra=False)
            else:
                self.texto("código", (rk.centerx, rk.centery), self.f_peq, (130, 120, 110), centro=True, sombra=False)
        self.rect_console = None
        if self.dono:
            rc = pygame.Rect(494, 14, 490, 36)
            self.rect_console = rc
            ativo = self.console_ativo and self.console_modo == "comando"
            pygame.draw.rect(tela, (24, 16, 26) if ativo else (16, 14, 18), rc, border_radius=8)
            pygame.draw.rect(tela, (255, 140, 220) if ativo else (140, 80, 130), rc, 2, border_radius=8)
            if self.console_txt or ativo:
                pisca = "|" if ativo and int(time.time() * 2) % 2 == 0 else ""
                self.texto("> " + self.console_txt + pisca, (rc.x + 10, rc.y + 7), self.f_med2, (255, 220, 245))
            else:
                self.texto("Escrever (só o dono)  ·  clique aqui e digite: ajuda", (rc.x + 10, rc.y + 8), self.f_peq,
                           (170, 120, 160))
        if self.agachado:
            self.texto("AGACHADO  (C levanta)", (24, H - 160 - 24 * (p.sangrando + p.perna + p.braco)), self.f_med,
                       (170, 220, 255))
        fr = min(1, uso / cap)
        pygame.draw.rect(tela, (30, 30, 34), (rb.right + 8, H - 98, 150, 8), border_radius=4)
        pygame.draw.rect(tela, (230, 90, 70) if fr > 0.95 else (200, 180, 120), (rb.right + 8, H - 98, int(150 * fr), 8),
                         border_radius=4)
        self.texto(f"{MOCHILAS[self.nivel_mochila][0]}  {uso:.0f}/{cap}", (rb.right + 8, H - 124), self.f_peq,
                   (220, 215, 200))
        # machucados no HUD
        avisos = []
        if p.sangrando:
            avisos.append(("SANGRANDO", (240, 80, 70)))
        if p.perna:
            avisos.append(("PERNA QUEBRADA", (240, 170, 70)))
        if p.braco:
            avisos.append(("BRAÇO QUEBRADO", (240, 170, 70)))
        for k, (txt, cor) in enumerate(avisos):
            self.texto(txt, (24, H - 160 - k * 24), self.f_med, cor)
        # relogio e objetivo
        self.painel(pygame.Rect(14, 14, 470, 74))
        esc = self.escuridao()
        if esc < 0.5:
            pygame.draw.circle(tela, (255, 210, 80), (40, 38), 11)
            for k in range(8):
                ang = k * math.pi / 4
                pygame.draw.line(tela, (255, 210, 80), (40 + math.cos(ang) * 14, 38 + math.sin(ang) * 14),
                                 (40 + math.cos(ang) * 18, 38 + math.sin(ang) * 18), 2)
        else:
            pygame.draw.circle(tela, (220, 220, 200), (40, 38), 11)
            pygame.draw.circle(tela, (20, 22, 28), (45, 34), 10)
        h = int(self.hora)
        mi = int((self.hora - h) * 60) // 10 * 10
        clima = "  ·  chuva" if self.chuva else ""
        self.texto(f"Dia {self.dia}  ·  {h:02d}:{mi:02d}  ·  {ESTACOES[self.estacao()][0]}{clima}", (64, 22), self.f_med)
        self.texto(f"zumbis: {self.mortes}", (380, 24), self.f_peq, (200, 170, 160))
        self.painel(pygame.Rect(W - 207, 238, 194, 34))
        pygame.draw.circle(tela, (120, 90, 20), (W - 186, 255), 10)
        pygame.draw.circle(tela, (240, 200, 70), (W - 186, 255), 8)
        self.texto("DONO" if self.dono else f"{self.moedas}", (W - 168, 243), self.f_med, (255, 220, 110))
        self.texto("moedas", (W - 90, 246), self.f_peq, (220, 200, 150))
        self.texto(self.objetivo(), (26, 56), self.f_peq, (255, 225, 150))
        # mensagens
        y = H - 170
        for txt, t, cor in reversed(self.msgs):
            img = self.f_med2.render(txt, True, cor)
            img.set_alpha(int(255 * min(1, t)))
            sh = self.f_med2.render(txt, True, (0, 0, 0))
            sh.set_alpha(int(200 * min(1, t)))
            tela.blit(sh, (22, y - 28 + 2))
            tela.blit(img, (20, y - 28))
            y -= 28
        # interacao / acao
        if self.acao:
            k = self.acao["t"] / self.acao["total"]
            r = pygame.Rect(W // 2 - 120, H // 2 + 50, 240, 16)
            pygame.draw.rect(tela, (20, 20, 20), r, border_radius=8)
            pygame.draw.rect(tela, (240, 200, 90), (r.x + 2, r.y + 2, int((r.w - 4) * k), r.h - 4), border_radius=6)
            self.texto(self.acao["txt"], (W // 2, H // 2 + 82), self.f_med2, centro=True)
        else:
            alvo = self.alvo_interacao()
            if alvo:
                self.texto(self.texto_interacao(alvo), (W // 2, H - 100), self.f_med, (255, 245, 210), centro=True)
        if self.resgate is not None and self.resgate > 0:
            mm = int(self.resgate) // 60
            ss = int(self.resgate) % 60
            self.texto(f"HELICÓPTERO EM {mm}:{ss:02d}", (W // 2, 120), self.f_grande, (255, 220, 120), centro=True)
        self.desenhar_minimapa()

    def objetivo(self):
        pecas = self.inv.get("peca", 0)
        if self.resgate is not None:
            return "Objetivo: sobreviva até o helicóptero chegar!"
        if pecas >= PECAS_RADIO:
            return "Objetivo: leve as peças até a TORRE DE RÁDIO (veja no mapa)"
        return f"Objetivo: ache as peças do rádio nos bunkers militares ({pecas}/{PECAS_RADIO})  ·  M = mapa"

    def desenhar_minimapa(self):
        m = self.mundo
        p = self.p
        TAM = 190
        V = 95  # quadradinhos mostrados
        r = pygame.Rect(W - TAM - 18, 14, TAM + 8, TAM + 8)
        pygame.draw.rect(self.tela, (20, 20, 22), r, border_radius=10)
        pygame.draw.rect(self.tela, (120, 110, 90), r, 2, border_radius=10)
        tx = int(p.x // T) - V // 2
        ty = int(p.y // T) - V // 2
        mini = pygame.Surface((V, V))
        mini.fill((10, 12, 16))
        mini.blit(m.mapa, (-tx, -ty))
        mini.blit(self.fog, (-tx, -ty))
        mini = pygame.transform.scale(mini, (TAM, TAM))
        self.tela.blit(mini, (r.x + 4, r.y + 4))
        k = TAM / V

        def P(x, y):
            return r.x + 4 + (x / T - tx) * k, r.y + 4 + (y / T - ty) * k

        clip = self.tela.get_clip()
        self.tela.set_clip(pygame.Rect(r.x + 4, r.y + 4, TAM, TAM))
        for i in self.revelados:
            b = m.bunkers[i]
            px, py = P((b["x"] + b["w"] / 2) * T, (b["y"] + b["h"] / 2) * T)
            pygame.draw.circle(self.tela, (120, 200, 90), (int(px), int(py)), 5)
        for c in self.construidos:
            if c["tipo"] == "abrigo":
                px, py = P(c["x"], c["y"])
                pygame.draw.circle(self.tela, (90, 170, 255), (int(px), int(py)), 5)
        self.tela.set_clip(clip)
        # setas para o bunker revelado mais perto e torre
        destinos = []
        pecas = self.inv.get("peca", 0)
        if pecas >= PECAS_RADIO and m.torre:
            destinos.append(((m.torre["x"] + 4.5) * T, (m.torre["y"] + 4.5) * T, (255, 90, 70)))
        else:
            for i in self.revelados:
                b = m.bunkers[i]
                caixa = [mv for mv in m.moveis if mv.get("predio") is b and "revela" in mv]
                if caixa and not caixa[0]["aberto"]:
                    destinos.append(((b["x"] + b["w"] / 2) * T, (b["y"] + b["h"] / 2) * T, (120, 220, 90)))
        cxm = r.x + 4 + TAM / 2
        cym = r.y + 4 + TAM / 2
        for dx_, dy_, cor in destinos:
            ang = math.atan2(dy_ - p.y, dx_ - p.x)
            dist = math.hypot(dx_ - p.x, dy_ - p.y)
            if dist / T < V / 2:
                continue
            ex = cxm + math.cos(ang) * (TAM / 2 - 8)
            ey = cym + math.sin(ang) * (TAM / 2 - 8)
            pts = [(ex + math.cos(ang) * 8, ey + math.sin(ang) * 8), (ex + math.cos(ang + 2.4) * 7, ey + math.sin(ang + 2.4) * 7),
                   (ex + math.cos(ang - 2.4) * 7, ey + math.sin(ang - 2.4) * 7)]
            pygame.draw.polygon(self.tela, cor, pts)
            self.texto(f"{int(dist / T * 2)} m", (ex - 16, ey + 6), self.f_peq, cor)
        a = p.ang
        pts = [(cxm + math.cos(a) * 8, cym + math.sin(a) * 8), (cxm + math.cos(a + 2.5) * 6, cym + math.sin(a + 2.5) * 6),
               (cxm + math.cos(a - 2.5) * 6, cym + math.sin(a - 2.5) * 6)]
        pygame.draw.polygon(self.tela, (255, 255, 255), pts)
        pygame.draw.polygon(self.tela, (0, 0, 0), pts, 1)
        cid = m.cidade_perto(p.x, p.y, 1.2)
        nome = cid["nome"] if cid else ("Bunker militar" if (m.predio_em(p.x, p.y) or {}).get("tipo") == "militar" else "Floresta")
        self.texto(nome, (r.centerx, r.bottom + 14), self.f_peq, (230, 225, 210), centro=True)

    # ================================================================ teste automatico
    def teste(self):
        t0 = time.time()
        self.novo_jogo(seed=12345)
        m = self.mundo
        print(f"mundo gerado em {time.time() - t0:.1f}s")
        print("cidades:", len(m.cidades), "predios:", len(m.construcoes), "hospitais:",
              sum(1 for b in m.construcoes if b["tipo"] in ("hospital", "posto")), "bunkers:", len(m.bunkers),
              "torre:", bool(m.torre), "arvores:", len(m.arvores), "capim grande:", len(m.capim_g),
              "carros:", len(m.carros), "moveis:", len(m.moveis), "itens chao:", len(m.itens_chao))
        cont = np.bincount(m.tn.ravel(), minlength=13)
        print("tiles %:", {k: round(100 * cont[v] / cont.sum(), 1) for k, v in
                           (("grama", GRAMA), ("mato", MATO), ("agua", AGUA), ("areia", AREIA), ("terra", TERRA), ("asfalto", ASFALTO))})
        rnd = random.Random(1)
        ms = []
        self.fake = dict(mv=(0, 0), corre=False, mira=False, tiro=False, mouse=(W // 2 + 100, H // 2))
        shots = {}
        for f in range(4200):
            if f % 80 == 0:
                self.fake = dict(mv=(rnd.choice([-1, 0, 1]), rnd.choice([-1, 0, 1])), corre=rnd.random() < 0.3,
                                 mira=rnd.random() < 0.3, tiro=rnd.random() < 0.5,
                                 mouse=(rnd.randint(0, W), rnd.randint(0, H)))
            if f == 200:
                for a in ("machado", "pistola", "espingarda", "fuzil", "rifle", "silenciador", "silenciador"):
                    self.dar(a, 1)
                for k in ("9mm", "12", "556", "308"):
                    self.inv[k] = 200
                self.inv.update(tabua=60, sucata=30, ferramentas=2, comida=5, agua=5, kit=3, bandagem=3)
            if f % 300 == 0 and f >= 200:
                self.trocar_arma(self.armas[(f // 300) % len(self.armas)])
            if f == 900:  # teleporta para uma cidade
                c = m.cidades[0]
                self.teleportar(c["x"] * T + 40, c["y"] * T + 40)
            if f == 1000:
                self.estado = "jogo"
                shots["cidade_dia"] = self.foto()
            if f == 1100:  # dentro de uma casa e revista
                casa = next(b for b in m.construcoes if b["tipo"] == "casa" and b["cidade"])
                mv = next(mv for mv in m.moveis if mv.get("predio") is casa)
                self.teleportar(mv["x"], mv["y"] + (14 if mv["y"] % T < 16 else -14))
                self.fake["mv"] = (0, 0)
                self.interagir()
                print("acao revistar:", self.acao and self.acao["tipo"])
            if 1100 <= f < 1200:
                self.fake["mv"] = (0, 0)
                self.fake["tiro"] = False
            if f == 1199:
                shots["dentro_casa"] = self.foto()
            if f == 1300:  # constroi
                self.modo_construir = 1
                self.fake["mv"] = (0, 0)
                self.click = True
                self.fake["mouse"] = (W // 2 + 60, H // 2)
                self.cam = [self.p.x, self.p.y]
            if f == 1301:
                self.click = False
                print("construidos:", [c["tipo"] for c in self.construidos], "| msg:", self.msgs[-1][0])
                self.modo_construir = 2
                self.click = True
                self.fake["mouse"] = (W // 2 - 90, H // 2 + 30)
            if f == 1302:
                self.click = False
                print("construidos:", [c["tipo"] for c in self.construidos], "| msg:", self.msgs[-1][0])
            if f == 1500:  # hospital
                hosp = next(b for b in m.construcoes if b["tipo"] == "hospital")
                cama = next(c for c in m.camas if c.get("hospital") and hosp["x"] * T < c["x"] < (hosp["x"] + hosp["w"]) * T)
                self.teleportar(cama["x"], cama["y"] + 36)
                self.p.vida = 40
                self.zumbis = []
                self.fake["mv"] = (0, 0)
                self.interagir()
                print("acao hospital:", self.acao and self.acao["tipo"])
            if 1500 <= f < 1760:
                self.fake["mv"] = (0, 0)
                self.fake["tiro"] = False
            if f == 1759:
                print("vida depois do hospital:", round(self.p.vida))
                shots["hospital"] = self.foto()
            if f == 1800:  # floresta, de noite
                self.hora = 22.0
                for _ in range(500):
                    x = rnd.uniform(1000, N * T - 1000)
                    y = rnd.uniform(1000, N * T - 1000)
                    if m.tile_px(x, y) == MATO and not m.bloqueado(x, y, 14):
                        self.teleportar(x, y)
                        break
            if f == 2100:
                shots["noite_floresta"] = self.foto()
            if f == 2200:  # bunker militar
                self.hora = 11.0
                b = m.bunkers[0]
                cx_ = (b["x"] + 3) * T + 16
                cy_ = (b["y"] + 4) * T + 16
                self.teleportar(cx_, cy_)
                caixas = [mv for mv in m.moveis if mv.get("predio") is b and mv["tipo"] == "militar"]
                for mv in caixas:
                    self.acao = dict(tipo="movel", obj=mv, t=0, total=0, txt="")
                    self.terminar_acao()
                print("pecas:", self.inv.get("peca"), "revelados:", self.revelados)
            if f == 2300:
                shots["bunker"] = self.foto()
            if f == 2400:
                shots["mapa"] = self.foto_mapa()
            if f == 2600:  # capim alto ao meio-dia
                self.hora = 13.0
                for i, c in m.capim_g.items():
                    if not m.bloqueado(c[0] + 40, c[1], 14) and m.tile_px(c[0], c[1]) == GRAMA:
                        self.teleportar(c[0] + 40, c[1])
                        break
            if f == 2700:
                shots["capim"] = self.foto()
            if f == 3000:  # morte e renascer
                self.p.vida = -1
            if f == 3001:
                print("estado apos morrer:", self.estado)
                self.renascer()
                print("mochila criada:", any(mv["tipo"] == "mochila" for mv in m.moveis))
            if f == 3100:  # resgate
                self.inv["peca"] = 5
                tor = m.torre
                self.teleportar((tor["x"] + 4.5) * T, (tor["y"] + 7.5) * T)
                self.fake["mv"] = (0, 0)
                self.interagir()
                print("acao torre:", self.acao and self.acao["tipo"])
            if 3100 <= f < 3300:
                self.fake["mv"] = (0, 0)
            if f == 3400:
                print("resgate:", self.resgate, "zumbis:", len(self.zumbis))
                shots["horda"] = self.foto()
            if self.estado == "morto":
                self.p.vida = 100
                self.estado = "jogo"
            if f < 3000 or f > 3001:
                self.p.vida = max(self.p.vida, 60)
            if self.estado == "jogo":
                s = time.perf_counter()
                self.atualizar(1 / 60)
                self.desenhar()
                ms.append((time.perf_counter() - s) * 1000)
            if self.estado == "vitoria":
                print("venceu no quadro", f)
                break
        ms.sort()
        print(f"quadro: medio {sum(ms) / len(ms):.1f} ms, 95% {ms[int(len(ms) * .95)]:.1f} ms, max {ms[-1]:.1f} ms")
        print("zumbis derrubados:", self.mortes, "| no mapa agora:", len(self.zumbis))
        self.resgate = None
        self.heli = None
        self.estado = "jogo"
        self.salvar()
        antes = (round(self.p.x), round(self.p.y), self.dia, dict(self.inv), list(self.armas))
        self.carregar()
        depois = (round(self.p.x), round(self.p.y), self.dia, dict(self.inv), list(self.armas))
        print("salvar/carregar igual:", antes == depois)
        if antes != depois:
            print(antes, depois)
        pasta = os.path.join(HERE, "fotos_teste")
        os.makedirs(pasta, exist_ok=True)
        for nome, img in shots.items():
            pygame.image.save(img, os.path.join(pasta, nome + ".png"))
        self.estado = "menu"
        self.tela_menu(0.016)
        pygame.image.save(self.tela, os.path.join(pasta, "menu.png"))
        print("fotos salvas em", pasta)

    def teleportar(self, x, y):
        self.p.x = x
        self.p.y = y
        self.cam = [x, y]
        self.zumbis = []

    def foto(self):
        self.desenhar()
        return self.tela.copy()

    def foto_mapa(self):
        self.estado = "mapa"
        self.mapa_grande = None
        self.teclas = set()
        self.tela_mapa(0.016)
        self.estado = "jogo"
        return self.tela.copy()


def main():
    try:
        j = Jogo()
        if TESTE:
            j.teste()
            return
        j.rodar()
    except SystemExit:
        raise
    except Exception:
        import traceback
        with open(ERRO_FILE, "a", encoding="utf-8") as f:
            f.write("\n===== ERRO =====\n" + time.strftime("%Y-%m-%d %H:%M:%S\n") + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
