"""
Tela temporária: eletrônicos muito baratos no Marketplace da cidade de uma viagem, publicada cifrada em
agenda-iphone/marketplace/viagem/ (mesmas senhas e o mesmo "lembrar neste aparelho" da página principal, privado.py).

Tudo o que identifica a viagem (cidade, ID de localização do Facebook, raio, data final, cidades vizinhas, achados
de fora do Facebook e dicas locais) fica só em dados/viagem.json, fora do git: os repositórios são públicos.
A coleta é só HTTP (urllib), sem Chrome/Playwright: a primeira página de cada busca, com pausa de 2 a 4 s.
"Muito barato" = 25% a 55% abaixo da média do mesmo modelo (mesma normalização de salvar_fotos.classificar):
na própria região com 5+ anúncios, senão a de Palmas em historico/medias.json com 5+ anúncios, senão sem referência.

    python viagem.py               # coleta, gera dados/viagem/site/index.html e publica marketplace/viagem/
    python viagem.py --teste       # 2 buscas, gera a página local e não publica
    python viagem.py --sem-coleta  # regera com o que já foi visto (dados/viagem/vistos.json) e publica
    python viagem.py --remover     # apaga marketplace/viagem/ do site e publica

Depois da data final de dados/viagem.json, rodar o script remove a tela sozinho. A página principal só mostra o
link (dentro do cofre) enquanto a data valer e marketplace/viagem/ existir (gerar_pagina.py + teste no navegador).
"""
import argparse
import ctypes
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import golpistas
import privado
from salvar_fotos import classificar as classificar_base  # iPhone 13-18, Galaxy S25/S26, TV por polegada, videogames

PROJ = Path(__file__).resolve().parent
CFG_ARQ = PROJ / "dados" / "viagem.json"
PASTA = PROJ / "dados" / "viagem"
VISTOS = PASTA / "vistos.json"
ESTADO = PASTA / "estado.json"  # a última coleta (quando, quantas buscas, bloqueio)
SITE = PASTA / "site"
DESTINO = "marketplace/viagem"
BUSCAS = ["iphone", "iphone 15", "iphone 16", "samsung galaxy s", "notebook", "macbook", "ps5", "xbox",
          "nintendo switch", "smart tv", "airpods", "apple watch", "ipad", "monitor",
          # 20/10/2026: só a 1ª página (24 anúncios) de cada busca; termos por modelo trazem anúncios que a busca larga não mostra
          "iphone 13", "iphone 14", "iphone 12", "iphone 11", "iphone 17", "galaxy s23", "galaxy s24", "galaxy s25",
          "notebook gamer", "ps4", "tv 50", "tv 55"]
PAUSA = (2, 4)
RAM_MIN = 250        # MB livres; abaixo disso a rodada fica para depois
DESCONTO_MIN = 25    # % abaixo da referência para "muito barato"
BOM_DEMAIS = 55      # mais que isso abaixo: golpe, peça ou erro (fica separado)
PISO = 0.15          # abaixo de 15% da referência: preço absurdo, fora da tela
N_REF = 5            # anúncios mínimos para uma média valer como referência
VALIDADE_H = 48      # anúncio que não aparece em nenhuma busca há mais de 48 h sai da tela
CABECALHOS = {  # sem os Sec-Fetch o Facebook responde 400; sem Accept-Encoding o HTML vem sem compressão
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="141", "Not?A_Brand";v="8", "Google Chrome";v="141"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
}

PRECO_MIN = {"iPhone": 300, "Galaxy": 300, "Notebook": 300, "iPad": 250, "Apple Watch": 150, "AirPods": 80,
             "TV": 100, "Monitor": 100, "Videogame": 100}
