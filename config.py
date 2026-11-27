"""Constantes, itens, armas e tabelas de saque do Ultimo Sobrevivente."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(HERE, "save.json")
RECORDE_FILE = os.path.join(HERE, "recorde.json")
ERRO_FILE = os.path.join(HERE, "erro.txt")
MUNDOS_DIR = os.path.join(HERE, "mundos")   # cada mundo salvo fica num arquivo aqui

W, H = 1280, 720
FPS = 60
T = 32                 # tamanho do quadradinho do mapa (pixels)
N = 768                # mundo tem N x N quadradinhos (24.576 px de lado)
CH = 16                # pedaco (chunk) de 16x16 quadradinhos
CHPX = CH * T
EXPLO = 4              # celula do "mapa explorado" = 4x4 quadradinhos
NE = N // EXPLO

# ---- tipos de chao ----
GRAMA, MATO, AREIA, AGUA, TERRA, PONTE, ASFALTO, PISO_MAD, PISO_HOSP, PISO_CONC, PAREDE, PAREDE_CONC, PORTA = range(13)
SOLIDO = {AGUA, PAREDE, PAREDE_CONC}
BLOQ_TIRO = {PAREDE, PAREDE_CONC}
ESTRUTURA = {PISO_MAD, PISO_HOSP, PISO_CONC, PAREDE, PAREDE_CONC, PORTA, PONTE}

# ---- tempo / sobrevivencia (jogo longo) ----
DIA_SEG = 960.0          # um dia inteiro = 16 minutos reais
FOME_SEG = 2600.0        # barra de fome esvazia em ~43 min
SEDE_SEG = 1800.0        # barra de sede esvazia em 30 min
PECAS_RADIO = 5          # pecas para consertar o radio e chamar o resgate
TEMPO_RESGATE = 240.0    # segundos aguentando a horda ate o helicoptero

NOMES_CIDADES = [
    "Santa Rita", "Boa Vista", "Pedra Branca", "São Jorge", "Vale Verde", "Rio Claro",
    "Monte Alto", "Serra Azul", "Campo Belo", "Água Fria", "Tres Pinheiros", "Porto Velho",
    "Lagoa Seca", "Bom Jesus", "Alto Alegre", "Vila Nova", "Ponte Alta", "Cruz das Almas", "Pinhal",
    "Rio Fundo", "Céu Azul", "Morro Velho", "Areia Branca", "Sol Nascente", "Barro Preto", "Campo Largo",
    "Ouro Fino", "Palmeiras", "Cachoeira", "Ventania", "Riacho Doce", "Esperança", "Toca da Onça",
]
NOME_METROPOLE = "Nova Capital"

ITENS = {
    "comida": "Comida enlatada",
    "agua": "Garrafa de água",
    "bandagem": "Bandagem",
    "kit": "Kit médico",
    "9mm": "Balas 9mm",
    "12": "Cartuchos cal.12",
    "556": "Munição de AK-47",
    "308": "Munição de sniper",
    "silenciador": "Silenciador",
    "flecha": "Flechas",
    "galao": "Galão de gasolina",
    "colete": "Colete",
    "capacete": "Capacete",
    "calca": "Calça reforçada",
    "lanterna1": "Lanterna boa",
    "lanterna2": "Lanterna tática",
    "lanterna3": "Holofote militar",
    "38": "Balas .38",
    "taco": "Taco com pregos",
    "revolver": "Revólver",
    "foguete": "Foguetes de RPG",
    "katana": "Katana",
    "minigun": "Minigun",
    "dragao": "Escopeta Dragão",
    "dourado": "Sniper Dourado",
    "rpg": "RPG",
    "mira": "Mira (luneta)",
    "facao": "Facão",
    "smg": "Submetralhadora",
    "besta": "Besta",
    "tabua": "Tábuas",
    "sucata": "Sucata de metal",
    "ferramentas": "Ferramentas",
    "peca": "Peça do rádio",
    "seringa": "Seringa de adrenalina",
    "saco": "Saco de dormir",
    "mochila1": "Mochila escolar",
    "mochila2": "Mochila de trilha",
    "mochila3": "Mochila militar",
    "mochila4": "Mochila tática grande",
    "mochila5": "Mochilão de expedição",
    "faca": "Faca",
    "machado": "Machado",
    "pistola": "Pistola",
    "espingarda": "Espingarda",
    "fuzil": "AK-47",
    "rifle": "Sniper",
}

ARMAS = [
    dict(id="faca", nome="Faca", melee=True, dano=34, cd=0.36, alcance=52, ruido=0),
    dict(id="machado", nome="Machado", melee=True, dano=75, cd=0.85, alcance=60, ruido=80),
    dict(id="pistola", nome="Pistola", melee=False, mun="9mm", pente=15, dano=34, cd=0.18, disp=0.03,
         balas=1, alcance=720, recarga=1.3, ruido=800, auto=False, silencia=True, fura=0),
    dict(id="espingarda", nome="Espingarda", melee=False, mun="12", pente=6, dano=17, cd=0.8, disp=0.15,
         balas=9, alcance=380, recarga=2.6, ruido=1100, auto=False, silencia=False, fura=0),
    dict(id="fuzil", nome="AK-47", melee=False, mun="556", pente=30, dano=30, cd=0.095, disp=0.05,
         balas=1, alcance=950, recarga=2.2, ruido=1100, auto=True, silencia=True, fura=1),
    dict(id="rifle", nome="Sniper", melee=False, mun="308", pente=5, dano=150, cd=1.1, disp=0.004,
         balas=1, alcance=1500, recarga=2.6, ruido=1400, auto=False, silencia=True, fura=3),
    dict(id="facao", nome="Facão", melee=True, dano=58, cd=0.42, alcance=60, ruido=0),
    dict(id="smg", nome="Submetralhadora", melee=False, mun="9mm", pente=32, dano=19, cd=0.065, disp=0.075,
         balas=1, alcance=650, recarga=1.8, ruido=900, auto=True, silencia=True, fura=0),
    dict(id="besta", nome="Besta", melee=False, mun="flecha", pente=1, dano=130, cd=0.3, disp=0.008,
         balas=1, alcance=950, recarga=1.3, ruido=30, auto=False, silencia=False, fura=1),
    dict(id="taco", nome="Taco com pregos", melee=True, dano=48, cd=0.5, alcance=62, ruido=40, empurra=True),
    dict(id="revolver", nome="Revólver", melee=False, mun="38", pente=6, dano=72, cd=0.42, disp=0.02,
         balas=1, alcance=820, recarga=2.0, ruido=1000, auto=False, silencia=False, fura=1),
    # armas lendarias: so na LOJA, compradas com moedinhas
    dict(id="katana", nome="Katana", melee=True, dano=140, cd=0.28, alcance=74, ruido=0, loja=150,
         desc="Corta rápido e forte. Sem barulho."),
    dict(id="dragao", nome="Escopeta Dragão", melee=False, mun="12", pente=12, dano=28, cd=0.3, disp=0.13,
         balas=12, alcance=520, recarga=2.0, ruido=1200, auto=True, silencia=False, fura=1, loja=250,
         desc="Escopeta automática: 12 chumbos por tiro."),
    dict(id="minigun", nome="Minigun", melee=False, mun="556", pente=150, dano=30, cd=0.035, disp=0.06,
         balas=1, alcance=900, recarga=3.0, ruido=1300, auto=True, silencia=False, fura=2, loja=300,
         desc="150 balas sem parar. Usa munição de AK-47."),
    dict(id="rpg", nome="RPG", melee=False, mun="foguete", pente=1, dano=320, cd=0.5, disp=0.01,
         balas=1, alcance=900, recarga=2.2, ruido=1800, auto=False, silencia=False, fura=0, explode=True, loja=350,
         desc="Foguete que EXPLODE e derruba vários zumbis."),
    dict(id="dourado", nome="Sniper Dourado", melee=False, mun="308", pente=10, dano=420, cd=0.45, disp=0.002,
         balas=1, alcance=1800, recarga=2.0, ruido=600, auto=False, silencia=True, fura=8, loja=400,
         desc="Atravessa 8 zumbis. 10 tiros no pente."),
]
ARMAS.append(dict(id="maos", nome="Sem arma", melee=True, dano=10, cd=0.4, alcance=42, ruido=0, escondida=True))
ARMA_IDX = {a["id"]: i for i, a in enumerate(ARMAS)}
ARMAS_IDS = set(ARMA_IDX) - {"maos"}
# pacotes da loja: (nome, itens, preco em moedas)
LOJA_PACOTES = [("Munição de AK-47 x120", {"556": 120}, 25), ("Cartuchos x40", {"12": 40}, 20),
                ("Munição de sniper x30", {"308": 30}, 25), ("Foguetes de RPG x5", {"foguete": 5}, 40),
                ("Kit médico x3", {"kit": 3}, 30)]
CODIGO_DONO = "DONO"
MOEDAS_ZERAR = 6          # moedas ganhas cada vez que zera o jogo (resgate)
# lanternas: (nome, alcance da luz, abertura, pisca falhando?)
LANTERNAS = [("Lanterna velha", 330, 0.34, True), ("Lanterna boa", 480, 0.42, False),
             ("Lanterna tática", 640, 0.50, False), ("Holofote militar", 840, 0.58, False)]
# dificuldade do mundo (escolhida ao criar): quantidade de zumbis, forca da mordida, fome/sede, visao dos zumbis
DIFICULDADES = {
    "facil": dict(nome="Fácil", zumbis=0.6, dano=0.6, fome=0.7, visao=0.8, cor=(110, 200, 110)),
    "medio": dict(nome="Médio", zumbis=1.0, dano=1.0, fome=1.0, visao=1.0, cor=(230, 200, 90)),
    "dificil": dict(nome="Difícil", zumbis=1.5, dano=1.45, fome=1.3, visao=1.25, cor=(230, 80, 70)),
}
# bancada: coisas para fabricar (id, nome, explicacao, custo)
FABRICAR = [
    ("colete", "Colete de sucata", "Você leva quase metade do dano dos zumbis.", {"sucata": 12, "ferramentas": 2}),
    ("capacete", "Capacete", "Bem menos chance de sangrar ou quebrar osso.", {"sucata": 6, "ferramentas": 1}),
    ("calca", "Calça reforçada", "Quase nunca quebra a perna e leva menos dano.", {"sucata": 5, "tabua": 2}),
    ("flechas", "10 flechas", "Munição da besta.", {"tabua": 2, "sucata": 1}),
]
# o que da para construir na base direto da bancada
BASE_BANCADA = ["muro", "espinhos", "portao", "bau", "arame", "barricada", "fogueira", "abrigo"]
# construcoes que da para colocar uma atras da outra (sem sair do modo construir) e alinhadas no chao
EM_SERIE = ("muro", "espinhos", "arame", "barricada", "ponte", "portao")
# bancada: nivel maximo das melhorias
NIVEL_MAX = 3
MOCHILA_EXTRA = 40      # espaco a mais por nivel de reforco da mochila
# quanto a tela treme em cada tiro
TREMOR = {"revolver": 5, "pistola": 2.5, "espingarda": 8, "fuzil": 2.2, "rifle": 9, "smg": 1.8, "besta": 1.5, "minigun": 2,
          "dragao": 9, "dourado": 9, "rpg": 16}
ARMA_IDX = {a["id"]: i for i, a in enumerate(ARMAS)}
ARMAS_IDS = set(ARMA_IDX)

# item: (peso, min, max)
LOOT = {
    "casa": [("comida", 22, 1, 2), ("agua", 22, 1, 2), ("bandagem", 12, 1, 2), ("kit", 2.5, 1, 1),
             ("9mm", 10, 6, 15), ("12", 6, 2, 6), ("308", 1.5, 2, 5), ("556", 2, 6, 15), ("tabua", 8, 2, 4),
             ("ferramentas", 2.5, 1, 1), ("pistola", 2.6, 1, 1), ("espingarda", 1.6, 1, 1),
             ("machado", 1.6, 1, 1), ("silenciador", 0.8, 1, 1), ("rifle", 0.5, 1, 1), ("fuzil", 0.4, 1, 1)],
    "medico": [("bandagem", 30, 1, 3), ("kit", 24, 1, 2), ("agua", 14, 1, 2), ("comida", 6, 1, 1), ("9mm", 5, 5, 10)],
    "militar": [("556", 18, 15, 40), ("9mm", 12, 10, 25), ("308", 10, 5, 12), ("12", 8, 4, 10), ("kit", 12, 1, 2),
                ("comida", 8, 2, 3), ("agua", 8, 2, 3), ("fuzil", 6, 1, 1), ("rifle", 5, 1, 1),
                ("silenciador", 7, 1, 1), ("pistola", 3, 1, 1), ("ferramentas", 4, 1, 1)],
    "porta_malas": [("sucata", 30, 2, 5), ("agua", 12, 1, 2), ("comida", 10, 1, 2), ("ferramentas", 8, 1, 1),
                    ("9mm", 8, 4, 10), ("12", 6, 2, 5), ("bandagem", 8, 1, 2), ("tabua", 5, 1, 3),
                    ("pistola", 1.5, 1, 1), ("espingarda", 1.0, 1, 1)],
    "chao": [("agua", 16, 1, 1), ("comida", 14, 1, 1), ("bandagem", 8, 1, 1), ("9mm", 10, 4, 10),
             ("12", 6, 2, 5), ("556", 4, 8, 20), ("308", 3, 2, 5), ("tabua", 14, 2, 4), ("sucata", 8, 1, 3),
             ("pistola", 4, 1, 1), ("espingarda", 2.5, 1, 1), ("machado", 3, 1, 1), ("fuzil", 1.2, 1, 1),
             ("rifle", 1.2, 1, 1), ("silenciador", 1.6, 1, 1), ("kit", 1.5, 1, 1)],
}
# o que um zumbi derrubado pode deixar cair (inclui as armas novas)
LOOT_ZUMBI = LOOT["chao"] + [("facao", 1.5, 1, 1), ("smg", 0.6, 1, 1), ("besta", 0.6, 1, 1), ("flecha", 4, 3, 8),
                             ("taco", 1.5, 1, 1), ("revolver", 0.6, 1, 1), ("38", 4, 4, 10)]

# mercados, shopping e posto de gasolina
LOOT["mercado"] = [("comida", 30, 1, 3), ("agua", 30, 1, 3), ("bandagem", 8, 1, 2), ("kit", 2, 1, 1),
                   ("ferramentas", 3, 1, 1), ("tabua", 4, 2, 4), ("saco", 1, 1, 1), ("lanterna_pilha", 0, 1, 1)]
LOOT["mercado"] = [x for x in LOOT["mercado"] if x[1] > 0]
LOOT["loja_armas"] = [("pistola", 6, 1, 1), ("revolver", 4, 1, 1), ("espingarda", 4, 1, 1), ("smg", 3, 1, 1),
                      ("fuzil", 2, 1, 1), ("rifle", 1.5, 1, 1), ("9mm", 10, 10, 25), ("12", 8, 4, 12),
                      ("38", 8, 6, 14), ("556", 5, 10, 30), ("silenciador", 3, 1, 1), ("mira", 2, 1, 1)]
LOOT["conveniencia"] = [("comida", 20, 1, 2), ("agua", 25, 1, 3), ("sucata", 14, 2, 5), ("ferramentas", 6, 1, 1),
                        ("tabua", 6, 2, 4), ("bandagem", 6, 1, 1)]

NOMES_MOVEIS = {
    "armario": "armário", "geladeira": "geladeira", "gaveta": "cômoda", "caixa": "caixa",
    "medico": "armário de remédios", "militar": "caixa militar", "porta_malas": "porta-malas",
    "mochila": "sua mochila",
    "prateleira": "prateleira", "vitrine": "vitrine de armas",
    "despensa": "despensa do bunker", "arsenal": "arsenal do bunker",
}

# espaco que cada unidade ocupa na mochila
ESPACO = {"comida": 1, "agua": 1, "bandagem": 0.5, "kit": 1.5, "9mm": 0.04, "12": 0.08, "556": 0.04, "308": 0.08,
          "tabua": 1, "sucata": 1, "ferramentas": 2, "seringa": 0.5, "saco": 4,
          "flecha": 0.15, "galao": 3, "38": 0.05, "mira": 0.5, "foguete": 1}
# estacoes do ano: cada uma dura 6 dias. (nome, multiplica cor, soma cor, fome x, sede x)
ESTACOES = [("Verão", (1.04, 1.02, 0.92), (8, 6, 0), 1.0, 1.35),
            ("Outono", (1.12, 0.92, 0.70), (14, 4, 0), 1.0, 1.0),
            ("Inverno", (0.80, 0.86, 0.92), (70, 74, 82), 1.35, 0.8),
            ("Primavera", (0.95, 1.06, 0.95), (0, 6, 0), 1.0, 1.0)]
DIAS_ESTACAO = 6
# (nome, espaco, cor) por nivel; nivel 0 = so os bolsos
MOCHILAS = [("Bolsos", 30, (90, 90, 90)), ("Mochila escolar", 80, (60, 110, 190)),
            ("Mochila de trilha", 150, (200, 120, 40)), ("Mochila militar", 250, (80, 110, 60)),
            ("Mochila tática grande", 390, (40, 44, 40)), ("Mochilão de expedição", 600, (150, 40, 34))]

RECEITAS = [
    dict(id="barricada", nome="Barricada", custo={"tabua": 4}),
    dict(id="fogueira", nome="Fogueira", custo={"tabua": 3}),
    dict(id="abrigo", nome="Bunker (abrigo)", custo={"tabua": 25, "sucata": 15, "ferramentas": 1}),
    dict(id="arame", nome="Arame farpado", custo={"sucata": 3}),
    dict(id="ponte", nome="Ponte de madeira", custo={"tabua": 4}),
    dict(id="bancada", nome="Bancada", custo={"tabua": 10, "sucata": 6, "ferramentas": 1}),
    dict(id="muro", nome="Muro", custo={"tabua": 4, "sucata": 2}),
    dict(id="portao", nome="Portão", custo={"tabua": 5, "sucata": 3}),
    dict(id="bau", nome="Baú", custo={"tabua": 8}),
    dict(id="espinhos", nome="Espinhos", custo={"sucata": 2, "tabua": 1}),
]
RAIO_ABRIGO = 260
