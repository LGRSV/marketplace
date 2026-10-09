# -*- coding: utf-8 -*-
"""
Consolida a coleta do Facebook Marketplace e gera a planilha Excel do iPhone 13.

Junta dois insumos da pasta dados/:
    lote_completo.json    -> anuncios crus (titulo, preco, local, condicao, descricao, link)
    classificacao*.json   -> analise das descricoes (variante, bateria, estado, original...)

Uso:
    python gerar_excel.py [pasta_dados] [pasta_saida]

Saida em planilhas/:
    iphone13_palmas_<AAAA-MM-DD>.xlsx  -> abas Resumo e Anuncios
    historico_iphone13.xlsx            -> uma linha por execucao (evolucao semanal)
"""

import json
import os
import sys
import glob
import statistics
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

AQUI = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- geografia
#
# O Marketplace ignora o raio pedido quando faltam resultados locais: a busca de
# Palmas trouxe anuncios de Maraba/PA, Balsas/MA e ate Barreiras/BA. Por isso a
# regiao e definida por lista explicita, e nao pela distancia que o Facebook diz.
#
# Localidades aceitas — definidas pelo usuario, nao pelo raio do Facebook.
# Taquaralto e Taquarucu sao distritos/regioes de Palmas: o Marketplace as vezes
# rotula como "Palmas, TO" e as vezes com o nome do distrito, entao ambos entram.
# Distancias rodoviarias aproximadas ate o centro de Palmas/TO, em km.
REGIAO_PALMAS = {
    "palmas": 0,
    "taquaralto": 20,
    "taquarucu": 30,
    "taquarucu do porto": 30,
    "porto nacional": 60,
    "paraiso do tocantins": 65,
    "paraiso": 65,
}

# Fora da lista — guardadas so para a coluna de distancia ficar informativa.
FORA = {
    "luzimangues": 25, "lajeado": 54, "pugmil": 80, "miracema do tocantins": 90,
    "tocantinia": 95, "monte do carmo": 100, "aparecida do rio negro": 110,
    "guarai": 180, "gurupi": 230, "colinas do tocantins": 250,
    "porangatu": 400, "porto franco": 430, "imperatriz": 470,
    "conceicao do araguaia": 480, "uruacu": 490, "araguatins": 500,
    "acailandia": 550, "araguaina": 380, "maraba": 570,
    "santana do araguaia": 570, "redencao": 630, "balsas": 620,
    "parauapebas": 640, "canaa dos carajas": 660, "ourilandia do norte": 750,
    "luis eduardo magalhaes": 850, "barreiras": 900, "dianopolis": 330,
}

LOCALIDADES = "Palmas, Taquaralto, Taquaruçu, Porto Nacional e Paraíso do Tocantins"


def normaliza(txt):
    """Remove acentos para casar nomes de cidade de forma tolerante."""
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                           "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
    return txt.translate(tabela).strip().lower()


def geo(local):
    """Devolve (cidade, uf, distancia_km, na_regiao) a partir de 'Cidade, UF'."""
    if not local:
        return "", "", None, False
    partes = [p.strip() for p in local.split(",")]
    cidade = partes[0]
    uf = partes[1] if len(partes) > 1 else ""
    chave = normaliza(cidade)
    if chave in REGIAO_PALMAS:
        return cidade, uf, REGIAO_PALMAS[chave], True
    return cidade, uf, FORA.get(chave), False


# ---------------------------------------------------------------- carga

