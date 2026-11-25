"""Monta a versao de navegador: copia o jogo para versao_web/ e roda o pygbag.

Uso:  python montar_web.py          (so monta, resultado em versao_web/build/web)
      python montar_web.py --testar (monta e abre um servidor em http://localhost:8000)
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(AQUI, "versao_web")

for nome in ("jogo.py", "config.py", "graficos.py", "mundo.py", "icone.png"):
    shutil.copy2(os.path.join(AQUI, nome), os.path.join(WEB, nome))

args = [sys.executable, "-m", "pygbag", "--title", "Ultimo Sobrevivente", "--icon", "icone.png"]
if "--testar" not in sys.argv:
    args.append("--build")
args.append(WEB)
subprocess.run(args, cwd=WEB, check=True)
