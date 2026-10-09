"""
Histórico dos anúncios: quando cada um apareceu, por quanto, e quando saiu do ar (vendido ou apagado).

Fica em historico/anuncios.json (vai para o GitHub junto com a página). Serve para os dois projetos:
o de iPhone/TV/videogame (esta pasta) e o de aluguel (../marketplace-aluguel).

    python historico.py registrar [--proj PASTA] [--dia AAAA-MM-DD]   # junta a coleta de dados/ ao histórico
    python historico.py verificar [--proj PASTA] [--max N]            # revisita os que não vieram na coleta
    python historico.py resumo    [--proj PASTA]                      # ranking de vendidos no terminal

Status de cada anúncio:
    ativo     visto na coleta ou revisitado e ainda no ar (atualiza o preço se mudou)
    vendido   página mostra "· Indisponível" (o vendedor marcou como vendido)  -> certeza
    apagado   o link cai na tela de login (anúncio removido)                    -> venda por fora OU desistência
A verificação usa uma guia anônima, devagar, e confere um anúncio de controle antes de marcar
"apagado": se o controle também cair no login, é bloqueio do Facebook e a verificação para.
"""

import argparse
import glob
import json
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
PAUSA = (8, 18)            # segundos entre um anúncio e outro
PAUSA_LONGA = (90, 180)    # descanso a cada POR_VEZ anúncios
POR_VEZ = 10
BLOQUEIO = ("temporariamente bloqueado", "você está indo rápido demais", "you're temporarily blocked",
            "you’re temporarily blocked", "confirme que é você", "security check")


def arquivo(proj):
    return os.path.join(proj, "historico", "anuncios.json")


def carregar(proj):
    try:
        return json.load(open(arquivo(proj), encoding="utf-8"))
    except FileNotFoundError:
        return {}


def salvar(proj, H):
    os.makedirs(os.path.dirname(arquivo(proj)), exist_ok=True)
    tmp = arquivo(proj) + ".tmp"
    json.dump(H, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, arquivo(proj))


def valor(preco):
    m = re.search(r"[\d.]+", str(preco or ""))
    return int(m.group().replace(".", "")) if m and m.group().replace(".", "") else 0


def anotar_preco(h, dia, preco):
    if preco and (not h["precos"] or h["precos"][-1][1] != preco):
        h["precos"].append([dia, preco])


def registrar_itens(proj, itens, dia=None):
    """Os anúncios lidos agora ficam 'ativo' e vistos hoje (novos entram com primeiro_visto = hoje)."""
    dia = dia or date.today().isoformat()
    H, n_novos, n = carregar(proj), 0, 0
    for d in itens:
        if d.get("erro") or not d.get("id"):
            continue
        n += 1
        h = H.get(d["id"])
        if not h:
            n_novos += 1
            h = H[d["id"]] = {"titulo": "", "local": "", "mod": "", "primeiro_visto": dia, "precos": []}
        h.update(titulo=d.get("titulo", ""), local=d.get("local", ""), status="ativo",
                 ultimo_ativo=dia, ultima_coleta=dia, data_status=dia)
        anotar_preco(h, dia, valor(d.get("preco")))
    salvar(proj, H)
    print(f"histórico: {n} anúncios lidos, {n_novos} novos, {len(H)} no total")
    return H


def registrar_coleta(proj, dia=None):
    """Tudo que veio em dados/_anuncios_*.json (coleta completa) fica 'ativo' e visto hoje."""
    itens = []
    for f in sorted(glob.glob(os.path.join(proj, "dados", "_anuncios_*.json"))):
        itens += json.load(open(f, encoding="utf-8-sig"))
    return registrar_itens(proj, itens, dia)


def definir_modelos(proj, mods):
    """mods = {id: (categoria, modelo)}; chamado pelo gerador da página, que é quem sabe o modelo."""
    H = carregar(proj)
    for i, (cat, mod) in mods.items():
        if i in H:
            H[i]["cat"], H[i]["mod"] = cat, mod
    salvar(proj, H)


def ler_pagina(pg, item):
    pg.goto(f"https://www.facebook.com/marketplace/item/{item}/", timeout=60000)
    try:  # espera o anúncio desenhar (pausa fixa às vezes lê a página ainda vazia)
        pg.wait_for_function(r"/\nAnunciado|\/\s*m[êe]s|Indispon[íi]vel/.test(document.body.innerText)"
                             r" || location.pathname.includes('/login')", timeout=25000)
    except Exception:
        pass
    time.sleep(random.uniform(1, 2))
    if "/login" in pg.url:
        return "login", 0
    t = pg.inner_text("body")
    if any(b in t.lower() for b in BLOQUEIO):
        return "bloqueio", 0
    L = [s.strip() for s in t.split("\n") if s.strip()]
    preco = valor(next((s for s in L if re.match(r"^R\$\s?[\d.]+", s)), ""))
    if re.search(r"^·?\s*(Indispon[íi]vel|Vendido|Alugado)$", t, re.M):
        return "vendido", preco
    if preco or any(s.startswith("Anunciado") for s in L):
        return "ativo", preco
    return "incerto", 0


