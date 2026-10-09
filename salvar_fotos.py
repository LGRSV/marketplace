"""
Monta a pasta fotos/ a partir dos dados/_anuncios_*.json capturados no Marketplace:

    fotos/<Categoria>/<Modelo>/<R$ preco - titulo - cidade - id>/01.jpg, 02.jpg ... + info.txt
    fotos/oportunidades.html   -> pagina interativa com todas as fotos e descricoes

Uso:  python salvar_fotos.py
"""

import base64
import glob
import html
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE, "dados")
FOTOS = os.path.join(BASE, "fotos")

# medias de 08/08/2026 (historico_iphoneNN.xlsx) por faixa, para comparar o preco
MEDIA_IPHONE = {
    "iPhone 13": 1931, "iPhone 13 Pro": 2340, "iPhone 13 Pro Max": 2794,
    "iPhone 14": 2129, "iPhone 14 Pro": 2943, "iPhone 14 Pro Max": 3043,
    "iPhone 15": 2806, "iPhone 15 Pro": 3592, "iPhone 15 Pro Max": 4042,
    "iPhone 16": 3900, "iPhone 16 Pro": 4362, "iPhone 16 Pro Max": 5125,
    "iPhone 17": 4733, "iPhone 17 Pro": 6374, "iPhone 17 Pro Max": 7165,
}

ALERTA = re.compile(r"(?<!sem )(?<!nenhum )defeito|queimad|retirada de pe[çc]a|(?<!tem )(?<!sem )trinca(do)?\b|quebrad|n[ãa]o liga"
                    r"|mancha|listra|sem imagem|n[ãa]o d[áa] imagem|tela preta", re.I)


def limpar_descricao(d):
    """Corta o que vem depois da descricao (mapa, anuncios patrocinados)."""
    return re.split(r"\n?[^\n]*A localiza[çc][ãa]o é aproximada|\nPatrocinado", d or "")[0].strip()


def classificar(titulo, descricao):
    """(categoria, modelo) a partir do titulo (e descricao para TVs)."""
    t = titulo.lower().replace("promax", "pro max")
    m = re.search(r"iphone\s*(1[3-7])\s*(pro\s*max|pro|plus|mini|e\b)?", t)
    if m:
        v = re.sub(r"\s+", " ", m.group(2) or "").strip()
        suf = {"pro max": " Pro Max", "pro": " Pro", "plus": " Plus", "mini": " mini", "e": "e"}.get(v, "")
        return "iPhone", f"iPhone {m.group(1)}{suf}"
    if re.search(r"\b(tv|televis|smart)", t):
        pol = (re.search(r"(\d{2})\s*(\"|”|pol|plg|p\b)", t) or re.search(r"\b(2[4-9]|[3-8]\d)\b", t)
               or re.search(r"(\d{2})\s*(\"|”|pol|plg)", descricao.lower()))
        return "TV", f"TV {pol.group(1)} pol" if pol else "TV"
    for chave, nome in (("portal", "PlayStation Portal"), ("ps5|playstation 5|825", "PlayStation 5"),
                        ("ps4|playstation 4", "PlayStation 4"), ("ps3|playstation 3", "PlayStation 3"),
                        ("ps2|playstation 2", "PlayStation 2"), (r"series\s*x\b", "Xbox Series X"),
                        (r"series\s*s\b", "Xbox Series S"), ("series", "Xbox Series"),
                        (r"\bone\b", "Xbox One"), ("360", "Xbox 360"), ("switch", "Nintendo Switch")):
        if re.search(chave, t):
            return "Videogame", nome
    return "Outros", "Outros"


def limpo(s, n=60):
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", s)
    s = re.sub(r"[^\w\s.,()+&$-]", "", s)
    return re.sub(r"\s+", " ", s).strip()[:n].rstrip(" .")


