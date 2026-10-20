"""
Página da coleta (index.html, publicada no GitHub): uma tira JPEG por anúncio em s/, médias da coleta,
destaques automáticos e o ranking de vendidos do histórico.

    python gerar_pagina.py [dd/mm/aaaa]      # data da coleta; padrão: hoje
"""
import base64
import glob
import io
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image

import golpistas
import historico
import privado

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent
DATA = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%d/%m/%Y")
REGIAO = ("palmas", "taquaralto", "taquaruçu", "taquarucu", "porto nacional", "paraíso do tocantins", "paraiso do tocantins")
LADO, MAXF = 380, 5

h = (PROJ / "fotos" / "oportunidades.html").read_text(encoding="utf-8")
m = re.search(r"const D=", h)
D = json.JSONDecoder().raw_decode(h[m.end():])[0]
D = [d for d in D if d["cat"] != "Outros" and d["local"].split(",")[0].strip().lower() in REGIAO and d["preco"] > 0]
ACESS = re.compile(r"\bjogos?\b|controle|suporte|\bcase\b|\bcapa\b|desbloque|\bcabo\b|\bfonte\b|pel[íi]cula|headset|volante|\bpainel\b|\brack\b|\bdock\b|carregador|m[íi]dia f[íi]sica|\bfallout\b|god of war|\bbatman\b|\bmario\b|\bzelda\b|\bgta\b|\bfifa\b|\bfc\s?\d{2}\b", re.I)
# título que começa pelo console ("PS4 com 4 jogos", "Nintendo Switch desbloqueado + combo") é o console, não o acessório
CONSOLE_1O = re.compile(r"^\W*(vendo|vende-se|troco)?\s*(o |um |meu |minha )?(console\s+|video ?game\s+)?(ps ?[2-5]|playstation|xbox|nintendo|switch)\b", re.I)
for d in D:
    if d["cat"] != "iPhone" and re.search(r"iphone", d["titulo"], re.I):
        d["cat"] = "Outros"  # iPhone antigo (XR, 11...) que caiu como videogame
    elif d["cat"] == "iPhone" and re.search(r"montado (n[oa]|em|sobre)\b|carca[çc]a (do|de) \d+ (n[oa]|em)|\bsabor\b|r[ée]plica|\bclone\b|xing ?ling", d["titulo"] + " " + d["descricao"], re.I):
        d["cat"] = "Outros"  # "iPhone 18 Pro montado no XR", "SABOR iPhone 16": não é o aparelho de verdade
    elif (d["cat"] not in ("iPhone", "Galaxy") and ACESS.search(d["titulo"])
          and not (d["cat"] == "Videogame" and CONSOLE_1O.search(d["titulo"]) and d["preco"] >= 500)
          and not re.search(r"\bcom\b.*controle|\+\s*controle|controles?\s*\+|e \d+ controles?|acompanha", d["titulo"], re.I)):
        d["cat"], d["mod"] = "Jogos e acessórios", "Jogos e acessórios"
D = [d for d in D if d["cat"] != "Outros"]
# preço simbólico ("R$ 1", "R$ 30" num celular) é "chama no chat", não preço de venda: fica fora da página
PRECO_MIN = {"iPhone": 300, "Galaxy": 300, "Videogame": 100, "TV": 100}
# e preço absurdo ("R$ 65.893" num iPhone) é erro de digitação: também fica fora
PRECO_MAX = {"iPhone": 20000, "Galaxy": 20000, "Videogame": 15000, "TV": 40000, "Jogos e acessórios": 15000}
simb = [d for d in D if not PRECO_MIN.get(d["cat"], 0) <= d["preco"] <= PRECO_MAX.get(d["cat"], 10**9)]
D = [d for d in D if d not in simb]
if simb:
    print(f"preço simbólico ou absurdo: {len(simb)} anúncios fora da página ({', '.join(f'{d['mod']} R$ {d['preco']}' for d in simb)})")
H = historico.carregar(PROJ)
D = [d for d in D if H.get(d["id"], {}).get("status", "ativo") == "ativo"]  # vendidos/apagados saem da página
G = golpistas.carregar(PROJ)
fora = [d for d in D if golpistas.bloqueado(G, d["id"], H.get(d["id"], {}).get("vendedor_id"), H.get(d["id"], {}).get("vendedor"))]
D = [d for d in D if d not in fora]
if fora:
    print(f"golpistas: {len(fora)} anúncios fora da página ({', '.join(sorted({H.get(d['id'], {}).get('vendedor') or d['id'] for d in fora}))})")