def verificar(proj, dia=None, maximo=None):
    from playwright.sync_api import sync_playwright
    dia = dia or date.today().isoformat()
    H = carregar(proj)
    fila = [i for i, h in H.items() if h.get("status") == "ativo" and h.get("ultima_coleta") != dia
            and h.get("verificado") != dia]
    controles = [i for i, h in H.items() if h.get("ultima_coleta") == max(x.get("ultima_coleta", "") for x in H.values())]
    random.shuffle(fila)
    fila.sort(key=lambda i: H[i].get("verificado") or H[i].get("ultima_coleta") or "")  # os conferidos há mais tempo primeiro
    fila = fila[:maximo] if maximo else fila
    print(f"verificando {len(fila)} anúncios que não vieram na última coleta (controles: {len(controles)})")
    cont = defaultdict(int)
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=False)
        pg = nav.new_context(locale="pt-BR", viewport={"width": 1280, "height": 900}).new_page()
        try:
            for n, item in enumerate(fila, 1):
                st, preco = ler_pagina(pg, item)
                if st == "login":  # anúncio apagado ou o Facebook pedindo login para tudo? confere um controle
                    time.sleep(random.uniform(*PAUSA))
                    st_c, _ = ler_pagina(pg, random.choice(controles)) if controles else ("ativo", 0)
                    st = "apagado" if st_c in ("ativo", "vendido") else "bloqueio"
                if st == "bloqueio":
                    print(f"  Facebook bloqueou/pediu login no controle depois de {n - 1} anúncios; paro aqui e retomo na próxima.")
                    break
                h = H[item]
                if st != "incerto":  # incerto = não carregou; tenta de novo na próxima
                    h["verificado"] = dia
                if st == "ativo":
                    h["ultimo_ativo"] = dia
                    anotar_preco(h, dia, preco)
                elif st in ("vendido", "apagado"):
                    h["status"], h["data_status"] = st, dia
                    anotar_preco(h, dia, preco)
                cont[st] += 1
                print(f"  {n}/{len(fila)} {item} {st} {preco or ''} | {h['titulo'][:40]}", flush=True)
                if n % 10 == 0:
                    salvar(proj, H)
                time.sleep(random.uniform(*(PAUSA_LONGA if n % POR_VEZ == 0 else PAUSA)))
        finally:
            salvar(proj, H)
            nav.close()
    print("resultado:", dict(cont))
    return cont


def dias(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def resumo(H):
    """Por modelo: quantos saíram do ar, tempo até sair e preço de quem vendeu vs. quem continua."""
    grupos = defaultdict(list)
    for h in H.values():
        if h.get("mod"):
            grupos[h["mod"]].append(h)
    linhas = []
    for mod, hs in grupos.items():
        vend = [h for h in hs if h["status"] == "vendido"]
        apag = [h for h in hs if h["status"] == "apagado"]
        ativ = [h for h in hs if h["status"] == "ativo"]
        sairam = vend + apag
        # tempo até sair: do primeiro dia visto até o meio da janela entre o último "ativo" e o dia em que saiu
        t = [dias(h["primeiro_visto"], h["ultimo_ativo"]) + dias(h["ultimo_ativo"], h["data_status"]) / 2 for h in sairam]
        pv = [h["precos"][-1][1] for h in sairam if h["precos"]]
        pa = [h["precos"][-1][1] for h in ativ if h["precos"]]
        linhas.append({"mod": mod, "anuncios": len(hs), "vendidos": len(vend), "apagados": len(apag), "ativos": len(ativ),
                       "giro": round(100 * len(sairam) / len(hs)) if hs else 0,
                       "dias": round(statistics.median(t)) if t else None,
                       "preco_saiu": round(statistics.median(pv)) if pv else None,
                       "preco_ativo": round(statistics.median(pa)) if pa else None})
    linhas.sort(key=lambda r: (-(r["vendidos"] + r["apagados"]), -r["anuncios"]))
    inicio = min((h["primeiro_visto"] for h in H.values()), default="")
    return {"inicio": inicio, "linhas": linhas}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["registrar", "verificar", "resumo"])
    ap.add_argument("--proj", default=AQUI)
    ap.add_argument("--dia")
    ap.add_argument("--max", type=int)
    a = ap.parse_args()
    if a.modo == "registrar":
        registrar_coleta(a.proj, a.dia)
    elif a.modo == "verificar":
        verificar(a.proj, a.dia, a.max)
    else:
        r = resumo(carregar(a.proj))
        print("histórico desde", r["inicio"])
        for l in r["linhas"]:
            print(f"  {l['mod'][:28]:28} {l['anuncios']:4} anúncios | {l['vendidos']:3} vendidos {l['apagados']:3} apagados "
                  f"| giro {l['giro']:3}% | {l['dias']} dias | saiu a R$ {l['preco_saiu']} vs ativo R$ {l['preco_ativo']}")


if __name__ == "__main__":
    main()
