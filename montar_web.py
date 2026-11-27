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
    # cada versao nova tem um "carimbo" no nome do arquivo do jogo: o navegador nao usa a versao velha guardada
    import time as _t
    carimbo = str(int(_t.time()))
    for arq_ in ("versao_web.apk", "versao_web.tar.gz"):
        html = html.replace(f'platform.fopen("{arq_}"', f'platform.fopen("{arq_}?v={carimbo}"')
    html = html.replace("ume_block : 1,", "ume_block : 0,")
    # o jogo comecava com metade do tamanho (gui_divider 2) e as vezes ficava pequeno e achatado
    html = html.replace("gui_divider : 2,", "gui_divider : 1,")
    ajuste = """
<script>
// sempre encher a tela: refaz a conta do tamanho quando a janela muda, ao entrar em tela cheia
// e algumas vezes logo depois que a pagina abre (antes do jogo saber o tamanho certo)
function ajustarTela() {
    try {
        if (window.config) window.config.gui_divider = 1;
        const c = document.getElementById("canvas");
        if (c && c.width && c.height && Math.abs(c.width / c.height - 1280 / 720) > 0.01) { c.width = 1280; c.height = 720; }
        if (window.window_resize) window.window_resize();
    } catch (e) {}
}
window.addEventListener("resize", () => setTimeout(ajustarTela, 150));
document.addEventListener("fullscreenchange", () => setTimeout(ajustarTela, 150));
let __ajustes = 0;
const __timerAjuste = setInterval(() => { ajustarTela(); if (++__ajustes > 30) clearInterval(__timerAjuste); }, 1000);
</script>
</body>"""
    if "function ajustarTela" not in html:
        html = html.replace("</body>", ajuste, 1)
    # contador de jogadores: cada navegador conta 1 vez (so guarda um numero, nenhum dado da pessoa)
    contador = """
<script>
window.jogadoresTotal = 0;
(function () {
    const base = "https://abacus.jasoncameron.dev/";
    const ja = localStorage.getItem("ultimo_contado");
    const url = base + (ja ? "get" : "hit") + "/ultimo-sobrevivente-jogo/jogadores";
    fetch(url).then(r => r.json()).then(d => {
        if (d && d.value) { window.jogadoresTotal = d.value; if (!ja) localStorage.setItem("ultimo_contado", "1"); }
    }).catch(() => {});
    // quem esta jogando AGORA: cada jogo aberto avisa "estou aqui" uma vez por minuto (so soma um numero)
    window.jogandoAgora = 1;
    function online() {
        const m = Math.floor(Date.now() / 60000);
        const k = base + "%s/ultimo-sobrevivente-jogo/on";
        fetch(k.replace("%s", "hit") + m).catch(() => {});
        Promise.all([m - 1, m].map(x => fetch(k.replace("%s", "get") + x).then(r => r.json()).catch(() => ({}))))
            .then(l => { window.jogandoAgora = Math.max(1, ...l.map(d => (d && d.value) || 0)); });
    }
    online();
    setInterval(online, 60000);
})();
</script>
</body>"""
    if "jogadoresTotal" not in html:
        html = html.replace("</body>", contador, 1)
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
    # tela de carregamento com cara de jogo de zumbi (some quando o jogo aparece)
    carga = """
<div id="telacarga">
  <div class="tc-sangue"></div>
  <img src="favicon.png" class="tc-zumbi" alt="">
  <div class="tc-titulo">ÚLTIMO SOBREVIVENTE</div>
  <div class="tc-sub">um apocalipse zumbi em mundo aberto</div>
  <div class="tc-barra"><div class="tc-enche"></div></div>
  <div class="tc-txt" id="tc-txt">Carregando o jogo...</div>
  <div class="tc-aviso">Na primeira vez demora uns 30 segundos: o navegador está baixando o jogo.<br>
  Não é vírus, não precisa instalar nada.</div>
  <div class="tc-dica" id="tc-dica"></div>
</div>
<style>
#telacarga { position: fixed; inset: 0; z-index: 9999999; background: radial-gradient(circle at 50% 40%, #2a0d0d 0%, #0b0606 60%, #000 100%);
  display: flex; flex-direction: column; align-items: center; justify-content: center; font-family: Arial, sans-serif; color: #e8d8c8;
  overflow: hidden; }
.tc-sangue { position: absolute; top: 0; left: 0; right: 0; height: 90px; background:
  repeating-linear-gradient(90deg, #6a0000 0 18px, transparent 18px 46px); opacity: .55;
  -webkit-mask-image: linear-gradient(#000, transparent); mask-image: linear-gradient(#000, transparent); animation: pinga 4s ease-in-out infinite alternate; }
@keyframes pinga { from { height: 60px } to { height: 120px } }
.tc-zumbi { width: 150px; height: 150px; image-rendering: pixelated; filter: drop-shadow(0 0 22px #a00);
  animation: balanca 1.6s ease-in-out infinite; }
@keyframes balanca { 0%,100% { transform: rotate(-6deg) translateY(0) } 50% { transform: rotate(6deg) translateY(-8px) } }
.tc-titulo { font-size: min(64px, 10vw); text-align: center; font-weight: 900; color: #e3271b; letter-spacing: 3px; margin-top: 14px;
  text-shadow: 4px 5px 0 #300, 0 0 26px #ff1a1a88; animation: treme 3s infinite; }
@keyframes treme { 0%,92%,100% { transform: translate(0,0) } 94% { transform: translate(-3px,2px) } 96% { transform: translate(3px,-2px) } }
.tc-sub { font-size: 18px; color: #b9a99a; margin-bottom: 26px; }
.tc-barra { width: min(520px, 80vw); height: 18px; border: 2px solid #7a1a14; border-radius: 10px; background: #1a0a0a; overflow: hidden; }
.tc-enche { height: 100%; width: 0%; background: linear-gradient(90deg, #7a0d08, #e3271b); box-shadow: 0 0 14px #e3271b;
  animation: enche 32s cubic-bezier(.2,.7,.4,1) forwards; }
@keyframes enche { to { width: 96% } }
.tc-txt { margin-top: 12px; font-size: 18px; font-weight: bold; }
.tc-aviso { margin-top: 10px; font-size: 14px; color: #a89888; text-align: center; line-height: 1.5; }
.tc-dica { margin-top: 26px; font-size: 16px; color: #f0c070; text-align: center; max-width: 80vw; min-height: 22px; }
</style>
<script>
(function () {
  const dicas = ["Dica: zumbi de costas não te vê.", "Dica: no capim alto você fica quase invisível.",
    "Dica: aperte V para abrir a mochila.", "Dica: a bancada dos bunkers melhora suas armas.",
    "Dica: deitado (T) quase ninguém te vê.", "Dica: o SHOPPING fica no meio da cidade grande.",
    "Dica: a besta não faz barulho.", "Dica: beba água! A sede mata."];
  const passos = ["Carregando o jogo...", "Acordando os zumbis...", "Espalhando armas pelo mapa...",
    "Construindo a cidade grande...", "Quase lá..."];
  let i = 0, j = 0;
  const d = document.getElementById("tc-dica"), t = document.getElementById("tc-txt");
  d.textContent = dicas[Math.floor(Math.random() * dicas.length)];
  window.__tcTimer = setInterval(() => {
    i++; d.textContent = dicas[(i + Math.floor(Math.random() * 3)) % dicas.length];
    if (j < passos.length - 1) { j++; t.textContent = passos[j]; }
  }, 5000);
  window.esconderTelaCarga = function () {
    const el = document.getElementById("telacarga");
    if (el) { el.style.transition = "opacity .6s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 700); }
    clearInterval(window.__tcTimer);
  };
})();
</script>
</body>"""
    if 'id="telacarga"' not in html:
        html = html.replace("</body>", carga, 1)
    # sair do jogo: sai da tela cheia, tenta fechar a janela; se nao der, mostra uma tela de "ate logo"
    sair = """
<div id="telasair" style="display:none">
  <img src="favicon.png" alt="">
  <div class="ts-titulo">ATÉ A PRÓXIMA, SOBREVIVENTE</div>
  <div class="ts-txt">Seu jogo foi salvo.</div>
  <button id="ts-fechar">Fechar o jogo</button>
  <button id="ts-voltar">Voltar a jogar</button>
  <div class="ts-dica">Se a janela não fechar, aperte <b>Alt + F4</b>.</div>
</div>
<style>
#telasair { position: fixed; inset: 0; z-index: 99999999; background: radial-gradient(circle at 50% 40%, #2a0d0d, #000 80%);
  display: flex; flex-direction: column; align-items: center; justify-content: center; font-family: Arial, sans-serif; color: #e8d8c8; }
#telasair img { width: 120px; height: 120px; image-rendering: pixelated; filter: drop-shadow(0 0 18px #a00); }
.ts-titulo { font-size: min(44px, 9vw); font-weight: 900; color: #e3271b; margin: 14px 0 6px; text-shadow: 3px 4px 0 #300; text-align: center; }
.ts-txt { font-size: 18px; margin-bottom: 22px; }
#telasair button { font-size: 20px; font-weight: bold; padding: 12px 36px; margin: 6px; border-radius: 10px; cursor: pointer;
  background: #5a1a14; color: #f0e0d0; border: 2px solid #c0503c; min-width: 280px; }
#telasair button:hover { background: #8a2a20; }
.ts-dica { margin-top: 18px; font-size: 15px; color: #a89888; }
</style>
<script>
window.sairDoJogo = function () {
  try { if (document.fullscreenElement) document.exitFullscreen(); } catch (e) {}
  const t = document.getElementById("telasair");
  t.style.display = "flex";
  try { window.close(); } catch (e) {}
};
document.getElementById("ts-fechar").onclick = function () {
  try { window.close(); } catch (e) {}
  setTimeout(() => { document.querySelector("#telasair .ts-dica").innerHTML =
    "O navegador não deixou fechar sozinho: aperte <b>Alt + F4</b> (ou o X lá em cima)."; }, 300);
};
document.getElementById("ts-voltar").onclick = function () { location.reload(); };
</script>
</body>"""
    if 'id="telasair"' not in html:
        html = html.replace("</body>", sair, 1)
    # celular em pe: pede para deitar o celular (o jogo e largo)
    girar = """
<div id="girar"><div style="font-size:64px">📱↻</div><div>Vire o celular <b>deitado</b> para jogar</div>
<div style="font-size:16px;opacity:.75;margin-top:10px">Esquerda: joystick para andar · Direita: toque para mirar e atirar</div></div>
<style>
#girar { display: none; position: fixed; inset: 0; z-index: 999999999; background: #000; color: #fff;
  flex-direction: column; align-items: center; justify-content: center; text-align: center;
  font: 24px sans-serif; padding: 24px; }
@media (orientation: portrait) and (pointer: coarse) { #girar { display: flex; } }
</style>
</body>"""
    # toques na tela (celular): a pagina guarda onde cada dedo esta, e o jogo le isso a cada quadro
    toques = """
<script>
(function () {
  window.toquesJSON = "[]";
  function atualiza(ev) {
    const c = document.querySelector("canvas");
    if (!c) return;
    const r = c.getBoundingClientRect();
    const l = [];
    for (const t of ev.touches) l.push([t.identifier, (t.clientX - r.left) / r.width, (t.clientY - r.top) / r.height]);
    window.toquesJSON = JSON.stringify(l);
  }
  ["touchstart", "touchmove", "touchend", "touchcancel"].forEach(n =>
    document.addEventListener(n, atualiza, { capture: true, passive: true }));
})();
</script>
</body>"""
    if "toquesJSON" not in html:
        html = html.replace("</body>", toques, 1)
    if 'id="girar"' not in html:
        html = html.replace("</body>", girar, 1)
    with open(pagina, "w", encoding="utf-8") as f:
        f.write(html)
    print("pagina ajustada: tela cheia e sem clique para comecar")
