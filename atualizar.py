"""
Atualização contínua entre as coletas completas (agendada pelo agendar_atualizacao.ps1).

    python atualizar.py novos  [--proj iphone|aluguel] [--max 5] [--buscas 3]
        A cada 2 horas: abre poucas buscas ordenadas por "mais recentes", pega até --max anúncios que
        ainda não estão no histórico, lê cada um (com fotos) e grava em dados/_anuncios_novos_<dia>.json.
        Depois refaz a página e publica no GitHub. Sem Haiku no iPhone (o modelo sai do título);
        no aluguel o Haiku classifica só esses poucos novos, senão eles não aparecem na página.

    python atualizar.py diario [--proj iphone|aluguel] [--conferir 40]
        No almoço: confere --conferir anúncios antigos (vendido/apagado), classifica com o Haiku os iPhones
        que entraram desde o último compilado (variante/bateria/estado), refaz a página e publica.

Não roda se a coleta completa estiver em andamento (coleta.log mexido nos últimos 10 minutos) ou se
outra atualização ainda não terminou (dados/.atualizando).
"""

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from datetime import date, datetime
from urllib.parse import quote

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import coleta  # noqa: E402
import historico  # noqa: E402
from publicar import publicar  # noqa: E402

PROJETOS = {"iphone": AQUI, "aluguel": os.path.join(os.path.dirname(AQUI), "marketplace-aluguel")}

# só a primeira tela de resultados, já ordenada por mais recentes: rolar pouco é o que basta
TOPO = r"""
async () => {
  for (let i = 0; i < 3; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 1500 + Math.random() * 1500));
  }
  return [...new Set([...document.querySelectorAll('a[href*="/marketplace/item/"]')]
    .map(a => (a.getAttribute('href').match(/item\/(\d+)/) || [])[1]).filter(Boolean))];
}
"""


def preparar(nome):
    """Ajusta o módulo coleta para o projeto e devolve (pasta, lista de buscas)."""
    proj = PROJETOS[nome]
    if nome == "aluguel":
        sys.path.insert(0, proj)
        import coleta_aluguel  # troca DADOS, LOG e EXTRATOR do coleta
        buscas = coleta_aluguel.BUSCAS
    else:
        buscas = [t for g in coleta.BUSCAS.values() for t in g]
    coleta.LOG = os.path.join(coleta.DADOS, "atualizar.log")
    coleta.ARGS_EXTRA = ["--window-position=-2400,0"]  # fora da tela; minimizado o Chrome não desenha a página e a leitura falha
    return proj, buscas


def url_recentes(termo):
    if termo.startswith("/"):
        return coleta.MARKETPLACE + termo + ("&" if "?" in termo else "?") + "sortBy=creation_time_descend"
    return f"{coleta.MARKETPLACE}/search/?query={quote(termo)}&sortBy=creation_time_descend"


class Trava:
    def __init__(self, dados):
        self.arq = os.path.join(dados, ".atualizando")
        self.log_completa = os.path.join(dados, "coleta.log")

    def __enter__(self):
        if os.path.exists(self.log_completa) and time.time() - os.path.getmtime(self.log_completa) < 600:
            raise SystemExit("coleta completa em andamento; fica para a próxima")
        if os.path.exists(self.arq) and time.time() - os.path.getmtime(self.arq) < 4 * 3600:
            raise SystemExit("outra atualização ainda rodando; fica para a próxima")
        open(self.arq, "w").write(str(os.getpid()))
        return self

    def __exit__(self, *_):
        try:
            os.remove(self.arq)
        except OSError:
            pass