def carregar(pasta):
    # aceita varios arquivos de coleta: lote_completo.json, lote_pro.json, ...
    arquivos = sorted(glob.glob(os.path.join(pasta, "lote_*.json")))
    arquivos = [a for a in arquivos if ".bak." not in os.path.basename(a)]
    if not arquivos:
        sys.exit(f"Nenhum lote_*.json encontrado em {pasta}")

    itens = []
    for arq in arquivos:
        with open(arq, encoding="utf-8-sig") as f:
            dados = json.load(f)
        itens.extend(dados)
        print(f"  {os.path.basename(arq)}: {len(dados)} anuncios")

    # indexa as classificacoes por id
    classif = {}
    for arq in sorted(glob.glob(os.path.join(pasta, "classificacao*.json"))):
        try:
            with open(arq, encoding="utf-8-sig") as f:
                for c in json.load(f):
                    if c.get("id"):
                        classif[str(c["id"])] = c
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ! {os.path.basename(arq)} ignorado ({e})")

    # anuncios reprovados na auditoria de titulos (multiplos modelos, outro aparelho, etc.)
    descartes = {}
    for arq in sorted(glob.glob(os.path.join(pasta, "descartes*.json"))):
        try:
            with open(arq, encoding="utf-8-sig") as f:
                for d in json.load(f):
                    if d.get("id"):
                        descartes[str(d["id"])] = d.get("motivo", "descartado")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ! {os.path.basename(arq)} ignorado ({e})")

    print(f"  classificacoes: {len(classif)}  |  descartes na auditoria: {len(descartes)}")

    saida, vistos, n_desc = [], set(), 0
    for it in itens:
        if it.get("erro") or not it.get("preco"):
            continue
        idc = str(it.get("id", ""))
        if idc in vistos:
            continue
        vistos.add(idc)

        it.update(classif.get(idc, {}))
        cidade, uf, km, dentro = geo(it.get("local", ""))
        it["cidade"], it["uf"] = cidade, uf
        it["distancia_km"], it["na_regiao"] = km, dentro
        it.setdefault("variante", "")

        # motivo do descarte: auditoria de titulo OU classificado como "outro"
        motivo = descartes.get(idc)
        if not motivo and it.get("variante") == "outro":
            motivo = "nao_identificado"
        it["descartado"] = motivo or ""
        if motivo:
            n_desc += 1
        saida.append(it)

    print(f"  anuncios unicos: {len(saida)}  |  descartados do calculo: {n_desc}")
    return saida


def validos(itens):
    """Anuncios que podem entrar em media: dentro das localidades e nao descartados."""
    return [i for i in itens if i["na_regiao"] and not i["descartado"]]


# ---------------------------------------------------------------- recortes

def eh_base(it):
    """Modelo base da geracao — exclui Pro, Pro Max e mini."""
    var = (it.get("variante") or "").strip()
    return var in GERACOES


# Geracoes acompanhadas. Uma planilha por geracao.
GERACOES = ["13", "14", "15", "16", "17"]
AMOSTRA_MINIMA = 10   # abaixo disso a media e sinalizada como pouco confiavel


def geracao(it):
    """Geracao do aparelho ('13', '14'...) a partir da variante. None se nao identificado."""
    var = (it.get("variante") or "").strip()
    if not var or var == "outro":
        return None
    n = var.split()[0]
    return n if n in GERACOES else None


def faixas_de(g):
    """Os tres rotulos de faixa de uma geracao, na ordem de exibicao."""
    return [f"iPhone {g} (normal)", f"iPhone {g} Pro", f"iPhone {g} Pro Max"]


def faixa(it):
    """Faixa do aparelho: normal, Pro ou Pro Max, com a geracao no rotulo."""
    var = (it.get("variante") or "").strip()
    g = geracao(it)
    if not g:
        return None
    resto = var[len(g):].strip().lower()
    if resto == "":
        return f"iPhone {g} (normal)"
    if resto == "pro":
        return f"iPhone {g} Pro"
    if resto in ("pro max", "promax"):
        return f"iPhone {g} Pro Max"
    return None   # "mini", "plus" e afins ficam de fora das tres faixas


def modelo(it):
    """
    Detalhamento dentro da faixa: variante + armazenamento.
    'iPhone 13 128GB' e 'iPhone 13 256GB' sao modelos diferentes.
    """
    var = it.get("variante")
    if not var or var == "outro":
        return None
    arm = it.get("armazenamento") or ""
    return f"iPhone {var} {arm}".strip() if arm else f"iPhone {var} (GB não informado)"


