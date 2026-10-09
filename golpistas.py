"""
Vendedores marcados como golpistas: nenhum anúncio deles aparece na página nem é baixado de novo.

Fica em golpistas.json na raiz de cada repositório (iPhone e aluguel têm listas separadas):
    {"vendedores": {id_do_vendedor: {"nome", "desde", "anuncio"}}, "anuncios": {id_do_anuncio: dia}}

Como marcar:
  - no site: abrir o anúncio > "🚩 Marcar como golpista". Abre uma issue no GitHub "golpista <id>"; é só clicar em
    "Submit new issue" (logado como LGRSV). A próxima rodada do script (de 2 em 2 horas) descobre o vendedor,
    grava aqui, tira todos os anúncios dele da página e fecha a issue pelo commit.
  - no terminal: python golpistas.py marcar <id do anúncio> [--proj PASTA]
  - para desfazer: python golpistas.py desmarcar <id do anúncio ou do vendedor> [--proj PASTA]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
DONO = "LGRSV"  # só issues abertas por esta conta valem (o repositório é público)

# O nome e o id do vendedor vêm no JSON embutido na página do anúncio, mesmo sem login.
VENDEDOR_JS = r"""() => {
  for (const s of document.querySelectorAll('script')) {
    const m = s.textContent.match(/"marketplace_listing_seller":\{"__typename":"\w+","name":"((?:[^"\\]|\\.)*)","id":"([^"]+)"/);
    if (m) { let nome = m[1]; try { nome = JSON.parse('"' + m[1] + '"'); } catch (e) {} return {nome, id: m[2]}; }
  }
  return null;
}"""


# Vai para as páginas logo depois de "const D=...": esconde na hora (neste navegador) o que já foi marcado e
# monta o botão "🚩 Marcar como golpista", que abre a issue no GitHub para o script tornar a marcação definitiva.
PAGINA_JS = r"""
const GOLPE=(()=>{try{return JSON.parse(localStorage.getItem('golpe')||'{"a":[],"v":[]}')}catch(e){return{a:[],v:[]}}})();
const golpeOculto=d=>GOLPE.a.includes(d.id)||(d.vendedor&&GOLPE.v.includes(d.vendedor));
for(let i=D.length-1;i>=0;i--)if(golpeOculto(D[i]))D.splice(i,1);
function golpeLink(d){const corpo=`Vendedor: ${d.vendedor||'(o script descobre)'}\nAnúncio: ${d.titulo} | R$ ${d.preco}\n${d.link}\n\nNa próxima rodada (de 2 em 2 horas) o script tira os anúncios desse vendedor do site e fecha esta issue.`;
 return `https://github.com/__REPO__/issues/new?title=${encodeURIComponent('golpista '+d.id)}&body=${encodeURIComponent(corpo)}`}
function golpeBotao(d){return `${d.vendedor?`<div class="m" style="margin-top:6px">Vendedor: ${esc(d.vendedor)}</div>`:''}<div class="acts"><a href="${golpeLink(d)}" target="_blank" rel="noopener" style="background:#c62828" onclick="golpeMarcar('${d.id}')">🚩 Marcar como golpista</a></div>`}
function golpeMarcar(id){const d=D.find(x=>x.id===id);if(!d)return;GOLPE.a.push(id);if(d.vendedor)GOLPE.v.push(d.vendedor);
 try{localStorage.setItem('golpe',JSON.stringify(GOLPE))}catch(e){}
 const fora=D.filter(golpeOculto).map(x=>x.id);fora.forEach(i=>document.querySelectorAll(`.c[data-id="${i}"]`).forEach(e=>e.remove()));
 for(let i=D.length-1;i>=0;i--)if(golpeOculto(D[i]))D.splice(i,1);setTimeout(fechar,300)}