PRECO_MAX = {"TV": 40000}  # demais: 20.000
# Copiados de gerar_pagina.py (importar roda a página inteira): defeito citado, com negação logo antes valendo "sem defeito"
DEFEITO = re.compile(r"defeito|trincad|\btrinc[oa]s?\b|desligand|desliga sozinh|n[ãa]o liga|queimad|quebrad|mancha|listra|\btravand|vezes trava"
                     r"|tela (j[áa] )?(foi )?(substitu|trocad)|troc\w* (a )?tela|tela (linha )?premium|soft ?oled|tela (paralela|incell|n[ãa]o original)"
                     r"|face ?id (off|n[ãa]o|n\b)|face off|sem face|c[âa]mera[^\n]{0,15}(borrad|emba[çc]|n[ãa]o funciona|tremend)|detalhe (n[ao] )?c[âa]mera|troca(r)? a c[âa]mera"
                     r"|\bdet?h?al?h?es?\b( pequenos?)? n[ao]s? (vidro|tela|c[âa]mera)|mensagem (de )?(bateria|c[âa]mera|tela|pe[çc]a)|pe[çc]a desconhecida|n[ãa]o genu[íi]n|bateria usada"
                     r"|n[ãa]o (t[áa] )?peg(a|ando) (o )?chip|sim (est[áa] )?bloquead|bloquead[ao] (por|na|pela) operadora|icloud bloq|conta bloq"
                     r"|\bproblemas? (de|n[ao]) |controles?\b[^.\n]{0,25}\bdrift|drift n[oa] (controle|anal[óo]gico)|controles?\b[^.\n]{0,25}\b(ruins?|desgastad)|retirad[ao] (de|pra|para) pe|\bp(a)?ra pe[çc]as"
                     r"|n[ãa]o d[áa] (v[íi]deo|imagem)|sem imagem|tela preta|\bp(a)?ra arrumar|precisa (de )?(reparo|conserto|arrumar)|levar na assist[êe]ncia", re.I)
NEGA = re.compile(r"(\bsem\b|\bnenhum|\bnem\b|n[ãa]o (tem|possui|apresenta|h[áa])|\bnunca\b|\blivre de)[^.,;:!?\n✅❌•]{0,22}\Z|\bzero\s*\Z", re.I)
# fora em qualquer posição do título: peça, troca, compra, caixa, réplica...
FORA = re.compile(r"\bpe[çc]as?\b|retirad[ao] (de|pra|para) pe|caixa vazia|s[óo] (a )?caixa|\btroc[oa]s?\b|\btroca\b|\bcompro\b|\bprocuro\b"
                  r"|\balug[oa]\b|\baluguel\b|\bconserto\b|assist[êe]ncia|\bbloquead|r[ée]plica|\bclone\b|\bsabor\b|xing ?ling|\bmontado\b"
                  r"|placa[- ]m[ãa]e|s[óo] (o )?(carregador|controle|case|estojo|fone)|(case|estojo) avulso|fone (direito|esquerdo)|lado (direito|esquerdo)"
                  r"|\b(tipo|estilo|similar|igual)\s+(ao?\s+|o\s+)?(air ?pods?|iphone|apple ?watch)|primeira linha|linha premium|\b1[:.]1\b"
                  r"|caixas? de som|soundbar|\bprojetor", re.I)  # "Caixa de som Smart JBL" e projetor "Smart TV" não são TV
# acessório antes do aparelho ("Capa iPhone 15", "Controle PS5") ou "para <aparelho>" ("Película para iPad"): é o acessório
ACESS = re.compile(r"\bcapas?\b|capinha|pel[íi]cula|\bcase\b|carregador|\bcabo\b|\bfonte\b|suporte|pulseira|controle|\bjogos?\b|headset|\bfones?\b"
                   r"|\btela\b|display|bateria|carca[çc]a|teclado|mouse|\bbase\b|\bdock\b|\bkit\b|bolsa|mochila|volante|adaptador|\bhub\b|cooler|\bssd\b|\bhd\b|mem[óo]ria|estojo", re.I)
# "Caixa iPhone 13" vendida sozinha já cai no PRECO_MIN; "caixa" aqui descartava "Na caixa iPhone 13" e "PS4 com caixa"
STREAMING = re.compile(r"apple\s*tv|tv\s*box|chromecast|fire\s*(tv\s*)?stick|mi\s*box|roku", re.I)
PARA = re.compile(r"\b(para|pra|p/)\s+(o\s+|a\s+)?(iphone|galaxy|samsung|ipad|macbook|notebook|apple ?watch|air ?pods|ps[45]|playstation|xbox|switch|nintendo|tv|smart|monitor)", re.I)
LACRADO = re.compile(r"lacrad", re.I)
# modelo genérico demais para ter média (como "TV" sem polegada em gerar_pagina.py)
GENERICOS = {"iPad", "iPad Pro", "iPad Air", "iPad mini", "Notebook", "Notebook gamer", "MacBook", "MacBook Air", "MacBook Pro",
             "Apple Watch", "AirPods", "Monitor", "TV", "TV (não smart)"}
