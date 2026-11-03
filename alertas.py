"""Alerta no WhatsApp quando aparece anúncio bom para revenda (roda no fim de cada coleta).

Critério: anúncio ativo e recente, preço bem abaixo da referência do modelo (mediana dos VENDIDOS no histórico;
sem vendidos suficientes, a média da última coleta), lucro estimado mínimo, sem golpista e sem palavra de risco.
A mensagem vai só para a conversa do próprio dono. Número e estado ficam em dados/ (fora do Git).
  python alertas.py            envia o que for novo
  python alertas.py --simular  só mostra o que enviaria, não envia nem grava estado
"""
import json, re, sqlite3, statistics, subprocess, sys
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CFG = AQUI / "dados" / "alertas.json"           # {"destino": "...@s.whatsapp.net"}
ESTADO = AQUI / "dados" / "alertas_estado.json"
ZAP = Path.home() / "whatsapp-mcp" / "whatsapp_web.py"
DB = Path.home() / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "messages.db"
DESCONTO, PISO, LUCRO_MIN, DIAS, MAX_POR_RODADA, AMOSTRA_MIN = 0.82, 0.45, 150, 2, 5, 5
RISCO = re.compile(r"pe[cç]as?\b|defeito|quebrad|trincad|n[aã]o liga|icloud|bloquead|sucata|troco|troca|compro|procuro|aluguel|capa\b|carregador|controle\b", re.I)


def ler(p, padrao):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return padrao


def preco(a):
    return a["precos"][-1][1] if a.get("precos") else None


def referencias(anuncios, medias):
    ultima = medias[max(medias)] if medias else {}
    vendidos, dias = {}, {}
    for a in anuncios.values():
        if a.get("status") != "vendido" or not preco(a):
            continue
        vendidos.setdefault(a.get("mod"), []).append(preco(a))
        try:
            d = (date.fromisoformat(a["data_status"]) - date.fromisoformat(a["primeiro_visto"])).days
            dias.setdefault(a.get("mod"), []).append(d)
        except (KeyError, ValueError):
            pass
    ref = {}
    for mod, (media, n) in ultima.items():
        if n >= AMOSTRA_MIN:
            ref[mod] = (media, f"média de {n} anúncios")
    for mod, ps in vendidos.items():
        if len(ps) >= AMOSTRA_MIN:
            ref[mod] = (round(statistics.median(ps)), f"mediana de {len(ps)} vendidos")
    return ref, {m: round(statistics.median(d)) for m, d in dias.items() if len(d) >= AMOSTRA_MIN}


def candidatos(anuncios, ref, dias_venda, golpistas, hoje):
    corte = (hoje - timedelta(days=DIAS)).isoformat()
    ruins = json.dumps(golpistas, ensure_ascii=False)   # ids de anúncio e de vendedor marcados
    achados = []
    for id_, a in anuncios.items():
        p, r = preco(a), ref.get(a.get("mod"))
        if a.get("status") != "ativo" or not p or not r or a.get("primeiro_visto", "") < corte:
            continue
        if id_ in ruins or (a.get("vendedor_id") and a["vendedor_id"] in ruins) or RISCO.search(a.get("titulo", "")):
            continue
        valor, base = r
        lucro = valor - p
        if p > valor * DESCONTO or p < valor * PISO or lucro < LUCRO_MIN:
            continue
        achados.append({"id": id_, "a": a, "p": p, "valor": valor, "base": base, "lucro": lucro, "dias": dias_venda.get(a.get("mod"))})
    return sorted(achados, key=lambda x: -x["lucro"])


def modelo_no_texto(txt, modelos):
    """O nome de modelo mais longo que aparece no texto (iPhone 13 Pro antes de iPhone 13)."""
    t = re.sub(r"\s+", " ", txt.lower())
    for m in sorted(modelos, key=len, reverse=True):
        if m.lower() in t:
            return m
    return None