"""


def pagina_js(proj):
    return PAGINA_JS.replace("__REPO__", repositorio(proj))


def arquivo(proj):
    return os.path.join(proj, "golpistas.json")


def carregar(proj):
    try:
        G = json.load(open(arquivo(proj), encoding="utf-8"))
    except FileNotFoundError:
        G = {}
    G.setdefault("vendedores", {})
    G.setdefault("anuncios", {})
    return G


def salvar(proj, G):
    json.dump(G, open(arquivo(proj), "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)


def bloqueado(G, anuncio, vendedor_id=None):
    return anuncio in G["anuncios"] or bool(vendedor_id and vendedor_id in G["vendedores"])


def vendedor_na_pagina(anuncio):
    """Abre o anúncio numa guia anônima só para descobrir o vendedor (quando o histórico ainda não sabe)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=False, args=["--window-position=-2400,0"])
        try:
            pg = nav.new_context(locale="pt-BR").new_page()
            pg.goto(f"https://www.facebook.com/marketplace/item/{anuncio}/", timeout=60000)
            try:
                pg.wait_for_function(r"/\nAnunciado|\/\s*m[êe]s|Indispon[íi]vel/.test(document.body.innerText)", timeout=25000)
            except Exception:
                pass
            return pg.evaluate(VENDEDOR_JS)
        finally:
            nav.close()


def marcar(proj, anuncio, abrir=True):
    """Bloqueia o anúncio e o vendedor dele. Devolve o nome do vendedor (ou '' se não deu para descobrir)."""
    import historico
    G, H = carregar(proj), historico.carregar(proj)
    h = H.get(anuncio, {})
    v = {"id": h["vendedor_id"], "nome": h.get("vendedor", "")} if h.get("vendedor_id") else None
    if not v and abrir:
        v = vendedor_na_pagina(anuncio)
    G["anuncios"].setdefault(anuncio, date.today().isoformat())
    if v:
        G["vendedores"].setdefault(v["id"], {"nome": v["nome"], "desde": date.today().isoformat(), "anuncio": anuncio})
        if anuncio in H:
            H[anuncio]["vendedor"], H[anuncio]["vendedor_id"] = v["nome"], v["id"]
            historico.salvar(proj, H)
    salvar(proj, G)
    return v["nome"] if v else ""


def desmarcar(proj, ident):
    G = carregar(proj)
    v = G["vendedores"].pop(ident, None)
    G["anuncios"].pop(ident, None)
    for vid, info in list(G["vendedores"].items()):
        if info.get("anuncio") == ident:
            G["vendedores"].pop(vid)
    salvar(proj, G)
    return v


def repositorio(proj):
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=proj, capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[/:]([^/]+/[^/.]+)", url)
    return m.group(1) if m else ""


def sincronizar(proj, log=print):
    """Lê as issues "golpista <id>" abertas pelo dono, marca cada uma e devolve os números para fechar no commit."""
    repo = repositorio(proj)
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues?state=open&creator={DONO}&per_page=50",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "marketplace-script"})
        issues = json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as e:
        log(f"golpistas: não consegui ler as issues do GitHub ({e})")
        return []
    fechar = []
    for i in issues:
        m = re.match(r"\s*golpista\s+(\d+)", i.get("title", ""), re.I)
        if not m or i.get("user", {}).get("login") != DONO or "pull_request" in i:
            continue
        nome = marcar(proj, m.group(1))
        log(f"golpistas: anúncio {m.group(1)} marcado (vendedor: {nome or 'não identificado'}) pela issue #{i['number']}")
        fechar.append(i["number"])
    return fechar


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["marcar", "desmarcar", "listar", "sincronizar"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--proj", default=AQUI)
    a = ap.parse_args()
    sys.path.insert(0, AQUI)
    if a.modo == "marcar":
        print("vendedor:", marcar(a.proj, a.id) or "não identificado (só o anúncio foi bloqueado)")
    elif a.modo == "desmarcar":
        print("removido:", desmarcar(a.proj, a.id))
    elif a.modo == "sincronizar":
        print("issues:", sincronizar(a.proj))
    else:
        G = carregar(a.proj)
        for vid, v in G["vendedores"].items():
            print(f"  {v['nome']:30} desde {v['desde']}  (anúncio {v['anuncio']})  {vid[:20]}...")
        print(f"  {len(G['anuncios'])} anúncios bloqueados")


if __name__ == "__main__":
    main()
