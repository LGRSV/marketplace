# Oportunidades no Marketplace — Palmas/TO

**Site:** https://lgrsv.github.io/marketplace/ — atualizado sozinho de 2 em 2 horas (7h–21h) e compilado às 12h.

Coleta anúncios do Facebook Marketplace da região de Palmas (Palmas, Taquaralto, Taquaruçu, Porto Nacional e
Paraíso do Tocantins), compara cada um com o preço médio do mesmo modelo e guarda o histórico de quem vendeu.

## As buscas

Cada busca vira uma aba no site, com os anúncios, o preço médio por modelo e o ranking de vendas **só dela**.

| Aba no site | Termos buscados no Marketplace | Média por |
|---|---|---|
| 📱 **iPhone** | `iphone 13` … `iphone 18`, cada um também `pro` e `pro max` (18 buscas) | variante (ex.: iPhone 15 Pro Max) |
| 📲 **Galaxy** | `galaxy s25 ultra`, `galaxy s26 ultra` | modelo (S25 Ultra, S26 Ultra) |
| 🎮 **Videogame** | `ps5`, `ps4`, `xbox`, `nintendo switch`, `playstation portal` | console |
| 📺 **TV** | `smart tv`, `televisao` | polegada |
| 🕹️ **Jogos e acessórios** | sai das buscas de videogame (jogo avulso, controle, suporte…) | sem média (itens variados demais) |

Os termos ficam em `BUSCAS`, no `coleta.py`. Para incluir uma busca nova, acrescente ali.

## O que tem em cada aba do site

- **🛒 Anúncios** — novos das últimas 24h, melhores oportunidades (bem abaixo da média do modelo) e todos os anúncios,
  com filtro por modelo, ordenação e busca por texto.
- **💲 Preço médio** — média de cada modelo nesta coleta, sem anúncios com defeito, de troca ou com preço absurdo.
- **📈 Ranking de vendas** — o que mais sai do ar desde 08/10/2026: vendidos, apagados, giro e dias até sair.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `atualizar.py` | Rodada automática: `novos` (de 2 em 2 h) e `compilado` (12h). Coleta, gera e publica. |
| `coleta.py` | Abre as buscas e os anúncios no Chrome, em ritmo humano. |
| `historico.py` | `historico/anuncios.json`: cada anúncio já visto e se foi vendido ou apagado. |
| `gerar_pagina.py` + `pagina_template.html` | Monta o `index.html` (o site). Fotos em `s/`, uma tira por anúncio. |
| `golpistas.py` + `golpistas.json` | Vendedores marcados como golpistas: os anúncios deles não aparecem mais. |
| `publicar.py` | `git commit` + `push` do site. |
| `classificar_haiku.py` | Lê a descrição dos iPhones (variante, armazenamento, bateria, estado). |
| `gerar_excel.py`, `prompt_coleta.md`, `rodar_coleta.ps1`, `agendar_rotina.ps1` | Rotina antiga das planilhas semanais de iPhone. |

## Marcar golpista

No site, abra o anúncio e clique em **🚩 Marcar como golpista**. Abre uma issue aqui no GitHub; é só enviar.
A próxima rodada descobre o vendedor, tira todos os anúncios dele do site e fecha a issue.
Pelo terminal: `python golpistas.py marcar <id do anúncio>` / `desmarcar` / `listar`.

## Cuidados

- O Facebook ignora o raio da busca e mistura anúncios de outras cidades; a região é decidida pela lista acima.
- Não existe API do Marketplace: a coleta roda devagar de propósito para não cair em verificação. Não acelere.
- `dados/`, `fotos/` e `planilhas/` ficam só no computador (estão no `.gitignore`).
