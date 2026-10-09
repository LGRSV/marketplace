"""
Classifica os iPhones coletados com o Claude Haiku (barato) e prepara a pasta para gerar_excel.py.

Lê dados/_anuncios_*.json, manda só título + preço + começo da descrição em lotes de 40
para `claude -p --model haiku` (cada lote é uma conversa nova, sem histórico) e grava:
    dados/lote_coleta.json            anúncios sem as fotos (é o que gerar_excel.py lê)
    dados/classificacao_haiku.json    variante, armazenamento, bateria, estado, original
    dados/descartes_haiku.json        o que não é um iPhone 13–17 específico (regra 5)

Uso:  python classificar_haiku.py        depois:  python gerar_excel.py
"""

import glob
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DADOS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "dados")
LOTE = 40

PROMPT = """Você classifica anúncios de iPhone do Facebook Marketplace. Responda SÓ com um array JSON,
um objeto por anúncio, na mesma ordem, sem texto antes ou depois:
{"id":"...","variante":"13|13 mini|13 Pro|13 Pro Max|14|14 Plus|... até 17 Pro Max|outro",
 "armazenamento":"128GB|256GB|512GB|1TB|","bateria_pct":número ou null,
 "estado":"novo/lacrado|seminovo|usado|com defeito","original":true|false|null,
 "descarte":""|"multiplos_modelos"|"modelo_fora_13_a_17"|"nao_e_aparelho"|"preco_invalido",
 "observacoes":"até 120 caracteres"}
Regras: armazenamento é obrigatório quando estiver escrito; nunca invente bateria.
Descarte anúncio com vários modelos, outro aparelho (iPhone 11, 12, SE, Android), acessório,
peça ou serviço, e preço que não é do aparelho (sinal, parcela, R$ 1). NÃO descarte iPhone
legítimo só por defeito, tela trocada ou bateria ruim.
Anúncios:
"""


def carregar():
    itens, vistos = [], set()
    for arq in sorted(glob.glob(os.path.join(DADOS, "_anuncios_*.json"))):
        with open(arq, encoding="utf-8-sig") as f:
            for it in json.load(f):
                if it.get("erro") or it["id"] in vistos:
                    continue
                vistos.add(it["id"])
                it = {k: v for k, v in it.items() if k != "fotos"}
                it["preco"] = int(re.sub(r"\D", "", str(it.get("preco") or "0")) or 0)
                itens.append(it)
    return itens


def perguntar(lote):
    entrada = PROMPT + json.dumps(
        [{"id": i["id"], "titulo": i["titulo"], "preco": i["preco"], "descricao": i.get("descricao", "")[:500]}
         for i in lote], ensure_ascii=False)
    r = subprocess.run(["claude", "-p", "--model", "haiku"], input=entrada, capture_output=True,
                       text=True, encoding="utf-8", timeout=300, shell=(os.name == "nt"))
    m = re.search(r"\[.*\]", r.stdout, re.S)
    if not m:
        raise RuntimeError(f"Resposta sem JSON: {r.stdout[:200]} {r.stderr[:200]}")
    return json.loads(m.group(0))


def main():
    todos = carregar()
    iphones = [i for i in todos if re.search(r"iphone", i["titulo"], re.I)]
    # incremental: o que já está em classificacao_haiku.json não volta para o Haiku (a coleta completa arquiva o arquivo antes)
    ler = lambda n: json.load(open(os.path.join(DADOS, n), encoding="utf-8")) if os.path.exists(os.path.join(DADOS, n)) else []
    classif, descartes = ler("classificacao_haiku.json"), ler("descartes_haiku.json")
    feitos = {c["id"] for c in classif}
    faltam = [i for i in iphones if i["id"] not in feitos]
    print(f"{len(todos)} anúncios, {len(iphones)} com 'iPhone' no título, {len(faltam)} sem classificação -> {-(-len(faltam) // LOTE)} lotes")
    for k in range(0, len(faltam), LOTE):
        lote = faltam[k:k + LOTE]
        try:
            res = perguntar(lote)
        except Exception as e:
            print(f"  lote {k // LOTE + 1}: falhou ({e}); tentando de novo")
            res = perguntar(lote)
        por_id = {i["id"]: i for i in lote}
        for c in res:
            if c.get("id") not in por_id:
                continue
            classif.append(c)
            if c.get("descarte"):
                descartes.append({"id": c["id"], "titulo": por_id[c["id"]]["titulo"],
                                  "preco": por_id[c["id"]]["preco"], "motivo": c["descarte"],
                                  "explicacao": c.get("observacoes", "")})
        print(f"  lote {k // LOTE + 1}: {len(res)} classificados")

    for nome, dados in (("lote_coleta.json", iphones), ("classificacao_haiku.json", classif),
                        ("descartes_haiku.json", descartes)):
        with open(os.path.join(DADOS, nome), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    print(f"{len(classif)} classificados, {len(descartes)} descartados. Agora: python gerar_excel.py")


if __name__ == "__main__":
    sys.exit(main())
