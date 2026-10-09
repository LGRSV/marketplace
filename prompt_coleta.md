Você vai refazer a coleta semanal de anúncios de iPhone 13, 14, 15, 16 e 17 no Facebook Marketplace,
usando o Chrome já aberto e logado do usuário.

## Contexto

A pasta de trabalho é `C:\Users\JOAO ANTONIO LAGARES\Documents\marketplace-iphone13`.
A coleta anterior está em `dados\lote_completo.json` — ela será substituída pela nova.

## REGRAS DE PESQUISA (definidas pelo usuário — não altere por conta própria)

**1. Localidades aceitas.** Só entram na média anúncios destas localidades:

> **Palmas, Taquaralto, Taquaruçu, Porto Nacional e Paraíso do Tocantins** — todas no TO.

Taquaralto e Taquaruçu são distritos de Palmas; o Marketplace às vezes os rotula como
"Palmas, TO" e às vezes com o nome próprio, por isso os três contam.

Colete tudo o que a busca trouxer (o Facebook estoura o raio sozinho e traz Araguaína,
Gurupi, Marabá/PA, Balsas/MA...), mas **o filtro é aplicado depois**, pela lista
`REGIAO_PALMAS` em `gerar_excel.py`. Não tente filtrar no site. O que vier de fora fica
na planilha marcado como "Na regiao = Nao" e não entra em nenhuma média.

**2. A média principal é por FAIXA.** São três por geração (13, 14, 15, 16 e 17), e cada
uma tem média própria:

> **iPhone NN (normal)** · **iPhone NN Pro** · **iPhone NN Pro Max**

Abaixo disso, a planilha detalha por capacidade (128GB / 256GB / 512GB) — por isso o campo
`armazenamento` continua importante na classificação. Extraia sempre que estiver escrito.

**3. Cada faixa precisa de pelo menos 10 anúncios.** Média com 2 ou 3 anúncios não é preço
de mercado. A busca pelo número sozinho **não** traz Pro e Pro Max suficientes — rode as
**três buscas de cada geração** e junte tudo (15 buscas no total):

```
.../search/?query=iphone%20NN
.../search/?query=iphone%20NN%20pro
.../search/?query=iphone%20NN%20pro%20max
```

com `NN` em **13, 14, 15, 16 e 17**, sobre a base
`https://www.facebook.com/marketplace/113043862042267`.

Se alguma faixa ficar abaixo de 10 mesmo assim, **diga isso no relatório** em vez de
apresentar a média como se fosse confiável. Na região, as faixas *normal* e *Pro* das
gerações novas costumam ter poucos anúncios — é característica do mercado, não erro.

**4. Use média, não mediana.** O usuário acompanha a média aritmética dos preços
anunciados. A planilha não mostra mediana.

**5. Auditoria de títulos — descarte o que não é um iPhone 13 a 17 específico.** As buscas
trazem lixo que contamina a média. Precisa sair:

- **anúncios de múltiplos modelos** ("Apple iphones 13,14,15,16", lojas com "12, 13, 14, 15
  disponíveis") — o preço não corresponde a nenhum modelo;
- **outros aparelhos** (iPhone 11, 12, SE, Android...) que a busca misturou. Um iPhone 14
  que apareceu na busca do 13 **não** é descartado: vale para a geração 14;
- **acessórios, peças e serviços**;
- **preços que não são do aparelho** (sinal, parcela, "R$ 1 para retirada de peças").

**Não** descarte um iPhone legítimo só porque tem defeito, tela trocada ou bateria ruim —
esses são dados válidos, apenas entram em outro recorte.

## Passo 1 — Carregar as ferramentas do Chrome

Uma única chamada:

```
ToolSearch: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__browser_batch,mcp__claude-in-chrome__computer
```

Depois `tabs_context_mcp` com `createIfEmpty: true` para obter o tabId.

## Passo 2 — Levantar os anúncios da busca

Faça as **15 buscas** da regra 3 (NN = 13, 14, 15, 16, 17 × normal, pro, pro max), por exemplo:
`https://www.facebook.com/marketplace/113043862042267/search/?query=iphone%2013%20pro%20max`

Em cada uma, role até esgotar o lazy-load e colete os IDs. Junte os IDs das 15 buscas
sem repetir (o mesmo anúncio aparece em várias):

```js
let prev = 0;
for (let i = 0; i < 25; i++) {
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 1200));
  const n = document.querySelectorAll('a[href*="/marketplace/item/"]').length;
  if (n === prev && i > 3) break;
  prev = n;
}
const ids = [...new Set([...document.querySelectorAll('a[href*="/marketplace/item/"]')]
  .map(a => (a.getAttribute('href').match(/item\/(\d+)/) || [])[1]).filter(Boolean))];
ids.join(',');
```

Se a lista vier vazia, provavelmente a **sessão do Facebook expirou** — pare, registre isso
e avise. Não tente fazer login.

## Passo 3 — Instalar o extrator

O extrator fica em `window.name` (o Facebook apaga chaves próprias do localStorage, então
`localStorage` NÃO funciona aqui). O separador é `String.fromCharCode(1)` — não use um
literal, senão o `split` corta dentro do próprio código.

```js
const CODE = `
const SEP=String.fromCharCode(1);
await new Promise(r=>setTimeout(r,2500));
[...document.querySelectorAll('div[role="button"],span')].filter(e=>/^Ver mais$/i.test(e.innerText.trim())).forEach(b=>b.click());
await new Promise(r=>setTimeout(r,800));
const S=window.name.split(SEP);
const arr=JSON.parse(S[1]||'[]');
const id=(location.pathname.match(/item\\/(\\d+)/)||[])[1];
const b=document.body.innerText;
const i=b.indexOf('Grupos de compra e venda');
const j=b.indexOf('Informações do vendedor');
if(i<0){arr.push({id,erro:'indisponivel'});window.name=S[0]+SEP+JSON.stringify(arr);return arr.length+'|ERRO|'+id;}
const bloco=b.slice(i+24, j>i?j:i+3000);
const L=bloco.split('\\n').map(s=>s.trim()).filter(Boolean);
const titulo=L[0]||'';
const mp=bloco.match(/R\\$\\s?([\\d.]+)/);
const preco=mp?Number(mp[1].replace(/\\D/g,'')):0;
const ml=L.map(s=>s.match(/^Anunciado\\s+(?:h[áa]\\s+.+?\\s+)?em\\s+(.+)$/)).find(Boolean);
const local=ml?ml[1].trim():'';
const ic=L.findIndex(s=>s==='Condição');
const condicao=ic>-1?L[ic+1]:'';
const fim=L.findIndex(s=>/A localização é aproximada/.test(s));
const ini=ic>-1?ic+2:L.findIndex(s=>s==='Detalhes')+1;
const descricao=L.slice(ini, fim>ini?fim:L.length).filter(s=>!/^(Ver mais|Sem menos|Enviar mensagem|Detalhes)$/i.test(s)).join(' ');
const obj={id,titulo,preco,local,condicao,descricao,link:'https://www.facebook.com/marketplace/item/'+id+'/'};
const k=arr.findIndex(x=>x.id===id);
if(k>-1)arr[k]=obj;else arr.push(obj);
window.name=S[0]+SEP+JSON.stringify(arr);
return arr.length+'|'+titulo.slice(0,22)+'|R$'+preco+'|'+local.split(',')[0];
`;
window.name = CODE + String.fromCharCode(1) + '[]';
```

## Passo 4 — Percorrer os anúncios

Para cada ID, em `browser_batch` de **no máximo 4 anúncios** (lotes maiores são barrados
pelo classificador de permissões e estouram o tempo de resposta):

- `navigate` para `https://www.facebook.com/marketplace/item/<ID>/`
- `javascript_tool`:
  `await (new Function('return (async()=>{'+window.name.split(String.fromCharCode(1))[0]+'})()'))()`

Se um anúncio devolver `ERRO`, siga em frente e tente de novo no fim — não trave.

**Salve o progresso a cada ~20 anúncios** (passo 5). A extensão do Chrome pode cair no meio
da coleta; sem salvar, tudo se perde.

## Passo 5 — Gravar em disco (salve a cada ~15 anúncios!)

`window.name` não é legível pelo shell, e **a aba pode ser recriada a qualquer momento**,
zerando tudo. Salve com frequência — já perdemos 30 e 14 registros por não fazer isso.

**Não use `navigator.clipboard.writeText`**: exige que a aba esteja ativa E a janela do
Chrome em primeiro plano no Windows. Quando o usuário volta ao terminal, falha com
"Document is not focused", e a Promise pendente trava o renderer inteiro.

**Não use download via blob**: o Chrome libera o primeiro e bloqueia os seguintes
("downloads automáticos" negado para o site).

**O que funciona:** textarea + Ctrl+C nativo via CDP, que independe de foco de janela.

```js
const arr = JSON.parse(window.name.split(String.fromCharCode(1))[1] || '[]');
let ta = document.getElementById('__TA');
if (!ta) {
  ta = document.createElement('textarea');
  ta.id = '__TA';
  ta.style.cssText = 'position:fixed;top:10px;left:10px;width:300px;height:100px;z-index:999999';
  document.body.appendChild(ta);
}
ta.value = JSON.stringify(arr);
ta.focus(); ta.select();
```

Em seguida, no mesmo `browser_batch`, duas ações `computer`: `key ctrl+a` e `key ctrl+c`.
Depois leia com PowerShell e **remova o textarea** antes de continuar navegando:

```powershell
Get-Clipboard -Raw | Out-File "...\dados\lote_<nome>.json" -Encoding utf8 -NoNewline
```

## Passo 6 — Classificar as descrições e auditar os títulos

Apague os `classificacao*.json` e o `descartes.json` antigos.

**6a) Classificação.** Lance **4 agentes Sonnet em paralelo**, cada um com uma fatia do
array (0-19, 20-39, 40-59, 60-fim). Cada agente lê os `lote_*.json`, analisa título +
descrição e grava `dados\classificacaoN.json` com:

