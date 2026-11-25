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

# ajusta a pagina: fundo preto, comeca sozinho (sem clique) e entra em tela cheia no primeiro toque
pagina = os.path.join(WEB, "build", "web", "index.html")
if os.path.exists(pagina):
    with open(pagina, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("ume_block : 1,", "ume_block : 0,")
    html = html.replace("background-color:powderblue;", "background-color:#000; overflow:hidden;")
    html = html.replace('''            background: green;
            color: blue;''', '''            background: #1a1414;
            color: #e8d8c8;
            border-radius: 8px;
            left: 50%; top: 50%; transform: translate(-50%, -50%);''')
    html = html.replace("Loading, please wait ...", "Carregando o Último Sobrevivente... (na primeira vez demora uns 30 segundos)")
    extra = """
<script>
// tela cheia no primeiro clique ou tecla (o navegador so deixa depois de um toque)
function telaCheia() {
    const el = document.documentElement;
    if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen().catch(() => {});
}
document.addEventListener("pointerdown", telaCheia, {once: true});
document.addEventListener("keydown", telaCheia, {once: true});
</script>
</body>"""
    if "function telaCheia" not in html:
        html = html.replace("</body>", extra, 1)
    with open(pagina, "w", encoding="utf-8") as f:
        f.write(html)
    print("pagina ajustada: tela cheia e sem clique para comecar")