def ordem_modelo(nome):
    """Ordena: base antes de Pro antes de Pro Max; dentro disso, por capacidade."""
    fam = 0 if " Pro" not in nome else (1 if "Pro Max" not in nome else 2)
    gb = 0
    for cap, peso in (("128GB", 1), ("256GB", 2), ("512GB", 3), ("1TB", 4)):
        if cap in nome:
            gb = peso
    return (fam, gb, nome)


def eh_bom_estado(it):
    """Recorte pedido: mais novo + bateria boa + nao descaracterizado."""
    if it.get("estado") not in ("novo/lacrado", "seminovo"):
        return False
    if it.get("original") is False:
        return False
    bat = it.get("bateria_pct")
    if bat is not None and bat < 85:
        return False
    return True


def stats(precos):
    if not precos:
        return dict(qtd=0, media=0, mediana=0, minimo=0, maximo=0)
    return dict(qtd=len(precos), media=round(statistics.mean(precos)),
                mediana=round(statistics.median(precos)),
                minimo=min(precos), maximo=max(precos))


# ---------------------------------------------------------------- planilha

CAB = PatternFill("solid", fgColor="1F3864")
CAB_FONTE = Font(color="FFFFFF", bold=True)
DESTAQUE = PatternFill("solid", fgColor="FFF2CC")
CINZA = PatternFill("solid", fgColor="F2F2F2")     # fora das localidades
VERMELHO = PatternFill("solid", fgColor="FCE4E4")  # reprovado na auditoria de titulos

COLUNAS = [
    ("titulo", "Titulo", 40),
    ("preco", "Preco", 12),
    ("variante", "Modelo", 12),
    ("armazenamento", "Armazen.", 11),
    ("bateria_pct", "Bateria %", 10),
    ("estado", "Estado", 14),
    ("original", "Original", 10),
    ("condicao", "Condicao (FB)", 22),
    ("cidade", "Cidade", 20),
    ("uf", "UF", 6),
    ("distancia_km", "Dist. (km)", 11),
    ("na_regiao", "Na regiao", 11),
    ("descartado", "Descartado por", 18),
    ("observacoes", "Observacoes", 34),
    ("descricao", "Descricao integral", 75),
    ("link", "Link do anuncio", 44),
]


def aba_anuncios(wb, itens):
    ws = wb.create_sheet("Anuncios")
    ws.append([c[1] for c in COLUNAS])
    for i, (_, _, larg) in enumerate(COLUNAS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = larg
        cel = ws.cell(row=1, column=i)
        cel.fill, cel.font = CAB, CAB_FONTE
        cel.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.row_dimensions[1].height = 30

    for it in sorted(itens, key=lambda x: x.get("preco", 0), reverse=True):
        linha = []
        for chave, _, _ in COLUNAS:
            v = it.get(chave)
            if chave == "original":
                v = {True: "Sim", False: "Nao"}.get(v, "?")
            elif chave == "na_regiao":
                v = "Sim" if v else "Nao"
            elif v is None:
                v = ""
            linha.append(v)
        ws.append(linha)

    col_link = len(COLUNAS)
    col_desc = col_link - 1
    col_reg = [c[0] for c in COLUNAS].index("na_regiao") + 1

    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=2).number_format = 'R$ #,##0'
        ws.cell(row=r, column=col_desc).alignment = Alignment(wrap_text=True, vertical="top")
        link = ws.cell(row=r, column=col_link)
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="0563C1", underline="single")
        col_desc_mot = [c[0] for c in COLUNAS].index("descartado") + 1
        fora_reg = ws.cell(row=r, column=col_reg).value == "Nao"
        descartado = bool(ws.cell(row=r, column=col_desc_mot).value)
        if fora_reg or descartado:
            fill = VERMELHO if descartado else CINZA
            for c in range(1, col_link + 1):
                ws.cell(row=r, column=c).fill = fill

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(col_link)}{ws.max_row}"