`id`, `variante` ("NN" | "NN mini" | "NN Plus" | "NN Pro" | "NN Pro Max" | "outro", com NN
de 13 a 17 — ex.: "15 Pro Max", "16", "17 Pro"), `armazenamento`
("128GB" | "256GB" | "512GB" | "1TB" | ""), `bateria_pct` (inteiro ou null — nunca inventar),
`estado` ("novo/lacrado" | "seminovo" | "usado" | "com defeito"), `original`
(true/false/null), `observacoes` (máx. 120 chars).

Reforce nos agentes que **`armazenamento` é obrigatório sempre que estiver escrito** no
título ou na descrição — é ele que separa um modelo do outro no detalhamento.

**6b) Auditoria de títulos.** Lance **mais um agente Sonnet** que lê TODOS os anúncios de
todos os `lote_*.json` e aplica a regra 5 acima, gravando `dados\descartes.json`:

```json
[{"id":"...", "titulo":"...", "preco":0, "motivo":"multiplos_modelos", "explicacao":"..."}]
```

`motivo` ∈ `multiplos_modelos` | `modelo_fora_13_a_17` | `nao_e_aparelho` | `preco_invalido`.
Liste **só os descartados**. O `gerar_excel.py` lê esse arquivo e tira esses anúncios de
todas as médias, deixando-os na planilha em vermelho com o motivo.

## Passo 7 — Gerar as planilhas

```powershell
cd "C:\Users\JOAO ANTONIO LAGARES\Documents\marketplace-iphone13"
python gerar_excel.py
```

Gera **uma planilha por geração** (`iphone13_...xlsx`, `iphone14_...xlsx`, ...) e um
`historico_iphoneNN.xlsx` para cada. O script lê todos os `lote_*.json`,
`classificacao*.json` e `descartes*.json` da pasta `dados`.

Ao final, informe:

- quantos anúncios foram lidos e quantos ficaram dentro das localidades aceitas;
- **o preço médio de cada faixa de cada geração** (13, 13 Pro, 13 Pro Max ... 17 Pro Max),
  sinalizando quais têm menos de 10 anúncios — nesses a média não é confiável;
- como cada faixa se compara à linha anterior do `planilhas\historico_iphoneNN.xlsx`
  da sua geração (subiu, caiu ou estável).
