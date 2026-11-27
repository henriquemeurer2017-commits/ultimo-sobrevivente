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
        elif tipo == "cuspidor":
            self.hp = 90
            self.vel = rnd.uniform(55, 66)
            self.r = 12
            self.dano = 8
        elif tipo == "gritador":
            self.hp = 70
            self.vel = rnd.uniform(72, 86)
            self.r = 11
            self.dano = 6
        elif tipo == "bombeiro":
            self.hp = 260
            self.vel = rnd.uniform(40, 48)
            self.r = 14
            self.dano = 14
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
        self.mao = None        # "taco" ou "machado" na mao
        self.capacete = False
        self.colete = False


class Jogo:
    intro_cap2 = None  # tempo da cena da queda do helicoptero no comeco do capitulo 2 (None = sem cena)
    toque = False      # jogando no celular/tablet (liga sozinho no primeiro toque na tela)
    # botoes da tela de toque: (tecla, texto, x, y)
    BOTOES_TOQUE = [
        ("e", "Pegar", 1220, 318), ("r", "Recarr.", 1220, 384), ("roda", "Arma", 1220, 450), ("espaco", "Pular", 1220, 516),
        ("h", "Curar", 1152, 351), ("f", "Comer", 1152, 417), ("g", "Beber", 1152, 483),
        ("v", "Mochila", 560, 40), ("m", "Mapa", 626, 40), ("x", "Thor", 692, 40), ("z", "Recua", 758, 40),
        ("l", "Luz", 824, 40), ("b", "Constr.", 890, 40), ("esc", "Pausa", 956, 40),
    ]
    capitulo = 1       # 1 = o mundo normal; 2 = a DIMENSAO SOMBRIA (depois de zerar o 1)
    no_elevado = None  # linha do trem elevado onde voce esta (la em cima)
    no_trem = None     # dentro do trem elevado: distancia ate a frente do trem
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
                      "gigante": [G.sprite_zumbi(r, "gigante") for _ in range(2)],
                      "cuspidor": [G.sprite_zumbi(r, "cuspidor") for _ in range(3)],
                      "gritador": [G.sprite_zumbi(r, "gritador") for _ in range(3)],
                      "bombeiro": [G.sprite_zumbi(r, "bombeiro") for _ in range(3)]}
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
        self.spr_escada = G.sprite_escada()
        self.spr_cao = [G.sprite_cachorro(0), G.sprite_cachorro(1)]
        self.mascara_luneta = G.luneta_mascara(230)
        self.spr_muro = G.sprite_muro()
        self.spr_portao = G.sprite_portao(False)
        self.spr_portao_aberto = G.sprite_portao(True)
        self.spr_bau = G.sprite_bau()
        self.spr_arame = G.sprite_arame()
        self.spr_espinhos = G.sprite_espinhos()
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
        self.letras = ""
        self.recorde = self.ler_recorde()
        # o modo dono agora vale so por mundo; moedas de dono nao contam fora do mundo dele
        self.recorde.pop("dono", None)
        if self.recorde.get("moedas", 0) >= 999999:
            self.recorde["moedas"] = 0
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
        piloto = self.__dict__.get("piloto")
        if piloto and self.mundo is not None:
            piloto.quadro(dt)
        getattr(self, "tela_" + self.estado)(dt)
        if self.toque and self.estado in ("mochila", "mapa", "bau", "bancada"):  # celular: botao para fechar
            if self.botao_peq("Fechar", pygame.Rect(W - 150, H - 64, 130, 48), (90, 40, 34)):
                self.estado = "jogo"
        if piloto and self.mundo is not None and self.estado == "jogo":
            piloto.desenhar(self.tela, self.f_med, self.f_peq)
        pygame.display.flip()

    def iniciar_piloto(self):
        """Mundo novo so do piloto (nao mexe nos seus mundos) e o Claude joga sozinho."""
        import piloto as _pil
        self.arq = os.path.join(MUNDOS_DIR, "piloto_do_claude.json")
        self.nome_mundo = "Piloto do Claude"
        if os.path.exists(self.arq):  # continua de onde parou
            self.carregar(self.arq)
        else:
            self.novo_jogo()
        self.piloto = _pil.Piloto(self)

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
                # uma arma por vez: no navegador um "clique" da rodinha pode vir como 3 ou mais
                if e.y and time.time() - self.__dict__.get("t_roda", 0) > 0.12:
                    self.roda = 1 if e.y > 0 else -1
                    self.t_roda = time.time()
            elif e.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP) and not NAVEGADOR:
                self.toque_evento(e)
        if NAVEGADOR:  # no site os dedos vem direto da pagina (o navegador so transforma toque em clique)
            self.ler_toques_da_pagina()

    def ler_toques_da_pagina(self):
        try:
            import platform
            s = str(platform.window.toquesJSON)
        except Exception:
            return
        ant = self.__dict__.setdefault("toques_js", {})
        if s == "[]" and not ant:
            return
        try:
            atual = {int(i): (float(x), float(y)) for i, x, y in json.loads(s)}
        except Exception:
            return

        class Ev:
            def __init__(self, tipo, i, x, y):
                self.type, self.finger_id, self.touch_id, self.x, self.y = tipo, i, 9, x, y
        for i, (x, y) in atual.items():
            if i not in ant:
                self.toque_evento(Ev(pygame.FINGERDOWN, i, x, y))
            elif ant[i] != (x, y):
                self.toque_evento(Ev(pygame.FINGERMOTION, i, x, y))
        for i, (x, y) in ant.items():
            if i not in atual:
                self.toque_evento(Ev(pygame.FINGERUP, i, x, y))
        self.toques_js = atual

    def toque_evento(self, e):
        """Celular: dedo do lado esquerdo = joystick; do lado direito = mira e atira; botoes redondos = teclas."""
        self.toque = True
        dedos = self.__dict__.setdefault("dedos", {})
        x, y = e.x * W, e.y * H
        fid = (getattr(e, "touch_id", 0), e.finger_id)
        if e.type == pygame.FINGERUP:
            dedos.pop(fid, None)
            return
        if e.type == pygame.FINGERMOTION:
            if fid in dedos:
                dedos[fid]["x"], dedos[fid]["y"] = x, y
            return
        if self.estado != "jogo":  # nos menus o toque funciona como clique do mouse
            return
        for tecla, _txt, bx, by in self.BOTOES_TOQUE:
            if (x - bx) ** 2 + (y - by) ** 2 < 32 ** 2:
                dedos[fid] = dict(papel="botao", x=x, y=y)
                if tecla == "roda":
                    self.roda = -1
                else:
                    k = {"espaco": pygame.K_SPACE, "esc": pygame.K_ESCAPE}.get(tecla) or getattr(pygame, "K_" + tecla)
                    self.teclas.add(k)
                return
        if x < W * 0.42 and y > H * 0.28:
            dedos[fid] = dict(papel="joy", x0=x, y0=y, x=x, y=y)
        else:
            dedos[fid] = dict(papel="mira", x=x, y=y)
            self.click = True  # tocar no mundo tambem serve de clique (ex.: colocar construcao)

    def sair(self):
        if self.mundo is not None and self.estado in ("jogo", "pausa", "mapa", "construir"):
            self.salvar()
        if NAVEGADOR:
            # no site: sai da tela cheia e fecha a janela (sem ficar aquela tela cinza travada)
            try:
                import platform
                platform.window.sairDoJogo()
            except Exception:
                pass
            self.mundo = None
            self.estado = "menu"
            return
        pygame.quit()
        sys.exit(0)

    # ================================================================ menus
    def criar_fundo_menu(self):
        """Fundo da tela de inicio: cidade destruida pegando fogo, de noite."""
        r = random.Random(7)
        # ceu: roxo escuro em cima, laranja do fogo perto do horizonte
        yy = np.linspace(0, 1, H, dtype=np.float32)[None, :, None]
        topo = np.array([8, 8, 22], np.float32)
        meio = np.array([40, 18, 40], np.float32)
        baixo = np.array([150, 60, 30], np.float32)
        k1 = np.clip(yy / 0.55, 0, 1)
        k2 = np.clip((yy - 0.55) / 0.25, 0, 1)
        ceu = topo + (meio - topo) * k1
        ceu = ceu + (baixo - ceu) * k2
        arr = np.repeat(ceu, W, axis=0)
        # brilho do incendio no horizonte
        xx = np.linspace(0, 1, W, dtype=np.float32)[:, None]
        for cx, forca in ((0.22, 1.0), (0.63, 0.8), (0.88, 0.6)):
            d = np.sqrt(((xx - cx) * 2.2) ** 2 + ((yy[0, :, 0][None, :] - 0.74) * 3.5) ** 2)
            arr += (np.clip(1 - d, 0, 1) ** 2 * forca)[:, :, None] * np.array([120, 50, 10], np.float32)
        s = pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8))
        # estrelas
        for _ in range(140):
            x, y = r.randint(0, W), r.randint(0, int(H * 0.45))
            c = r.randint(120, 230)
            s.set_at((x, y), (c, c, min(255, c + 20)))
        # lua com brilho
        for k in range(10):
            pygame.draw.circle(s, G.mistura((26, 20, 40), (90, 80, 90), (k + 1) / 12), (1080, 120), 110 - k * 6)
        pygame.draw.circle(s, (232, 226, 205), (1080, 120), 48)
        pygame.draw.circle(s, (210, 204, 182), (1066, 108), 9)
        pygame.draw.circle(s, (214, 208, 186), (1095, 136), 6)
        pygame.draw.circle(s, (205, 200, 178), (1090, 100), 4)
        # nuvens de fumaca escura
        fum = pygame.Surface((W, H), pygame.SRCALPHA)
        for _ in range(40):
            x, y = r.randint(-100, W), r.randint(150, 420)
            pygame.draw.ellipse(fum, (20, 14, 18, r.randint(25, 60)), (x, y, r.randint(160, 360), r.randint(40, 90)))
        s.blit(fum, (0, 0))
        # cidade destruida (duas camadas de predios)
        for cor, base, alt, luz in (((34, 22, 30), 520, 260, 0.05), ((16, 11, 16), 560, 200, 0.12)):
            x = -20
            while x < W + 20:
                larg = r.randint(50, 120)
                h = r.randint(alt // 3, alt)
                topo_y = base - h
                pts = [(x, base + 200), (x, topo_y)]
                # topo quebrado
                for k in range(1, 5):
                    pts.append((x + larg * k / 5, topo_y + r.randint(-6, 26)))
                pts += [(x + larg, topo_y + r.randint(0, 30)), (x + larg, base + 200)]
                pygame.draw.polygon(s, cor, pts)
                if r.random() < 0.25:  # antena
                    pygame.draw.line(s, cor, (x + larg // 2, topo_y), (x + larg // 2, topo_y - r.randint(20, 50)), 2)
                for wy in range(topo_y + 28, base, 18):  # janelas
                    for wx in range(x + 8, x + larg - 8, 14):
                        if r.random() < luz:
                            pygame.draw.rect(s, r.choice([(255, 200, 90), (240, 160, 60), (200, 220, 255)]), (wx, wy, 5, 7))
                x += larg + r.randint(-10, 12)
        # mato e chao na frente
        for x in range(-20, W + 40, 18):
            h = r.randint(30, 90)
            pygame.draw.polygon(s, (8, 8, 10), [(x - 14, 600), (x, 600 - h), (x + 14, 600)])
        pygame.draw.rect(s, (8, 8, 10), (0, 596, W, H))
        # carro abandonado na frente
        pygame.draw.rect(s, (12, 12, 14), (140, 560, 170, 46), border_radius=12)
        pygame.draw.rect(s, (12, 12, 14), (180, 532, 96, 40), border_radius=10)
        pygame.draw.circle(s, (4, 4, 6), (180, 606), 18)
        pygame.draw.circle(s, (4, 4, 6), (276, 606), 18)
        # brilho de fogo pronto (para piscar)
        self.fogo_menu = []
        for cx, cy, R in ((280, 470, 150), (800, 500, 120), (1120, 520, 100)):
            yy2, xx2 = np.mgrid[0:R * 2, 0:R * 2]
            d = np.sqrt((xx2 - R + 0.5) ** 2 + (yy2 - R + 0.5) ** 2) / R
            forca = np.clip(1 - d, 0, 1) ** 1.6
            niveis = []
            for n in range(8):  # varias intensidades prontas: o fogo pisca trocando entre elas
                k = 0.35 + 0.65 * n / 7
                rgb = (forca[:, :, None] * np.array([170, 75, 18], np.float32) * k).transpose(1, 0, 2)
                niveis.append(pygame.surfarray.make_surface(rgb.astype(np.uint8)))
            self.fogo_menu.append((niveis, cx, cy))
        self.brasas = [[r.uniform(0, W), r.uniform(0, H), r.uniform(10, 40), r.uniform(0, 6)] for _ in range(60)]
        self.fumaca_menu = [[r.choice((280, 800, 1120)) + r.uniform(-40, 40), r.uniform(300, 520), r.uniform(10, 30)]
                            for _ in range(24)]
        self.zumbis_menu = [[r.uniform(-200, W), r.uniform(14, 26), r.uniform(0.8, 1.15), r.uniform(0, 6)] for _ in range(5)]
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
        t = self.t_menu
        tela = self.tela
        tela.blit(self.fundo_menu, (0, 0))
        # incendios piscando
        for i, (niveis, cx, cy) in enumerate(self.fogo_menu):
            k = 0.5 + 0.5 * math.sin(t * 7 + i * 2) * math.sin(t * 3.1 + i)
            fogo = niveis[min(7, max(0, int(k * 8)))]
            tela.blit(fogo, (cx - fogo.get_width() // 2, cy - fogo.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
            # chamas
            for n in range(7):
                fx = cx - 48 + n * 16
                alt = 34 + 22 * math.sin(t * 9 + n * 1.7 + i) + 10 * math.sin(t * 4.3 + n)
                base_y = cy + 46
                for cor, esc in (((230, 70, 20), 1.0), ((255, 150, 40), 0.7), ((255, 225, 120), 0.4)):
                    h = alt * esc
                    pygame.draw.polygon(tela, cor, [(fx - 9 * esc, base_y), (fx + math.sin(t * 6 + n) * 4, base_y - h),
                                                    (fx + 9 * esc, base_y)])
        # fumaca subindo dos incendios
        for f in self.fumaca_menu:
            f[1] -= f[2] * dt
            if f[1] < 120:
                f[1] = 540
            a = int(70 * min(1, (f[1] - 120) / 300))
            rr = int(30 + (540 - f[1]) * 0.15)
            sup = self.__dict__.setdefault("bola_fumaca", {})
            if rr not in sup:
                b = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
                pygame.draw.circle(b, (30, 24, 28, 255), (rr, rr), rr)
                sup[rr] = b
            b = sup[rr]
            b.set_alpha(a)
            tela.blit(b, (f[0] + math.sin(t + f[1] * 0.02) * 20 - rr, f[1] - rr))
        # zumbis andando na frente (silhuetas)
        for z in self.zumbis_menu:
            z[0] += z[1] * dt
            if z[0] > W + 80:
                z[0] = -80
            e = z[2]
            x, y = z[0], 596
            passo = math.sin(t * 3 + z[3])
            cor = (6, 6, 8)
            pygame.draw.line(tela, cor, (x, y - 34 * e), (x - 9 * e * passo, y), int(6 * e))
            pygame.draw.line(tela, cor, (x, y - 34 * e), (x + 9 * e * passo, y), int(6 * e))
            pygame.draw.ellipse(tela, cor, (x - 9 * e, y - 72 * e, 18 * e, 42 * e))
            pygame.draw.circle(tela, cor, (int(x + 3 * e), int(y - 80 * e)), int(9 * e))
            pygame.draw.line(tela, cor, (x, y - 62 * e), (x + 26 * e, y - 60 * e + 3 * passo), int(5 * e))
            pygame.draw.line(tela, cor, (x, y - 56 * e), (x + 24 * e, y - 52 * e - 3 * passo), int(5 * e))
        # brasas subindo
        for b in self.brasas:
            b[1] -= b[2] * dt
            b[0] += math.sin(t * 1.5 + b[3]) * 10 * dt
            if b[1] < 0:
                b[1] = H
                b[0] = random.uniform(0, W)
            brilho = 180 + int(70 * math.sin(t * 6 + b[3]))
            tela.fill((255, brilho // 2 + 60, 40), (int(b[0]), int(b[1]), 2, 2))
        # neblina no chao
        nevoa = pygame.Surface((W, 200), pygame.SRCALPHA)
        for i in range(8):
            x = (i * 260 + t * (12 + i * 3)) % (W + 400) - 200
            pygame.draw.ellipse(nevoa, (170, 150, 150, 16), (x, 60 + (i % 3) * 30, 420, 90))
        tela.blit(nevoa, (0, 480))
        tela.blit(self.vinheta, (0, 0))

    def titulo_menu(self, y=140):
        """Titulo grande com contorno escuro e brilho vermelho."""
        img = self.__dict__.get("img_titulo")
        if img is None:
            fonte = self.f_titulo
            letra = fonte.render("ÚLTIMO SOBREVIVENTE", True, (235, 70, 50))
            borda = fonte.render("ÚLTIMO SOBREVIVENTE", True, (20, 4, 4))
            img = pygame.Surface((letra.get_width() + 12, letra.get_height() + 12), pygame.SRCALPHA)
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx * dx + dy * dy <= 10:
                        img.blit(borda, (6 + dx, 6 + dy))
            img.blit(letra, (6, 6))
            self.img_titulo = img
            mask = pygame.mask.from_surface(letra, 20)
            sil = mask.to_surface(setcolor=(255, 60, 30, 255), unsetcolor=(255, 60, 30, 0))
            base = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            base.blit(sil, (6, 6))
            brilho = pygame.transform.smoothscale(base, (img.get_width() // 8, img.get_height() // 8))
            self.img_titulo_brilho = pygame.transform.smoothscale(brilho, img.get_size())
        k = 0.6 + 0.4 * math.sin(self.t_menu * 2)
        b = self.img_titulo_brilho
        b.set_alpha(int(150 * k))
        r = img.get_rect(center=(W // 2, y))
        self.tela.blit(b, r.move(0, 2))
        self.tela.blit(img, r)

    def nick(self):
        return (self.recorde.get("nick") or "").strip()

    def tela_nome(self, dt):
        """Tela de colocar o nome (nickname). Aparece na primeira vez que a pessoa entra no jogo."""
        self.desenhar_fundo_menu(dt)
        self.titulo_menu(120)
        txt = self.__dict__.get("nick_txt")
        if txt is None:
            txt = self.nick_txt = self.nick()
        if pygame.K_BACKSPACE in self.teclas:
            txt = txt[:-1]
        elif self.letras and pygame.K_RETURN not in self.teclas:
            txt = (txt + "".join(c for c in self.letras if c.isprintable()))[:16]
        self.nick_txt = txt
        self.texto("COLOQUE SEU NOME", (W // 2, 250), self.f_grande, (255, 220, 140), centro=True)
        self.texto("Ele vai aparecer em cima do seu personagem e quando você zerar o jogo.", (W // 2, 296),
                   self.f_peq, (210, 200, 190), centro=True)
        campo = pygame.Rect(W // 2 - 260, 330, 520, 64)
        pygame.draw.rect(self.tela, (20, 18, 18), campo, border_radius=10)
        pygame.draw.rect(self.tela, (220, 170, 90), campo, 3, border_radius=10)
        pisca = "|" if int(time.time() * 2) % 2 == 0 else " "
        self.texto((txt or "") + pisca if txt or not self.toque else "toque aqui para escrever",
                   (campo.centerx, campo.y + 14), self.f_med2, (245, 240, 230) if txt else (140, 130, 120), centro=True)
        # celular: tocar na caixa abre o teclado do celular
        if self.click and campo.collidepoint(pygame.mouse.get_pos()) and NAVEGADOR:
            try:
                import platform
                r = platform.window.prompt("Coloque seu nome:", txt or "")
                if r is not None and str(r) not in ("null", "undefined"):
                    self.nick_txt = txt = str(r).strip()[:16]
            except Exception:
                pass
        pronto = self.botao("Pronto!", W // 2, 420, w=260, ativo=bool(txt.strip()))
        if (pronto or pygame.K_RETURN in self.teclas) and txt.strip():
            self.recorde["nick"] = txt.strip()
            self.gravar_recorde()
            self.nick_txt = None
            self.estado = "menu"
            return
        if self.nick() and self.botao("Voltar", W // 2, 490, w=260):
            self.nick_txt = None
            self.estado = "menu"

    def tela_menu(self, dt):
        if not self.nick() and "--teste" not in sys.argv:  # primeira vez: coloca o nome
            self.estado = "nome"
            return
        self.desenhar_fundo_menu(dt)
        self.titulo_menu(140)
        self.texto(f"Olá, {self.nick()}!", (W // 2, 248), self.f_med, (140, 230, 150), centro=True)
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
        if self.botao("Trocar meu nome", W // 2, y):
            self.nick_txt = self.nick()
            self.estado = "nome"
            return
        y += 64
        if self.botao("Sair", W // 2, y):
            self.sair()
        rec = self.recorde
        if NAVEGADOR:
            try:
                import platform
                qtd = platform.window.jogadoresTotal
                agora = int(platform.window.jogandoAgora or 1)
                if qtd:
                    self.texto(f"{int(qtd)} pessoas já jogaram   ·   {agora} jogando agora", (W // 2, H - 72),
                               self.f_med2, (255, 210, 120), centro=True)
                    pygame.draw.circle(self.tela, (60, 230, 90), (W // 2 + self.f_med2.size(
                        f"{int(qtd)} pessoas já jogaram   ·   {agora} jogando agora")[0] // 2 + 16, H - 58), 6)
            except Exception:
                pass
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
        caixa = pygame.Rect(W // 2 - 380, 100, 760, 336)
        self.painel(caixa, 200)
        if not mundos:
            self.texto("Você ainda não tem nenhum mundo. Crie um aí embaixo!", (W // 2, caixa.centery), self.f_med2,
                       (210, 200, 190), centro=True)
        mouse = pygame.mouse.get_pos()
        for i, (arq, nome, dia, mortes, _) in enumerate(mundos[:5]):
            r = pygame.Rect(caixa.x + 16, caixa.y + 14 + i * 64, caixa.w - 32, 56)
            pygame.draw.rect(self.tela, (52, 40, 34) if r.collidepoint(mouse) else (34, 30, 28), r, border_radius=10)
            G.desenha_icone(self.tela, "mochila3", r.x + 30, r.centery, 1.3)
            self.texto(nome if len(nome) <= 34 else nome[:33] + "…", (r.x + 60, r.y + 6), self.f_med, (240, 225, 200))
            self.texto(f"Dia {dia}   ·   {mortes} zumbis derrubados", (r.x + 60, r.y + 31), self.f_peq, (190, 180, 170))
            if self.botao_peq("Jogar", pygame.Rect(r.right - 230, r.y + 10, 110, 36), (60, 90, 50)):
                self.comecar_carga(self.carregar_passos(arq))
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
        if len(mundos) > 5:
            self.texto(f"(+{len(mundos) - 5} mundos mais antigos)", (W // 2, caixa.bottom - 16), self.f_peq,
                       (170, 160, 150), centro=True)
        # mundo novo com nome
        nome = self.__dict__.get("nome_novo", "")
        if pygame.K_BACKSPACE in self.teclas:
            nome = nome[:-1]
        elif self.letras and pygame.K_RETURN not in self.teclas:
            nome = (nome + self.letras)[:200]
        self.nome_novo = nome
        self.texto("MUNDO NOVO  ·  escreva o nome dele:", (W // 2 - 380, 446), self.f_med, (255, 220, 140))
        # campo grande: cabem 3 linhas de nome
        campo = pygame.Rect(W // 2 - 380, 476, 500, 116)
        pygame.draw.rect(self.tela, (20, 18, 18), campo, border_radius=8)
        pygame.draw.rect(self.tela, (200, 150, 90), campo, 2, border_radius=8)
        pisca = "|" if int(time.time() * 2) % 2 == 0 else ""
        txt = nome + pisca if nome else "ex.: Mundo do Leandro" + pisca
        linhas, atual = [], ""
        for palavra in txt.split(" "):
            teste = (atual + " " + palavra).strip() if atual else palavra
            while self.f_med2.size(teste)[0] > campo.w - 28 and len(teste) > 1:
                if not atual:  # palavra comprida demais: corta no meio
                    corte = len(teste) - 1
                    while corte > 1 and self.f_med2.size(teste[:corte])[0] > campo.w - 28:
                        corte -= 1
                    linhas.append(teste[:corte])
                    teste = teste[corte:]
                else:
                    linhas.append(atual)
                    atual = ""
                    teste = palavra
            atual = teste
        linhas.append(atual)
        if len(linhas) > 3:  # passou de 3 linhas: nao deixa escrever mais
            self.nome_novo = nome = nome[:-1] if nome else nome
            linhas = linhas[:3]
        for k, ln in enumerate(linhas[:3]):
            self.texto(ln, (campo.x + 14, campo.y + 8 + k * 34), self.f_med2, (240, 235, 225) if nome else (120, 115, 110))
        escolha = self.__dict__.get("dif_novo", "medio")
        self.texto("Dificuldade:", (campo.right + 12, campo.y - 2), self.f_peq, (220, 210, 190))
        for k, (id_d, d_) in enumerate(DIFICULDADES.items()):
            r = pygame.Rect(campo.right + 12 + k * 84, campo.y + 20, 80, 32)
            if self.botao_peq(d_["nome"], r, (90, 70, 30) if escolha == id_d else (44, 40, 38)):
                self.dif_novo = escolha = id_d
            if escolha == id_d:
                pygame.draw.rect(self.tela, d_["cor"], r, 2, border_radius=7)
        criar = self.botao_peq("Criar mundo", pygame.Rect(campo.right + 12, campo.y + 62, 248, 46), (60, 90, 50))
        if criar or (pygame.K_RETURN in self.teclas):
            nome_final = nome.strip() or f"Mundo {len(mundos) + 1}"
            self.arq = self.arquivo_novo()
            self.nome_mundo = nome_final

            def criar():
                yield from self.novo_jogo_passos()
                self.dificuldade = escolha
                self.msg(f"Dificuldade: {DIFICULDADES[escolha]['nome']}", DIFICULDADES[escolha]["cor"])
                self.salvar()
            self.comecar_carga(criar())
            return
        if self.botao("Voltar", W // 2, 620, w=220):
            self.estado = "menu"

    def comecar_carga(self, passos):
        self.ger_carga = passos
        self.txt_carga = "Preparando..."
        self.t_carga = 0.0
        self.estado = "carregando"

    def tela_carregando(self, dt):
        """Monta o mundo um passo por quadro, mostrando o progresso (o navegador nao trava)."""
        self.desenhar_fundo_menu(dt)
        self.t_carga = self.__dict__.get("t_carga", 0.0) + dt
        self.titulo_menu(200)
        caixa = pygame.Rect(W // 2 - 300, 300, 600, 120)
        self.painel(caixa, 200)
        self.texto(self.__dict__.get("txt_carga", "Preparando..."), (W // 2, 336), self.f_med2, (240, 225, 200), centro=True)
        pontos = "." * (1 + int(self.t_carga * 3) % 3)
        self.texto("Carregando o mundo" + pontos, (W // 2, 378), self.f_med, (255, 200, 120), centro=True)
        ger = self.__dict__.get("ger_carga")
        if ger is None:
            self.estado = "menu"
            return
        try:
            next(ger)
        except StopIteration:
            self.ger_carga = None
            if self.estado == "carregando":
                self.estado = "jogo"
        except Exception:
            import traceback
            try:
                with open(ERRO_FILE, "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
            except Exception:
                pass
            print(traceback.format_exc())
            self.ger_carga = None
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
            "Botão direito: mirar  ·  R: recarregar  ·  1 a 0: armas  ·  Q: guardar a arma  ·  ESPAÇO: esquiva  ·  C: agachar",
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
        for _ in self.preparar_passos(seed):
            pass

    def preparar_passos(self, seed):
        m = Mundo.__new__(Mundo)
        for txt in m.gerar(seed):
            self.txt_carga = txt
            yield txt
        self.mundo = m
        self.n_itens_base = len(self.mundo.itens_chao)
        self.n_moveis_base = len(self.mundo.moveis)
        self.cache_chao = OrderedDict()
        self.cache_copa = OrderedDict()
        self.telhados = {}
        self.alfa_telhado = {}
        self.zumbis = []
        self.particulas = []
        self.rastros = []
        self.acidos = []     # cuspes de acido voando: [x, y, vx, vy, t]
        self.pocas = []      # pocas de acido no chao: [x, y, t]
        self.ondas = []      # grito do gritador: [x, y, t]
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
        self.telhado_b = None   # predio em cujo telhado voce esta
        self.metro = None       # estacao de metro onde voce esta (debaixo da terra)
        self.dirigindo = None   # carro que voce esta dirigindo
        self.dificuldade = "medio"
        self.nivel_lanterna = 0
        self.cao = None         # o cachorro: {x, y, amigo, ang, t_mordida, t_latido, au}
        self.vel_carro = 0.0
        self.colete = 0.0
        self.capacete = 0.0
        self.calca = 0.0
        self.luneta = False
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
        for _ in self.novo_jogo_passos(seed):
            pass

    def novo_jogo_passos(self, seed=None, tamanho=None):
        definir_tamanho(tamanho or N_CAP1)
        seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        yield from self.preparar_passos(seed)
        m = self.mundo
        self.capitulo = 1
        self.radio_consertado = False
        self.embarcou = False
        self.thor_junto = False
        self.no_elevado = None
        self.no_trem = None
        self.resgate = None
        self.heli = None
        self.p = Jogador(*m.inicio)
        self.respawn = list(m.inicio)
        self.inv = {"comida": 1, "agua": 1, "bandagem": 1}
        self.moedas = self.recorde.get("moedas", 0)
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
        self.criar_cachorro()
        self.msg("Você acordou sozinho. O mundo acabou.", (240, 220, 200))
        self.msg("Revista as casas (E). Ache água, comida e armas.", (200, 220, 240))
        self.msg("No seu bolso: um bilhete com a posição de um bunker militar (M).", (200, 240, 200))
        self.salvar()

    def salvar(self):
        if self.mundo is None or getattr(self, "p", None) is None:
            return
        if not self.dono and self.recorde.get("moedas") != self.moedas:  # moedas valem para todos os mundos
            self.recorde["moedas"] = self.moedas
            self.gravar_recorde()
        m = self.mundo
        extras = [dict(x=mv["x"], y=mv["y"], tipo=mv["tipo"], itens=mv["itens"], aberto=mv["aberto"])
                  for mv in m.moveis[self.n_moveis_base:] if mv["tipo"] == "mochila" and not mv["aberto"]]
        dados = dict(
            versao=1, tam=N, seed=m.seed,
            x=self.telhado_b["escada"]["fora"][0] if self.telhado_b else
            self.mundo.metros[self.metro]["ent"][0] if self.metro is not None else self.p.x,
            y=self.telhado_b["escada"]["fora"][1] if self.telhado_b else
            self.mundo.metros[self.metro]["ent"][1] + 70 if self.metro is not None else self.p.y, vida=self.p.vida, fome=self.p.fome, sede=self.p.sede,
            inv=self.inv, armas=self.armas, pente=self.pente, silen=self.silen, arma=self.arma, hora=self.hora,
            dia=self.dia, mortes=self.mortes, vezes_morto=self.vezes_morto, revelados=self.revelados,
            respawn=self.respawn, abertos=[mv["id"] for mv in m.moveis[:self.n_moveis_base] if mv["aberto"]],
            pegos=[it["id"] for it in m.itens_chao[:self.n_itens_base] if it.get("pego")],
            cortadas=self.cortadas, construidos=self.construidos, mochilas=extras,
            explorado=self.explorado.hex(), lanterna=self.lanterna, nivel_mochila=self.nivel_mochila,
            feridas=[self.p.sangrando, self.p.perna, self.p.braco],
            niveis=self.niveis, miras=self.miras, reforco_mochila=self.reforco_mochila,
            colete=self.colete, capacete=self.capacete, radio_consertado=self.__dict__.get("radio_consertado", False), calca=self.calca, nivel_lanterna=self.nivel_lanterna,
            dificuldade=self.dificuldade, capitulo=self.capitulo,
            cao=dict(x=self.cao["x"], y=self.cao["y"], amigo=self.cao["amigo"], vida=self.cao.get("vida", 100),
                     fome=self.cao.get("fome", 100), sede=self.cao.get("sede", 100),
                     morto=self.cao.get("morto", False), sentado=self.cao.get("sentado", False)) if self.cao else None,
            carros=[[i, round(c["x"], 1), round(c["y"], 1), round(c["ang"], 1), c.get("gas", 0)]
                    for i, c in enumerate(m.carros) if c.get("mexeu")],
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
        for _ in self.carregar_passos(arq):
            pass

    def carregar_passos(self, arq=None):
        if arq:
            self.arq = arq
        try:
            with open(self.caminho_save(), encoding="utf-8") as f:
                d = json.load(f)
            self.nome_mundo = d.get("nome", "Meu mundo")
        except Exception:
            self.msg("Save estragado, começando de novo.")
            yield from self.novo_jogo_passos()
            return
        definir_tamanho(N_CAP2 if d.get("capitulo", 1) == 2 else N_CAP1)
        yield from self.preparar_passos(d["seed"])
        m = self.mundo
        cresceu = d.get("tam", 512) != N
        if cresceu:
            # o mundo ficou maior: voce comeca no comeco do mapa novo, mas leva suas coisas
            d["x"], d["y"] = m.inicio
            d["respawn"] = list(m.inicio)
            for k_ in ("abertos", "pegos", "cortadas", "construidos", "mochilas"):
                d[k_] = []
            d["revelados"] = [0] if m.bunkers else []
            d["explorado"] = ""
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
        self.colete = d.get("colete", 0.0)
        self.radio_consertado = d.get("radio_consertado", False)
        self.nivel_lanterna = d.get("nivel_lanterna", 1)
        if d.get("cao"):
            self.cao = dict(d["cao"], ang=0.0, t_mordida=0.0, t_latido=0.0, au=0.0, t_aviso=0.0, passo=0.0)
            if self.cao["amigo"]:
                self.cao["x"], self.cao["y"] = self.p.x + 40, self.p.y + 30
        else:
            self.criar_cachorro()
        for i, x_, y_, a_, g_ in d.get("carros", []):
            if i < len(m.carros):
                self.estacionar(m.carros[i], x_, y_, a_, g_, tirar=True)
        self.capacete = d.get("capacete", 0.0)
        self.calca = d.get("calca", 0.0)
        self.dificuldade = d.get("dificuldade", "medio")
        self.capitulo = d.get("capitulo", 1)
        if self.capitulo == 2:
            self.fechar_portas_metro()
        self.miras = d.get("miras", [])
        self.reforco_mochila = d.get("reforco_mochila", 0)
        self.dono = d.get("dono", False)  # o modo dono vale so neste mundo
        self.moedas = d.get("moedas", 0) if self.dono else self.recorde.get("moedas", d.get("moedas", 0))
        self.mochila_infinita = d.get("mochila_infinita", False)
        self.p.sangrando, self.p.perna, self.p.braco = d.get("feridas", [False, False, False])
        self.armas = sorted(d["armas"], key=ordem_arma)
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
        if cresceu:
            self.msg("O MUNDO FICOU MAIOR! Mais cidades, a CIDADE GRANDE e o SHOPPING. Suas coisas vieram com você.",
                     (255, 220, 120))
            self.salvar()

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
                # voce ja tem essa arma: tira as balas dela, mas a arma FICA no lugar (vazia), se um dia precisar
                if q > 0 and not a["melee"]:
                    self.inv[a["mun"]] = self.inv.get(a["mun"], 0) + max(3, a["pente"] // 2)
                    if avisar:
                        self.msg(f"Outra {a['nome']}: tirou a munição dela (+{max(3, a['pente'] // 2)}). "
                                 f"A arma ficou aí, se precisar.", (230, 220, 160))
                elif q > 0 and avisar:
                    self.msg(f"Você já tem {a['nome']}: ela ficou aí guardada.", (230, 220, 160))
                return -1  # -1 = arma vazia que ficou no lugar
            self.armas.append(item)
            self.armas.sort(key=ordem_arma)
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
        if item in ("colete", "capacete", "calca"):
            atual = getattr(self, item)
            if atual >= 100:
                if avisar:
                    self.msg(f"Achou um(a) {ITENS[item].lower()}, mas o seu ainda está novo.", (190, 185, 175))
                return 0
            setattr(self, item, 100.0)
            self.msg(f"Vestiu: {ITENS[item]}! Mais proteção contra os zumbis.", (170, 220, 255))
            return 0
        if item.startswith("lanterna") and item[8:].isdigit():
            n = int(item[8:])
            if n > self.nivel_lanterna:
                self.nivel_lanterna = n
                self.msg(f"Lanterna nova: {LANTERNAS[n][0]}! A luz vai mais longe.", (255, 240, 150))
            elif avisar:
                self.msg(f"Achou uma {LANTERNAS[n][0]}, mas a sua é igual ou melhor.", (190, 185, 175))
            return 0
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

    def zumbi_no_mouse(self, pos):
        """Tem zumbi bem embaixo da setinha? Entao o clique e tiro, mesmo em cima da barra."""
        wx = pos[0] + self.cam[0] - W / 2
        wy = pos[1] + self.cam[1] - H / 2
        return any((z.x - wx) ** 2 + (z.y - wy) ** 2 < (z.r + 22) ** 2 for z in self.zumbis)

    def mouse_no_hud(self, pos):
        if self.estado == "jogo" and self.zumbi_no_mouse(pos):
            return False
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
        if self.zumbi_no_mouse(pos):
            return False
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
        if self.capacete > 0 and random.random() < 0.6:  # o capacete protegeu
            self.capacete = max(0.0, self.capacete - 8)
            if self.capacete <= 0:
                self.msg("Seu CAPACETE quebrou!", (255, 170, 120))
            return
        r = random.random()
        if r < 0.2 and not p.sangrando:
            p.sangrando = True
            self.msg("Você foi mordido e está SANGRANDO! Use uma bandagem (H).", (255, 110, 100))
        elif r < 0.26:
            if random.random() < 0.5 and not p.perna:
                if self.calca > 0 and random.random() < 0.85:  # a calca protegeu a perna
                    return
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
                 "galao": "Abastecer",
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
        yc = 592
        self.texto("CONSTRUIR  (passe o mouse para ver o preço)", (450, yc - 4), self.f_med, (255, 220, 140))
        curto = {"tabua": "tábuas", "sucata": "sucata", "ferramentas": "ferram."}
        nomes_curtos = {"abrigo": "Bunker", "arame": "Arame", "ponte": "Ponte"}
        mouse = pygame.mouse.get_pos()
        dica = None
        for i, rec in enumerate(RECEITAS):
            pode = all(self.inv.get(k, 0) >= q for k, q in rec["custo"].items())
            r = pygame.Rect(450 + (i % 5) * 158, yc + 22 + (i // 5) * 38, 152, 33)
            if r.collidepoint(mouse):
                dica = (rec["nome"] + ": " + ", ".join(f"{q} {curto.get(k, k)}" for k, q in rec["custo"].items()), pode)
            if self.botao_peq(nomes_curtos.get(rec["id"], rec["nome"]), r, (40, 60, 40), pode):
                self.estado = "jogo"
                self.modo_construir = i
                self.msg("Clique no chão para colocar. B ou ESC cancela.", (200, 230, 255))
                return
        if dica:
            self.texto(dica[0], (450, 128), self.f_peq, (200, 230, 180) if dica[1] else (230, 160, 150))
        if self.botao_peq("Fechar (V)", pygame.Rect(1130, 40, 104, 36)):
            self.estado = "jogo"

    # ================================================================ bau da base
    def tela_bau(self, dt):
        tc = self.teclas
        bau = self.__dict__.get("bau_atual")
        if bau is None or pygame.K_ESCAPE in tc or pygame.K_e in tc:
            self.estado = "jogo"
            return
        self.desenhar()
        tela = self.tela
        sh = pygame.Surface((W, H), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 180))
        tela.blit(sh, (0, 0))
        guardar = [k for k in ITENS if k in ESPACO and self.inv.get(k, 0) > 0]
        dentro = [k for k in ITENS if bau["itens"].get(k, 0) > 0]
        for lado, (titulo, lista, x0) in enumerate((("SUA MOCHILA", guardar, 60), ("BAÚ DA BASE", dentro, 660))):
            caixa = pygame.Rect(x0, 30, 560, 620)
            self.painel(caixa, 225)
            self.texto(titulo, (x0 + 20, 42), self.f_grande, (255, 220, 140))
            if not lista:
                self.texto("vazio", (x0 + 24, 110), self.f_med2, (160, 150, 140))
            for i, it in enumerate(lista[:16]):
                r = pygame.Rect(x0 + 16, 96 + i * 34, 528, 30)
                pygame.draw.rect(tela, (34, 36, 40), r, border_radius=6)
                G.desenha_icone(tela, it, r.x + 18, r.centery, 0.9)
                q = self.inv.get(it, 0) if lado == 0 else bau["itens"][it]
                self.texto(f"{ITENS[it]}   x{q}", (r.x + 40, r.y + 5), self.f_peq)
                if lado == 0:
                    if self.botao_peq("Guardar", pygame.Rect(r.right - 96, r.y + 2, 90, 26), (40, 60, 40)):
                        bau["itens"][it] = bau["itens"].get(it, 0) + self.inv[it]
                        self.inv[it] = 0
                else:
                    if self.botao_peq("Pegar", pygame.Rect(r.right - 96, r.y + 2, 90, 26), (40, 60, 40)):
                        sobra = self.dar(it, bau["itens"][it], avisar=False) or 0
                        bau["itens"][it] = sobra
                        if sobra:
                            self.msg("Mochila cheia: o resto ficou no baú.", (255, 170, 120))
        self.texto("O baú fica na sua base: guarde aqui o que não cabe na mochila.  (E ou ESC fecha)",
                   (W // 2, 672), self.f_peq, (200, 195, 180), centro=True)

    def estacao(self):
        return ((self.dia - 1) // DIAS_ESTACAO) % len(ESTACOES)

    def tingir(self, s, copa=False):
        """Pinta o chao (ou as copas) com a cor da estacao. So mexe nas cores, nunca na transparencia."""
        if s is None:
            return s
        _, mult, soma, _, _ = ESTACOES[self.estacao()]
        if self.capitulo == 2:  # DIMENSAO SOMBRIA: tudo roxo e avermelhado
            mult = (mult[0] * 0.92, mult[1] * 0.72, mult[2] * 1.08)
            soma = (soma[0] + 22, soma[1] - 4, soma[2] + 30)
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
        self.msg("Modo DONO ligado SÓ NESTE MUNDO. Lá em cima: lugar de escrever; do lado do mapa: botão DONO.",
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
            for linha in ("tudo  ·  moedas 1000  ·  curar  ·  noite  ·  dia  ·  dia 10  ·  desligar (volta ao normal)",
                          "gigante  ·  zumbis 5  ·  bunker 2 (te leva no bunker 2)  ·  limpar (some com os zumbis)",
                          "caixa 2 (te leva na caixa da peça do bunker 2)  ·  torre (te leva na torre de rádio)"):
                self.msg(linha, (255, 200, 240))
        elif cmd == "tudo":
            self.tudo_do_melhor()
        elif cmd == "desligar":
            self.dono = False
            self.mochila_infinita = False
            self.moedas = self.recorde.get("moedas", 0)
            self.console_ativo = False
            self.msg("Modo dono desligado neste mundo. Agora ele é um mundo normal.", (200, 230, 255))
            self.salvar()
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
                self.zumbis.append(self.equipar_zumbi(Zumbi(x, y, t, random.randrange(len(self.spr_z[t])), random)))
            self.msg("Lá vem eles!", (255, 150, 130))
        elif cmd == "caixa" and num and 1 <= num <= len(self.mundo.bunkers):
            b = self.mundo.bunkers[num - 1]
            caixa = next((mv for mv in self.mundo.moveis if mv.get("predio") is b and "revela" in mv), None)
            if caixa:
                for ox, oy in ((0, 30), (-30, 0), (0, -30), (30, 0)):
                    p.x, p.y = caixa["x"] + ox, caixa["y"] + oy
                    if not self.mundo.bloqueado(p.x, p.y, p.r):
                        break
                self.cam = [p.x, p.y]
                if num - 1 not in self.revelados:
                    self.revelados.append(num - 1)
                self.msg(f"Você está do lado da caixa da peça do bunker {num}. Aperte E.", (200, 255, 200))
        elif cmd == "torre" and self.mundo.torre:
            t_ = self.mundo.torre
            p.x, p.y = (t_["x"] + t_["w"] / 2) * T, (t_["y"] + t_["h"] / 2) * T + 70
            self.cam = [p.x, p.y]
            self.msg("Você está na torre de rádio. Aperte E para usar o rádio.", (200, 255, 200))
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
            if a.get("escondida"):
                continue
            if a["id"] not in self.armas:
                self.armas.append(a["id"])
            self.niveis[a["id"]] = NIVEL_MAX
            if not a["melee"]:
                self.pente[a["id"]] = self.arma_melhorada(a["id"])["pente"]
                if a["id"] not in self.miras:
                    self.miras.append(a["id"])
                if a.get("silencia") and a["id"] not in self.silen:
                    self.silen.append(a["id"])
        self.armas.sort(key=ordem_arma)
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
            self.msg("Modo DONO ligado SÓ NESTE MUNDO. Clique no botão DONO para ter tudo.", (255, 160, 230))
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
    def cuidar_thor(self, oque, item):
        obj = self.cao
        if self.inv.get(item, 0) <= 0:
            return
        self.inv[item] -= 1
        if self.inv[item] <= 0:
            self.inv.pop(item)
        if oque == "curar":
            obj["vida"] = min(100.0, obj.get("vida", 100) + (70 if item == "kit" else 35))
            self.msg("Você cuidou dos machucados do Thor.", (170, 240, 170))
        elif oque == "comida":
            obj["fome"] = min(100.0, obj.get("fome", 100) + 50)
            self.msg("O Thor comeu tudinho! Ele abanou o rabo.", (255, 220, 140))
        else:
            obj["sede"] = min(100.0, obj.get("sede", 100) + 55)
            self.msg("O Thor bebeu a água.", (160, 210, 255))
        obj["au"] = 0.6
        self.som("comer", 0.5)

    def tela_menu_cao(self, dt):
        tc = self.teclas
        cao = self.cao
        if pygame.K_ESCAPE in tc or pygame.K_e in tc or not cao or cao.get("morto") or self.__dict__.get("piloto"):
            self.estado = "jogo"
            return
        self.desenhar()
        tela = self.tela
        caixa = pygame.Rect(W // 2 - 260, H // 2 - 200, 520, 400)
        self.painel(caixa, 235)
        self.texto("THOR", (caixa.x + 24, caixa.y + 12), self.f_grande, (255, 220, 140))
        if self.botao_peq("Fechar (E)", pygame.Rect(caixa.right - 120, caixa.y + 16, 104, 36)):
            self.estado = "jogo"
            return
        y = caixa.y + 74
        for k_, (nome_, v_, cor_) in enumerate((("Vida", cao.get("vida", 100), (220, 60, 60)),
                                                ("Fome", cao.get("fome", 100), (230, 160, 60)),
                                                ("Sede", cao.get("sede", 100), (80, 150, 230)))):
            self.texto(nome_, (caixa.x + 28, y), self.f_peq, (220, 210, 200))
            pygame.draw.rect(tela, (20, 20, 20), (caixa.x + 100, y + 4, 300, 14), border_radius=5)
            pygame.draw.rect(tela, cor_, (caixa.x + 100, y + 4, int(300 * max(0, v_) / 100), 14), border_radius=5)
            self.texto(f"{int(v_)}", (caixa.x + 412, y), self.f_peq, (220, 210, 200))
            y += 26
        y += 12
        sentado = cao.get("sentado", False)
        cura = "kit" if self.inv.get("bandagem", 0) <= 0 and self.inv.get("kit", 0) > 0 else "bandagem"
        opcoes = [
            ("1", "Levantar e me seguir" if sentado else "Sentar e ficar aqui", "sentar", None, True),
            ("2", f"Dar comida  (você tem {self.inv.get('comida', 0)})", "comida", "comida", self.inv.get("comida", 0) > 0),
            ("3", f"Dar água  (você tem {self.inv.get('agua', 0)})", "agua", "agua", self.inv.get("agua", 0) > 0),
            ("4", f"Curar com {ITENS[cura].lower()}  (você tem {self.inv.get(cura, 0)})", "curar", cura,
             self.inv.get(cura, 0) > 0),
        ]
        teclas_n = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4)
        for k_, (tecla_, txt_, oque_, item_, pode_) in enumerate(opcoes):
            r = pygame.Rect(caixa.x + 24, y, caixa.w - 48, 46)
            apertou = self.botao_peq(f"{tecla_}  ·  {txt_}", r, (50, 60, 44), pode_) or (pode_ and teclas_n[k_] in tc)
            if apertou:
                if oque_ == "sentar":
                    cao["sentado"] = not sentado
                    cao["modo"] = "quieto"
                    cao["au"] = 0.5
                    self.msg("Thor, SENTA! Ele fica aqui te esperando." if cao["sentado"] else
                             "Thor, vem! Ele voltou a te seguir.", (255, 220, 140))
                    self.estado = "jogo"
                    self.salvar()
                    return
                self.cuidar_thor(oque_, item_)
            y += 54
        self.texto("Dica: X manda ele atacar  ·  Z manda ele recuar para perto de você", (caixa.x + 26, caixa.bottom - 34),
                   self.f_peq, (170, 200, 230))

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
        aba = self.__dict__.get("aba_bancada", "melhorar")
        for k, (id_aba, nome_aba) in enumerate((("melhorar", "MELHORAR"), ("fabricar", "FABRICAR"))):
            r = pygame.Rect(caixa.x + 300 + k * 170, caixa.y + 16, 160, 36)
            if self.botao_peq(nome_aba, r, (90, 70, 30) if aba == id_aba else (44, 40, 38)):
                self.aba_bancada = aba = id_aba
        if aba == "fabricar":
            self.bancada_fabricar(caixa)
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

    def bancada_fabricar(self, caixa):
        tela = self.tela
        y = caixa.y + 116
        self.texto("PROTEÇÃO E MUNIÇÃO", (caixa.x + 24, y), self.f_med, (255, 220, 140))
        y += 32
        for id_, nome, expl, custo in FABRICAR:
            r = pygame.Rect(caixa.x + 20, y, caixa.w - 40, 56)
            pygame.draw.rect(tela, (34, 36, 40), r, border_radius=8)
            self.texto(nome, (r.x + 20, r.y + 6), self.f_med2)
            atual = {"colete": self.colete, "capacete": self.capacete}.get(id_)
            self.texto(expl + (f"   (o seu está em {int(atual)}%)" if atual else ""), (r.x + 20, r.y + 31), self.f_peq,
                       (200, 195, 180))
            txt = ", ".join(f"{q} {ITENS[k].split(' ')[0].lower()}" for k, q in custo.items())
            pode = all(self.inv.get(k, 0) >= q for k, q in custo.items())
            self.texto(txt, (r.x + 560, r.y + 18), self.f_peq, (200, 195, 180) if pode else (150, 140, 140))
            if self.botao_peq("Fabricar", pygame.Rect(r.right - 150, r.y + 10, 140, 36), (40, 60, 40), pode):
                if self.pagar(custo):
                    if id_ == "colete":
                        self.colete = 100.0
                    elif id_ == "calca":
                        self.calca = 100.0
                    elif id_ == "capacete":
                        self.capacete = 100.0
                    elif id_ == "flechas":
                        self.inv["flecha"] = self.inv.get("flecha", 0) + 10
                    self.som("golpe", 0.6)
                    self.msg(f"Fabricou: {nome}!", (255, 220, 120))
                    self.salvar()
            y += 62
        y += 10
        self.texto("PARA A SUA BASE (clique e coloque no chão)", (caixa.x + 24, y), self.f_med, (255, 220, 140))
        y += 34
        ids = [r_["id"] for r_ in RECEITAS]
        for k, id_ in enumerate([i for i in BASE_BANCADA if i in ids]):
            rec = RECEITAS[ids.index(id_)]
            r = pygame.Rect(caixa.x + 20 + (k % 4) * 240, y + (k // 4) * 74, 230, 66)
            pode = all(self.inv.get(q_, 0) >= n_ for q_, n_ in rec["custo"].items())
            if self.botao_peq(rec["nome"], pygame.Rect(r.x, r.y, r.w, 36), (40, 60, 40), pode):
                self.estado = "jogo"
                self.modo_construir = ids.index(id_)
                self.msg("Clique no chão para colocar. B ou ESC cancela.", (200, 230, 255))
                return
            txt = ", ".join(f"{n_} {ITENS[q_].split(' ')[0].lower()}" for q_, n_ in rec["custo"].items())
            self.texto(txt, (r.centerx, r.y + 48), self.f_peq, (200, 195, 180) if pode else (150, 140, 140), centro=True)

    # ================================================================ carros
    def tirar_carro_do_mapa(self, c):
        """Tira o carro do chao desenhado e das batidas (para ele poder andar)."""
        m = self.mundo
        a = math.radians(c["ang"])
        for k in (-16, 0, 16):
            px, py = c["x"] + math.cos(a) * k, c["y"] - math.sin(a) * k
            i = int(py // T) * N + int(px // T)
            m.col[i] = [q for q in m.col.get(i, []) if abs(q[0] - px) > 0.01 or abs(q[1] - py) > 0.01]
        lst = m.carros_ch.get((int(c["x"] // CHPX), int(c["y"] // CHPX)), [])
        if c in lst:
            lst.remove(c)
        self.invalidar(c["x"], c["y"])

    def estacionar(self, c, x, y, ang, gas, tirar=False):
        m = self.mundo
        if tirar:
            self.tirar_carro_do_mapa(c)
        c.update(x=x, y=y, ang=ang, gas=gas, mexeu=True)
        a = math.radians(ang)
        for k in (-16, 0, 16):
            m.add_colisor(x + math.cos(a) * k, y - math.sin(a) * k, 13)
        m.carros_ch.setdefault((int(x // CHPX), int(y // CHPX)), []).append(c)
        m.spr_carro[c["spr"]] = pygame.transform.rotate(m.base_carro[c["spr"]], ang)
        mala = c.get("mala")
        if mala is not None and mala < len(m.moveis):  # o porta-malas vai junto
            mv = m.moveis[mala]
            lst = m.moveis_ch.get((int(mv["x"] // CHPX), int(mv["y"] // CHPX)), [])
            if mv in lst:
                lst.remove(mv)
            mv["x"], mv["y"] = x - math.cos(a) * 36, y + math.sin(a) * 36
            m.moveis_ch.setdefault((int(mv["x"] // CHPX), int(mv["y"] // CHPX)), []).append(mv)
        self.invalidar(x, y)

    def entrar_carro(self, c):
        if self.telhado_b:
            return
        self.tirar_carro_do_mapa(c)
        self.dirigindo = c
        self.vel_carro = 0.0
        self.agachado = False
        self.__dict__["deitado"] = False
        self.p.x, self.p.y = c["x"], c["y"]
        self.som("clique", 0.6)
        self.msg("Dirigindo! W acelera · S freia/ré · A e D viram · E sai. Atropele os zumbis!", (170, 220, 255))
        if c.get("gas", 0) <= 0:
            self.msg("Este carro está sem gasolina. Use um GALÃO (ache nos postos e porta-malas).", (255, 190, 130))

    def sair_carro(self):
        c = self.dirigindo
        m = self.mundo
        a = math.radians(c["ang"])
        for lado in (1, -1):  # sai pela porta do lado do carro
            sx = c["x"] + math.cos(a + lado * math.pi / 2) * 40
            sy = c["y"] - math.sin(a + lado * math.pi / 2) * 40
            if not m.bloqueado(sx, sy, self.p.r):
                break
        self.dirigindo = None
        self.vel_carro = 0.0
        self.estacionar(c, c["x"], c["y"], c["ang"], c.get("gas", 0))
        self.p.x, self.p.y = sx, sy
        self.som("clique", 0.6)

    def dirigir(self, dt, mv):
        c = self.dirigindo
        m = self.mundo
        mx, my = mv
        gas = c.get("gas", 0)
        acel = -my  # W = para frente, S = freia / re
        if acel > 0 and gas > 0:
            self.vel_carro = min(430.0, self.vel_carro + 300 * dt)
        elif acel < 0:
            self.vel_carro = max(-140.0, self.vel_carro - 420 * dt)
        else:
            self.vel_carro *= max(0.0, 1 - 1.6 * dt)
        if abs(self.vel_carro) > 5:
            vira = -mx * 150 * dt * min(1.0, abs(self.vel_carro) / 160) * (1 if self.vel_carro > 0 else -1)
            c["ang"] = (c["ang"] + vira) % 360
        a = math.radians(c["ang"])
        dx, dy = math.cos(a) * self.vel_carro * dt, -math.sin(a) * self.vel_carro * dt
        frente = 30 if self.vel_carro >= 0 else -30
        nx, ny = c["x"] + dx, c["y"] + dy
        if m.bloqueado(nx + math.cos(a) * frente, ny - math.sin(a) * frente, 14) or m.bloqueado(nx, ny, 14) \
                or m.tile_px(nx, ny) == AGUA:
            if abs(self.vel_carro) > 200:
                self.tremor = max(self.tremor, 8)
                self.som("golpe", 0.7)
            self.vel_carro = -self.vel_carro * 0.25
        else:
            c["x"], c["y"] = nx, ny
        if gas > 0:
            c["gas"] = max(0.0, gas - abs(self.vel_carro) / 430 * dt * 0.6)
            if c["gas"] <= 0:
                self.msg("Acabou a gasolina! Use um GALÃO.", (255, 190, 130))
        self.p.x, self.p.y = c["x"], c["y"]
        self.p.ang = -a
        # atropelar zumbis
        if abs(self.vel_carro) > 110:
            for z in list(self.zumbis):
                if (z.x - c["x"]) ** 2 + (z.y - c["y"]) ** 2 < (z.r + 26) ** 2:
                    self.ferir_zumbi(z, 70 + abs(self.vel_carro) * 0.6, -a)
                    z.x += math.cos(a) * 30
                    z.y -= math.sin(a) * 30
                    self.tremor = max(self.tremor, 4)
                    self.vel_carro *= 0.85
            for z in [z for z in self.zumbis if z.hp <= 0]:
                self.matar(z, -a)
        if abs(self.vel_carro) > 60:  # o motor faz barulho
            self.fazer_barulho(c["x"], c["y"], 300 + abs(self.vel_carro))

    # ================================================================ cachorro
    def criar_cachorro(self):
        """O Thor fica esperando perto de onde voce comeca."""
        m = self.mundo
        p = self.p
        for k in range(40):
            a = k * 0.7
            x, y = p.x + math.cos(a) * 150, p.y + math.sin(a) * 150
            if not m.bloqueado(x, y, 14):
                break
        self.cao = dict(x=x, y=y, amigo=False, ang=0.0, t_mordida=0.0, t_latido=0.0, au=0.0, t_aviso=0.0, passo=0.0)

    def reviver_thor(self, txt):
        """Se o Thor tinha morrido, ele volta vivo (com vida, fome e sede cheias) do seu lado."""
        cao = self.cao
        if not cao or not cao.get("amigo") or not cao.get("morto"):
            return False
        p = self.p
        x, y = p.x + 40, p.y + 30
        for k in range(12):
            a = k / 12 * 6.283
            if not self.mundo.bloqueado(p.x + math.cos(a) * 45, p.y + math.sin(a) * 45, 12):
                x, y = p.x + math.cos(a) * 45, p.y + math.sin(a) * 45
                break
        cao.update(morto=False, vida=100.0, fome=100.0, sede=100.0, sentado=False, modo="quieto", recuar=0,
                   x=x, y=y, au=1.2)
        self.msg(txt, (255, 220, 140))
        self.som("pegar", 0.8)
        return True

    def cuidado_cao(self):
        """O que o Thor precisa agora e com o que da para dar: ("curar"/"comida"/"agua", item) ou None."""
        cao = self.cao
        if not cao or cao.get("morto"):
            return None
        inv = self.inv
        if cao.get("vida", 100) < 85:
            for item in ("bandagem", "kit"):
                if inv.get(item, 0) > 0:
                    return ("curar", item)
        if cao.get("fome", 100) < 70 and inv.get("comida", 0) > 0:
            return ("comida", "comida")
        if cao.get("sede", 100) < 70 and inv.get("agua", 0) > 0:
            return ("agua", "agua")
        return None

    def atualizar_cachorro(self, dt):
        cao = self.cao
        if not cao:
            return
        if cao.get("morto"):
            return
        if cao["amigo"]:  # o Thor sente fome e sede; sem comer ou beber ele vai ficando fraco
            cao["fome"] = max(0.0, cao.get("fome", 100) - 100 / 2400 * dt)
            cao["sede"] = max(0.0, cao.get("sede", 100) - 100 / 1800 * dt)
            if cao["fome"] <= 0 or cao["sede"] <= 0:
                cao["vida"] = cao.get("vida", 100) - 0.5 * dt
            cao["t_pede"] = cao.get("t_pede", 0) - dt
            if cao["t_pede"] <= 0 and (cao["fome"] < 35 or cao["sede"] < 35 or cao.get("vida", 100) < 40):
                cao["t_pede"] = 40.0
                falta = "machucado" if cao.get("vida", 100) < 40 else ("com fome" if cao["fome"] < 35 else "com sede")
                self.msg(f"O Thor está {falta}! Chegue perto dele e aperte E para cuidar.", (255, 200, 140))
            # zumbi colado no Thor morde ele
            for z in self.zumbis:
                if (z.x - cao["x"]) ** 2 + (z.y - cao["y"]) ** 2 < (z.r + 14) ** 2 and z.t_ataque <= 0:
                    z.t_ataque = 1.3
                    cao["vida"] = cao.get("vida", 100) - z.dano * 0.8
                    self.particula(cao["x"], cao["y"], random.uniform(-40, 40), random.uniform(-40, 40), 0.4, (150, 10, 12), 3)
                    break
            if cao.get("vida", 100) <= 0:
                cao["morto"] = True
                cao["vida"] = 0
                self.msg("O THOR MORREU... :( Cuide bem dele da próxima vez.", (255, 120, 110))
                self.som("dor", 0.6)
                return
        m = self.mundo
        p = self.p
        cao["au"] = max(0.0, cao["au"] - dt)
        cao["t_mordida"] -= dt
        cao["t_latido"] -= dt
        cao["t_aviso"] -= dt
        if not cao["amigo"]:
            if math.hypot(cao["x"] - p.x, cao["y"] - p.y) < 300 and cao["t_latido"] <= 0:
                cao["t_latido"] = 6.0
                cao["au"] = 0.8
            return
        alvo_x, alvo_y, vel = None, None, 0.0
        # so ataca quando voce manda (tecla X); quieto ele nao late, para nao entregar voce
        ataca = cao.get("modo") == "ataque"
        perigo = [z for z in self.zumbis if (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 380 ** 2] if ataca else []
        if perigo:
            if cao["t_latido"] <= 0:
                cao["t_latido"] = 2.5
                cao["au"] = 0.9
            if cao["t_aviso"] <= 0:
                cao["t_aviso"] = 25.0
                self.msg("O Thor está latindo: tem ZUMBI perto!", (255, 220, 140))
            z = min(perigo, key=lambda z: (z.x - cao["x"]) ** 2 + (z.y - cao["y"]) ** 2)
            d = math.hypot(z.x - cao["x"], z.y - cao["y"])
            if d < z.r + 18:
                if cao["t_mordida"] <= 0:  # MORDIDA
                    cao["t_mordida"] = 0.75
                    self.ferir_zumbi(z, 24, math.atan2(z.y - cao["y"], z.x - cao["x"]))
                    if z.hp <= 0:
                        self.matar(z, math.atan2(z.y - cao["y"], z.x - cao["x"]))
                        self.msg("O Thor derrubou um zumbi!", (255, 220, 140))
            else:
                alvo_x, alvo_y, vel = z.x, z.y, 230.0
        elif cao.get("sentado"):
            pass  # sentadinho, esperando voce voltar
        elif cao.get("recuar", 0) > 0:
            # RECUANDO: fica escondido atras de voce, do lado contrario dos zumbis, ate voce mandar atacar (X)
            perto = [z for z in self.zumbis if (z.x - p.x) ** 2 + (z.y - p.y) ** 2 < 600 ** 2]
            if perto:
                zx = sum(z.x for z in perto) / len(perto)
                zy = sum(z.y for z in perto) / len(perto)
                dz = math.hypot(p.x - zx, p.y - zy) or 1
                bx, by = p.x + (p.x - zx) / dz * 45, p.y + (p.y - zy) / dz * 45
                cao["recuar"] = 1.0
            else:
                bx, by = p.x, p.y
                cao["recuar"] = cao.get("recuar", 1.0) - dt * 0.12  # sem zumbi perto por uns segundos: volta ao normal
            d = math.hypot(bx - cao["x"], by - cao["y"])
            if d > 12:
                alvo_x, alvo_y, vel = bx, by, 330.0
        else:
            d = math.hypot(p.x - cao["x"], p.y - cao["y"])
            ult = cao.get("ult_p", (p.x, p.y))
            andando = math.hypot(p.x - ult[0], p.y - ult[1]) > 0.5
            cao["ult_p"] = (p.x, p.y)
            if d > 1100:  # ficou muito para tras: aparece do seu lado
                cao["x"], cao["y"] = p.x + 50, p.y + 40
            elif d > 70 and (andando or d > 180):  # voce anda, ele anda; voce para, ele para do seu lado
                alvo_x, alvo_y, vel = p.x, p.y, (300.0 if d > 300 or self.dirigindo else 150.0)
        if alvo_x is not None:
            a = math.atan2(alvo_y - cao["y"], alvo_x - cao["x"])
            cao["ang"] = a
            nx, ny = cao["x"] + math.cos(a) * vel * dt, cao["y"] + math.sin(a) * vel * dt
            x0, y0 = cao["x"], cao["y"]
            if not m.bloqueado(nx, ny, 8):
                cao["x"], cao["y"] = nx, ny
            elif not m.bloqueado(nx, cao["y"], 8):
                cao["x"] = nx
            elif not m.bloqueado(cao["x"], ny, 8):
                cao["y"] = ny
            else:  # contorna o mato: tenta andar de lado
                for da in (0.8, -0.8, 1.5, -1.5):
                    tx, ty = cao["x"] + math.cos(a + da) * vel * dt, cao["y"] + math.sin(a + da) * vel * dt
                    if not m.bloqueado(tx, ty, 8):
                        cao["x"], cao["y"] = tx, ty
                        break
            # travou mesmo assim? depois de um tempinho ele pula para perto de voce
            if math.hypot(cao["x"] - x0, cao["y"] - y0) < vel * dt * 0.3:
                cao["preso"] = cao.get("preso", 0) + dt
            else:
                cao["preso"] = 0
            if cao.get("preso", 0) > 1.2:
                cao["preso"] = 0
                for k_ in range(16):
                    aa = k_ / 16 * 6.283
                    tx, ty = p.x + math.cos(aa) * 40, p.y + math.sin(aa) * 40
                    if not m.bloqueado(tx, ty, 10):
                        cao["x"], cao["y"] = tx, ty
                        break
            cao["passo"] += vel * dt / 14

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
        elif tipo in ("muro", "portao", "bau"):
            for px, py in self.pontos_colisor(c):
                m.add_colisor(px, py, 11 if tipo != "bau" else 14)
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
        if c["tipo"] in ("fogueira", "abrigo", "bancada", "bau"):
            return [(x, y)]
        if c["tipo"] == "muro" or (c["tipo"] == "portao" and not c.get("aberto")):
            a = math.radians(c.get("ang", 0))
            return [(x + math.cos(a) * k, y + math.sin(a) * k) for k in (-42, -21, 0, 21, 42)]
        return []

    def abrir_portao(self, c):
        """Abre ou fecha o portao: fechado, zumbi nao passa."""
        m = self.mundo
        if not c.get("aberto"):
            for px, py in self.pontos_colisor(c):  # tira a parede
                i = int(py // T) * N + int(px // T)
                m.col[i] = [q for q in m.col.get(i, []) if abs(q[0] - px) > 0.01 or abs(q[1] - py) > 0.01]
            c["aberto"] = True
            self.msg("Portão aberto.", (200, 230, 200))
        else:
            c["aberto"] = False
            for px, py in self.pontos_colisor(c):
                m.add_colisor(px, py, 11)
            self.msg("Portão fechado: zumbi não passa.", (200, 230, 200))
        self.som("golpe", 0.4)

    def desmontar(self, c):
        m = self.mundo
        for px, py in self.pontos_colisor(c):
            i = int(py // T) * N + int(px // T)
            lst = m.col.get(i, [])
            m.col[i] = [q for q in lst if abs(q[0] - px) > 0.01 or abs(q[1] - py) > 0.01]
        if c in self.construidos:
            self.construidos.remove(c)
        if c["tipo"] == "bau" and c.get("itens"):
            m.add_movel(dict(id=len(m.moveis), x=c["x"], y=c["y"], tipo="mochila", aberto=False,
                             itens=[[k, q] for k, q in c["itens"].items() if q > 0]))
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
        if self.toque:
            return self.entrada_toque()
        k = pygame.key.get_pressed()
        mx = (k[pygame.K_d] or k[pygame.K_RIGHT]) - (k[pygame.K_a] or k[pygame.K_LEFT])
        my = (k[pygame.K_s] or k[pygame.K_DOWN]) - (k[pygame.K_w] or k[pygame.K_UP])
        b = pygame.mouse.get_pressed()
        pos = pygame.mouse.get_pos()
        tiro = b[0] and not self.mouse_no_hud(pos)
        return (mx, my), (k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]), b[2], tiro, pos

    def entrada_toque(self):
        dedos = self.__dict__.setdefault("dedos", {})
        mv, corre, tiro = (0.0, 0.0), False, False
        R = 70
        joy = next((d for d in dedos.values() if d["papel"] == "joy"), None)
        if joy:
            dx, dy = joy["x"] - joy["x0"], joy["y"] - joy["y0"]
            d = math.hypot(dx, dy)
            if d > R:  # o joystick acompanha o dedo
                joy["x0"] += dx / d * (d - R)
                joy["y0"] += dy / d * (d - R)
                d = R
            if d > 12:
                mv = (dx / math.hypot(dx, dy), dy / math.hypot(dx, dy))
                corre = d >= R * 0.95
        mira = next((d for d in dedos.values() if d["papel"] == "mira"), None)
        if mira:
            pos = (mira["x"], mira["y"])
            tiro = True
            self.mouse_toque = pos
        elif mv != (0.0, 0.0):  # sem mirar: olha para onde esta andando
            pos = (W / 2 + mv[0] * 160, H / 2 + mv[1] * 160)
            self.mouse_toque = pos
        else:
            pos = self.__dict__.get("mouse_toque", (W / 2 + 160, H / 2))
        return mv, corre, False, tiro, pos

    def desenhar_toque(self):
        """Joystick e botoes redondos (so no celular)."""
        tela = self.tela
        cam = self.__dict__.setdefault("camada_toque", pygame.Surface((W, H), pygame.SRCALPHA))
        cam.fill((0, 0, 0, 0))
        dedos = self.__dict__.get("dedos", {})
        joy = next((d for d in dedos.values() if d["papel"] == "joy"), None)
        cx, cy = (joy["x0"], joy["y0"]) if joy else (170, 470)
        pygame.draw.circle(cam, (255, 255, 255, 40), (int(cx), int(cy)), 70)
        pygame.draw.circle(cam, (255, 255, 255, 110), (int(cx), int(cy)), 70, 3)
        kx, ky = (joy["x"], joy["y"]) if joy else (cx, cy)
        if joy and math.hypot(kx - cx, ky - cy) > 70:
            a = math.atan2(ky - cy, kx - cx)
            kx, ky = cx + math.cos(a) * 70, cy + math.sin(a) * 70
        pygame.draw.circle(cam, (255, 255, 255, 150), (int(kx), int(ky)), 30)
        if not joy:
            self.texto("andar", (cx, cy + 82), self.f_peq, (230, 230, 230), centro=True)
        for tecla, txt, bx, by in self.BOTOES_TOQUE:
            apertado = any((d["x"] - bx) ** 2 + (d["y"] - by) ** 2 < 32 ** 2 and d["papel"] == "botao" for d in dedos.values())
            pygame.draw.circle(cam, (255, 220, 140, 150) if apertado else (20, 22, 28, 150), (bx, by), 29)
            pygame.draw.circle(cam, (255, 230, 170, 200), (bx, by), 29, 2)
        tela.blit(cam, (0, 0))
        for tecla, txt, bx, by in self.BOTOES_TOQUE:
            self.texto(txt, (bx, by - 9), self.f_peq, (255, 245, 225), centro=True)
        mira = next((d for d in dedos.values() if d["papel"] == "mira"), None)
        if mira:
            pygame.draw.circle(tela, (255, 80, 60), (int(mira["x"]), int(mira["y"])), 16, 2)
            pygame.draw.circle(tela, (255, 80, 60), (int(mira["x"]), int(mira["y"])), 3)
        elif not joy:
            self.texto("toque aqui para mirar e atirar", (W * 0.72, H * 0.62), self.f_peq, (230, 230, 230), centro=True)

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
        if pygame.K_q in tc:
            if self.arma != "maos":
                self.arma_guardada = self.arma
                self.trocar_arma("maos")
                self.msg("Arma guardada. Sem nada na mão você corre um pouco mais. (Q pega de volta)", (200, 220, 200))
            else:
                volta = self.__dict__.get("arma_guardada")
                self.trocar_arma(volta if volta in self.armas else self.armas[-1])
        if pygame.K_x in tc and self.cao and self.cao["amigo"]:
            ataque = self.cao.get("modo") != "ataque"
            self.cao["modo"] = "ataque" if ataque else "quieto"
            self.cao["recuar"] = 0
            self.cao["au"] = 0.8 if ataque else 0.0
            self.msg("THOR, ATACA! Ele vai morder os zumbis perto de você. (X de novo: quieto)" if ataque else
                     "Thor quieto: ele só te segue, sem latir. (X: ataca)", (255, 220, 140))
        if pygame.K_z in tc and self.cao and self.cao["amigo"] and not self.cao.get("morto"):
            self.cao["modo"] = "quieto"
            self.cao["recuar"] = 1.0
            self.cao["au"] = 0.0
            self.msg("THOR, RECUA! Ele fica escondido atrás de você até você apertar X.", (255, 220, 140))
        if pygame.K_t in tc:
            self.deitado = not self.__dict__.get("deitado", False)
            if self.deitado:
                self.agachado = False
            self.msg("Deitado: quase ninguém te vê, mas você se arrasta bem devagar." if self.deitado else "Levantou.",
                     (170, 220, 255))
        if pygame.K_c in tc:
            self.deitado = False
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
            i = self.armas.index(self.arma) if self.arma in self.armas else 0
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
                self.msg("CONSTRUIR SUA BASE: escolha na lista (teclas 1 a 0 ou clique) e clique no chão.",
                         (200, 230, 255))
                self.msg("Muro = bloquinho (fica colocando um do lado do outro). Faça uma BANCADA para melhorar as armas!",
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
        elif item == "galao":
            carro = self.dirigindo or next((c for c in self.mundo.perto(self.mundo.carros_ch, p.x, p.y)
                                            if math.hypot(c["x"] - p.x, c["y"] - p.y) < 70), None)
            if not carro:
                self.msg("Chegue perto de um carro (ou entre nele) para pôr a gasolina.", (220, 170, 150))
                return
            if carro.get("gas", 0) >= 99:
                self.msg("O tanque já está cheio.")
                return
            carro["gas"] = min(100, carro.get("gas", 0) + 50)
            self.msg(f"Abasteceu o carro: gasolina {int(carro['gas'])}%.", (200, 230, 200))
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
        if self.__dict__.get("embarcou"):
            return None
        r = self._alvo_interacao()
        if r is None and self.cao and self.cao["amigo"] and not self.cao.get("morto") and not self.dirigindo and not self.__dict__.get("piloto") and not self.telhado_b and math.hypot(self.cao["x"] - self.p.x, self.cao["y"] - self.p.y) < 60:
            return ("cuidar_cao", self.cao)  # nada mais perto: o botao do Thor
        return r

    def _alvo_interacao(self):
        p = self.p
        m = self.mundo
        if self.dirigindo:
            return ("sair_carro", self.dirigindo)
        if self.telhado_b:  # no telhado so da para descer pela escada
            e = self.telhado_b.get("escada")
            if e and math.hypot(e["dentro"][0] - p.x, e["dentro"][1] - p.y) < 50:
                return ("descer", self.telhado_b)
            return None
        if self.no_elevado is not None:
            if self.no_trem is not None:
                return ("pular_trem", None)
            el = m.elevados[self.no_elevado]
            for px_, py_ in el["pilares"]:
                if math.hypot(px_ - p.x, py_ - p.y) < 48:
                    return ("descer_elevado", (px_, py_))
            return None
        if not self.__dict__.get("piloto") and self.metro is None:
            for i_, el in enumerate(getattr(m, "elevados", ())):
                for px_, py_ in el["pilares"]:
                    if abs(px_ - p.x) < 60 and abs(py_ - p.y) < 60 and math.hypot(px_ - p.x, py_ - p.y) < 52:
                        return ("subir_elevado", (i_, px_, py_))
        if self.metro is not None:
            mt = m.metros[self.metro]
            for sx_, sy_ in mt["saidas"]:
                if math.hypot(sx_ - p.x, sy_ - p.y) < 50:
                    return ("subir_metro", mt)
        elif not self.__dict__.get("piloto") or getattr(self.__dict__.get("piloto"), "quer_metro", False):
            for mt in getattr(m, "metros", ()):
                ex_, ey_ = mt["ent"]
                if abs(ex_ - p.x) < 300 and math.hypot(ex_ - p.x, ey_ + 30 - p.y) < 56:
                    return ("descer_metro", mt)
        melhor = None
        md = 999
        for c in m.perto(m.carros_ch, p.x, p.y):
            d = math.hypot(c["x"] - p.x, c["y"] - p.y)
            if d < 46 and d < md:
                md = d
                melhor = ("carro", c)
        if self.cao and not self.cao.get("morto") and math.hypot(self.cao["x"] - p.x, self.cao["y"] - p.y) < 60:
            if not self.cao["amigo"]:
                return ("cao", self.cao)
            if (self.cuidado_cao() or self.cao.get("sentado")) and not self.__dict__.get("piloto"):
                return ("cuidar_cao", self.cao)  # ele precisa de voce: o botao dele vem primeiro
        cx_, cy_ = int(p.x // CHPX), int(p.y // CHPX)
        perto_b = [b for yy in (cy_ - 1, cy_, cy_ + 1) for xx in (cx_ - 1, cx_, cx_ + 1) for b in m.pred_ch.get((xx, yy), ())]
        for b in perto_b:
            e = b.get("escada")
            if e:
                d = math.hypot(e["fora"][0] - p.x, e["fora"][1] - p.y)
                if d < 40 and d < md:
                    md = d
                    melhor = ("subir", b)
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
            elif c["tipo"] in ("portao", "bau"):
                d = math.hypot(c["x"] - p.x, c["y"] - p.y)
                if d < 60 and d < md:
                    md = d
                    melhor = (c["tipo"], c)
            elif c["tipo"] in ("barricada", "fogueira", "arame", "muro", "espinhos"):
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
        if tipo == "cao":
            return "[E] Fazer carinho no cachorro (ele vira seu amigo)"
        if tipo == "cuidar_cao":
            return "[E] Thor: sentar, comida, água, bandagem"
        if tipo == "carro":
            return f"[E] Entrar no carro (gasolina {int(obj.get('gas', 0))}%)"
        if tipo == "sair_carro":
            return "[E] Sair do carro"
        if tipo == "subir_elevado":
            return "[E] Subir a escada da torre (trilho do trem elevado)"
        if tipo == "descer_elevado":
            return "[E] Descer a escada da torre"
        if tipo == "pular_trem":
            return "[E] Pular do trem (fica em cima do trilho)"
        if tipo == "descer_metro":
            return f"[E] Descer a escada do metrô (estação {obj['cidade']})"
        if tipo == "subir_metro":
            return "[E] Subir a escada para a rua"
        if tipo == "subir":
            return "[E] Subir no telhado pela escada"
        if tipo == "descer":
            return "[E] Descer do telhado"
        if tipo == "movel":
            return f"[E] Revistar {NOMES_MOVEIS.get(obj['tipo'], 'móvel')}"
        if tipo == "cama":
            return "[E] Descansar e se curar" if obj.get("hospital") else "[E] Dormir no bunker (salva o jogo)"
        if tipo == "abrigo":
            return "[E] Dormir no seu bunker (salva o jogo)"
        if tipo == "bancada":
            return "[E] Usar a bancada (melhorar armas e mochila)"
        if tipo == "portao":
            return "[E] Fechar o portão" if obj.get("aberto") else "[E] Abrir o portão"
        if tipo == "bau":
            return "[E] Abrir o baú (guardar coisas na base)"
        if tipo == "desmontar":
            nome = {"barricada": "a barricada", "fogueira": "a fogueira", "arame": "o arame farpado",
                    "muro": "o muro"}[obj["tipo"]]
            return f"[E] Desmontar {nome} (devolve o material)"
        if tipo == "arvore":
            return "[E] Cortar árvore (tábuas)"
        if tipo == "agua":
            return "[E] Beber água do lago"
        if tipo == "torre":
            if self.resgate:
                return "Aguente firme! O helicóptero está vindo."
            if self.__dict__.get("radio_consertado"):
                return "[E] Chamar o helicóptero de novo pelo rádio"
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
        if tipo == "cuidar_cao":
            self.estado = "menu_cao"
            self.som("clique", 0.4)
            return
        if tipo == "cao":
            obj["amigo"] = True
            obj["au"] = 1.2
            self.msg("O THOR agora é seu amigo! Ele te segue quietinho. Aperte X para ele ATACAR os zumbis.",
                     (255, 220, 140))
            self.salvar()
            return
        if tipo == "carro":
            self.entrar_carro(obj)
            return
        if tipo == "sair_carro":
            self.sair_carro()
            return
        if tipo == "subir_elevado":
            i_, px_, py_ = obj
            el = self.mundo.elevados[i_]
            self.no_elevado = i_
            self.no_trem = None
            self.p.x, self.p.y = (px_, el["fixo"]) if el["dir"] == "h" else (el["fixo"], py_)
            self.agachado = False
            self.__dict__["deitado"] = False
            self.som("clique", 0.5)
            self.msg("Você subiu no TRILHO do trem elevado! Zumbi não alcança aqui. Quando o trem passar, você PULA NELE.",
                     (255, 220, 140))
            return
        if tipo == "descer_elevado":
            px_, py_ = obj
            self.no_elevado = None
            self.no_trem = None
            for k_ in range(12):
                a_ = k_ / 12 * 6.283
                x_, y_ = px_ + math.cos(a_) * 44, py_ + math.sin(a_) * 44
                if not self.mundo.bloqueado(x_, y_, self.p.r):
                    break
            self.p.x, self.p.y = x_, y_
            self.som("clique", 0.5)
            self.msg("Você desceu da torre.", (220, 230, 200))
            return
        if tipo == "pular_trem":
            self.no_trem = None
            self.som("golpe", 0.5)
            self.msg("Você pulou do trem! Está em cima do trilho.", (255, 220, 140))
            return
        if tipo in ("descer_metro", "subir_metro"):
            if tipo == "descer_metro":
                x_, y_ = obj["saidas"][0]
            else:
                x_, y_ = obj["ent"][0], obj["ent"][1] + 70
            self.p.x, self.p.y = x_, y_
            cao = self.cao
            if cao and cao["amigo"] and not cao.get("morto") and not cao.get("sentado"):
                cao["x"], cao["y"] = x_ + 30, y_ + 10
            self.agachado = False
            self.acao = None
            self.som("clique", 0.5)
            self.cam = [x_, y_]
            self.atualizar_metro()
            return
        if tipo == "subir":
            self.telhado_b = obj
            self.p.x, self.p.y = obj["escada"]["dentro"]
            self.agachado = False
            self.som("clique", 0.5)
            self.msg("Você subiu no telhado! Aqui os zumbis não te alcançam. (T deita, E na escada desce)",
                     (170, 220, 255))
            return
        if tipo == "descer":
            self.p.x, self.p.y = obj["escada"]["fora"]
            self.telhado_b = None
            self.som("clique", 0.5)
            return
        if tipo == "movel":
            dur = 2.0 if obj["tipo"] == "militar" else 1.3
            self.acao = dict(tipo="movel", obj=obj, t=0.0, total=dur, txt="Revistando...")
        elif tipo == "desmontar":
            self.acao = dict(tipo="desmontar", obj=obj, t=0.0, total=1.2, txt="Desmontando...")
        elif tipo == "bancada":
            self.estado = "bancada"
            self.som("clique", 0.4)
        elif tipo == "portao":
            self.abrir_portao(obj)
        elif tipo == "bau":
            self.bau_atual = obj
            obj.setdefault("itens", {})
            self.estado = "bau"
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
            if self.inv.get("peca", 0) >= PECAS_RADIO or self.__dict__.get("radio_consertado"):
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
            vazias = [ITENS.get(i_, i_) for i_, q_ in ficou if q_ == -1]
            if vazias and all(q_ == -1 for _, q_ in mv["itens"]):
                self.msg("Aqui só tem arma que você já tem (sem bala): " + ", ".join(vazias) + ". Ficou guardada.",
                         (200, 195, 180))
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
            if not self.__dict__.get("radio_consertado"):
                self.inv["peca"] -= PECAS_RADIO
            self.radio_consertado = True  # se voce morrer, da para chamar o helicoptero de novo
            self.resgate = TEMPO_RESGATE * (1.25 if self.capitulo == 2 else 1.0)  # na dimensao sombria demora mais
            self.hora = 9.0  # o resgate acontece de dia: da para ver os zumbis chegando
            self.chuva = False
            self.msg("RÁDIO: \"Recebido! Helicóptero a caminho. Aguente firme!\"", (255, 230, 120))
            self.reviver_thor("O THOR OUVIU O RÁDIO E VOLTOU! Ele está vivo e veio correndo te ajudar!")
            self.msg("O dia clareou. Alguns zumbis ouviram o rádio... aguente!", (255, 200, 140))
            self.fazer_barulho(p.x, p.y, 1200)

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
            if d < 150:  # o bombeiro aguenta fogo: quase nao sente a explosao
                self.ferir_zumbi(z, dano * (1 - d / 190) * (0.3 if z.tipo == "bombeiro" else 1.0),
                                 math.atan2(z.y - y, z.x - x))
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
        if z.tipo == "bombeiro":  # roupa grossa de bombeiro: metade do dano
            dano *= 0.5
        if z.estado != "perseguir" and getattr(z, "viu", 0) <= 0:  # nao te viu: ATAQUE SURPRESA
            dano *= 3
            if len(self.numeros) < 40:
                self.numeros.append([z.x, z.y - 40, "SURPRESA!", 0.9, True])
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

    def equipar_zumbi(self, z):
        """Alguns zumbis nascem com taco/machado na mao, capacete ou colete."""
        if self.capitulo == 2 and not getattr(z, "forte", False):  # dimensao sombria: zumbi mais forte e rapido
            z.forte = True
            z.hp *= 1.5
            z.vel *= 1.15
            z.dano *= 1.35
        if z.tipo in ("gigante", "cuspidor", "gritador", "bombeiro"):
            return z
        r = random.random()
        if r < 0.10:
            z.mao = "taco"
            z.dano += 5
        elif r < 0.16:
            z.mao = "machado"
            z.dano += 9
        if random.random() < 0.08:
            z.capacete = True
            z.hp += 45
        if random.random() < 0.06:
            z.colete = True
            z.hp += 60
        return z

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
        # o que ele tinha na mao ou vestido pode cair no chao
        for item, chance in ((z.mao, 0.6), ("capacete" if z.capacete else None, 0.5),
                             ("colete" if z.colete else None, 0.5)):
            if item and random.random() < chance:
                self.drop_id += 1
                self.mundo.add_item_chao(dict(id=self.drop_id, x=z.x + random.uniform(-18, 18),
                                              y=z.y + random.uniform(-18, 18), item=item, q=1))
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
                if dif < 0.95 or (d < p.r + z.r + 8 and dif < 1.7) or d < p.r + z.r + 2:  # colado tambem leva
                    self.ferir_zumbi(z, a["dano"] * random.uniform(0.85, 1.15), ang)
                    self.som("golpe", 0.6)
                    acertos += 1
                    if a.get("empurra") and z.tipo != "gigante":  # taco: joga o zumbi para tras
                        for _ in range(6):
                            nx, ny = z.x + math.cos(ang) * 7, z.y + math.sin(ang) * 7
                            if self.mundo.bloqueado(nx, ny, z.r):
                                break
                            z.x, z.y = nx, ny
                        z.t_ataque = max(z.t_ataque, 0.8)
                        self.tremor = max(self.tremor, 4)
                    if acertos >= (2 if a["id"] in ("machado", "taco") else 1):
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
        if not self.dono:  # modo dono: bala infinita
            self.pente[self.arma] -= 1
        self.cd = a["cd"]
        sil = self.arma in self.silen
        disp = a["disp"] * (0.35 if mira else 1.0) * (1.7 if movendo and not mira else 1.0) * (2.0 if p.braco else 1.0)
        ox = p.x + math.cos(p.ang) * 22
        oy = p.y + math.sin(p.ang) * 22
        for _ in range(a["balas"]):
            ang = p.ang + random.gauss(0, disp)
            # a conta do tiro comeca no CENTRO do personagem (antes comecava no cano, e o zumbi grudado
            # em voce ficava "atras" do cano e a bala passava direto)
            fim = a["alcance"] if self.telhado_b else self.mundo.bala_para(p.x, p.y, ang, a["alcance"])
            dx = math.cos(ang)
            dy = math.sin(ang)
            alvos = []
            for z in self.zumbis:
                rx = z.x - p.x
                ry = z.y - p.y
                tt = rx * dx + ry * dy
                colado = rx * rx + ry * ry < (p.r + z.r + 2) ** 2 or (rx * rx + ry * ry < (p.r + z.r + 16) ** 2 and
                          abs((math.atan2(ry, rx) - p.ang + math.pi) % (2 * math.pi) - math.pi) < 1.6)
                if colado:  # zumbi grudado na sua frente: o tiro pega sempre
                    alvos.append((max(1.0, tt), z))
                elif -z.r < tt < fim:
                    perp = abs(rx * dy - ry * dx)
                    if perp < z.r + 3:
                        alvos.append((max(1.0, tt), z))
            alvos.sort(key=lambda q: q[0])
            fim_vis = fim
            if a.get("explode"):
                t_imp = alvos[0][0] if alvos else fim
                ix, iy = p.x + dx * t_imp, p.y + dy * t_imp
                self.rastros.append([ox, oy, ix, iy, 0.12])
                self.explodir(ix, iy, a["dano"])
                continue
            for k, (tt, z) in enumerate(alvos[:a["fura"] + 1]):
                queda = 1.0 - 0.6 * (tt / a["alcance"]) if a["id"] == "espingarda" else 1.0
                self.ferir_zumbi(z, a["dano"] * queda * random.uniform(0.9, 1.1), ang)
                fim_vis = tt
            self.rastros.append([ox, oy, p.x + dx * max(fim_vis, 22), p.y + dy * max(fim_vis, 22), 0.06])
            if not alvos and fim < a["alcance"]:
                for _ in range(3):
                    self.particula(p.x + dx * fim, p.y + dy * fim, random.uniform(-60, 60), random.uniform(-60, 60), 0.25,
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
        self.atualizar_metro()
        if self.no_elevado is not None:
            self.andar_de_trem(dt)
        self.atualizar_trens(dt)
        if self.intro_cap2 is not None and self.atualizar_queda(dt):
            for q in self.particulas:  # fumaca e fogo continuam andando
                q[0] += q[2] * dt
                q[1] += q[3] * dt
                q[2] *= 0.9
                q[3] *= 0.9
                q[4] -= dt
            self.particulas = [q for q in self.particulas if q[4] > 0]
            self.cam[0] += (p.x - self.cam[0]) * min(1, dt * 6)  # a camera acompanha o helicoptero
            self.cam[1] += (p.y - self.cam[1]) * min(1, dt * 6)
            self.tremor = max(0.0, self.tremor - 30 * dt)
            return
        mv, corre, mira, tiro, mouse = self.entrada()
        if self.__dict__.get("embarcou"):  # pendurado na corda do helicoptero
            mv, corre, mira, tiro = (0, 0), False, False, False
        if self.dirigindo:
            self.dirigir(dt, mv)
            mv, tiro, mira = (0, 0), False, False
        a_ = self.arma_atual()
        self.luneta = bool(mira and self.arma in self.miras and not a_["melee"])
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
        if pygame.K_SPACE in self.teclas and self.t_esquiva <= 0 and p.folego >= 20 and self.esquiva <= 0 \
                and not self.telhado_b and self.no_elevado is None:
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
        if self.arma == "maos" and not mira:
            vel *= 1.12
        if self.agachado:
            vel = min(vel, 128) * 0.5
            correndo = False
        if self.__dict__.get("deitado"):
            vel = min(vel, 128) * 0.3
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
            if self.no_elevado is not None:  # em cima do trilho do trem: anda so ao longo da linha
                el = self.mundo.elevados[self.no_elevado]
                if el["dir"] == "h":
                    p.x = clamp(p.x + dx, el["a"] + 16, el["b"] - 16)
                    p.y = el["fixo"] + clamp(p.y + dy - el["fixo"], -16, 16)
                else:
                    p.y = clamp(p.y + dy, el["a"] + 16, el["b"] - 16)
                    p.x = el["fixo"] + clamp(p.x + dx - el["fixo"], -16, 16)
            elif self.telhado_b:  # no telhado: anda livre em cima dele, sem cair pela borda
                b = self.telhado_b
                p.x = clamp(p.x + dx, b["x"] * T + 14, (b["x"] + b["w"]) * T - 14)
                p.y = clamp(p.y + dy, b["y"] * T + 14, (b["y"] + b["h"]) * T - 14)
            else:
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
        dif = DIFICULDADES.get(self.dificuldade, DIFICULDADES["medio"])
        p.fome = max(0, p.fome - 100 / FOME_SEG * dt * est[3] * dif["fome"])
        p.sede = max(0, p.sede - 100 / SEDE_SEG * dt * (1.6 if correndo else 1.0) * est[4] * dif["fome"])
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
            pode = a["melee"] or a.get("auto") or self.click or self.fake is not None or self.toque  # celular: segura e atira
            if pode:
                self.atirar(mira, movendo)
        # acao
        if self.acao:
            self.acao["t"] += dt
            if self.acao["t"] >= self.acao["total"]:
                self.terminar_acao()
        if not self.__dict__.get("dica_base") and self.inv.get("tabua", 0) >= 8:  # dica: da para construir a base
            self.dica_base = True
            self.msg("DICA: você já tem tábuas! Aperte B para CONSTRUIR SUA BASE (muros, portão, espinhos, bancada...).",
                     (255, 230, 140))
        # pegar itens no chao (pendurado no helicoptero nao pega nada)
        for it in (() if self.__dict__.get("embarcou") else m.perto(m.itens_ch, p.x, p.y, 0)):
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
        self.atualizar_acido(dt)
        self.atualizar_cachorro(dt)
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
            if self.chuva and self.estacao() == 2:
                self.msg("Começou a NEVAR! Os zumbis ouvem e enxergam menos.", (220, 235, 255))
            elif self.chuva:
                self.msg("Começou a chover. Os zumbis ouvem e enxergam menos.", (170, 200, 230))
        if self.chuva and self.canal_chuva is None and "chuva" in self.sons and self.estacao() != 2:
            self.canal_chuva = self.sons["chuva"].play(loops=-1)
            if self.canal_chuva:
                self.canal_chuva.set_volume(0.5)
        if not self.chuva and self.canal_chuva is not None:
            self.canal_chuva.stop()
            self.canal_chuva = None
        neve = self.estacao() == 2
        for g in self.gotas:
            if neve:  # floco de neve: cai devagar e balanca
                g[1] += 110 * dt * g[2]
                g[0] += math.sin(time.time() * 1.5 + g[2] * 9) * 30 * dt
            else:
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
                self.heli = [p.x - 1500, p.y - 700, 0.0]
                self.heli_fase = "chegando"
                self.heli_ang = math.atan2(700, 1500)
                self.heli_corda = 0.0
                self.heli_tiro = 0.0
                self.heli_alt = 1.25
                self.embarcou = False
                self.thor_junto = False
                self.msg("O HELICÓPTERO CHEGOU! O soldado vai te dar cobertura. Fique embaixo da corda!",
                         (255, 240, 150))
                self.som("helicoptero", 1.0)
        if self.heli is not None and self.intro_cap2 is None:
            if self.atualizar_heli(dt):
                return
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
        if rec["id"] == "ponte" or rec["id"] in EM_SERIE:  # alinha no quadradinho do chao
            wx = (int(wx // T)) * T + 16
            wy = (int(wy // T)) * T + 16
            if any(c_["tipo"] == rec["id"] and abs(c_["x"] - wx) < 2 and abs(c_["y"] - wy) < 2 for c_ in self.construidos):
                for i, q in rec["custo"].items():  # ja tem um igual aqui: devolve o material
                    self.inv[i] += q
                return
        c = dict(tipo=rec["id"], x=wx, y=wy, ang=math.degrees(p.ang) + 90)
        if rec["id"] in ("muro", "portao"):  # muro reto: de pe ou deitado
            c["ang"] = 90.0 if abs(math.cos(p.ang)) > abs(math.sin(p.ang)) else 0.0
        self.construir(c)
        self.som("golpe", 0.8)
        self.msg(f"Construiu: {rec['nome']}!", (200, 255, 200))
        if rec["id"] == "abrigo":
            self.msg("Zumbis não chegam perto do seu bunker. Durma nele com E.", (200, 230, 255))
        if rec["id"] == "arame":
            self.msg("Zumbi que passar no arame se machuca e fica lento.", (200, 230, 255))
        if rec["id"] == "bancada":
            self.msg("Bancada pronta! Chegue perto e aperte E para melhorar armas e a mochila.", (200, 230, 255))
        if rec["id"] == "espinhos":
            self.msg("Espinhos! Zumbi que pisar se machuca MUITO e fica lento.", (200, 230, 255))
        if rec["id"] in EM_SERIE:  # continua construindo: clique de novo para o proximo (B ou ESC para sair)
            return
        if rec["id"] == "bau":
            self.msg("Baú pronto! Aperte E perto dele para guardar suas coisas.", (200, 230, 255))
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
        r = {"barricada": 14, "fogueira": 14, "abrigo": 40, "arame": 10, "bancada": 20, "muro": 14, "portao": 14,
             "espinhos": 8,
             "bau": 16}[tipo]
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
        alvo = round((6 + min(self.dia * 0.1, 2) + 1 * esc) * min(1.0, dl * 2.5))
        # cidades e vilas tem zumbi andando pelas ruas, de dia tambem (a regiao calma do comeco continua calma)
        cid = m.cidade_perto(p.x, p.y, 1.3)
        na_cidade = cid is not None and m.densidade(p.x, p.y) > 0
        if na_cidade:
            base = {"metropole": 14, "cidade": 9}.get(cid["tipo"], 7)
            alvo = max(alvo, round(base + min(self.dia * 0.2, 3) + 1 * esc))
        alvo = round(alvo * DIFICULDADES.get(self.dificuldade, {}).get("zumbis", 1.0) * (1.3 if self.capitulo == 2 else 1.0))
        if self.resgate is not None:
            alvo = round(10 * DIFICULDADES.get(self.dificuldade, {}).get("zumbis", 1.0))  # no resgate: sem multidao
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
            if self.resgate is not None:
                self.t_spawn = 2.0
            elif na_cidade:  # chegando na cidade enche rapido, depois vai devagar
                self.t_spawn = 0.6 if len(self.zumbis) < alvo // 2 else 2.0
            else:
                self.t_spawn = 5.0
            self.criar_zumbi(esc)
        visao = (190 * (1 - esc) + esc * (150 if self.lanterna else 95)) * DIFICULDADES.get(self.dificuldade, {}).get("visao", 1.0)
        if self.chuva:
            visao *= 0.8
        if m.no_capim(p.x, p.y):
            visao *= 0.35
        if self.agachado:
            visao *= 0.55
        if self.__dict__.get("deitado"):
            visao *= 0.3
        zonas = list(self.zonas_seguras())
        self.arames = [c for c in self.construidos if c["tipo"] in ("arame", "espinhos")]
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
            self.dano_arame(z, dt)
            if z.tipo in ("cuspidor", "gritador"):
                self.especial(z, d, dt)
            if 0.01 < d < p.r + z.r - 2 and not self.dirigindo and not self.telhado_b:
                ex_ = (p.r + z.r - 2 - d) * 0.5  # se mesmo assim entrou, empurra para fora
                nx_, ny_ = z.x - dx / d * ex_, z.y - dy / d * ex_
                if not self.mundo.bloqueado(nx_, ny_, z.r):
                    z.x, z.y = nx_, ny_
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
                            z.na_rua = True
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
                    if z.estado == "perseguir" and d < p.r + z.r + 2:
                        vel = 0  # ja encostou em voce: nao entra dentro do seu corpo
                    ang_ = math.atan2(ay, ax)
                    if z.tipo == "cuspidor" and 130 < d < 360 and m.linha_livre(z.x, z.y, p.x, p.y):
                        vel = 0  # fica de longe cuspindo
                        z.ang = ang_
                    elif z.tipo == "gritador" and z.estado == "perseguir" and d < 170:
                        ang_ += math.pi  # foge de voce
                    self.passo_zumbi(z, ang_, vel * dt)
            elif not z.parado:
                rapido = 0.55 if getattr(z, "na_rua", False) and na_cidade else 0.3
                self.passo_zumbi(z, z.ang, z.vel * rapido * dt * self.no_arame(z, dt), vagando=True)
            # ataque
            if d < z.r + p.r + 8 and z.t_ataque <= 0 and not seguro and self.esquiva <= 0 and not self.telhado_b \
                    and not self.dirigindo and not self.__dict__.get("embarcou") and self.no_elevado is None:
                z.t_ataque = {"gordo": 1.4, "corredor": 0.7, "gigante": 1.7}.get(z.tipo, 1.0)
                dano_z = z.dano * DIFICULDADES.get(self.dificuldade, {}).get("dano", 1.0)
                if self.calca > 0:  # a calca reforcada segura um pouco
                    dano_z *= 0.85
                    self.calca = max(0.0, self.calca - z.dano * 0.4)
                    if self.calca <= 0:
                        self.msg("Sua CALÇA reforçada rasgou!", (255, 170, 120))
                if self.colete > 0:  # o colete segura boa parte da mordida
                    dano_z *= 0.55
                    self.colete = max(0.0, self.colete - z.dano * 0.8)
                    if self.colete <= 0:
                        self.msg("Seu COLETE quebrou! Faça outro na bancada.", (255, 170, 120))
                p.vida -= dano_z
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

    def especial(self, z, d, dt):
        """Cuspidor cospe acido de longe; gritador grita e chama a horda."""
        p = self.p
        z.t_esp = getattr(z, "t_esp", random.uniform(1.0, 2.0)) - dt
        if z.estado not in ("perseguir", "investigar") or self.dirigindo and z.tipo == "cuspidor":
            return
        if z.tipo == "cuspidor" and 90 < d < 420 and z.t_esp <= 0 and self.mundo.linha_livre(z.x, z.y, p.x, p.y):
            z.t_esp = random.uniform(2.2, 3.0)
            ang = math.atan2(p.y - z.y, p.x - z.x) + random.uniform(-0.06, 0.06)
            self.acidos.append([z.x + math.cos(ang) * 16, z.y + math.sin(ang) * 16, math.cos(ang) * 330, math.sin(ang) * 330, 0.0])
            self.som("faca", 0.4)
            self.aviso_especial("cuspidor", "CUSPIDOR! Ele cospe ÁCIDO de longe. Desvie e não pise na poça verde!")
        if z.tipo == "gritador" and d < 650 and z.t_esp <= 0:
            z.t_esp = 14.0
            self.ondas.append([z.x, z.y, 0.0])
            self.fazer_barulho(z.x, z.y, 1300)
            self.tremor = max(self.tremor, 5)
            self.som("gemido0", 1.0)
            self.som("gemido2", 1.0)
            # chama mais zumbis de longe
            if self.metro is None:
                for _ in range(3):
                    for _t in range(10):
                        a = random.uniform(0, 6.283)
                        x, y = p.x + math.cos(a) * random.uniform(650, 850), p.y + math.sin(a) * random.uniform(650, 850)
                        if not self.mundo.bloqueado(x, y, 14) and self.mundo.tile_px(x, y) not in SOLIDO:
                            nz = Zumbi(x, y, "normal", random.randrange(len(self.spr_z["normal"])), random)
                            nz.estado = "perseguir"
                            nz.alvo = (p.x, p.y)
                            self.zumbis.append(self.equipar_zumbi(nz))
                            break
            self.aviso_especial("gritador", "GRITADOR! O grito dele chama a horda. Mate ele primeiro!", sempre=True)

    def aviso_especial(self, tipo, txt, sempre=False):
        vistos = self.__dict__.setdefault("vistos_especiais", set())
        if tipo not in vistos or sempre:
            vistos.add(tipo)
            self.msg(txt, (190, 255, 120) if tipo == "cuspidor" else (255, 150, 150))

    def atualizar_acido(self, dt):
        p = self.p
        m = self.mundo
        for a in list(self.acidos):
            a[0] += a[2] * dt
            a[1] += a[3] * dt
            a[4] += dt
            bateu = (a[0] - p.x) ** 2 + (a[1] - p.y) ** 2 < 18 ** 2 and not self.telhado_b and not self.dirigindo \
                and self.esquiva <= 0 and not self.__dict__.get("embarcou")
            if bateu or a[4] > 1.3 or m.bloqueado(a[0], a[1], 3):
                self.acidos.remove(a)
                self.pocas.append([a[0], a[1], 6.0])
                if bateu:
                    p.vida -= 9 * DIFICULDADES.get(self.dificuldade, {}).get("dano", 1.0)
                    self.dano_t = 0.45
                    self.som("dor", 0.6)
                    self.msg("O ÁCIDO te queimou!", (190, 255, 120))
                for _ in range(8):
                    an = random.uniform(0, 6.283)
                    self.particula(a[0], a[1], math.cos(an) * 90, math.sin(an) * 90, 0.4, (170, 240, 70), 3)
        for po in list(self.pocas):
            po[2] -= dt
            if po[2] <= 0:
                self.pocas.remove(po)
            elif (po[0] - p.x) ** 2 + (po[1] - p.y) ** 2 < 26 ** 2 and not self.telhado_b and not self.dirigindo:
                p.vida -= 7 * dt
                self.dano_t = max(self.dano_t, 0.2)
        for o in list(self.ondas):
            o[2] += dt
            if o[2] > 1.2:
                self.ondas.remove(o)

    def dano_arame(self, z, dt):
        """Espinhos/arame: machucam o zumbi todo quadro, parado ou andando."""
        for c in self.arames:
            if (c["x"] - z.x) ** 2 + (c["y"] - z.y) ** 2 < 34 * 34:
                z.hp -= (50 if c["tipo"] == "espinhos" else 18) * dt * (0.5 if z.tipo == "bombeiro" else 1.0)
                z.flash = 0.05
                if random.random() < dt * 3:
                    self.particula(z.x, z.y, random.uniform(-30, 30), random.uniform(-30, 30), 0.4, (120, 20, 16), 3)
                return

    def desenhar_equip_zumbi(self, tela, z, sx, sy, a):
        ca, sa = math.cos(a), math.sin(a)
        if z.colete:  # colete: placa larga nos ombros (de lado a lado do corpo)
            w_, h_ = z.r - 1, 6
            pts = [(sx + ca * dx_ - sa * dy_, sy + sa * dx_ + ca * dy_)
                   for dx_, dy_ in ((-h_, -w_), (h_ - 2, -w_), (h_ - 2, w_), (-h_, w_))]
            pygame.draw.polygon(tela, (64, 72, 50), pts)
            pygame.draw.polygon(tela, (28, 32, 22), pts, 2)
            pygame.draw.line(tela, (120, 110, 70), pts[0], pts[3], 2)
        if z.mao:  # na mao direita, apontando para frente
            hx = sx + ca * (z.r - 2) - sa * (z.r - 1)
            hy = sy + sa * (z.r - 2) + ca * (z.r - 1)
            ex, ey = hx + ca * 22, hy + sa * 22
            if z.mao == "taco":
                pygame.draw.line(tela, (110, 70, 36), (hx, hy), (ex, ey), 5)
                for k in (0.65, 0.85):  # pregos
                    px, py = hx + ca * 22 * k, hy + sa * 22 * k
                    pygame.draw.line(tela, (200, 200, 210), (px - sa * 4, py + ca * 4), (px + sa * 4, py - ca * 4), 1)
            else:
                pygame.draw.line(tela, (96, 62, 32), (hx, hy), (ex, ey), 4)
                lam = [(ex - sa * 1, ey + ca * 1), (ex + sa * 9 - ca * 3, ey - ca * 9 - sa * 3),
                       (ex + sa * 9 - ca * 11, ey - ca * 9 - sa * 11), (ex - ca * 8, ey - sa * 8)]
                pygame.draw.polygon(tela, (160, 166, 176), lam)
                pygame.draw.polygon(tela, (60, 62, 70), lam, 1)
        if z.capacete:  # capacete na cabeca
            hx_, hy_ = int(sx + ca * 2), int(sy + sa * 2)
            pygame.draw.circle(tela, (40, 48, 30), (hx_, hy_), max(6, z.r - 4))
            pygame.draw.circle(tela, (92, 108, 70), (hx_, hy_), max(4, z.r - 6))
            pygame.draw.circle(tela, (130, 146, 104), (hx_ - 2, hy_ - 2), 2)

    def no_arame(self, z, dt):
        """Arame farpado/espinhos: deixam o zumbi lento."""
        for c in self.arames:
            if (c["x"] - z.x) ** 2 + (c["y"] - z.y) ** 2 < 34 * 34:
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

    def atualizar_metro(self):
        """Ve se voce esta na estacao de metro; ao descer ou subir, troca os zumbis."""
        m = self.mundo
        p = self.p
        novo = m.metro_em(p.x, p.y) if getattr(m, "metros", None) else None
        if novo == self.metro:
            return
        self.metro = novo
        self.zumbis = []
        if novo is None:
            self.msg("Você voltou para a rua.", (220, 230, 200))
            return
        mt = m.metros[novo]
        self.msg(f"ESTAÇÃO {mt['cidade'].upper()}: o trem está parado. Cuidado, tem zumbi aqui embaixo!",
                 (255, 210, 140))
        x0, y0, w, h = mt["sala"]
        qtd = round(11 * DIFICULDADES.get(self.dificuldade, {}).get("zumbis", 1.0))
        for _ in range(400):
            if len(self.zumbis) >= qtd:
                break
            x = (x0 + random.uniform(1.5, w - 1.5)) * T
            y = (y0 + random.uniform(1.5, h - 1.5)) * T
            if math.hypot(x - p.x, y - p.y) < 420 or m.bloqueado(x, y, 14):
                continue
            r = random.random()
            tipo = "corredor" if r < 0.15 else "gordo" if r < 0.35 else "normal"
            z = self.equipar_zumbi(Zumbi(x, y, tipo, random.randrange(len(self.spr_z[tipo])), random))
            z.parado = random.random() < 0.6
            self.zumbis.append(z)

    def criar_zumbi(self, esc):
        p = self.p
        m = self.mundo
        if self.metro is not None:  # la embaixo so tem os zumbis que ja estavam na estacao
            return
        for _ in range(12):
            a = random.uniform(0, 6.283)
            if self.resgate is not None:
                d = random.uniform(700, 1000)
            elif m.cidade_perto(p.x, p.y, 1.3):  # na cidade nasce mais perto (mas fora da tela), dentro da cidade
                d = random.uniform(700, 950)
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
            if tipo != "gigante":  # zumbis especiais
                r2 = random.random()
                k2 = 2.0 if self.capitulo == 2 else 1.0  # na dimensao sombria tem o dobro de especiais
                if r2 < 0.045 * k2:
                    tipo = "cuspidor"
                elif r2 < 0.075 * k2:
                    tipo = "gritador"
                elif r2 < 0.11 * k2:
                    tipo = "bombeiro"
            z = self.equipar_zumbi(Zumbi(x, y, tipo, random.randrange(len(self.spr_z[tipo])), random))
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
        if not self.dono:  # mundo com codigo nao ganha moedas
            self.moedas += MOEDAS_ZERAR_CAP2 if self.capitulo == 2 else MOEDAS_ZERAR
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
        # o helicoptero indo embora com voce, cruzando a tela
        base = self.__dict__.get("spr_heli")
        if base is None:
            base = self.spr_heli = G.sprite_helicoptero()
        t = time.time()
        hx = (t * 160) % (W + 600) - 300
        hy = 560 + math.sin(t * 1.3) * 10
        self.tela.blit(base, (hx - base.get_width() / 2, hy - base.get_height() / 2))
        for k in range(4):
            a = t * 22 + k * math.pi / 2
            pygame.draw.line(self.tela, (24, 24, 26), (hx + 9, hy), (hx + 9 + math.cos(a) * 112, hy + math.sin(a) * 112), 5)
        pygame.draw.line(self.tela, (150, 120, 70), (hx - 6, hy + 10), (hx - 6, hy + 70), 2)
        pygame.draw.circle(self.tela, (196, 150, 110), (int(hx - 6), int(hy + 74)), 7)
        thor = self.__dict__.get("thor_junto")
        if thor:
            cz = self.rot(("cao_colo",), self.spr_cao[0], 90, 90)
            self.tela.blit(cz, (hx, hy + 70))
        quem = self.nick().upper() if self.nick() else "VOCÊ"
        self.texto(f"{quem} E O THOR FORAM RESGATADOS!" if thor else
                   (f"{quem} FOI RESGATADO!" if self.nick() else "VOCÊ FOI RESGATADO!"), (W // 2, 190),
                   self.f_titulo if not thor and not self.nick() else self.f_grande, (120, 230, 140), centro=True)
        self.texto(f"Sobreviveu {self.dia} dias e derrubou {self.mortes} zumbis.", (W // 2, 280), self.f_med2, centro=True)
        self.texto("O helicóptero levou você e o Thor para a zona segura. Ele abanou o rabo o caminho todo!"
                   if thor else "O helicóptero levou você para a zona segura. Parabéns, sobrevivente.",
                   (W // 2, 320), self.f_med2, centro=True)
        self.texto("Mundo com código de dono: não ganha moedas." if self.dono else
                   f"+{MOEDAS_ZERAR_CAP2 if self.capitulo == 2 else MOEDAS_ZERAR} MOEDAS por zerar o "
                   f"{'CAPÍTULO 2' if self.capitulo == 2 else 'capítulo 1'}!  (agora você tem {self.moedas})", (W // 2, 366),
                   self.f_med, (255, 220, 110), centro=True)
        if self.capitulo == 1:
            self.texto("No caminho, o helicóptero entrou numa LUZ ROXA no céu... e o motor começou a falhar!",
                       (W // 2, 402), self.f_med, (210, 160, 255), centro=True)
            if self.botao("CAPÍTULO 2: a Dimensão Sombria", W // 2, 450, w=460):
                self.ir_capitulo2()
                return
            if self.botao("Menu", W // 2, 516):
                self.mundo = None
                self.estado = "menu"
        else:
            self.texto("VOCÊ ZEROU OS DOIS CAPÍTULOS! Você é uma lenda.", (W // 2, 410), self.f_med, (255, 220, 110),
                       centro=True)
            if self.botao("Menu", W // 2, 470):
                self.mundo = None
                self.estado = "menu"

    def ir_capitulo2(self):
        """Depois de zerar: voce e o Thor atravessam o portal. Mundo novo, mesmas coisas na mochila."""
        leva = dict(inv=dict(self.inv), armas=list(self.armas), pente=dict(self.pente), silen=list(self.silen),
                    arma=self.arma, niveis=dict(self.niveis), miras=list(self.miras),
                    reforco_mochila=self.reforco_mochila, nivel_mochila=self.nivel_mochila, colete=self.colete,
                    capacete=self.capacete, calca=self.calca, nivel_lanterna=self.nivel_lanterna,
                    dificuldade=self.dificuldade, dono=self.dono, mochila_infinita=self.mochila_infinita,
                    moedas=self.moedas, nome=self.__dict__.get("nome_mundo", "Meu mundo"), mortes=self.mortes)
        cao = self.cao
        tinha_thor = bool(cao and cao.get("amigo"))
        if tinha_thor and cao.get("morto"):  # o Thor tinha morrido: no capitulo 2 ele volta vivo
            thor = dict(vida=100.0, fome=100.0, sede=100.0, morto=False)
            self.thor_voltou = True
        else:
            thor = dict(vida=cao.get("vida", 100), fome=cao.get("fome", 100), sede=cao.get("sede", 100)) if tinha_thor else None
        semente = (self.mundo.seed * 7 + 13) % (10 ** 9) if self.mundo else None

        def passos():
            yield from self.novo_jogo_passos(seed=semente, tamanho=N_CAP2)
            for k, v in leva.items():
                if k == "nome":
                    self.nome_mundo = v + " · Cap. 2"
                else:
                    setattr(self, k, v)
            self.inv.pop("peca", None)
            self.capitulo = 2
            self.fechar_portas_metro()
            self.cache_chao.clear()
            self.cache_copa.clear()
            self.telhados = {}
            if thor:  # o Thor atravessou o portal com voce
                self.cao.update(amigo=True, x=self.p.x + 40, y=self.p.y + 30, sentado=False, modo="quieto", **thor)
            self.msgs = []
            self.comecar_queda(bool(thor))
            self.salvar()
        self.comecar_carga(passos())

    def comecar_queda(self, thor):
        """Cena: o helicoptero vem caindo, girando e soltando fumaca, e bate no chao. Voces saem dos destrocos."""
        p = self.p
        self.intro_cap2 = 0.0
        self.queda_thor = thor
        self.queda_ponto = (p.x, p.y)
        self.heli = [p.x - 1300, p.y - 900, 0.0]
        self.heli_fase = "caindo"
        self.heli_ang = math.atan2(900, 1300)
        self.heli_alt = 1.6
        self.heli_corda = 0.0
        self.embarcou = True       # voce (e o Thor) ainda estao dentro do helicoptero
        self.thor_junto = thor
        self.zumbis = []
        self.hora = 17.5
        self.cam = [p.x, p.y]
        self.som("helicoptero", 1.0)

    def atualizar_queda(self, dt):
        """Roda a cena da queda. Devolve True enquanto o helicoptero ainda nao caiu."""
        t = self.intro_cap2
        self.intro_cap2 = t + dt
        p = self.p
        px, py = self.queda_ponto
        if self.heli is not None and self.heli_fase == "caindo":
            alvo = (px + 90, py - 40)
            dx, dy = alvo[0] - self.heli[0], alvo[1] - self.heli[1]
            d = math.hypot(dx, dy)
            vel = 520.0
            if d > 10:
                self.heli[0] += dx / d * min(d, vel * dt)
                self.heli[1] += dy / d * min(d, vel * dt)
            self.heli_ang += dt * (3 + t * 2.5)          # girando sem controle
            self.heli_alt = max(0.9, 1.6 - t * 0.2)
            self.tremor = max(self.tremor, 2 + t)
            p.x, p.y = self.heli[0], self.heli[1] + 70   # a camera vai junto
            if random.random() < dt * 40:  # fumaca preta e fogo no motor
                self.particula(self.heli[0] + random.uniform(-10, 10), self.heli[1] + random.uniform(-10, 10),
                               random.uniform(-40, 40), random.uniform(-60, 10), random.uniform(0.6, 1.2),
                               random.choice([(40, 40, 40), (60, 56, 52), (255, 140, 40)]), random.randint(4, 8))
            if random.random() < dt * 2:
                self.som("helicoptero", 0.9)
            if d <= 10 or t > 4.5:
                self.bater_helicoptero()
            return True
        # depois da batida: titulo do capitulo e fogo nos destrocos
        if random.random() < dt * 25 and t < 40:
            wx, wy = self.queda_destrocos
            self.particula(wx + random.uniform(-30, 30), wy + random.uniform(-14, 14), random.uniform(-10, 10),
                           random.uniform(-60, -20), random.uniform(0.5, 1.0),
                           random.choice([(255, 150, 40), (255, 90, 30), (60, 56, 52)]), random.randint(3, 7), "f")
        if t > 14:
            self.intro_cap2 = None
        return False

    def bater_helicoptero(self):
        p = self.p
        hx, hy = self.heli[0], self.heli[1] + 60
        self.queda_destrocos = (hx, hy)
        # destrocos queimados no chao
        base = self.__dict__.get("spr_heli") or G.sprite_helicoptero()
        quebrado = pygame.transform.rotate(base, -math.degrees(self.heli_ang) + 20)
        quebrado = quebrado.copy()
        quebrado.fill((70, 60, 56, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self.decalque(quebrado, hx - quebrado.get_width() / 2, hy - quebrado.get_height() / 2)
        for _ in range(60):
            a = random.uniform(0, 6.283)
            v = random.uniform(80, 380)
            cor = random.choice([(255, 200, 60), (255, 120, 30), (240, 60, 20), (90, 80, 70)])
            self.particula(hx, hy, math.cos(a) * v, math.sin(a) * v, random.uniform(0.4, 1.0), cor, random.randint(3, 8), "f")
        self.flash_t = 0.2
        self.flash_pos = (hx - self.cam[0] + W / 2, hy - self.cam[1] + H / 2)
        self.tremor = 22
        self.som("rpg", 1.0) if "rpg" in self.sons else self.som("espingarda", 1.0)
        self.heli = None
        self.heli_fase = None
        self.embarcou = False
        # voce e o Thor saem rolando dos destrocos
        sx, sy = self.queda_ponto
        for k in range(16):
            a = k / 16 * 6.283
            x, y = hx + math.cos(a) * 110, hy + math.sin(a) * 110
            if not self.mundo.bloqueado(x, y, 14):
                sx, sy = x, y
                break
        p.x, p.y = sx, sy
        p.vida = max(40, p.vida - 15)
        self.cam = [p.x, p.y]
        if self.queda_thor and self.cao:
            self.cao.update(x=sx + 36, y=sy + 20, sentado=False)
        self.msg("O HELICÓPTERO CAIU! Você saiu dos destroços machucado...", (255, 170, 120))
        if self.queda_thor:
            if self.__dict__.pop("thor_voltou", False):
                self.msg("O THOR ESTÁ VIVO! A luz roxa trouxe ele de volta!", (255, 220, 140))
            else:
                self.msg("O Thor saiu junto! Ele está do seu lado, abanando o rabo.", (255, 220, 140))
        self.msg("Esse lugar é estranho... o céu é ROXO e os zumbis são MAIS FORTES.", (230, 200, 255))
        self.msg("Ache as 5 peças do rádio de novo e chame o resgate. Zerando: +18 MOEDAS!", (255, 220, 110))

    def desenhar_titulo_cap2(self):
        t = self.intro_cap2
        if t is None or self.heli is not None:
            return
        tq = t - 0  # comeca logo depois da batida
        dur = 9.0
        if tq > dur:
            return
        a = min(1.0, tq / 1.2) * min(1.0, (dur - tq) / 1.5)
        img = self.__dict__.get("img_cap2")
        if img is None:
            img = self.img_cap2 = self.f_morte.render("CAPÍTULO 2", True, (215, 150, 255))
            self.img_cap2_s = self.f_morte.render("CAPÍTULO 2", True, (30, 0, 40))
            self.img_cap2_sub = self.f_grande.render("A DIMENSÃO SOMBRIA", True, (240, 225, 255))
        for im, (x, y) in ((self.img_cap2_s, (W // 2 + 6, 150 + 7)), (img, (W // 2, 150)), (self.img_cap2_sub, (W // 2, 230))):
            c = im.copy()
            c.set_alpha(int(255 * a))
            self.tela.blit(c, c.get_rect(center=(x, y)))

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
            base = m.mapa.copy()  # o mapa mostra o mundo inteiro
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
            cor = {"metropole": (255, 140, 110), "cidade": (255, 230, 170)}.get(c["tipo"], (220, 225, 215))
            fonte = self.f_med if c["tipo"] != "vila" else self.f_peq
            nome = c["nome"].upper() if c["tipo"] == "metropole" else c["nome"]
            self.texto(nome, P(x, y - c["raio"] * T - 26), fonte, cor, centro=True)
        for b in m.construcoes:
            if b["tipo"] in ("shopping", "mercado", "gas"):
                px, py = P((b["x"] + b["w"] / 2) * T, (b["y"] + b["h"] / 2) * T)
                cor, letra = {"shopping": ((150, 90, 220), "S"), "mercado": ((60, 130, 210), "M"),
                              "gas": ((230, 160, 30), "P")}[b["tipo"]]
                pygame.draw.circle(self.tela, (0, 0, 0), (px, py), 8)
                pygame.draw.circle(self.tela, cor, (px, py), 7)
                self.texto(letra, (px, py), self.f_peq, (255, 255, 255), centro=True, sombra=False)
        for b in m.construcoes:
            x = (b["x"] + b["w"] / 2) * T
            y = (b["y"] + b["h"] / 2) * T
            if b["tipo"] in ("hospital", "posto"):
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
        self.texto("S = shopping   ·   M = mercado   ·   P = posto de gasolina", (lx, y + 74), self.f_peq, (170, 170, 170))
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
                s.blit(txt, txt.get_rect(center=(max(60, cx - rr - 62), cy)))
            pygame.draw.rect(s, (150, 152, 148), (0, 0, w, h), 5)
            for _ in range(10):
                pygame.draw.circle(s, (150, 140, 120), (r.randint(0, w), r.randint(0, h)), r.randint(3, 9))
        elif b["tipo"] in ("mercado", "shopping", "gas"):
            fundo = {"mercado": (60, 110, 170), "shopping": (150, 154, 162), "gas": (200, 60, 40)}[b["tipo"]]
            s.fill(fundo)
            if b["tipo"] == "shopping":  # claraboias
                for gx in range(40, w - 40, 90):
                    for gy in range(40, h - 40, 90):
                        pygame.draw.rect(s, (120, 180, 210), (gx, gy, 46, 46))
                        pygame.draw.rect(s, (90, 94, 100), (gx, gy, 46, 46), 3)
            else:
                for x_ in range(0, w, 24):
                    pygame.draw.line(s, G.tom(fundo, -14), (x_, 0), (x_, h), 2)
            if b["tipo"] == "gas":
                pygame.draw.rect(s, (250, 210, 40), (0, h // 2 - 10, w, 20))
            nome = {"mercado": "MERCADO", "shopping": "SHOPPING", "gas": "POSTO"}[b["tipo"]]
            fonte = self.f_titulo if b["tipo"] == "shopping" else self.f_med
            txt = fonte.render(nome, True, (255, 255, 255))
            sh = fonte.render(nome, True, (0, 0, 0))
            s.blit(sh, sh.get_rect(center=(w // 2 + 3, h // 2 + 3)))
            s.blit(txt, txt.get_rect(center=(w // 2, h // 2)))
            pygame.draw.rect(s, G.tom(fundo, -40), (0, 0, w, h), 5)
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
        for px, py in (b.get("portas", []) if b["tipo"] in ("casa", "militar", "hospital", "posto", "mercado",
                                                              "shopping", "gas") else []):
            lx = (px - b["x"]) * T
            ly = (py - b["y"]) * T
            pygame.draw.rect(s, (26, 24, 22), (lx, ly, T, T))
            pygame.draw.rect(s, (200, 170, 90), (lx, ly, T, T), 2)
        if b["tipo"] in ("militar", "hospital", "posto", "mercado", "shopping", "gas"):
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
                claro = b["tipo"] in ("hospital", "posto")  # telhado branco: letra escura
                img = fonte.render("ENTRADA", True, (170, 30, 30) if claro else (255, 220, 120))
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
        for mt in getattr(m, "metros", ()):
            x0_, y0_, w_, h_ = mt["sala"]
            ret_ = pygame.Rect(x0_ * T, y0_ * T, w_ * T, h_ * T)
            if vis.colliderect(ret_):
                spm = self.__dict__.setdefault("spr_metro", {})
                if mt["idx"] not in spm:
                    sp_ = G.sprite_estacao(T, m.seed + mt["idx"])
                    nome_ = self.f_med.render(f"ESTAÇÃO {mt['cidade'].upper()}", True, (240, 240, 250))
                    for k_ in range(2):
                        xx_ = (12 + k_ * 22) * T
                        pygame.draw.rect(sp_, (20, 60, 140), (xx_ - 8, 2, nome_.get_width() + 16, 26), border_radius=4)
                        sp_.blit(nome_, (xx_, 3))
                    spm[mt["idx"]] = sp_
                tela.blit(spm[mt["idx"]], (ret_.x - camx, ret_.y - camy))
            ex_, ey_ = mt["ent"]
            if vis.collidepoint(ex_, ey_):
                spe = self.__dict__.get("spr_entrada_metro")
                if spe is None:
                    spe = self.spr_entrada_metro = G.sprite_entrada_metro()
                tela.blit(spe, (ex_ - camx - 42, ey_ - camy - 55))
                self.texto("METRÔ", (ex_ - camx, ey_ - camy - 72), self.f_peq, (200, 220, 255), centro=True)
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
                elif c["tipo"] == "espinhos":
                    tela.blit(self.spr_espinhos, (c["x"] - camx - 18, c["y"] - camy - 18))
                elif c["tipo"] == "abrigo":
                    tela.blit(self.spr_abrigo, (c["x"] - camx - 56, c["y"] - camy - 56))
                elif c["tipo"] == "bancada":
                    tela.blit(self.spr_bancada, (c["x"] - camx - 32, c["y"] - camy - 20))
        for c in getattr(m, "bancadas", ()):
            if vis.collidepoint(c["x"], c["y"]):
                tela.blit(self.spr_bancada, (c["x"] - camx - 32, c["y"] - camy - 20))
        # o cachorro
        cao = self.cao
        if self.__dict__.get("embarcou") and self.__dict__.get("thor_junto"):
            cao = None  # o Thor esta no helicoptero com voce
        if cao and vis.collidepoint(cao["x"], cao["y"]) and not (cao["amigo"] and (self.dirigindo or self.telhado_b)
                                                                 and math.hypot(cao["x"] - p.x, cao["y"] - p.y) < 30):
            sx, sy = cao["x"] - camx, cao["y"] - camy
            tela.blit(self.spr_sombra, (sx - self.spr_sombra.get_width() / 2 + 3, sy - self.spr_sombra.get_height() / 2 + 5))
            if cao.get("morto"):
                morto = self.__dict__.get("spr_cao_morto")
                if morto is None:
                    morto = pygame.transform.rotate(self.spr_cao[0], 90)
                    morto.fill((110, 100, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    self.spr_cao_morto = morto
                tela.blit(morto, (sx - morto.get_width() / 2, sy - morto.get_height() / 2))
            else:
                spr = self.rot(("cao", int(cao["passo"]) % 2), self.spr_cao[int(cao["passo"]) % 2], math.degrees(cao["ang"]), 6)
                if cao.get("sentado"):
                    spr = pygame.transform.smoothscale(spr, (int(spr.get_width() * 0.8), int(spr.get_height() * 0.8)))
                tela.blit(spr, (sx - spr.get_width() / 2, sy - spr.get_height() / 2))
                if cao.get("sentado") and cao["amigo"]:
                    self.texto("sentado", (sx, sy + 16), self.f_peq, (255, 230, 160), centro=True)
                elif cao.get("recuar", 0) > 0 and cao["amigo"]:
                    self.texto("recuando", (sx, sy + 16), self.f_peq, (180, 220, 255), centro=True)
                if cao["amigo"] and (cao.get("vida", 100) < 100 or cao.get("fome", 100) < 50 or cao.get("sede", 100) < 50):
                    for k_, (v_, cor_) in enumerate(((cao.get("vida", 100), (220, 60, 60)), (cao.get("fome", 100), (230, 160, 60)),
                                                    (cao.get("sede", 100), (80, 150, 230)))):
                        pygame.draw.rect(tela, (20, 20, 20), (sx - 17, sy - 34 + k_ * 5, 34, 4))
                        pygame.draw.rect(tela, cor_, (sx - 17, sy - 34 + k_ * 5, int(34 * max(0, v_) / 100), 4))
            if cao["au"] > 0 and not cao.get("morto"):
                self.texto("AU AU!", (sx, sy - 30), self.f_med, (255, 230, 120), centro=True)
            elif not cao["amigo"] and math.hypot(cao["x"] - p.x, cao["y"] - p.y) < 400:
                self.texto("?", (sx, sy - 28), self.f_med, (200, 230, 255), centro=True)
        # acido do cuspidor e grito do gritador
        for po in self.pocas:
            if vis.collidepoint(po[0], po[1]):
                al = int(150 * min(1.0, po[2] / 1.5))
                sp = pygame.Surface((60, 40), pygame.SRCALPHA)
                pygame.draw.ellipse(sp, (120, 220, 40, al), (0, 0, 60, 40))
                pygame.draw.ellipse(sp, (200, 255, 110, al), (14, 8, 26, 16))
                tela.blit(sp, (po[0] - camx - 30, po[1] - camy - 20))
        for a in self.acidos:
            pygame.draw.circle(tela, (90, 150, 20), (int(a[0] - camx), int(a[1] - camy)), 7)
            pygame.draw.circle(tela, (200, 255, 90), (int(a[0] - camx), int(a[1] - camy)), 5)
            pygame.draw.line(tela, (150, 220, 60), (a[0] - camx, a[1] - camy),
                             (a[0] - a[2] * 0.04 - camx, a[1] - a[3] * 0.04 - camy), 3)
        for o in self.ondas:
            r_ = int(30 + o[2] * 420)
            pygame.draw.circle(tela, (255, 90, 90), (int(o[0] - camx), int(o[1] - camy)), r_, max(1, int(6 * (1.2 - o[2]))))
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
                if z.colete or z.capacete or z.mao:
                    self.desenhar_equip_zumbi(tela, z, sx, sy, math.radians(ang))
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
        if self.__dict__.get("deitado"):
            dei = self.__dict__.setdefault("spr_deitado", {})
            if self.arma not in dei:
                b = self.spr_j[self.arma]
                d = pygame.transform.smoothscale(b, (int(b.get_width() * 1.1), int(b.get_height() * 0.62)))
                d.fill((170, 165, 160, 255), special_flags=pygame.BLEND_RGBA_MULT)
                dei[self.arma] = d
            spr = self.rot(("jd", self.arma), dei[self.arma], math.degrees(p.ang), 4)
        elif self.agachado:
            agach = self.__dict__.setdefault("spr_agachado", {})
            if self.arma not in agach:
                b = self.spr_j[self.arma]
                agach[self.arma] = pygame.transform.smoothscale(b, (int(b.get_width() * 0.82), int(b.get_height() * 0.82)))
            spr = self.rot(("ja", self.arma), agach[self.arma], math.degrees(p.ang), 4)
        else:
            spr = self.rot(("j", self.arma), self.spr_j[self.arma], math.degrees(p.ang), 4)
        if self.dirigindo:
            c = self.dirigindo
            base = self.mundo.base_carro[c["spr"]]
            sc = self.rot(("carro", c["spr"]), base, -c["ang"], 4)
            sombra = self.spr_sombra_gg
            tela.blit(sombra, (psx - sombra.get_width() / 2 + 6, psy - sombra.get_height() / 2 + 8))
            tela.blit(sc, (psx - sc.get_width() / 2, psy - sc.get_height() / 2))
        elif not self.__dict__.get("embarcou"):
            tela.blit(spr, (psx - spr.get_width() / 2, psy - spr.get_height() / 2))
        spr_jog = spr
        self.spr_jog_atual = spr
        nome_ = "Piloto do Claude" if self.__dict__.get("piloto") else self.nick()
        if nome_ and not self.dirigindo and not self.__dict__.get("embarcou"):
            self.texto(nome_, (psx, psy - 40), self.f_peq, (255, 255, 255), centro=True)
        for c in self.construidos:
            if c["tipo"] == "barricada" and vis.collidepoint(c["x"], c["y"]):
                spr = self.rot(("bar",), self.spr_barricada, c["ang"] - 90, 3)
                tela.blit(spr, (c["x"] - camx - spr.get_width() / 2, c["y"] - camy - spr.get_height() / 2))
            elif c["tipo"] in ("muro", "portao") and vis.collidepoint(c["x"], c["y"]):
                if c["tipo"] == "muro":
                    base, chave = self.spr_muro, ("muro",)
                elif c.get("aberto"):
                    base, chave = self.spr_portao_aberto, ("portao_a",)
                else:
                    base, chave = self.spr_portao, ("portao",)
                spr = self.rot(chave, base, c["ang"] - 90, 3)
                tela.blit(spr, (c["x"] - camx - spr.get_width() / 2, c["y"] - camy - spr.get_height() / 2))
            elif c["tipo"] == "bau" and vis.collidepoint(c["x"], c["y"]):
                tela.blit(self.spr_bau, (c["x"] - camx - 20, c["y"] - camy - 15))
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
        dentro = None if self.telhado_b else m.predio_em(p.x, p.y)
        vistos = set()
        vistos_b = []
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                for b in m.pred_ch.get((cx, cy), ()):
                    if b["id"] in vistos or b["tipo"] == "torre":
                        continue
                    vistos.add(b["id"])
                    vistos_b.append(b)
                    alvo = 0 if b is dentro else 255
                    a = self.alfa_telhado.get(b["id"], 255)
                    a += clamp(alvo - a, -40, 40)
                    self.alfa_telhado[b["id"]] = a
                    if a > 0:
                        s = self.telhado(b)
                        s.set_alpha(None if a >= 255 else a)
                        tela.blit(s, (b["x"] * T - camx, b["y"] * T - camy))
        # escadas encostadas nas paredes
        for b in vistos_b:
            e = b.get("escada")
            if e:
                spr = self.spr_escada if e["lado"] in "NS" else self.rot(("escada",), self.spr_escada, 90, 90)
                ex = (e["fora"][0] + e["dentro"][0]) / 2
                ey = (e["fora"][1] + e["dentro"][1]) / 2
                tela.blit(spr, (ex - camx - spr.get_width() / 2, ey - camy - spr.get_height() / 2))
        if self.telhado_b:  # voce em cima do telhado
            tela.blit(self.spr_sombra, (psx - self.spr_sombra.get_width() / 2 + 6, psy - self.spr_sombra.get_height() / 2 + 8))
            tela.blit(spr_jog, (psx - spr_jog.get_width() / 2, psy - spr_jog.get_height() / 2))
        if m.torre and vis.colliderect(pygame.Rect(m.torre["x"] * T, m.torre["y"] * T, 9 * T, 9 * T)):
            tela.blit(self.spr_torre, ((m.torre["x"] + 4.5) * T - camx - 75, (m.torre["y"] + 4.5) * T - camy - 75))
        if self.metro is None:
            self.desenhar_elevados(camx, camy, vis)
            if self.capitulo == 2:  # na dimensao sombria a estacao fica escondida embaixo da mata
                self.cobrir_estacoes(camx, camy, vis)
        # jogador debaixo de arvore/capim: contorno
        if m.no_capim(p.x, p.y) or self.debaixo_arvore():
            pygame.draw.circle(tela, (255, 255, 255), (int(psx), int(psy)), 15, 1)
        # fantasma da construcao
        if self.modo_construir is not None:
            self.desenhar_fantasma(camx, camy)
        if self.metro is not None:  # debaixo da terra: em volta da estacao e tudo terra (preto)
            x0_, y0_, w_, h_ = m.metros[self.metro]["sala"]
            r_ = pygame.Rect(x0_ * T - camx, y0_ * T - camy, w_ * T, h_ * T)
            preto = (6, 6, 8)
            tela.fill(preto, (0, 0, W, max(0, r_.y)))
            tela.fill(preto, (0, r_.bottom, W, max(0, H - r_.bottom)))
            tela.fill(preto, (0, 0, max(0, r_.x), H))
            tela.fill(preto, (r_.right, 0, max(0, W - r_.right), H))
        # chuva
        if self.chuva and self.metro is None:
            camada = pygame.Surface((W, H), pygame.SRCALPHA)
            if self.estacao() == 2:  # NEVE
                camada.fill((225, 232, 242, 46))
                for g in self.gotas:
                    pygame.draw.circle(camada, (255, 255, 255, 220), (int(g[0]), int(g[1])), 1 + int(g[2] * 2.4))
            else:
                camada.fill((40, 50, 70, 50))
                for g in self.gotas:
                    pygame.draw.line(camada, (180, 200, 230, 110), (g[0], g[1]), (g[0] - 5 * g[2], g[1] + 18 * g[2]), 1)
            tela.blit(camada, (0, 0))
        # luz e escuridao
        self.desenhar_luz(camx, camy, psx, psy)
        if self.heli is not None:  # o helicoptero voa acima de tudo, com as luzes acesas
            self.desenhar_heli(camx, camy)
        if not NAVEGADOR:  # a sombra das bordas pesa no navegador
            tela.blit(self.vinheta, (0, 0))
        if self.dano_t > 0:
            self.vinheta_v.set_alpha(int(255 * self.dano_t / 0.45))
            tela.blit(self.vinheta_v, (0, 0))
        if p.vida < 25:
            self.vinheta_v.set_alpha(int(80 + 60 * math.sin(time.time() * 5)))
            tela.blit(self.vinheta_v, (0, 0))
        if self.luneta:
            self.desenhar_luneta()
        self.desenhar_hud()
        if self.toque and self.estado == "jogo" and self.fake is None:
            self.desenhar_toque()
        if self.intro_cap2 is not None:
            self.desenhar_titulo_cap2()

    def pos_trem(self, el):
        """Onde esta o trem desta linha agora: (comeco, fim) ao longo da linha, ou None se esta parado longe."""
        comp_trem = 680
        L = el["b"] - el["a"]
        vel = 260.0
        ida = (L + comp_trem) / vel
        ciclo = 2 * ida + 30.0  # vai, espera, volta, espera
        t = (self.__dict__.get("relogio_trem", 0.0) + el["fase"] * 7) % ciclo
        if t < ida:
            ini = el["a"] - comp_trem + t * vel
        elif t < ida + 15:
            return None
        elif t < 2 * ida + 15:
            ini = el["b"] - (t - ida - 15) * vel
        else:
            return None
        return ini, ini + comp_trem

    def fechar_portas_metro(self):
        """Capitulo 2: a estacao fica escondida, entao as portas do mato ficam fechadas (so entra pela escada)."""
        m = self.mundo
        for mt in getattr(m, "metros", ()):
            for tx, ty in mt.get("portas", ()):
                m.t[ty * N + tx] = PAREDE_CONC
                m.tn[ty, tx] = PAREDE_CONC

    def cobrir_estacoes(self, camx, camy, vis):
        """A estacao de metro fica EMBAIXO da terra: vista de fora, o lugar dela e so mata fechada."""
        m = self.mundo
        cache = self.__dict__.setdefault("capa_metro", {})
        for mt in getattr(m, "metros", ()):
            x0, y0, w, h = mt["sala"]
            ret = pygame.Rect((x0 - 3) * T, (y0 - 3) * T, (w + 6) * T, (h + 6) * T)
            if not vis.colliderect(ret):
                continue
            chave = (mt["idx"], self.estacao(), self.capitulo)
            if chave not in cache:
                if len(cache) > 6:
                    cache.clear()
                r = random.Random(m.seed + mt["idx"] * 77)
                capa = pygame.Surface(ret.size, pygame.SRCALPHA)
                capa.fill((30, 58, 28, 255), (2 * T, 2 * T, ret.w - 4 * T, ret.h - 4 * T))  # chao escuro so no meio
                for _ in range(ret.w * ret.h // 900):
                    c_ = r.randint(-8, 10)
                    pygame.draw.circle(capa, (34 + c_, 64 + c_, 30 + c_),
                                       (r.randint(2 * T, ret.w - 2 * T), r.randint(2 * T, ret.h - 2 * T)), r.randint(6, 18))
                copas = m.spr_folhosa + m.spr_pinheiro
                for yy in range(T, ret.h - T, 34):
                    for xx in range(T, ret.w - T, 34):
                        sp = r.choice(copas)
                        capa.blit(sp, (xx + r.randint(-12, 12) - sp.get_width() // 2 + 17,
                                       yy + r.randint(-12, 12) - sp.get_height() // 2 + 17))
                cache[chave] = self.tingir(capa, copa=True)
            tela = self.tela
            tela.blit(cache[chave], (ret.x - camx, ret.y - camy))

    def desenhar_elevados(self, camx, camy, vis):
        tela = self.tela
        m = self.mundo
        cache = self.__dict__.setdefault("spr_elevado", {})
        for i, el in enumerate(getattr(m, "elevados", ())):
            h_ = el["dir"] == "h"
            ret = (pygame.Rect(el["a"], el["fixo"] - 75, el["b"] - el["a"], 150) if h_ else
                   pygame.Rect(el["fixo"] - 75, el["a"], 150, el["b"] - el["a"]))
            if not vis.colliderect(ret.inflate(80, 80)):
                continue
            if i not in cache:
                rel = [(px - el["a"]) if h_ else (py - el["a"]) for px, py in el["pilares"]]
                viga = G.sprite_elevado(el["b"] - el["a"], rel, T)
                sombra = pygame.Surface(viga.get_size(), pygame.SRCALPHA)
                sombra.fill((0, 0, 0, 255))
                sombra.blit(viga, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                sombra.fill((0, 0, 0, 70), special_flags=pygame.BLEND_RGBA_MIN)
                trem = G.sprite_trem_elevado()
                if not h_:
                    viga = pygame.transform.rotate(viga, -90)
                    sombra = pygame.transform.rotate(sombra, -90)
                    trem = pygame.transform.rotate(trem, -90)
                cache[i] = (viga, sombra, trem)
            viga, sombra, trem = cache[i]
            # sombra no chao, pe das torres, depois a viga la em cima
            tela.blit(sombra, (ret.x - camx + 26, ret.y - camy + 34))
            for px, py in el["pilares"]:
                if vis.collidepoint(px, py):
                    pygame.draw.circle(tela, (70, 66, 60), (int(px - camx + 6), int(py - camy + 8)), 22)
                    pygame.draw.circle(tela, (120, 116, 106), (int(px - camx), int(py - camy)), 20)
            tela.blit(viga, (ret.x - camx, ret.y - camy))
            for px, py in el["pilares"]:  # escadinha para subir na torre
                if vis.collidepoint(px, py):
                    spr_e = self.spr_escada if not h_ else self.rot(("escada",), self.spr_escada, 90, 90)
                    ox, oy = (0, 34) if h_ else (34, 0)
                    tela.blit(spr_e, (px + ox - camx - spr_e.get_width() / 2, py + oy - camy - spr_e.get_height() / 2))
            pt = self.pos_trem(el)
            if pt:
                ini, fim = pt
                if h_:
                    area = pygame.Rect(el["a"] - camx, ret.y - camy, el["b"] - el["a"], 150)
                    pos = (ini - camx, el["fixo"] - 20 - camy)
                else:
                    area = pygame.Rect(ret.x - camx, el["a"] - camy, 150, el["b"] - el["a"])
                    pos = (el["fixo"] - 20 - camx, ini - camy)
                sh = self.__dict__.get("sombra_trem_" + el["dir"])
                if sh is None:
                    sh = pygame.Surface(trem.get_size(), pygame.SRCALPHA)
                    sh.fill((0, 0, 0, 70))
                    self.__dict__["sombra_trem_" + el["dir"]] = sh
                tela.set_clip(area.move(26, 34))  # sombra do trem no chao
                tela.blit(sh, (pos[0] + 26, pos[1] + 34))
                tela.set_clip(area)  # o trem some no fim da linha
                tela.blit(trem, pos)
                tela.set_clip(None)
            if self.no_elevado == i:  # voce la em cima (por cima do trilho e do trem)
                spr_j = self.__dict__.get("spr_jog_atual")
                if spr_j is not None:
                    psx_, psy_ = self.p.x - camx, self.p.y - camy
                    tela.blit(self.spr_sombra, (psx_ - self.spr_sombra.get_width() / 2 + 5, psy_ - self.spr_sombra.get_height() / 2 + 7))
                    tela.blit(spr_j, (psx_ - spr_j.get_width() / 2, psy_ - spr_j.get_height() / 2))

    def andar_de_trem(self, dt):
        """Em cima do trilho: quando o trem chega, voce entra nele e vai junto ate o fim da linha."""
        p = self.p
        el = self.mundo.elevados[self.no_elevado]
        h_ = el["dir"] == "h"
        pos = p.x if h_ else p.y
        pt = self.pos_trem(el)
        if self.no_trem is None:
            if pt and pt[0] + 20 < pos < pt[1] - 20 and self.__dict__.get("t_pulou", 0) <= 0:
                self.no_trem = pos - pt[0]
                self.tremor = max(self.tremor, 6)
                self.som("golpe", 0.6)
                self.msg("Você ENTROU NO TREM! Ele te leva até o fim da linha. (E pula fora)", (140, 255, 160))
            self.t_pulou = self.__dict__.get("t_pulou", 0) - dt
            return
        if not pt:  # o trem chegou no fim e parou: voce desce dele em cima do trilho
            self.no_trem = None
            self.t_pulou = 3.0
            self.msg("O trem parou no fim da linha. Desça pela escada de uma torre (E).", (255, 220, 140))
            return
        novo = clamp(pt[0] + self.no_trem, el["a"] + 16, el["b"] - 16)
        if h_:
            p.x, p.y = novo, el["fixo"]
        else:
            p.x, p.y = el["fixo"], novo
        self.tremor = max(self.tremor, 1.2)

    def atualizar_trens(self, dt):
        """O trem elevado anda; quando passa perto, a tela treme, faz barulho e chama os zumbis."""
        self.relogio_trem = self.__dict__.get("relogio_trem", 0.0) + dt
        if self.metro is not None:
            return
        p = self.p
        self.t_barulho_trem = self.__dict__.get("t_barulho_trem", 0.0) - dt
        for el in getattr(self.mundo, "elevados", ()):
            pt = self.pos_trem(el)
            if not pt:
                continue
            meio = (pt[0] + pt[1]) / 2
            x, y = (meio, el["fixo"]) if el["dir"] == "h" else (el["fixo"], meio)
            d = math.hypot(x - p.x, y - p.y)
            if d < 700:
                self.tremor = max(self.tremor, 2.5 * (1 - d / 700))
                if self.t_barulho_trem <= 0:
                    self.t_barulho_trem = 2.2
                    self.som("trem", 0.9 * (1 - d / 700))
                    self.fazer_barulho(x, y, 380)
                    if d < 450 and not self.__dict__.get("avisou_trem"):
                        self.avisou_trem = True
                        self.msg("Lá em cima passa o TREM ELEVADO! O barulho chama os zumbis.", (255, 220, 140))

    def desenhar_luneta(self):
        """Visao pela luneta: o que esta na mira fica grande, o resto fica preto."""
        tela = self.tela
        mx, my = pygame.mouse.get_pos() if self.fake is None else self.fake["mouse"]
        R = 230
        r = int(R / 1.8)
        ret = pygame.Rect(mx - r, my - r, r * 2, r * 2).clip(tela.get_rect())
        if ret.w > 4 and ret.h > 4:
            perto = pygame.transform.smoothscale(tela.subsurface(ret).copy(), (int(ret.w * 1.8), int(ret.h * 1.8)))
            tela.blit(perto, (mx - (mx - ret.x) * 1.8, my - (my - ret.y) * 1.8))
        mk = self.mascara_luneta
        tela.blit(mk, (mx - mk.get_width() // 2, my - mk.get_height() // 2))
        self.texto("LUNETA  ·  zumbi distraído leva 3x de dano", (W // 2, 24), self.f_peq, (220, 220, 200), centro=True)

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
               "espinhos": self.spr_espinhos,
               "ponte": self.spr_ponte, "bancada": self.spr_bancada,
               "muro": self.rot(("muro",), self.spr_muro, math.degrees(p.ang), 3),
               "portao": self.rot(("portao",), self.spr_portao, math.degrees(p.ang), 3),
               "bau": self.spr_bau}[rec["id"]].copy()
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
        self.texto("CONSTRUIR SUA BASE (B ou ESC sai)", (W // 2, y + 18), self.f_med, centro=True)
        for i, r in enumerate(RECEITAS):
            custo = ", ".join(f"{q} {ITENS[k].lower()}" for k, q in r["custo"].items())
            pode = all(self.inv.get(k, 0) >= q for k, q in r["custo"].items())
            cor = (255, 240, 160) if i == self.modo_construir else ((210, 230, 210) if pode else (150, 140, 140))
            self.texto(f"{(i + 1) % 10}. {r['nome']}: {custo}", (W // 2 - 150, y + 40 + i * 32), self.f_peq, cor)

    def atualizar_heli(self, dt):
        """Helicoptero: chega voando, para em cima de voce, desce a corda, o soldado atira nos zumbis,
        voce sobe e ele vai embora. Devolve True quando o jogo acabou."""
        p = self.p
        hx, hy, ht = self.heli
        fase = self.__dict__.get("heli_fase", "chegando")
        self.heli[2] += dt
        alvo = (p.x, p.y - 70)
        dx, dy = alvo[0] - hx, alvo[1] - hy
        d = math.hypot(dx, dy)
        if fase == "chegando":
            vel = min(520.0, 140 + d * 0.9)
            if d > 6:
                self.heli[0] += dx / d * min(d, vel * dt)
                self.heli[1] += dy / d * min(d, vel * dt)
                quer = math.atan2(dy, dx)
                dif = (quer - self.heli_ang + math.pi) % (2 * math.pi) - math.pi
                self.heli_ang += dif * min(1.0, 3 * dt)
            self.heli_alt = max(1.0, self.heli_alt - 0.25 * dt)
            if d < 20:
                self.heli_fase = "parado"
                self.msg("A CORDA está descendo! Fique embaixo dela.", (255, 240, 150))
                cao = self.cao
                if cao and cao["amigo"] and not cao.get("morto"):
                    cao["sentado"] = False
                    cao["modo"] = "quieto"
                    if math.hypot(cao["x"] - p.x, cao["y"] - p.y) > 400:  # ele vem correndo
                        cao["x"], cao["y"] = p.x + 60, p.y + 40
                    self.msg("THOR, VEM! Ele vai subir junto com você!", (255, 220, 140))
        elif fase == "parado":
            if d > 2:  # vai acompanhando voce devagar
                self.heli[0] += dx / d * min(d, 150 * dt)
                self.heli[1] += dy / d * min(d, 150 * dt)
            self.heli_alt = max(1.0, self.heli_alt - 0.25 * dt)
            self.heli_corda = min(1.0, self.heli_corda + dt / 1.6)
            if self.heli_corda >= 1 and d < 50:
                self.t_corda = self.__dict__.get("t_corda", 0.0) + dt
                if self.t_corda > 1.4:
                    self.heli_fase = "indo"
                    self.embarcou = True
                    cao = self.cao
                    self.thor_junto = bool(cao and cao["amigo"] and not cao.get("morto"))
                    if self.thor_junto:
                        self.msg("O THOR SUBIU JUNTO! Você segurou ele no colo.", (255, 220, 140))
                    self.heli[2] = 0.0
                    self.dirigindo = None
                    self.acao = None
                    self.msg("VOCÊ SUBIU NA CORDA! Segura firme...", (140, 255, 160))
            else:
                self.t_corda = 0.0
            # vento das helices levanta poeira
            if random.random() < dt * 30:
                a = random.uniform(0, 6.283)
                gx, gy = hx, hy + 70
                self.particula(gx + math.cos(a) * 30, gy + math.sin(a) * 30, math.cos(a) * 240, math.sin(a) * 240,
                               0.6, (180, 170, 140), 3)
        else:  # indo embora com voce
            self.heli_corda = max(0.0, self.heli_corda - dt / 1.2)
            ang = self.heli_ang
            vel = 60 + self.heli[2] * 260
            self.heli[0] += math.cos(ang) * vel * dt
            self.heli[1] += math.sin(ang) * vel * dt
            self.heli_alt = min(1.6, self.heli_alt + 0.18 * dt)
            p.x, p.y = self.heli[0], self.heli[1] + 70  # a camera vai junto
            p.vida = max(p.vida, 1)
            if self.heli[2] > 4.0:
                self.embarcou = False
                self.vencer()
                return True
        # o soldado na porta atira nos zumbis perto
        if fase != "indo" and d < 900:
            self.heli_tiro = self.__dict__.get("heli_tiro", 0.0) - dt
            if self.heli_tiro <= 0:
                perto = [z for z in self.zumbis if (z.x - hx) ** 2 + (z.y - hy - 70) ** 2 < 480 ** 2]
                if perto:
                    z = min(perto, key=lambda z: (z.x - p.x) ** 2 + (z.y - p.y) ** 2)
                    self.heli_tiro = 0.32
                    ox, oy = hx + math.cos(self.heli_ang + 1.57) * 26, hy + math.sin(self.heli_ang + 1.57) * 26
                    self.rastros.append([ox, oy, z.x, z.y, 0.08])
                    self.ferir_zumbi(z, 55, math.atan2(z.y - oy, z.x - ox))
                    if z.hp <= 0:
                        self.matar(z, math.atan2(z.y - oy, z.x - ox))
                    self.som("fuzil", 0.35)
        if random.random() < dt * 2:
            self.som("helicoptero", 0.8)
        self.tremor = max(self.tremor, 1.5 if d < 300 else 0)
        return False

    def desenhar_heli(self, camx, camy):
        tela = self.tela
        hx, hy, _ = self.heli
        sx = hx - camx
        sy = hy - camy
        alt = self.__dict__.get("heli_alt", 1.0)
        ang = math.degrees(self.__dict__.get("heli_ang", 0.0))
        base = self.__dict__.get("spr_heli")
        if base is None:
            base = self.spr_heli = G.sprite_helicoptero()
        # sombra no chao (mais longe quanto mais alto)
        q = int(round(ang / 6)) % 60
        k_ = round(alt, 1)
        chave = (q, k_)
        cache = self.__dict__.setdefault("cache_heli", {})
        if chave not in cache:
            if len(cache) > 200:
                cache.clear()
            corpo = pygame.transform.rotozoom(base, -q * 6, k_)
            sombra = corpo.copy()
            sombra.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MIN)
            sombra.fill((255, 255, 255, 80), special_flags=pygame.BLEND_RGBA_MIN)
            cache[chave] = (corpo, sombra)
        corpo, sombra = cache[chave]
        off = 50 + (alt - 1) * 160
        tela.blit(sombra, (sx - sombra.get_width() / 2 + off * 0.5, sy - sombra.get_height() / 2 + off + 40))
        # corda de resgate
        corda = self.__dict__.get("heli_corda", 0.0)
        if corda > 0:
            fim = sy + 70 * corda
            pygame.draw.line(tela, (150, 120, 70), (sx - 6, sy), (sx - 6, fim), 2)
            pygame.draw.line(tela, (150, 120, 70), (sx + 6, sy), (sx + 6, fim), 2)
            for yy in range(int(sy + 10), int(fim), 10):
                pygame.draw.line(tela, (190, 160, 100), (sx - 6, yy), (sx + 6, yy), 2)
        tela.blit(corpo, (sx - corpo.get_width() / 2, sy - corpo.get_height() / 2))
        if self.__dict__.get("embarcou") and corda > 0.2:  # voce pendurado na corda (com o Thor no colo)
            pygame.draw.circle(tela, (40, 30, 24), (int(sx), int(sy + 70 * corda - 6)), 9)
            pygame.draw.circle(tela, (196, 150, 110), (int(sx), int(sy + 70 * corda - 6)), 6)
            if self.__dict__.get("thor_junto"):
                cz = self.rot(("cao_colo",), self.spr_cao[0], 90, 90)
                tela.blit(cz, (sx + 4, sy + 70 * corda - 4 - cz.get_height() / 2))
        # helice grande (borrao girando + 4 pas) e a helice da cauda
        t = time.time()
        r = int(118 * alt)
        disco = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(disco, (30, 30, 30, 40), (r, r), r)
        pygame.draw.circle(disco, (30, 30, 30, 60), (r, r), r, 3)
        tela.blit(disco, (sx - r + math.cos(math.radians(ang)) * 10 * alt, sy - r + math.sin(math.radians(ang)) * 10 * alt))
        cx_ = sx + math.cos(math.radians(ang)) * 10 * alt
        cy_ = sy + math.sin(math.radians(ang)) * 10 * alt
        for k in range(4):
            a = t * 22 + k * math.pi / 2
            pygame.draw.line(tela, (24, 24, 26), (cx_, cy_), (cx_ + math.cos(a) * r, cy_ + math.sin(a) * r), 5)
        pygame.draw.circle(tela, (60, 60, 64), (int(cx_), int(cy_)), 7)
        tx = sx - math.cos(math.radians(ang)) * 112 * alt
        ty = sy - math.sin(math.radians(ang)) * 112 * alt
        a = t * 40
        pygame.draw.line(tela, (24, 24, 26), (tx - math.cos(a) * 16, ty - math.sin(a) * 16),
                         (tx + math.cos(a) * 16, ty + math.sin(a) * 16), 3)

    def desenhar_luz(self, camx, camy, psx, psy):
        esc = self.escuridao()
        if self.chuva:
            esc = max(esc, 0.18)
        if self.metro is not None:  # debaixo da terra e sempre meio escuro (so as luzes velhas do teto)
            esc = 0.5
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
        nome_l, alcance_l, abertura_l, pisca_l = LANTERNAS[self.__dict__.get("nivel_lanterna", 1)]
        falhou = pisca_l and (math.sin(time.time() * 7.3) + math.sin(time.time() * 13.1) > 1.55)
        if self.lanterna and not falhou:
            cones = self.__dict__.setdefault("cones_lanterna", {})
            if alcance_l not in cones:
                cones[alcance_l] = G.luz_cone(alcance_l, abertura_l)
            q = int(round(math.degrees(self.p.ang) / 3)) % 120
            cone = self.cone_cache.get((alcance_l, q))
            if cone is None:
                cone = pygame.transform.rotate(cones[alcance_l], -q * 3)
                self.cone_cache[(alcance_l, q)] = cone
                if len(self.cone_cache) > 24:
                    self.cone_cache.popitem(last=False)
            self.escuro.blit(cone, (psx - cone.get_width() / 2, psy - cone.get_height() / 2), special_flags=sub)
        if self.heli is not None:  # holofote do helicoptero
            sz = 420
            luz = self.__dict__.get("luz_heli")
            if luz is None:
                luz = self.luz_heli = pygame.transform.scale(self.luz_fogo, (sz, sz))
            self.escuro.blit(luz, (self.heli[0] - camx - sz / 2, self.heli[1] + 70 - camy - sz / 2), special_flags=sub)
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
                fm = self.__dict__.get("f_mini") or pygame.font.SysFont("segoeui", 12)
                self.f_mini = fm
                self.texto(" + ".join(extras), (W - 140, H - 150), fm, (150, 210, 255), centro=True)
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
        if self.__dict__.get("deitado"):
            self.texto("DEITADO  (T levanta)", (24, H - 160 - 24 * (p.sangrando + p.perna + p.braco)), self.f_med,
                       (170, 220, 255))
        elif self.agachado:
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
        clima = ("  ·  neve" if self.estacao() == 2 else "  ·  chuva") if self.chuva else ""
        self.texto(f"Dia {self.dia}  ·  {h:02d}:{mi:02d}  ·  {ESTACOES[self.estacao()][0]}{clima}", (64, 22), self.f_med)
        d_ = DIFICULDADES.get(self.dificuldade, DIFICULDADES["medio"])
        self.texto(d_["nome"], (24, 96), self.f_peq, d_["cor"])
        if self.capitulo == 2:
            self.texto("Capítulo 2 · Dimensão Sombria", (24, 166), self.f_peq, (210, 160, 255))
        if self.dirigindo:
            g = self.dirigindo.get("gas", 0)
            self.texto(f"CARRO  ·  gasolina {int(g)}%  ·  {int(abs(self.vel_carro) / 4)} km/h  ·  E sai",
                       (W // 2, 120), self.f_med, (255, 120, 100) if g < 10 else (255, 230, 160), centro=True)
        for k_, (it_, v_) in enumerate((("capacete", self.capacete), ("colete", self.colete), ("calca", self.calca))):
            cx_, cy_ = 38 + k_ * 50, 140
            pygame.draw.circle(tela, (16, 18, 22), (cx_, cy_), 21)
            pygame.draw.circle(tela, (60, 62, 68), (cx_, cy_), 21, 3)
            if v_ > 0:
                cor_ = (110, 220, 120) if v_ > 50 else (240, 200, 70) if v_ > 20 else (240, 90, 70)
                pygame.draw.arc(tela, cor_, (cx_ - 21, cy_ - 21, 42, 42), math.pi / 2,
                                math.pi / 2 + 2 * math.pi * min(100, v_) / 100, 4)
                G.desenha_icone(tela, it_, cx_, cy_, 0.62)
            else:
                ic_ = self.__dict__.setdefault("icones_apagados", {})
                if it_ not in ic_:
                    sf_ = pygame.Surface((60, 60), pygame.SRCALPHA)
                    G.desenha_icone(sf_, it_, 30, 30, 0.62)
                    sf_.set_alpha(60)
                    ic_[it_] = sf_
                tela.blit(ic_[it_], (cx_ - 30, cy_ - 30))
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
        if self.metro is not None:  # la embaixo o GPS nao pega
            mt = m.metros[self.metro]
            pygame.draw.circle(self.tela, (20, 70, 160), (r.centerx, r.y + 60), 30)
            pygame.draw.circle(self.tela, (240, 240, 250), (r.centerx, r.y + 60), 30, 3)
            self.texto("M", (r.centerx, r.y + 42), self.f_grande, (250, 250, 255), centro=True)
            self.texto("METRÔ", (r.centerx, r.y + 104), self.f_med, (220, 230, 255), centro=True)
            self.texto(mt["cidade"], (r.centerx, r.y + 132), self.f_peq, (200, 200, 210), centro=True)
            self.texto("sem sinal de GPS", (r.centerx, r.y + 158), self.f_peq, (150, 150, 160), centro=True)
            return
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
        if "--piloto" in sys.argv:
            j.iniciar_piloto()
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
