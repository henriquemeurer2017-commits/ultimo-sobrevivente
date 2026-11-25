"""Constantes, itens, armas e tabelas de saque do Ultimo Sobrevivente."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(HERE, "save.json")
RECORDE_FILE = os.path.join(HERE, "recorde.json")
ERRO_FILE = os.path.join(HERE, "erro.txt")

W, H = 1280, 720
FPS = 60
T = 32                 # tamanho do quadradinho do mapa (pixels)
N = 512                # mundo tem N x N quadradinhos (16.384 px de lado)
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
FOME_SEG = 1500.0        # barra de fome esvazia em 25 min
SEDE_SEG = 1000.0        # barra de sede esvazia em ~17 min
PECAS_RADIO = 5          # pecas para consertar o radio e chamar o resgate
TEMPO_RESGATE = 240.0    # segundos aguentando a horda ate o helicoptero

NOMES_CIDADES = [
    "Santa Rita", "Boa Vista", "Pedra Branca", "São Jorge", "Vale Verde", "Rio Claro",
    "Monte Alto", "Serra Azul", "Campo Belo", "Água Fria", "Tres Pinheiros", "Porto Velho",
    "Lagoa Seca", "Bom Jesus", "Alto Alegre", "Vila Nova",
]

ITENS = {
    "comida": "Comida enlatada",
    "agua": "Garrafa de água",
    "bandagem": "Bandagem",
    "kit": "Kit médico",
    "9mm": "Balas 9mm",
    "12": "Cartuchos cal.12",
    "556": "Munição de fuzil",
    "308": "Munição de rifle",
    "silenciador": "Silenciador",
    "tabua": "Tábuas",
    "sucata": "Sucata de metal",
    "ferramentas": "Ferramentas",
    "peca": "Peça do rádio",
    "mochila1": "Mochila escolar",
    "mochila2": "Mochila de trilha",
    "mochila3": "Mochila militar",
    "mochila4": "Mochila tática grande",
    "faca": "Faca",
    "machado": "Machado",
    "pistola": "Pistola",
    "espingarda": "Espingarda",
    "fuzil": "Fuzil de assalto",
    "rifle": "Rifle de precisão",
}

ARMAS = [
    dict(id="faca", nome="Faca", melee=True, dano=34, cd=0.36, alcance=52, ruido=0),
    dict(id="machado", nome="Machado", melee=True, dano=75, cd=0.85, alcance=60, ruido=80),
    dict(id="pistola", nome="Pistola", melee=False, mun="9mm", pente=15, dano=34, cd=0.18, disp=0.03,
         balas=1, alcance=720, recarga=1.3, ruido=800, auto=False, silencia=True, fura=0),
    dict(id="espingarda", nome="Espingarda", melee=False, mun="12", pente=6, dano=17, cd=0.8, disp=0.15,
         balas=9, alcance=380, recarga=2.6, ruido=1100, auto=False, silencia=False, fura=0),
    dict(id="fuzil", nome="Fuzil de assalto", melee=False, mun="556", pente=30, dano=30, cd=0.095, disp=0.05,
         balas=1, alcance=950, recarga=2.2, ruido=1100, auto=True, silencia=True, fura=1),
    dict(id="rifle", nome="Rifle de precisão", melee=False, mun="308", pente=5, dano=150, cd=1.1, disp=0.004,
         balas=1, alcance=1500, recarga=2.6, ruido=1400, auto=False, silencia=True, fura=3),
]
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

NOMES_MOVEIS = {
    "armario": "armário", "geladeira": "geladeira", "gaveta": "cômoda", "caixa": "caixa",
    "medico": "armário de remédios", "militar": "caixa militar", "porta_malas": "porta-malas",
    "mochila": "sua mochila",
    "despensa": "despensa do bunker", "arsenal": "arsenal do bunker",
}

# espaco que cada unidade ocupa na mochila
ESPACO = {"comida": 1, "agua": 1, "bandagem": 0.5, "kit": 1.5, "9mm": 0.04, "12": 0.08, "556": 0.04, "308": 0.08,
          "tabua": 1, "sucata": 1, "ferramentas": 2}
# (nome, espaco, cor) por nivel; nivel 0 = so os bolsos
MOCHILAS = [("Bolsos", 30, (90, 90, 90)), ("Mochila escolar", 55, (60, 110, 190)),
            ("Mochila de trilha", 85, (200, 120, 40)), ("Mochila militar", 125, (80, 110, 60)),
            ("Mochila tática grande", 180, (40, 44, 40))]

RECEITAS = [
    dict(id="barricada", nome="Barricada", custo={"tabua": 4}),
    dict(id="fogueira", nome="Fogueira", custo={"tabua": 3}),
    dict(id="abrigo", nome="Bunker (abrigo)", custo={"tabua": 25, "sucata": 15, "ferramentas": 1}),
]
RAIO_ABRIGO = 260
