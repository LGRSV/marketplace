"""
Coleta do Facebook Marketplace sem IA: um Chrome automatizado (Playwright) faz as buscas,
abre cada anúncio e grava dados/_anuncios_NN.json no mesmo formato que salvar_fotos.py lê.

Uso:
    (padrão: Chrome em guia anônima, sem login e sem cookies guardados entre coletas)
    python coleta.py login            # opcional: entra no Facebook num perfil salvo (usar com --perfil)
    python coleta.py teste            # 2 buscas, até 8 anúncios (validar antes da coleta cheia)
    python coleta.py coletar          # todas as buscas de BUSCAS
    python coleta.py coletar --so iphone      # só as buscas de iPhone (ou: tv, videogame)

No fim da coleta roda salvar_fotos.py, que monta fotos/oportunidades.html.
"""

import argparse
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import asyncio
import time
from datetime import date, datetime
from urllib.parse import quote

from playwright.async_api import async_playwright

import historico
from publicar import publicar

BASE = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE, "dados")
# Perfil do Chrome do robô: fora do OneDrive (sincronizar um perfil do Chrome corrompe o perfil).
PERFIL = os.path.join(os.environ["LOCALAPPDATA"], "marketplace-coleta", "perfil-chrome")
LOG = os.path.join(DADOS, "coleta.log")

MARKETPLACE = "https://www.facebook.com/marketplace/113043862042267"  # Palmas/TO
BUSCAS = {
    "iphone": [f"iphone {n}{s}" for n in (13, 14, 15, 16, 17) for s in ("", " pro", " pro max")],
    "tv": ["smart tv", "televisao"],
    "videogame": ["ps5", "ps4", "xbox", "nintendo switch", "playstation portal"],
}

# Ritmo "humano": o Facebook travou em 30/09 depois de ~10 buscas seguidas sem pausa.
PAUSA_BUSCA = (40, 90)      # segundos entre uma busca e outra
PAUSA_ANUNCIO = (8, 18)     # segundos entre um anúncio e outro
PAUSA_LONGA = (120, 240)    # descanso de cada guia a cada POR_VEZ anúncios
MAX_ANUNCIOS = 450          # teto por rodada (sem login cada busca traz ~19)
MAX_FOTOS = 10
SALVAR_A_CADA = 10
GUIAS = 3                   # guias anônimas abrindo anúncios ao mesmo tempo
POR_VEZ = 10                # cada guia pega 10 anúncios por vez da fila

# Mesmo extrator do prompt_coleta.md (passo 3), agora rodando direto pelo Playwright.
EXTRATOR = r"""
async () => {
  await new Promise(r => setTimeout(r, 2500));
  [...document.querySelectorAll('div[role="button"],span')]
    .filter(e => /^Ver mais$/i.test(e.innerText.trim())).forEach(b => b.click());
  await new Promise(r => setTimeout(r, 800));
  const id = (location.pathname.match(/item\/(\d+)/) || [])[1];
  // Funciona logado e deslogado: ancora na linha "Anunciado ... em <cidade>";
  // o preço vem logo antes dela e o título antes do preço.
  const L = document.body.innerText.split('\n').map(s => s.trim()).filter(Boolean);
  const ia = L.findIndex(s => /^Anunciado\s+(?:h[áa]\s+.+?\s+)?em\s+.+$/.test(s));
  if (ia < 2) return {id, erro: 'indisponivel'};
  let ip = ia - 1;
  while (ip > 0 && !/^(R\$\s?[\d.]+|GRÁTIS|Grátis)/.test(L[ip])) ip--;
  const titulo = L[ip - 1] || '';
  const mp = L[ip].match(/R\$\s?([\d.]+)/);
  const local = L[ia].replace(/^Anunciado\s+(?:h[áa]\s+.+?\s+)?em\s+/, '').trim();
  const ic = L.findIndex((s, k) => k > ia && s === 'Condição');
  const fim = L.findIndex((s, k) => k > ia && /A localização é aproximada|^Informações do vendedor$/.test(s));
  const ini = ic > -1 ? ic + 2 : L.findIndex((s, k) => k > ia && s === 'Detalhes') + 1;
  const descricao = L.slice(ini, fim > ini ? fim : ini + 40)
    .map(s => s.replace(/\s*Ver (mais|menos)$/i, ''))
    .filter(s => s && !/^(Enviar mensagem|Detalhes|Salvar|Compartilhar)$/i.test(s)).join('\n');
  // Fotos do anúncio: o Facebook marca com alt "Foto de produto ..."; o resto são outros anúncios.
  const fotos = [...new Set([...document.querySelectorAll('img')]
    .filter(im => /^Foto de produto/i.test(im.alt) && /scontent|fbcdn/.test(im.src))
    .map(im => im.src))];
  return {id, titulo, preco: mp ? mp[1] : (/gr[áa]tis/i.test(L[ip]) ? '0' : ''), local,
          condicao: ic > -1 ? L[ic + 1] : '', descricao, fotos_url: fotos};
}
"""