GENERICO = re.compile(r"^Notebook (i\d|Ryzen|Core)|\(Intel\)")


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def ler_json(arq):
    """JSON gravado à mão no Windows: UTF-8 com ou sem BOM, UTF-16 (">" do PowerShell 5.1) ou cp1252 (Set-Content)."""
    b = Path(arq).read_bytes()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return json.loads(b.decode("utf-16"))
    try:
        return json.loads(b.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return json.loads(b.decode("cp1252"))


def cita_defeito(t):
    return any(not NEGA.search(t[max(0, m.start() - 40):m.start()]) for m in DEFEITO.finditer(t))


def media_robusta(v):
    """Média sem os absurdos (fora de 40%-250% da mediana), como em gerar_pagina.py."""
    med = statistics.median(v)
    ok = [x for x in v if 0.4 * med <= x <= 2.5 * med]
    return round(statistics.mean(ok)), len(ok)


def ram_livre_mb():
    class Mem(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                   [(n, ctypes.c_ulonglong) for n in ("tot", "livre", "tpf", "lpf", "tv", "lv", "lev")]
    m = Mem()
    m.dwLength = ctypes.sizeof(Mem)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.livre // 2**20


class Trava:
    """A mesma de atualizar.py: não roda junto com a rodada Novos/Compilado (que também usa o git do worktree)."""
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


def log(msg):
    print(msg)
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(PASTA / "viagem.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


# ---------------------------------------------------------------- coleta (só HTTP)
class Bloqueio(Exception):
    pass


def baixar(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=CABECALHOS), timeout=30) as r:
            final, corpo = r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise Bloqueio(f"HTTP {e.code}")
    if re.search(r"/login|checkpoint", final):
        raise Bloqueio("Facebook pediu login")
    return corpo


def extrair(html):
    """Anúncios do JSON embutido na página de busca (título, preço, cidade, foto, vendido, vendedor)."""
    achados = {}

    def anda(o):
        if isinstance(o, dict):
            if "marketplace_listing_title" in o and o.get("id"):
                achados[str(o["id"])] = o
            for v in o.values():
                anda(v)
        elif isinstance(o, list):
            for v in o:
                anda(v)

    for m in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S):
        if "marketplace_listing_title" in m.group(1):
            try:
                anda(json.loads(m.group(1)))
            except ValueError:
                pass
    out = []
    for i, o in achados.items():
        geo = (o.get("location") or {}).get("reverse_geocode") or {}
        try:
            preco = int(float((o.get("listing_price") or {}).get("amount") or 0))
        except (TypeError, ValueError):
            preco = 0
        foto = ((o.get("primary_listing_photo") or {}).get("image") or {}).get("uri") or ""
        vend = o.get("marketplace_listing_seller") or {}
        out.append({"id": i, "titulo": (o.get("marketplace_listing_title") or "").strip(), "preco": preco,
                    "cidade": geo.get("city") or "", "uf": geo.get("state") or "",
                    "foto": foto if foto.startswith("https://") else "", "criado": o.get("creation_time"),
                    "vendido": bool(o.get("is_sold") or o.get("is_pending") or o.get("is_hidden") or o.get("is_live") is False),
                    "vendedor": vend.get("name") or "", "vendedor_id": vend.get("id") or ""})
    return out


def coletar(cfg, buscas):
    vistos = json.loads(VISTOS.read_text(encoding="utf-8")) if VISTOS.exists() else {}
    agora = datetime.now().isoformat(timespec="minutes")
    feitas, bloqueio, vazias = 0, None, 0
    for n, termo in enumerate(buscas):
        if n:
            time.sleep(random.uniform(*PAUSA))
        url = (f"https://www.facebook.com/marketplace/{cfg['local_id']}/search/?query={quote(termo)}"
               f"&sortBy=creation_time_descend&radius={cfg.get('raio_km', 40)}&exact=false")
        try:
            L = extrair(baixar(url))
        except (Bloqueio, OSError) as e:
            bloqueio = f"busca {n + 1} de {len(buscas)}: {e}"
            log(f"Facebook barrou a coleta ({bloqueio}); fico com o que já veio")
            break
        if not L:  # uma busca vazia pode ser só falta de anúncio; duas seguidas, bloqueio ou página mudada
            vazias += 1
            if vazias >= 2:
                bloqueio = f"buscas {n} e {n + 1} de {len(buscas)} vieram sem anúncios (página mudou ou bloqueio)"
                log(bloqueio + "; paro aqui")
                break
            log(f"busca {n + 1}/{len(buscas)} ({termo}) veio vazia; sigo para a próxima")
            continue
        vazias = 0
        feitas += 1
        for d in L:
            v = vistos.get(d["id"], {"primeiro_visto": agora})
            v.update(d, ultimo_visto=agora)
            vistos[d["id"]] = v
        log(f"busca {n + 1}/{len(buscas)}: {len(L)} anúncios")
    PASTA.mkdir(parents=True, exist_ok=True)
    VISTOS.write_text(json.dumps(vistos, ensure_ascii=False), encoding="utf-8")
    ESTADO.write_text(json.dumps({"quando": datetime.now().strftime("%d/%m %H:%M"), "buscas": feitas, "de": len(buscas),
                                  "bloqueio": bloqueio}, ensure_ascii=False), encoding="utf-8")
    return feitas, bloqueio


# ---------------------------------------------------------------- classificação
def classificar(titulo):
    """(categoria, modelo, posição do aparelho no título). Mesma normalização do projeto onde ela existe."""
    titulo = re.sub(r"(?<=\w)[+_](?=\w)", " ", titulo)  # "Iphone+18+pro+max" (mas "S23+ 256" continua Plus)
    t = titulo.lower().replace("promax", "pro max")
    m = re.search(r"\bipad\b", t)
    if m:
        v = re.search(r"\b(pro|air|mini)\b", t)
        chip = re.search(r"\bm([1-5])\b", t)
        # "9ª geração", "9° geração", "Gen 9", "geração 9", "iPad 6"
        ger = (re.search(r"\b(\d{1,2})\s*(ª|a|º|°|o)?\s*gera", t) or re.search(r"\bgen(?:era[çc][ãa]o)?\s*(\d{1,2})\b", t)
               or re.search(r"ipad\s+(\d{1,2})\b(?!\s*(gb|pol|\"|”))", t))
        nome = "iPad" + (f" {v.group(1).capitalize()}" if v else "")
        nome = nome.replace("Mini", "mini") + (f" M{chip.group(1)}" if chip else f" {ger.group(1)}ª geração" if ger else "")
        return "iPad", nome, m.start()
    m = re.search(r"air\s?pods?", t)
    if m:
        pro, ger = re.search(r"\bpro\s*(\d)?", t), re.search(r"pods?\s*(\d)\b|(\d)\s*(ª|a)?\s*gera", t)
        v = ("Max" if re.search(r"\bmax\b", t) else f"Pro {pro.group(1) or ''}".strip() if pro
             else (ger.group(1) or ger.group(2)) if ger else "")
        return "AirPods", ("AirPods " + v).strip(), m.start()
    m = re.search(r"apple\s*watch|\biwatch\b", t)
    if m:
        u = re.search(r"\bultra\s*(\d)?", t)
        s = re.search(r"\bseries\s*(\d{1,2})\b|\bs(\d{1,2})\b", t)
        v = (f"Ultra {u.group(1)}".strip() if u else "SE" if re.search(r"\bse\b", t) else
             f"Series {s.group(1) or s.group(2)}" if s else "")
        return "Apple Watch", ("Apple Watch " + v).strip(), m.start()
    m = re.search(r"mac\s?book", t)
    if m:
        v = re.search(r"\b(air|pro)\b", t)
        chip = re.search(r"\bm([1-5])\b", t)
        nome = "MacBook" + (f" {v.group(1).capitalize()}" if v else "") + (f" M{chip.group(1)}" if chip else " (Intel)" if re.search(r"\bi[3579]\b|intel", t) else "")
        return "Notebook", nome, m.start()
    m = re.search(r"notebook|laptop|ultrabook|chromebook", t)
    if m:
        if re.search(r"rtx|gtx|nitro|\btuf\b|legion|\bloq\b|predator|\brog\b|odyssey|victus|\bomen\b|alienware|gamer", t):
            g = re.search(r"(rtx|gtx)\s?(\d{4})", t)
            return "Notebook", "Notebook gamer" + (f" {g.group(1).upper()} {g.group(2)}" if g else ""), m.start()
        p = re.search(r"\b(i[3579])\b|ryzen\s?([3579])\b|core\s?ultra", t)
        nome = ("Notebook " + (p.group(1) if p.group(1) else f"Ryzen {p.group(2)}" if p.group(2) else "Core Ultra")) if p else "Notebook"
        return "Notebook", nome, m.start()
    m = re.search(r"\bmonitor\b", t)
    if m and not re.search(r"bab[áa]|card[íi]ac|press[ãa]o|glic|pneu|veicular|de r[ée]|card[íi]o", t):
        pol = re.search(r"(\d{2})(?:[.,]\d)?\s*(\"|”|''|pol|polegadas|plg)", t) or re.search(r"\b(1[89]|2[0-9]|3[0-4]|4[0-9])\b", t)
        return "Monitor", f"Monitor {pol.group(1)} pol" if pol else "Monitor", m.start()
    cat, mod = classificar_base(titulo, "")
    # Apple TV, TV Box, Fire Stick: aparelho de streaming, não TV. "TV Box 32 GB" e "Fire Stick 1080p" davam polegada falsa:
    # sem os números de memória/resolução, se não sobrar polegada é streaming ("TV AOC Roku 43" continua TV 43 pol).
    if cat == "TV" and STREAMING.search(t):
        if classificar_base(re.sub(r"\b\d+\s*(gb|tb|mb|p|hz|fps|k)\b", " ", titulo, flags=re.I), "")[1] == "TV":
            return "Outros", "Outros", 0
    if cat == "Videogame" and not re.search(r"ps\s?\d|playstation|xbox|nintendo|switch", t):
        cat, mod = "Outros", "Outros"  # "câmera 360", "one" solto
    if mod == "Nintendo Switch" and re.search(r"\blite\b|switch\s*2\b", t):  # Lite custa metade; o 2, bem mais
        mod = "Nintendo Switch Lite" if re.search(r"\blite\b", t) else "Nintendo Switch 2"
    if cat == "TV" and re.search(r"n[ãa]o (é |e )?smart|sem smart", t):
        mod += " (não smart)"
    if cat != "Outros":
        k = re.search(r"iphone|galaxy|samsung|\bs\s?2[56]|\btv\b|televis|smart|ps\s?\d|playstation|xbox|nintendo|switch", t)
        return cat, mod, k.start() if k else 0
    m = re.search(r"iphone\s*(1[12]|x[rs]?|se)\s*(pro\s*max|pro|max|mini)?\b", t)
    if m:
        suf = {"pro max": " Pro Max", "pro": " Pro", "max": " Max", "mini": " mini"}.get(re.sub(r"\s+", " ", m.group(2) or ""), "")
        return "iPhone", f"iPhone {m.group(1).upper()}{suf}", m.start()
    m = re.search(r"\bs\s?(2[0-6])\s*(ultra|plus|\+|fe|edge)?(?!\w)", t)
    if m and re.search(r"galaxy|samsung", t):
        suf = {"ultra": " Ultra", "plus": "+", "+": "+", "fe": " FE", "edge": " Edge"}.get(m.group(2) or "", "")
        return "Galaxy", f"Galaxy S{m.group(1)}{suf}", min(m.start(), re.search(r"galaxy|samsung", t).start())
    return "Outros", "Outros", 0


def motivo_fora(d, cat, pos):
    t = d["titulo"]
    if cat == "Outros":
        return "fora das categorias"
    if FORA.search(t) or PARA.search(t):
        return "peça/troca/acessório"
    antes = t[:pos]
    if cat in ("TV", "Monitor"):  # "Tela 50 polegadas Samsung smart" é a TV
        antes = re.sub(r"\btela\b|display", "", antes, flags=re.I)
    if cat == "AirPods":  # "Fone AirPods Pro 2" é o AirPods
        antes = re.sub(r"\bfones?\b( de ouvido)?", "", antes, flags=re.I)
    if ACESS.search(antes):
        return "acessório"
    if cat == "Videogame" and d["preco"] < 400 and ACESS.search(t):
        return "jogo/acessório"
    if cita_defeito(t):
        return "cita defeito"
    if not PRECO_MIN.get(cat, 0) <= d["preco"] <= PRECO_MAX.get(cat, 20000):
        return "preço simbólico ou absurdo"
    return ""


# ---------------------------------------------------------------- página
def gerar(cfg):
    vistos = json.loads(VISTOS.read_text(encoding="utf-8")) if VISTOS.exists() else {}
    est = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    cidades = {sem_acento(c) for c in cfg["cidades"]}
    G = golpistas.carregar(str(PROJ))
    nomes_golpe = {golpistas.nome_chave(v.get("nome")) for v in G["vendedores"].values()} - {""}
    agora = datetime.now()
    fora, D = defaultdict(int), []
    for d in vistos.values():
        if (agora - datetime.fromisoformat(d["ultimo_visto"])).total_seconds() > VALIDADE_H * 3600:
            fora["não aparece há 48 h"] += 1
            continue
        if sem_acento(d["cidade"]) not in cidades:
            fora["fora da região"] += 1
            continue
        if d["vendido"]:
            fora["vendido/reservado"] += 1
            continue
        if golpistas.bloqueado(G, d["id"], d.get("vendedor_id"), d.get("vendedor")) or golpistas.nome_chave(d.get("vendedor")) in nomes_golpe:
            fora["golpista marcado"] += 1
            continue
        cat, mod, pos = classificar(d["titulo"])
        mot = motivo_fora(d, cat, pos)
        if mot:
            fora[mot] += 1
            continue
        D.append({**d, "cat": cat, "mod": mod})
    # referência por modelo: a própria região (5+), senão Palmas (historico/medias.json, 5+)
    por_mod = defaultdict(list)
    for d in D:
        if not LACRADO.search(d["titulo"]):  # "lacrado" é outro mercado (novo)
            por_mod[d["mod"]].append(d["preco"])
    arq_m = PROJ / "historico" / "medias.json"
    ev = json.loads(arq_m.read_text(encoding="utf-8")) if arq_m.exists() else {}
    palmas = ev[max(ev)] if ev else {}
    refs = {}
    for mod in {d["mod"] for d in D}:
        if mod in GENERICOS or GENERICO.search(mod):
            continue  # "iPad", "Notebook i5": mistura modelos de preços muito diferentes, a média não serve
        loc = media_robusta(por_mod[mod]) if len(por_mod[mod]) >= N_REF else None
        if loc and loc[1] >= N_REF:
            refs[mod] = [loc[0], loc[1], "região"]
        elif mod in palmas and palmas[mod][1] >= N_REF:
            refs[mod] = [palmas[mod][0], palmas[mod][1], "Palmas"]
    saida = []
    for d in D:
        r = refs.get(d["mod"])
        item = {"id": d["id"], "titulo": d["titulo"], "preco": d["preco"], "cat": d["cat"], "mod": d["mod"],
                "cidade": f"{d['cidade']}/{d['uf']}" if d["uf"] else d["cidade"], "foto": d["foto"],
                "link": f"https://www.facebook.com/marketplace/item/{d['id']}/", "criado": d.get("criado"),
                "ref": None, "ref_n": None, "ref_fonte": None, "pct": None, "grupo": "", "tags": []}
        if r:
            if d["preco"] < PISO * r[0]:
                fora["preço absurdo (<15% da média)"] += 1
                continue
            pct = round((d["preco"] / r[0] - 1) * 100)
            item.update(ref=r[0], ref_n=r[1], ref_fonte=r[2], pct=pct)
            if -pct > BOM_DEMAIS:
                item["grupo"] = "demais"
                item["tags"].append(["high", "bom demais: golpe ou peça?"])
            elif -pct >= DESCONTO_MIN:
                item["grupo"] = "barato"
                if -pct >= 35:
                    item["tags"].append(["warn", "muito abaixo: confira bem"])
        if LACRADO.search(d["titulo"]) and (item["pct"] is None or item["pct"] <= -15):
            item["tags"].append(["warn", "“lacrado”: exija nota e confira o serial"])
        saida.append(item)
    saida.sort(key=lambda x: (x["pct"] if x["pct"] is not None else 999, x["preco"]))
    resumo = {"data": agora.strftime("%d/%m"), "hora": agora.strftime("%H:%M"), "rotulo": cfg["rotulo"], "ate": cfg["ate"],
              "refs": refs, "fora": cfg.get("fora", []), "dicas": cfg.get("dicas", []), "coleta": est.get("quando", ""),
              "n_buscas": est.get("buscas", 0), "bloqueio": est.get("bloqueio"), "n_ref": N_REF, "faixa": [DESCONTO_MIN, BOM_DEMAIS]}
    tpl = (PROJ / "viagem_template.html").read_text(encoding="utf-8")
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(tpl.replace("__COFRE__", json.dumps(privado.cifrar({"D": saida, "R": resumo}))), encoding="utf-8")
    nb, nd = sum(x["grupo"] == "barato" for x in saida), sum(x["grupo"] == "demais" for x in saida)
    log(f"página: {len(saida)} anúncios na região, {nb} muito baratos, {nd} bons demais | fora: "
        + ", ".join(f"{k} {v}" for k, v in sorted(fora.items(), key=lambda kv: -kv[1])))
    return saida


# ---------------------------------------------------------------- publicação (worktree só de publicação, main)
def publicar_site(msg, remover=False):
    from publicar import AGENDA
    if not os.path.exists(os.path.join(AGENDA, ".git")):
        log(f"publicação: clone/worktree de agenda-iphone não encontrado em {AGENDA}")
        return 1
    git = lambda *a: subprocess.run(["git", "-C", AGENDA, *a], capture_output=True, text=True, encoding="utf-8")
    br = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if br != "main":
        log(f"publicação: {AGENDA} está no branch {br}, não publico (push só a partir da main)")
        return 2
    p = git("pull", "--rebase", "--autostash", "origin", "main")
    if p.returncode:
        log("publicação: pull falhou: " + (p.stderr or p.stdout).strip()[:200])
        return 1
    destino = os.path.join(AGENDA, *DESTINO.split("/"))
    if remover:
        shutil.rmtree(destino, ignore_errors=True)
    else:
        os.makedirs(destino, exist_ok=True)
        shutil.copyfile(SITE / "index.html", os.path.join(destino, "index.html"))
    git("add", "-A", "--", DESTINO)
    if git("diff", "--cached", "--quiet", "--", DESTINO).returncode == 0:
        # nada novo, mas um commit de antes pode ter ficado sem push (ex.: remoção cujo push falhou): manda de novo
        if git("rev-list", "--count", "origin/main..HEAD").stdout.strip() in ("", "0"):
            log("publicação: nada mudou.")
            return 0
        log("publicação: há commit local sem push; tentando de novo")
    else:
        c = git("commit", "-m", msg, "--", DESTINO)
        if c.returncode:
            log("publicação: commit falhou: " + (c.stderr or c.stdout).strip()[:200])
            return 1
    for _ in range(3):
        r = git("push", "origin", "HEAD:main")
        if r.returncode == 0:
            log("publicação: publicado.")
            return 0
        git("pull", "--rebase", "--autostash", "origin", "main")
    log("publicação: push falhou: " + r.stderr.strip()[:200])
    return r.returncode


def remover():
    r = publicar_site("Marketplace: encerra tela temporária", remover=True)
    if r == 0:
        shutil.rmtree(SITE, ignore_errors=True)
    return r


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true", help="2 buscas, gera local e não publica")
    ap.add_argument("--sem-coleta", action="store_true", help="regera com o que já foi visto e publica")
    ap.add_argument("--remover", action="store_true", help="apaga marketplace/viagem/ do site e publica")
    a = ap.parse_args()
    if not CFG_ARQ.exists():
        raise SystemExit(f"falta {CFG_ARQ} (configuração privada da viagem)")
    cfg = ler_json(CFG_ARQ)
    with Trava(str(PROJ / "dados")):
        if a.remover or date.today().isoformat() > cfg["ate"]:
            if not a.remover:
                log("viagem encerrada: removendo a tela do site")
            return remover()
        livre = ram_livre_mb()
        if livre < RAM_MIN and not a.sem_coleta:
            log(f"só {livre} MB de RAM livres (mínimo {RAM_MIN}): rodada adiada")
            return 0
        if not a.sem_coleta:
            coletar(cfg, BUSCAS[:2] if a.teste else BUSCAS)
        gerar(cfg)
        if a.teste:
            log(f"teste: página local em {SITE / 'index.html'} (não publicada)")
            return 0
        return publicar_site("Marketplace: tela temporária")


if __name__ == "__main__":
    sys.exit(main())