def _tabela(ws, r, titulo, grupos_dict, ordem, rotulo="MODELO", nota=None, minimo=3):
    """
    Escreve uma tabela 'grupo x estatisticas'. Coluna principal e a MEDIA
    (sem mediana, a pedido do usuario). Devolve a proxima linha livre.
    """
    ws.cell(row=r, column=1, value=titulo).font = Font(size=12, bold=True, color="1F3864")
    r += 1
    if nota:
        ws.cell(row=r, column=1, value=nota).font = Font(italic=True, size=9, color="666666")
        r += 1

    for c, txt in enumerate((rotulo, "Qtd", "PRECO MEDIO", "Menor", "Maior"), start=1):
        cel = ws.cell(row=r, column=c, value=txt)
        cel.fill, cel.font = CAB, CAB_FONTE
        cel.alignment = Alignment(horizontal="center")
    r += 1

    for nome in ordem:
        grupo = grupos_dict.get(nome, [])
        s = stats([i["preco"] for i in grupo])
        ws.cell(row=r, column=1, value=nome)
        for c, k in enumerate(("qtd", "media", "minimo", "maximo"), start=2):
            cel = ws.cell(row=r, column=c, value=s[k])
            if c > 2:
                cel.number_format = 'R$ #,##0'
            cel.alignment = Alignment(horizontal="center")
        ws.cell(row=r, column=3).font = Font(bold=True)

        if s["qtd"] < minimo:
            for c in range(1, 6):
                ws.cell(row=r, column=c).font = Font(color="999999", italic=True)
            ws.cell(row=r, column=6,
                    value=f"amostra pequena (min. {minimo})").font = Font(
                        italic=True, size=9, color="C00000")
        else:
            for c in range(1, 6):
                ws.cell(row=r, column=c).fill = DESTAQUE
            ws.cell(row=r, column=3).font = Font(bold=True)
        r += 1
    return r + 1


def agrupa(itens, chave=None):
    """Agrupa a lista por modelo (padrao) ou por outra funcao de chave."""
    chave = chave or modelo
    d = {}
    for it in itens:
        nome = chave(it)
        if nome:
            d.setdefault(nome, []).append(it)
    return d


def aba_resumo(wb, itens, hoje, g):
    """Resumo de UMA geracao. `itens` ja vem filtrado para ela."""
    ws = wb.create_sheet("Resumo", 0)
    bons = validos(itens)                      # nas localidades e aprovados na auditoria
    fora = [i for i in itens if not i["na_regiao"]]
    lixo = [i for i in itens if i["na_regiao"] and i["descartado"]]
    FX = faixas_de(g)

    ws["A1"] = f"iPhone {g} — Facebook Marketplace"
    ws["A1"].font = Font(size=14, bold=True, color="1F3864")
    ws["A2"] = f"Localidades: {LOCALIDADES}"
    ws["A2"].font = Font(bold=True, color="1F3864")
    ws["A3"] = (f"Coleta de {hoje.strftime('%d/%m/%Y')}  |  {len(itens)} anuncios desta geracao  |  "
                f"{len(bons)} entraram no calculo  |  {len(fora)} fora das localidades  |  "
                f"{len(lixo)} descartados na auditoria de titulos")
    ws["A3"].font = Font(italic=True, color="666666")

    r = 5
    r = _tabela(ws, r, "PRECO MEDIO POR FAIXA — todos os estados",
                agrupa(bons, faixa), FX, rotulo="FAIXA",
                nota="Media aritmetica dos precos anunciados. Anuncios de multiplos modelos "
                     "e de outros aparelhos ja foram removidos na auditoria de titulos.",
                minimo=AMOSTRA_MINIMA)

    r = _tabela(ws, r, "PRECO MEDIO POR FAIXA — so novo/seminovo com bateria boa (>=85%)",
                agrupa([i for i in bons if eh_bom_estado(i)], faixa), FX, rotulo="FAIXA",
                nota="Recorte para quem quer aparelho em melhor estado.",
                minimo=AMOSTRA_MINIMA)

    grupos_mod = agrupa(bons)
    r = _tabela(ws, r, "DETALHAMENTO POR CAPACIDADE",
                grupos_mod, sorted(grupos_mod, key=ordem_modelo), rotulo="MODELO",
                nota="Quebra de cada faixa por armazenamento. Amostras menores — use com cautela.",
                minimo=3)

    for col, larg in zip("ABCDEF", (40, 8, 16, 14, 14, 28)):
        ws.column_dimensions[col].width = larg
    return bons