ontem = (date.today() - timedelta(days=1)).isoformat()
for d in D:
    h = H.get(d["id"], {})
    d["novo"] = h.get("primeiro_visto", "") >= ontem
    d["vendedor"] = h.get("vendedor", "")
    if len(h.get("precos", [])) > 1 and h["precos"][-1][1]:  # preço mudou desde a leitura: vale o mais recente
        d["preco_antes"], d["preco"] = h["precos"][0][1], h["precos"][-1][1]
DEFEITO = re.compile(r"defeito|trincad|\btrinc[oa]s?\b|desligand|desliga sozinh|n[ãa]o liga|queimad|quebrad|mancha|listra|\btravand|vezes trava"
                     r"|tela (j[áa] )?(foi )?(substitu|trocad)|troc\w* (a )?tela|tela (linha )?premium|soft ?oled|tela (paralela|incell|n[ãa]o original)"
                     r"|face ?id (off|n[ãa]o|n\b)|face off|sem face|c[âa]mera[^\n]{0,15}(borrad|emba[çc]|n[ãa]o funciona|tremend)|detalhe (n[ao] )?c[âa]mera|troca(r)? a c[âa]mera"
                     r"|\bdet?h?al?h?es?\b( pequenos?)? n[ao]s? (vidro|tela|c[âa]mera)|mensagem (de )?(bateria|c[âa]mera|tela|pe[çc]a)|pe[çc]a desconhecida|n[ãa]o genu[íi]n|bateria usada"
                     r"|n[ãa]o (t[áa] )?peg(a|ando) (o )?chip|sim (est[áa] )?bloquead|bloquead[ao] (por|na|pela) operadora|icloud bloq|conta bloq"
                     r"|\bproblemas? (de|n[ao]) |controles?\b[^.\n]{0,25}\bdrift|drift n[oa] (controle|anal[óo]gico)|controles?\b[^.\n]{0,25}\b(ruins?|desgastad)|retirad[ao] (de|pra|para) pe|\bp(a)?ra pe[çc]as"
                     r"|n[ãa]o d[áa] (v[íi]deo|imagem)|sem imagem|tela preta|\bp(a)?ra arrumar|precisa (de )?(reparo|conserto|arrumar)|levar na assist[êe]ncia", re.I)
# "sem defeito", "não tem defeitos", "sem avarias ou trincado", "sem nenhum detalhe ou defeito": negação logo antes, na mesma frase
NEGA = re.compile(r"(\bsem\b|\bnenhum|\bnem\b|n[ãa]o (tem|possui|apresenta|h[áa])|\bnunca\b|\blivre de)[^.,;:!?\n✅❌•]{0,22}\Z|\bzero\s*\Z", re.I)


def cita_defeito(t):
    return any(not NEGA.search(t[max(0, m.start() - 40):m.start()]) for m in DEFEITO.finditer(t))


for d in D:
    d["alerta"] = cita_defeito(d["titulo"] + " " + d["descricao"])

# Médias novas por faixa de iPhone: classificação do Haiku, sem descartes, só a região.
classif = {}
for f in glob.glob(str(PROJ / "dados" / "classificacao*.json")):
    for c in json.load(open(f, encoding="utf-8-sig")):
        classif[str(c["id"])] = c
def media_robusta(v):
    """Média sem os absurdos: fora de 40%–250% da mediana é peça, caixa, troca ou erro de digitação."""
    med = statistics.median(v)
    ok = [x for x in v if 0.4 * med <= x <= 2.5 * med]
    return round(statistics.mean(ok)), len(ok)


def moda(v):
    """Preço que mais se repete (mesmo filtro da média). Empate: todos os empatados; ninguém repete: vazio."""
    med = statistics.median(v)
    ok = [x for x in v if 0.4 * med <= x <= 2.5 * med]
    cont = Counter(ok)
    vezes = max(cont.values())
    return (sorted(x for x, c in cont.items() if c == vezes), vezes) if vezes > 1 else ([], 1)


