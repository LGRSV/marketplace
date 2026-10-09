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
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from PIL import Image

import historico

sys.stdout.reconfigure(encoding="utf-8")
PROJ = Path(__file__).resolve().parent
DATA = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%d/%m/%Y")
REGIAO = ("palmas", "taquaralto", "taquaruçu", "taquarucu", "porto nacional", "paraíso do tocantins", "paraiso do tocantins")
LADO, MAXF = 380, 5

h = (PROJ / "fotos" / "oportunidades.html").read_text(encoding="utf-8")
m = re.search(r"const D=", h)
D = json.JSONDecoder().raw_decode(h[m.end():])[0]
D = [d for d in D if d["cat"] != "Outros" and d["local"].split(",")[0].strip().lower() in REGIAO and d["preco"] > 0]
ACESS = re.compile(r"\bjogos?\b|controle|suporte|\bcase\b|\bcapa\b|desbloque|\bcabo\b|\bfonte\b|pel[íi]cula|headset|volante|\bpainel\b|\brack\b|\bdock\b|carregador|m[íi]dia f[íi]sica|\bfallout\b|god of war|\bbatman\b|\bmario\b|\bzelda\b", re.I)
for d in D:
    if d["cat"] != "iPhone" and re.search(r"iphone", d["titulo"], re.I):
        d["cat"] = "Outros"  # iPhone antigo (XR, 11...) que caiu como videogame
    elif d["cat"] != "iPhone" and ACESS.search(d["titulo"]) and not re.search(r"\bcom\b.*controle|\+\s*controle|controles?\s*\+|e \d+ controles?|acompanha", d["titulo"], re.I):
        d["cat"], d["mod"] = "Jogos e acessórios", "Jogos e acessórios"
D = [d for d in D if d["cat"] != "Outros"]
H = historico.carregar(PROJ)
D = [d for d in D if H.get(d["id"], {}).get("status", "ativo") == "ativo"]  # vendidos/apagados saem da página
ontem = (date.today() - timedelta(days=1)).isoformat()
for d in D:
    h = H.get(d["id"], {})
    d["novo"] = h.get("primeiro_visto", "") >= ontem
    if len(h.get("precos", [])) > 1 and h["precos"][-1][1]:  # preço mudou desde a leitura: vale o mais recente
        d["preco_antes"], d["preco"] = h["precos"][0][1], h["precos"][-1][1]
DEFEITO = re.compile(r"trincad|desligand|desliga sozinh|tela (foi )?(substitu|trocad)|n[ãa]o liga|queimad|quebrad|com defeito|face ?id (off|n[ãa]o)|sem face|mancha|listra|retirada de pe", re.I)
for d in D:
    d["alerta"] = d["alerta"] or bool(DEFEITO.search(d["titulo"] + " " + d["descricao"]))

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


# Preço médio de cada modelo (iPhone por variante do Haiku, TV por polegada, videogame por console),
# sem anúncios que citam defeito e sem os modelos genéricos ("TV" sem polegada, jogos e acessórios).
SEM_MEDIA = ("TV", "Jogos e acessórios")
por_mod = defaultdict(list)
for d in D:
    c = classif.get(d["id"])
    if d["cat"] == "iPhone":
        if not (c and not c.get("descarte") and c.get("variante") not in (None, "", "outro")):
            continue
        d["mod"] = "iPhone " + c["variante"]
        if c.get("estado") == "com defeito":
            continue
    if d["mod"] not in SEM_MEDIA and not d["alerta"]:
        por_mod[d["mod"]].append(d["preco"])
medias = {k: (*media_robusta(v), next(d["cat"] for d in D if d["mod"] == k)) for k, v in por_mod.items() if len(v) >= 2}

for d in D:
    d["destaque"] = ""
    c = classif.get(d["id"])
    if d["cat"] == "iPhone":
        md = medias.get(d["mod"])
        d["vs_media"] = round((d["preco"] / md[0] - 1) * 100) if md and md[1] >= 3 else None
        if c and c.get("descarte"):
            d["vs_media"] = None
        if d["vs_media"] is not None and d["vs_media"] <= -15 and not d["alerta"] and not (c and c.get("estado") == "com defeito"):
            extra = [x for x in (c.get("armazenamento") if c else "", f"bateria {c['bateria_pct']}%" if c and c.get("bateria_pct") else "", c.get("estado") if c else "") if x]
            d["destaque"] = f"{-d['vs_media']}% abaixo da média do {d['mod']} (R$ {md[0]:,}".replace(",", ".") + f", {md[1]} anúncios). " + ", ".join(extra)
    else:
        md = medias.get(d["mod"])
        d["vs_media"] = round((d["preco"] / md[0] - 1) * 100) if md and md[1] >= 3 else None
        # abaixo de 40% da média quase sempre é controle, jogo, peça ou golpe: sem tag e sem destaque
        if d["vs_media"] is not None and d["vs_media"] < -60:
            d["vs_media"] = None
        if d["vs_media"] is not None and d["vs_media"] <= -25 and not d["alerta"]:
            d["destaque"] = f"{-d['vs_media']}% abaixo da média do {d['mod']} (R$ {md[0]:,}".replace(",", ".") + f", {md[1]} anúncios)."
for d in D:  # preço bom demais: avisa
    pct = d["vs_media"] if d["vs_media"] is not None else None
    if d["destaque"] and ((pct is not None and pct <= -35) or re.search(r"(\d+)% abaixo", d["destaque"]) and int(re.search(r"(\d+)% abaixo", d["destaque"]).group(1)) >= 35):
        d["destaque"] += " ⚠ Muito abaixo do normal: confira bem, pode ser golpe."

# Tiras de fotos em s/<id>.jpg: cada uma é criada uma vez só, então cada publicação leva só as novas.
TIRAS = PROJ / "s"
TIRAS.mkdir(exist_ok=True)
for d in D:
    fotos = d["fotos"][:MAXF]
    arq = TIRAS / f"{d['id']}.jpg"
    if fotos and not arq.exists():
        tira = Image.new("RGB", (LADO * len(fotos), LADO), (0, 0, 0))
        for i, f in enumerate(fotos):
            im = Image.open(PROJ / "fotos" / f).convert("RGB")
            im.thumbnail((LADO, LADO))
            tira.paste(im, (i * LADO + (LADO - im.width) // 2, (LADO - im.height) // 2))
        tira.save(arq, "JPEG", quality=52, optimize=True)
    d["tira"], d["nf"] = f"s/{d['id']}.jpg", len(fotos)
    for k in ("fotos", "pasta"):
        d.pop(k, None)
for velha in TIRAS.glob("*.jpg"):  # anúncio que saiu da página leva a tira junto
    if velha.stem not in {d["id"] for d in D}:
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
resumo = {"data": DATA, "medias": {k: v for k, v in sorted(medias.items())}, "vendas": vendas}
(PROJ / "index.html").write_text(tpl.replace("__DADOS__", json.dumps(D, ensure_ascii=False).replace("</", "<\\/"))
                                .replace("__RESUMO__", json.dumps(resumo, ensure_ascii=False)), encoding="utf-8")
tam = ((PROJ / "index.html").stat().st_size + sum(f.stat().st_size for f in TIRAS.glob("*.jpg"))) / 1e6
print(len(D), "anúncios |", sum(1 for d in D if d["destaque"]), "destaques |", f"página + fotos: {tam:.1f} MB")
for k, (v, q, _) in sorted(medias.items()):
    print(f"  {k:22} R$ {v:>6}  ({q})")
for d in D:
    if d["destaque"]:
        print("  *", d["mod"], d["preco"], d["titulo"][:40], "|", d["destaque"])
