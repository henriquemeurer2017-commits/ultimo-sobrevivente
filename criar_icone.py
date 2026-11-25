"""Cria icone.png e icone.ico (o desenho do atalho na Area de Trabalho)."""
import io
import os
import random
import struct

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

import graficos as G
from config import HERE

pygame.init()
pygame.display.set_mode((1, 1))


def desenho(tam):
    s = pygame.Surface((256, 256), pygame.SRCALPHA)
    pygame.draw.circle(s, (20, 26, 20), (128, 128), 124)
    for k in range(10):
        pygame.draw.circle(s, G.mistura((20, 26, 20), (90, 30, 26), k / 10), (128, 128), 118 - k * 8)
    pygame.draw.circle(s, (210, 70, 54), (128, 128), 124, 8)
    z = G.sprite_zumbi(random.Random(5), "normal")
    z = pygame.transform.rotozoom(z, 90, 3.3)
    s.blit(z, z.get_rect(center=(128, 138)))
    return pygame.transform.smoothscale(s, (tam, tam))


pygame.image.save(desenho(256), os.path.join(HERE, "icone.png"))
pngs = []
for tam in (256, 64, 48, 32, 16):
    buf = io.BytesIO()
    pygame.image.save(desenho(tam), buf, "icone.png")
    pngs.append((tam, buf.getvalue()))
cab = struct.pack("<HHH", 0, 1, len(pngs))
pos = 6 + 16 * len(pngs)
dirs = b""
dados = b""
for tam, d in pngs:
    dirs += struct.pack("<BBBBHHII", tam % 256, tam % 256, 0, 0, 1, 32, len(d), pos)
    pos += len(d)
    dados += d
with open(os.path.join(HERE, "icone.ico"), "wb") as f:
    f.write(cab + dirs + dados)
print("ok")