# Preço médio de cada modelo (iPhone por variante do Haiku, TV por polegada, videogame por console),
# sem anúncios que citam defeito e sem os modelos genéricos ("TV" sem polegada, jogos e acessórios).
SEM_MEDIA = ("TV", "Jogos e acessórios")
TROCA = re.compile(r"\btroc[oa]\b", re.I)  # "troco PS5 por PC R$ 7.000" não é preço de venda
por_mod = defaultdict(list)
for d in D:
    c = classif.get(d["id"])
    if d["cat"] == "iPhone":
        if not (c and not c.get("descarte") and c.get("variante") not in (None, "", "outro")):
            continue
        d["mod"] = "iPhone " + c["variante"]
        if c.get("estado") == "com defeito":
            continue
    if d["mod"] not in SEM_MEDIA and not d["alerta"] and not TROCA.search(d["titulo"]):
        por_mod[d["mod"]].append(d["preco"])
medias = {k: (*media_robusta(v), next(d["cat"] for d in D if d["mod"] == k), *moda(v)) for k, v in por_mod.items() if len(v) >= 2}

# iPhone só vira oportunidade com bateria informada de BAT_MIN% pra cima (abaixo disso a troca da bateria come o desconto;
# sem a bateria no anúncio não dá para saber). Vale o número do Haiku; sem ele, o que o texto disser.
BAT_MIN = 75
# "bateria 87%", "saúde da bateria: 92"; com "%" vale mesmo depois de outro número ("bateria trocada em 2024, 100%")
RBAT = (re.compile(r"(?:bateria|sa[úu]de)[^%\n]{0,30}?\b(\d{2,3})\s*%", re.I), re.compile(r"(?:bateria|sa[úu]de)\D{0,15}?(\d{2,3})(?!\d)", re.I))


def bateria(d, c):
    if c and c.get("bateria_pct"):
        return int(c["bateria_pct"])
    # o primeiro número plausível: "bateria trocada em 2024, 100%" não pode virar "202"
    t = d["titulo"] + " " + d["descricao"]
    return next((int(m.group(1)) for r in RBAT for m in r.finditer(t) if 50 <= int(m.group(1)) <= 100), None)


ANO = date.today().year
for d in D:
    d["destaque"] = ""
    c = classif.get(d["id"])
    desde = H.get(d["id"], {}).get("vendedor_desde")
    d["conta_nova"] = desde if desde and int(desde) >= ANO else None  # conta criada este ano: padrão dos golpes
    if d["cat"] == "iPhone":
        d["bateria"] = bateria(d, c)
        md = medias.get(d["mod"])
        d["vs_media"] = round((d["preco"] / md[0] - 1) * 100) if md and md[1] >= 3 else None
        if c and c.get("descarte"):
            d["vs_media"] = None
        if (d["vs_media"] is not None and d["vs_media"] <= -15 and not d["alerta"] and not d["conta_nova"]
                and (d["bateria"] or 0) >= BAT_MIN and not (c and c.get("estado") == "com defeito")):
            extra = [x for x in (c.get("armazenamento") if c else "", f"bateria {d['bateria']}%", c.get("estado") if c else "") if x]
            d["destaque"] = f"{-d['vs_media']}% abaixo da média do {d['mod']} (R$ {md[0]:,}".replace(",", ".") + f", {md[1]} anúncios). " + ", ".join(extra)
    else:
        md = medias.get(d["mod"])
        d["vs_media"] = round((d["preco"] / md[0] - 1) * 100) if md and md[1] >= 3 else None
        # abaixo de 40% da média quase sempre é controle, jogo, peça ou golpe: sem tag e sem destaque
        if d["vs_media"] is not None and d["vs_media"] < -60:
            d["vs_media"] = None
        if d["vs_media"] is not None and d["vs_media"] <= -25 and not d["alerta"] and not d["conta_nova"]:
            d["destaque"] = f"{-d['vs_media']}% abaixo da média do {d['mod']} (R$ {md[0]:,}".replace(",", ".") + f", {md[1]} anúncios)."
for d in D:  # preço bom demais: avisa
    pct = d["vs_media"] if d["vs_media"] is not None else None
    if d["destaque"] and ((pct is not None and pct <= -35) or re.search(r"(\d+)% abaixo", d["destaque"]) and int(re.search(r"(\d+)% abaixo", d["destaque"]).group(1)) >= 35):
        d["destaque"] += " ⚠ Muito abaixo do normal: confira bem, pode ser golpe."