async def buscar_novos(proj, buscas, maximo, n_buscas):
    from playwright.async_api import async_playwright
    conhecidos = set(historico.carregar(proj))
    arq = os.path.join(coleta.DADOS, f"_anuncios_novos_{date.today().isoformat()}.json")
    ja = json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else []
    conhecidos |= {d["id"] for d in ja}
    lidos = []
    async with async_playwright() as p:
        nav, nova_guia = await coleta.abrir_chrome(p)
        try:
            pg = await nova_guia()
            fila = []
            for k, termo in enumerate(random.sample(buscas, min(n_buscas, len(buscas)))):
                if k:
                    await coleta.dormir(coleta.PAUSA_BUSCA)
                await pg.goto(url_recentes(termo), wait_until="domcontentloaded")
                await coleta.dormir((4, 7))
                await coleta.checar(pg)
                achados = await pg.evaluate(TOPO)
                novos = [i for i in achados if i not in conhecidos and i not in fila]
                fila += novos
                coleta.log(f"Busca '{termo}' (recentes): {len(achados)} anúncios, {len(novos)} ainda não vistos")
                if len(fila) >= maximo:
                    break
            for item in fila[:maximo]:
                await coleta.dormir(coleta.PAUSA_ANUNCIO)
                for tentativa in range(2):  # a primeira abertura às vezes não termina de carregar
                    await pg.goto(f"https://www.facebook.com/marketplace/item/{item}/", wait_until="domcontentloaded")
                    try:  # espera o anúncio aparecer (às vezes a página demora a desenhar o conteúdo)
                        await pg.wait_for_function(r"/\nAnunciado|\/\s*m[êe]s/.test(document.body.innerText)", timeout=25000)
                    except Exception:
                        pass
                    await coleta.checar(pg)
                    d = await pg.evaluate(coleta.EXTRATOR)
                    if not d.get("erro"):
                        break
                    await coleta.dormir((6, 10))
                if d.get("erro"):
                    coleta.log(f"{item}: não deu para ler ({d['erro']}) | {await pg.title()}")
                    continue
                d["fotos"] = await coleta.baixar_fotos(pg, d.pop("fotos_url", []))
                lidos.append(d)
                coleta.log(f"novo: {d.get('titulo', '')[:45]} | R$ {d.get('preco', '')} | {len(d['fotos'])} fotos")
        except coleta.Parar as e:
            coleta.log(str(e))
        finally:
            await nav.close()
    if lidos:
        json.dump(ja + lidos, open(arq, "w", encoding="utf-8"), ensure_ascii=False)
        historico.registrar_itens(proj, lidos)
    coleta.log(f"Atualização: {len(lidos)} anúncios novos gravados")
    return len(lidos)


def montar_e_publicar(nome, proj, msg, haiku):
    """Refaz a página com o que está em dados/ e manda para o GitHub (o site atualiza em 1–2 min)."""
    py = sys.executable
    if nome == "iphone":
        subprocess.run([py, os.path.join(proj, "salvar_fotos.py")], cwd=proj, capture_output=True)
        if haiku:
            subprocess.run([py, os.path.join(proj, "classificar_haiku.py")], cwd=proj)
        ok = subprocess.run([py, os.path.join(proj, "gerar_pagina.py")], cwd=proj).returncode == 0
    else:  # aluguel: sem o Haiku o anúncio não tem tipo/finalidade e não aparece; são só os poucos novos
        ok = subprocess.run([py, os.path.join(proj, "gerar_aluguel.py"), "--diario"], cwd=proj).returncode == 0
    if ok:
        publicar(proj, msg)


def diario(nome, proj, conferir):
    hoje = datetime.now()
    coleta.log(f"Compilado do dia: conferindo {conferir} anúncios antigos ...")
    historico.verificar(proj, maximo=conferir)
    montar_e_publicar(nome, proj, f"Compilado de {hoje:%d/%m/%Y %H:%M}", haiku=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["novos", "diario"])
    ap.add_argument("--proj", choices=list(PROJETOS), default="iphone")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--buscas", type=int, default=3)
    ap.add_argument("--conferir", type=int, default=40)
    a = ap.parse_args()
    proj, buscas = preparar(a.proj)
    os.makedirs(coleta.DADOS, exist_ok=True)
    with Trava(coleta.DADOS):
        if a.modo == "novos":
            if asyncio.run(buscar_novos(proj, buscas, a.max, a.buscas)):
                montar_e_publicar(a.proj, proj, f"Novos anúncios {datetime.now():%d/%m %H:%M}", haiku=False)
        else:
            diario(a.proj, proj, a.conferir)


if __name__ == "__main__":
    main()
