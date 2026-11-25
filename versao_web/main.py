# /// script
# dependencies = [
#   "numpy",
# ]
# ///
"""Versao de navegador do Ultimo Sobrevivente (montada com pygbag).

O jogo de verdade esta em jogo.py; este arquivo so roda um quadro por vez
e guarda o jogo salvo no navegador (localStorage) para nao perder ao fechar a aba.
"""
import asyncio
import os
import sys
import time

import numpy  # noqa: F401  (o pygbag so carrega o que aparece aqui)
import pygame  # noqa: F401
import pygame.mixer  # noqa: F401

import config
import jogo

GUARDAR = {"ultimo_save": config.SAVE_FILE, "ultimo_recorde": config.RECORDE_FILE}


def _armazem():
    if sys.platform != "emscripten":
        return None
    try:
        import platform
        return platform.window.localStorage
    except Exception:
        return None


def restaurar():
    ls = _armazem()
    if ls is None:
        return
    for chave, caminho in GUARDAR.items():
        try:
            txt = ls.getItem(chave)
            if txt:
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(str(txt))
        except Exception:
            pass


_ultimo = {}


def guardar():
    ls = _armazem()
    if ls is None:
        return
    for chave, caminho in GUARDAR.items():
        try:
            if os.path.exists(caminho):
                with open(caminho, encoding="utf-8") as f:
                    txt = f.read()
                if _ultimo.get(chave) != txt:
                    ls.setItem(chave, txt)
                    _ultimo[chave] = txt
            elif _ultimo.get(chave) is not None or ls.getItem(chave):
                ls.removeItem(chave)
                _ultimo[chave] = None
        except Exception:
            pass


def log(txt):
    print(txt)
    try:
        import platform
        platform.window.console.log("[jogo] " + str(txt))
    except Exception:
        pass


async def main():
    try:
        log("restaurando save")
        restaurar()
        log("criando jogo")
        j = jogo.Jogo()
        log("jogo criado")
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
    t = time.time()
    n = 0
    while True:
        try:
            j.passo()
        except SystemExit:
            return
        except Exception:
            import traceback
            log(traceback.format_exc())
            raise
        n += 1
        if n == 1:
            log("primeiro quadro ok")
        if time.time() - t > 2:
            t = time.time()
            guardar()
        await asyncio.sleep(0)


asyncio.run(main())