ROLAR = r"""
async () => {
  let prev = 0;
  for (let i = 0; i < 25; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 1500 + Math.random() * 1500));
    const n = document.querySelectorAll('a[href*="/marketplace/item/"]').length;
    if (n === prev && i > 3) break;
    prev = n;
  }
  return [...new Set([...document.querySelectorAll('a[href*="/marketplace/item/"]')]
    .map(a => (a.getAttribute('href').match(/item\/(\d+)/) || [])[1]).filter(Boolean))];
}
"""

BLOQUEIO = ("temporariamente bloqueado", "você está indo rápido demais", "you're temporarily blocked",
            "going too fast", "confirme que é você", "checkpoint")
ANONIMO = True  # padrão: guias anônimas, sem cookies entre coletas (--perfil usa o perfil salvo)


class Parar(Exception):
    """Login exigido ou Facebook segurando: para e guarda o que já foi coletado."""


def log(msg):
    linha = f"{datetime.now():%d/%m %H:%M:%S}  {msg}"
    print(linha, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


async def dormir(faixa):
    await asyncio.sleep(random.uniform(*faixa))


async def abrir_chrome(p):
    """Devolve (navegador, função que abre uma guia nova)."""
    opcoes = dict(locale="pt-BR", viewport={"width": 1280, "height": 900})
    args = ["--disable-blink-features=AutomationControlled"]
    if ANONIMO:
        nav = await p.chromium.launch(channel="chrome", headless=False, args=args)

        async def nova_guia():  # cada guia é um contexto anônimo próprio (cookies separados)
            return await (await nav.new_context(**opcoes)).new_page()
        return nav, nova_guia
    os.makedirs(PERFIL, exist_ok=True)
    ctx = await p.chromium.launch_persistent_context(PERFIL, channel="chrome", headless=False, args=args, **opcoes)
    return ctx, ctx.new_page


async def checar(pagina):
    if "/login" in pagina.url or "checkpoint" in pagina.url:
        raise Parar("O Facebook pediu login. Parei.")
    txt = (await pagina.inner_text("body"))[:3000].lower()
    if any(b in txt for b in BLOQUEIO):
        raise Parar("O Facebook está segurando (aviso de bloqueio/verificação). Parei.")


def arquivar_coleta_anterior():
    """Move os arquivos da rodada anterior para dados/coleta_<data>/ (não apaga nada)."""
    velhos = [f for f in os.listdir(DADOS) if f.endswith(".json") and
              f.startswith(("_anuncios_", "lote_", "classificacao", "descartes"))]
    if not velhos:
        return
    dia = date.fromtimestamp(os.path.getmtime(os.path.join(DADOS, velhos[0]))).isoformat()
    destino = os.path.join(DADOS, f"coleta_{dia}")
    os.makedirs(destino, exist_ok=True)
    for f in velhos:
        shutil.move(os.path.join(DADOS, f), os.path.join(destino, f))
    log(f"Coleta anterior ({len(velhos)} arquivos) movida para dados/coleta_{dia}")


async def baixar_fotos(pagina, urls):
    fotos = []
    for u in urls[:MAX_FOTOS]:
        try:
            r = await pagina.context.request.get(u, timeout=30000)
            if r.ok and r.headers.get("content-type", "").startswith("image/"):
                fotos.append(base64.b64encode(await r.body()).decode())
        except Exception:
            pass
    return fotos


class Gravador:
    """Junta o que as guias leem e grava dados/_anuncios_NN.json a cada SALVAR_A_CADA."""

    def __init__(self):
        self.lote, self.arq, self.ok, self.feitos = [], 1, 0, 0
        self.repetir, self.ultima_volta = [], False

    def add(self, d):
        self.lote.append(d)
        self.feitos += 1
        self.ok += 0 if d.get("erro") else 1
        if len(self.lote) >= SALVAR_A_CADA:
            self.flush()

    def flush(self):
        if not self.lote:
            return
        if self.arq == 1:
            arquivar_coleta_anterior()  # só arquiva quando já há coleta nova para pôr no lugar
        with open(os.path.join(DADOS, f"_anuncios_{self.arq:02d}.json"), "w", encoding="utf-8") as f:
            json.dump(self.lote, f, ensure_ascii=False)
        self.lote, self.arq = [], self.arq + 1


async def guia(n, pagina, fila, total, grav, parar):
    """Uma guia: pega POR_VEZ anúncios da fila, lê um a um com pausa, descansa e pega mais."""
    while fila and not parar.is_set():
        vez = [fila.pop(0) for _ in range(min(POR_VEZ, len(fila)))]
        for item in vez:
            if parar.is_set():
                return
            try:
                await pagina.goto(f"https://www.facebook.com/marketplace/item/{item}/", wait_until="domcontentloaded")
                await checar(pagina)
                d = await pagina.evaluate(EXTRATOR)
            except Parar as e:
                log(f"[guia {n}] {e}")
                parar.set()
                return
            except Exception as e:
                d = {"id": item, "erro": str(e)[:120]}
            if not d.get("erro"):
                d["fotos"] = await baixar_fotos(pagina, d.pop("fotos_url", []))
            elif item not in grav.repetir and not grav.ultima_volta:
                grav.repetir.append(item)  # costuma ser só lentidão: tenta de novo no fim
                log(f"[guia {n}] {item}: não carregou, fica para o fim")
                await dormir(PAUSA_ANUNCIO)
                continue
            grav.add(d)
            log(f"[guia {n}] [{grav.feitos}/{total}] {d.get('titulo', d.get('erro', ''))[:40]} | "
                f"R$ {d.get('preco', '')} | {len(d.get('fotos', []))} fotos")
            await dormir(PAUSA_ANUNCIO)
        if fila:
            log(f"[guia {n}] terminou {len(vez)} anúncios; descansando antes dos próximos...")
            await dormir(PAUSA_LONGA)


async def coletar(buscas, max_anuncios):
    os.makedirs(DADOS, exist_ok=True)
    async with async_playwright() as p:
        nav, nova_guia = await abrir_chrome(p)
        try:
            pg = await nova_guia()
            ids, feitas = [], 0
            try:
                for k, termo in enumerate(buscas):
                    if k:
                        await dormir(PAUSA_BUSCA)
                    url = MARKETPLACE + termo if termo.startswith("/") else f"{MARKETPLACE}/search/?query={quote(termo)}"
                    await pg.goto(url, wait_until="domcontentloaded")
                    await dormir((4, 7))
                    await checar(pg)
                    achados = await pg.evaluate(ROLAR)
                    novos = [i for i in achados if i not in ids]
                    ids += novos
                    feitas += 1
                    log(f"Busca '{termo}': {len(achados)} anúncios ({len(novos)} novos)")
                    if not achados and k == 0:
                        raise Parar("A primeira busca voltou vazia: o Facebook pode estar exigindo login.")
            except Parar as e:
                log(str(e))
                if not ids:
                    return 2
            ids = ids[:max_anuncios]
            log(f"{feitas}/{len(buscas)} buscas feitas. Abrindo {len(ids)} anúncios em {GUIAS} guias...")

            paginas = [pg] + [await nova_guia() for _ in range(GUIAS - 1)]
            grav, parar, total = Gravador(), asyncio.Event(), len(ids)

            async def com_atraso(i, pagina):  # guias começam defasadas, não todas no mesmo segundo
                await asyncio.sleep(i * random.uniform(5, 10))
                await guia(i + 1, pagina, ids, total, grav, parar)
            await asyncio.gather(*(com_atraso(i, pagina) for i, pagina in enumerate(paginas)))
            if grav.repetir and not parar.is_set():
                log(f"Tentando de novo {len(grav.repetir)} anúncios que não carregaram...")
                grav.ultima_volta = True
                await guia(1, paginas[0], grav.repetir, total, grav, parar)
            grav.flush()
            log(f"Fim: {grav.ok} anúncios lidos com sucesso.")
            return 0 if grav.ok else 3
        finally:
            await nav.close()


def main():
    global ANONIMO, GUIAS, PAUSA_BUSCA, PAUSA_ANUNCIO, PAUSA_LONGA, POR_VEZ, DADOS
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["login", "teste", "coletar"])
    ap.add_argument("--so", choices=list(BUSCAS), help="só um grupo de buscas")
    ap.add_argument("--max", type=int, default=MAX_ANUNCIOS, help="teto de anúncios")
    ap.add_argument("--guias", type=int, default=GUIAS, help="quantas guias abrem anúncios ao mesmo tempo")
    ap.add_argument("--perfil", action="store_true", help="usa o perfil salvo (com login) em vez de guias anônimas")
    a = ap.parse_args()
    ANONIMO, GUIAS = not (a.perfil or a.modo == "login"), max(1, a.guias)

    if a.modo == "login":
        async def login():
            async with async_playwright() as p:
                ctx, nova = await abrir_chrome(p)
                await (await nova()).goto("https://www.facebook.com/")
                await asyncio.to_thread(input, "Entre no Facebook na janela que abriu e depois tecle Enter aqui...")
                await ctx.close()
        asyncio.run(login())
        return 0

    if a.modo == "teste":
        PAUSA_BUSCA, PAUSA_ANUNCIO, PAUSA_LONGA, POR_VEZ = (15, 25), (5, 9), (10, 20), 2
        DADOS = os.path.join(DADOS, "teste")  # não mexe na coleta oficial
        rc = asyncio.run(coletar(["iphone 13", "ps5"], 12))
        log(f"Teste gravado em {DADOS}")
        return rc

    grupos = [a.so] if a.so else list(BUSCAS)
    rc = asyncio.run(coletar([t for g in grupos for t in BUSCAS[g]], a.max))
    if rc == 0:
        log("Atualizando o histórico e conferindo os anúncios que sumiram ...")
        historico.registrar_coleta(BASE)
        historico.verificar(BASE)
        log("Gerando fotos/oportunidades.html ...")
        subprocess.run([sys.executable, os.path.join(BASE, "salvar_fotos.py")])
        if a.so in (None, "iphone"):
            log("Classificando iPhones com o Haiku e gerando as planilhas ...")
            if subprocess.run([sys.executable, os.path.join(BASE, "classificar_haiku.py")]).returncode == 0:
                subprocess.run([sys.executable, os.path.join(BASE, "gerar_excel.py")])
        log("Gerando index.html e publicando no GitHub ...")
        if subprocess.run([sys.executable, os.path.join(BASE, "gerar_pagina.py")]).returncode == 0:
            publicar(BASE, f"Coleta de {datetime.now():%d/%m/%Y}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