def carregar():
    itens, vistos = [], set()
    for arq in sorted(glob.glob(os.path.join(DADOS, "_anuncios_*.json"))):
        with open(arq, encoding="utf-8-sig") as f:
            for it in json.load(f):
                it["descricao"] = limpar_descricao(it.get("descricao"))
                if it.get("erro") or not it.get("fotos") or it["id"] in vistos:
                    continue
                vistos.add(it["id"])
                itens.append(it)
    return itens


def main():
    itens = carregar()
    cards = []
    for it in itens:
        cat, mod = classificar(it["titulo"], it.get("descricao", ""))
        preco = int(re.sub(r"\D", "", it.get("preco") or "0") or 0)
        cidade = (it.get("local") or "").split(",")[0]
        pasta_rel = os.path.join(cat, mod, limpo(f"R$ {preco} - {it['titulo']} - {cidade} - {it['id']}", 110))
        pasta = os.path.join(FOTOS, pasta_rel)
        os.makedirs(pasta, exist_ok=True)
        fotos = []
        for i, b64 in enumerate(it["fotos"], 1):
            nome = f"{i:02d}.jpg"
            if not os.path.exists(os.path.join(pasta, nome)):  # já salva: não regrava (evita o OneDrive subir tudo de novo)
                with open(os.path.join(pasta, nome), "wb") as f:
                    f.write(base64.b64decode(b64))
            fotos.append((pasta_rel + os.sep + nome).replace(os.sep, "/"))
        link = f"https://www.facebook.com/marketplace/item/{it['id']}/"
        info = os.path.join(pasta, "info.txt")
        if not os.path.exists(info):
            with open(info, "w", encoding="utf-8") as f:
                f.write(f"{it['titulo']}\nPreco: R$ {preco}\nLocal: {it.get('local', '')}\n"
                    f"Condicao: {it.get('condicao', '')}\nLink: {link}\n\n{it.get('descricao', '')}\n")
        media = MEDIA_IPHONE.get(mod)
        cards.append({
            "id": it["id"], "cat": cat, "mod": mod, "titulo": it["titulo"], "preco": preco,
            "local": it.get("local", ""), "condicao": it.get("condicao", ""),
            "descricao": it.get("descricao", ""), "fotos": fotos, "link": link,
            "pasta": pasta_rel.replace(os.sep, "/"),
            "vs_media": round((preco / media - 1) * 100) if media and preco else None,
            "alerta": bool(ALERTA.search(it["titulo"] + " " + it.get("descricao", ""))),
        })
    cards.sort(key=lambda c: (c["cat"], c["mod"], c["preco"]))
    gerar_html(cards)
    print(f"{len(cards)} anuncios, {sum(len(c['fotos']) for c in cards)} fotos em {FOTOS}")
    for cat in sorted({c["cat"] for c in cards}):
        print(f"  {cat}: {sum(1 for c in cards if c['cat'] == cat)}")


def gerar_html(cards):
    dados = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    pagina = MODELO.replace("__DADOS__", dados)
    with open(os.path.join(FOTOS, "oportunidades.html"), "w", encoding="utf-8") as f:
        f.write(pagina)