def historico(caminho, hoje, bons, g):
    """
    Uma linha por execucao: media e quantidade de cada FAIXA da geracao.
    Media 0 significa que nao houve anuncio daquela faixa na semana.
    """
    FAIXAS = faixas_de(g)
    cabecalho = ["Data", "Total"]
    for f in FAIXAS:
        cabecalho += [f"{f} — media", f"{f} — qtd"]

    if os.path.exists(caminho):
        wb = load_workbook(caminho)
        ws = wb["Historico"]
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Historico"
        ws.append(cabecalho)
        for c in range(1, len(cabecalho) + 1):
            cel = ws.cell(row=1, column=c)
            cel.fill, cel.font = CAB, CAB_FONTE
            cel.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 8
        for i in range(len(cabecalho) - 2):
            ws.column_dimensions[get_column_letter(3 + i)].width = 16
        ws.row_dimensions[1].height = 34

    grupos = agrupa(bons, faixa)
    linha = [hoje.strftime("%d/%m/%Y"), len(bons)]
    for f in FAIXAS:
        s = stats([i["preco"] for i in grupos.get(f, [])])
        linha += [s["media"], s["qtd"]]
    ws.append(linha)
    for i in range(len(FAIXAS)):
        ws.cell(row=ws.max_row, column=3 + i * 2).number_format = 'R$ #,##0'
    wb.save(caminho)


def main():
    pasta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, "dados")
    saida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(AQUI, "planilhas")
    os.makedirs(saida, exist_ok=True)

    print("Consolidando...")
    todos = carregar(pasta)
    hoje = date.today()

    # uma planilha por geracao; so gera as que tem anuncio
    por_ger = {}
    for it in todos:
        g = geracao(it)
        if g:
            por_ger.setdefault(g, []).append(it)

    if not por_ger:
        sys.exit("Nenhum anuncio classificado por geracao. Rode a classificacao antes.")

    print(f"\n  localidades: {LOCALIDADES}")
    for g in GERACOES:
        itens = por_ger.get(g)
        if not itens:
            print(f"\n=== iPhone {g}: nenhum anuncio coletado — planilha nao gerada")
            continue

        wb = Workbook()
        wb.remove(wb.active)
        aba_anuncios(wb, itens)
        bons = aba_resumo(wb, itens, hoje, g)

        arq = os.path.join(saida, f"iphone{g}_palmas_{hoje.isoformat()}.xlsx")
        wb.save(arq)
        historico(os.path.join(saida, f"historico_iphone{g}.xlsx"), hoje, bons, g)

        print(f"\n=== iPhone {g}  ->  {os.path.basename(arq)}")
        print(f"  {len(itens)} anuncios da geracao, {len(bons)} no calculo")
        print(f"  {'FAIXA':26} {'QTD':>4} {'MEDIA':>10} {'MENOR':>8} {'MAIOR':>8}")
        gf = agrupa(bons, faixa)
        for f in faixas_de(g):
            s = stats([i["preco"] for i in gf.get(f, [])])
            alerta = f"  <- so {s['qtd']} (min. {AMOSTRA_MINIMA})" \
                if s["qtd"] < AMOSTRA_MINIMA else ""
            print(f"  {f:26} {s['qtd']:>4} {s['media']:>10} "
                  f"{s['minimo']:>8} {s['maximo']:>8}{alerta}")


if __name__ == "__main__":
    main()