# Tiras de fotos em s/<hmac do id>.jpg (o nome não revela o anúncio): cada uma é criada uma vez só, então cada
# publicação leva só as novas.
TIRAS = PROJ / "s"
TIRAS.mkdir(exist_ok=True)
ACESSOS = privado.carregar()
for d in D:
    fotos = d["fotos"][:MAXF]
    nome = privado.nome_tira(d["id"], ACESSOS)
    arq = TIRAS / f"{nome}.jpg"
    if (TIRAS / f"{d['id']}.jpg").exists() and not arq.exists():  # tira do tempo em que o nome era o id
        (TIRAS / f"{d['id']}.jpg").rename(arq)
    if fotos and not arq.exists():
        tira = Image.new("RGB", (LADO * len(fotos), LADO), (0, 0, 0))
        for i, f in enumerate(fotos):
            im = Image.open(PROJ / "fotos" / f).convert("RGB")
            im.thumbnail((LADO, LADO))
            tira.paste(im, (i * LADO + (LADO - im.width) // 2, (LADO - im.height) // 2))
        tira.save(arq, "JPEG", quality=52, optimize=True)
    d["tira"], d["nf"] = f"s/{nome}.jpg", len(fotos)
    for k in ("fotos", "pasta"):
        d.pop(k, None)
for velha in TIRAS.glob("*.jpg"):  # anúncio que saiu da página leva a tira junto
    if velha.stem not in {d["tira"][2:-4] for d in D}:
        velha.unlink()

historico.definir_modelos(PROJ, {d["id"]: (d["cat"], d["mod"]) for d in D})
vendas = historico.resumo(historico.carregar(PROJ))
tpl = (PROJ / "pagina_template.html").read_text(encoding="utf-8")
# evolução das médias: uma entrada por coleta em historico/medias.json
arq_m = PROJ / "historico" / "medias.json"
evol = json.loads(arq_m.read_text(encoding="utf-8")) if arq_m.exists() else {}
evol[date.today().isoformat() if len(sys.argv) < 2 else "-".join(reversed(DATA.split("/")))] = {k: v[:2] for k, v in medias.items()}
arq_m.parent.mkdir(exist_ok=True)
arq_m.write_text(json.dumps(evol, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
resumo = {"data": DATA, "hora": datetime.now().strftime("%H:%M"), "medias": {k: v for k, v in sorted(medias.items())}, "vendas": vendas}
# Tela temporária da viagem (viagem.py): o link vai só dentro do cofre, enquanto dados/viagem.json valer e a pasta
# marketplace/viagem/ existir no worktree de publicação; depois da data ou do "viagem.py --remover" some sozinho.
try:
    from publicar import AGENDA
    _v = json.loads((PROJ / "dados" / "viagem.json").read_text(encoding="utf-8"))
    if date.today().isoformat() <= _v["ate"] and (Path(AGENDA) / "marketplace" / "viagem" / "index.html").exists():
        resumo["viagem"] = {"rotulo": _v["rotulo"], "ate": _v["ate"]}
except (OSError, ValueError, KeyError, ImportError):
    pass
# Os anúncios vão criptografados (privado.py): o HTML público não tem nenhum dado legível sem a senha.
(PROJ / "index.html").write_text(tpl.replace("__GOLPE__", golpistas.pagina_js(PROJ))
                                .replace("__COFRE__", json.dumps(privado.cifrar({"D": D, "R": resumo}))), encoding="utf-8")
tam = ((PROJ / "index.html").stat().st_size + sum(f.stat().st_size for f in TIRAS.glob("*.jpg"))) / 1e6
print(len(D), "anúncios |", sum(1 for d in D if d["destaque"]), "destaques |", f"página + fotos: {tam:.1f} MB")
for k, (v, q, _, mo, vz) in sorted(medias.items()):
    print(f"  {k:22} R$ {v:>6}  ({q})  moda: {' / '.join(map(str, mo)) or '-'} ({vz}x)")
for d in D:
    if d["destaque"]:
        print("  *", d["mod"], d["preco"], d["titulo"][:40], "|", d["destaque"])