MODELO = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oportunidades Marketplace</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1c1e21;--mut:#65676b;--bd:#dadde1;--ac:#1877f2;--ok:#1a7f37;--bad:#c62828;--warn:#b26a00}
@media (prefers-color-scheme:dark){:root{--bg:#18191a;--card:#242526;--tx:#e4e6eb;--mut:#b0b3b8;--bd:#3a3b3c;--ac:#4599ff;--ok:#4cc26a;--bad:#ff6b6b;--warn:#ffb74d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.4 system-ui,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--bd);padding:12px 16px}
h1{margin:0 0 8px;font-size:20px}.sub{color:var(--mut);font-size:13px;margin-bottom:10px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar button,.bar select,.bar input{font:inherit;padding:6px 12px;border-radius:18px;border:1px solid var(--bd);background:var(--bg);color:var(--tx);cursor:pointer}
.bar button.on{background:var(--ac);border-color:var(--ac);color:#fff}.bar input{cursor:text;min-width:180px;flex:1}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;padding:16px;max-width:1400px;margin:0 auto}
.c{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden;cursor:pointer;transition:transform .1s}
.c:hover{transform:translateY(-2px)}.c img{width:100%;aspect-ratio:1;object-fit:cover;display:block;background:#0002}
.c .b{padding:10px}.p{font-weight:700;font-size:18px}.t{margin:2px 0 4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.m{color:var(--mut);font-size:13px}.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.tag{font-size:12px;padding:2px 8px;border-radius:10px;border:1px solid var(--bd)}.low{color:var(--ok);border-color:var(--ok)}.high{color:var(--bad);border-color:var(--bad)}.warn{color:var(--warn);border-color:var(--warn)}
.n{position:relative}.n span{position:absolute;right:8px;bottom:8px;background:#000a;color:#fff;font-size:12px;padding:2px 7px;border-radius:10px}
#mod{position:fixed;inset:0;background:#000c;display:none;z-index:10;padding:16px;overflow:auto}
#mod .box{background:var(--card);max-width:1000px;margin:0 auto;border-radius:12px;display:grid;grid-template-columns:1.2fr 1fr;overflow:hidden}
@media (max-width:760px){#mod .box{grid-template-columns:1fr}}
.gal{background:#000;position:relative;display:flex;flex-direction:column}.gal .big{width:100%;max-height:75vh;object-fit:contain;flex:1}
.gal .nav{position:absolute;top:40%;background:#0008;color:#fff;border:0;font-size:28px;width:44px;height:44px;border-radius:50%;cursor:pointer}
.prev{left:8px}.next{right:8px}.th{display:flex;gap:4px;overflow-x:auto;padding:6px;background:#111}
.th img{width:58px;height:58px;object-fit:cover;opacity:.55;cursor:pointer;border-radius:4px}.th img.on{opacity:1;outline:2px solid var(--ac)}
.det{padding:18px;overflow:auto;max-height:85vh}.det h2{margin:0 0 6px;font-size:19px}.desc{white-space:pre-wrap;margin-top:12px;border-top:1px solid var(--bd);padding-top:12px}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.acts a{background:var(--ac);color:#fff;text-decoration:none;padding:8px 14px;border-radius:8px;font-weight:600}
.acts a.sec{background:transparent;color:var(--ac);border:1px solid var(--ac)}
.x{float:right;background:none;border:0;font-size:26px;color:var(--mut);cursor:pointer;line-height:1}
.vazio{grid-column:1/-1;text-align:center;color:var(--mut);padding:40px}
</style></head><body>
<header><h1>Oportunidades no Marketplace — região de Palmas/TO</h1>
<div class="sub">iPhones comparados com a média de 08/08/2026 · clique num anúncio para ver fotos e descrição</div>
<div class="bar" id="cats"></div>
<div class="bar" style="margin-top:8px"><select id="mods"></select>
<select id="ord"><option value="p">Menor preço</option><option value="P">Maior preço</option><option value="v">Mais abaixo da média</option></select>
<input id="q" placeholder="Buscar no título ou descrição…"></div></header>
<main id="g"></main>
<div id="mod"><div class="box"><div class="gal"><img class="big" id="big"><button class="nav prev" id="pv">‹</button><button class="nav next" id="nx">›</button><div class="th" id="th"></div></div>
<div class="det" id="det"></div></div></div>
<script>
const D=__DADOS__;
const fmt=v=>'R$ '+v.toLocaleString('pt-BR');
let cat='Todos',cur=null,idx=0;
const cats=['Todos',...new Set(D.map(d=>d.cat))];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function tags(d){let t='';if(d.vs_media!=null)t+=`<span class="tag ${d.vs_media<0?'low':'high'}">${d.vs_media>0?'+':''}${d.vs_media}% vs média</span>`;
 if(d.alerta)t+='<span class="tag warn">⚠ cita defeito</span>';return t}
function barra(){document.getElementById('cats').innerHTML=cats.map(c=>`<button class="${c===cat?'on':''}" data-c="${esc(c)}">${esc(c)} (${c==='Todos'?D.length:D.filter(d=>d.cat===c).length})</button>`).join('');
 const ms=[...new Set(D.filter(d=>cat==='Todos'||d.cat===cat).map(d=>d.mod))];
 document.getElementById('mods').innerHTML='<option value="">Todos os modelos</option>'+ms.map(m=>`<option>${esc(m)}</option>`).join('')}
function lista(){const mod=document.getElementById('mods').value,q=document.getElementById('q').value.toLowerCase(),o=document.getElementById('ord').value;
 let L=D.filter(d=>(cat==='Todos'||d.cat===cat)&&(!mod||d.mod===mod)&&(!q||(d.titulo+' '+d.descricao).toLowerCase().includes(q)));
 L.sort(o==='p'?(a,b)=>a.preco-b.preco:o==='P'?(a,b)=>b.preco-a.preco:(a,b)=>(a.vs_media??99)-(b.vs_media??99));
 document.getElementById('g').innerHTML=L.length?L.map(d=>`<div class="c" data-id="${d.id}"><div class="n"><img loading="lazy" src="${encodeURI(d.fotos[0])}"><span>📷 ${d.fotos.length}</span></div>
 <div class="b"><div class="p">${fmt(d.preco)}</div><div class="t">${esc(d.titulo)}</div><div class="m">${esc(d.mod)} · ${esc(d.local)}</div><div class="tags">${tags(d)}</div></div></div>`).join(''):'<div class="vazio">Nada encontrado.</div>'}
function abrir(id){cur=D.find(d=>d.id===id);idx=0;
 document.getElementById('det').innerHTML=`<button class="x" id="fx">×</button><h2>${esc(cur.titulo)}</h2><div class="p">${fmt(cur.preco)}</div>
 <div class="m">${esc(cur.mod)} · ${esc(cur.local)}${cur.condicao?' · '+esc(cur.condicao):''}</div><div class="tags">${tags(cur)}</div>
 <div class="acts"><a href="${cur.link}" target="_blank" rel="noopener">Abrir no Facebook</a><a class="sec" href="${encodeURI(cur.pasta)}/" target="_blank">Pasta das fotos</a></div>
 <div class="desc">${esc(cur.descricao||'(sem descrição)')}</div>`;
 document.getElementById('fx').onclick=fechar;
 document.getElementById('th').innerHTML=cur.fotos.map((f,i)=>`<img src="${encodeURI(f)}" data-i="${i}">`).join('');
 foto(0);document.getElementById('mod').style.display='block';document.body.style.overflow='hidden'}
function foto(i){idx=(i+cur.fotos.length)%cur.fotos.length;document.getElementById('big').src=encodeURI(cur.fotos[idx]);
 document.querySelectorAll('#th img').forEach((e,k)=>e.classList.toggle('on',k===idx));
 const multi=cur.fotos.length>1;pv.style.display=nx.style.display=multi?'':'none'}
function fechar(){document.getElementById('mod').style.display='none';document.body.style.overflow='';cur=null}
document.getElementById('cats').onclick=e=>{const c=e.target.dataset.c;if(c){cat=c;barra();lista()}};
['mods','ord'].forEach(i=>document.getElementById(i).onchange=lista);document.getElementById('q').oninput=lista;
document.getElementById('g').onclick=e=>{const c=e.target.closest('.c');if(c)abrir(c.dataset.id)};
document.getElementById('th').onclick=e=>{if(e.target.dataset.i)foto(+e.target.dataset.i)};
pv.onclick=()=>foto(idx-1);nx.onclick=()=>foto(idx+1);
document.getElementById('mod').onclick=e=>{if(e.target.id==='mod')fechar()};
document.onkeydown=e=>{if(!cur)return;if(e.key==='Escape')fechar();if(e.key==='ArrowLeft')foto(idx-1);if(e.key==='ArrowRight')foto(idx+1)};
barra();lista();
</script></body></html>
"""

if __name__ == "__main__":
    main()