def preco_no_texto(txt):
    m = re.search(r"r\$\s*(\d{1,2}[.,]?\d{3}|\d{3})\b", txt, re.I) or re.search(r"\b(\d{1,2}[.,]?\d{3}|\d{3})(?:,00)?\s*(?:reais|conto|no pix|pix|[àa] vista)\b", txt, re.I)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def dos_grupos(ref, grupos, desde):
    """Ofertas nos grupos de venda do WhatsApp (dados/alertas.json: "grupos": [nomes]), pela mesma régua."""
    if not grupos or not DB.exists():
        return []
    c = sqlite3.connect(DB, timeout=15)
    marcas = ",".join("?" * len(grupos))
    linhas = c.execute(f"select m.id, ch.name, m.content, m.timestamp from messages m join chats ch on ch.jid = m.chat_jid "
                       f"where ch.name in ({marcas}) and m.is_from_me = 0 and m.timestamp > ? and m.content != ''", (*grupos, desde)).fetchall()
    c.close()
    achados = []
    for id_, grupo, txt, ts in linhas:
        if len(txt) > 500 or RISCO.search(txt):
            continue
        mod, p = modelo_no_texto(txt, ref), preco_no_texto(txt)
        if not mod or not p:
            continue
        valor, base = ref[mod]
        if p > valor * DESCONTO or p < valor * PISO or valor - p < LUCRO_MIN:
            continue
        achados.append({"id": "g" + str(id_), "grupo": grupo, "txt": txt, "mod": mod, "p": p, "valor": valor, "base": base, "lucro": valor - p, "ts": ts})
    return sorted(achados, key=lambda x: -x["lucro"])


def texto_grupo(c):
    return (f"\U0001F9E0 Grupo {c['grupo']}: {c['mod']}\n{reais(c['p'])} | referência {reais(c['valor'])} ({c['base']})\n"
            f"Lucro estimado: {reais(c['lucro'])}\n{c['txt'][:160]}")


def reais(v):
    return f"R$ {v:,}".replace(",", ".")


def texto(c, hoje):
    a = c["a"]
    linhas = [f"\U0001F9E0 Marketplace: {a.get('titulo', '')[:70]}",
              f"{reais(c['p'])} | referência {reais(c['valor'])} ({c['base']})",
              f"Lucro estimado: {reais(c['lucro'])}"]
    if c["dias"] is not None:
        linhas.append(f"Esse modelo costuma vender em {c['dias']} dia(s)")
    if str(a.get("vendedor_desde", "")) == str(hoje.year):
        linhas.append("Atenção: conta do vendedor criada este ano")
    linhas.append(f"{a.get('local', '')} | https://www.facebook.com/marketplace/item/{c['id']}")
    return "\n".join(linhas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    simular = "--simular" in sys.argv
    hoje = date.today()
    anuncios = ler(AQUI / "historico" / "anuncios.json", {})
    ref, dias_venda = referencias(anuncios, ler(AQUI / "historico" / "medias.json", {}))
    achados = candidatos(anuncios, ref, dias_venda, ler(AQUI / "golpistas.json", {}), hoje)
    estado = ler(ESTADO, {"enviados": {}})
    novos = [c for c in achados if c["id"] not in estado["enviados"]][:MAX_POR_RODADA]
    cfg = ler(CFG, {})
    desde = (hoje - timedelta(days=DIAS)).isoformat()
    de_grupos = [c for c in dos_grupos(ref, cfg.get("grupos", []), desde) if c["id"] not in estado["enviados"]][:MAX_POR_RODADA]
    if simular:
        print(f"{len(achados)} candidatos no Marketplace; {len(novos)} seriam enviados agora; {len(de_grupos)} dos grupos")
        for c in novos:
            print("---\n" + texto(c, hoje))
        for c in de_grupos:
            print("---\n" + texto_grupo(c))
        return 0
    destino = cfg.get("destino")
    if not destino:
        print("alertas: sem destino em dados/alertas.json")
        return 0
    enviados = 0
    for c in novos + de_grupos:
        msg = texto_grupo(c) if "grupo" in c else texto(c, hoje)
        r = subprocess.run([sys.executable, str(ZAP), "enviar", destino, msg], cwd=ZAP.parent, capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            estado["enviados"][c["id"]] = datetime.now().isoformat(timespec="minutes")
            enviados += 1
    limite = (hoje - timedelta(days=60)).isoformat()
    estado["enviados"] = {k: v for k, v in estado["enviados"].items() if v >= limite}
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"alertas: {enviados} enviados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
