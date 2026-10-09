# Monitor de iPhone — Facebook Marketplace (região de Palmas/TO)

Coleta os anúncios de **iPhone 13, 14, 15, 16 e 17** no Marketplace, lê a descrição de cada
um, classifica estado e saúde da bateria, e gera **uma planilha Excel por geração** com o
preço médio da região.

## Como rodar

**Agora, uma vez:**

```powershell
cd "C:\Users\JOAO ANTONIO LAGARES\Documents\marketplace-iphone13"
.\rodar_coleta.ps1
```

**Agendar toda semana** (PowerShell **como Administrador**):

```powershell
.\agendar_rotina.ps1                       # segunda-feira, 09:00
.\agendar_rotina.ps1 -Dia Sexta -Hora 20:00
```

## Se a rotina se perder

`agendar_rotina.ps1` **é o script de recuperação**. Se a tarefa sumir do Agendador, se
alguém apagar, ou se você formatar a máquina, rode-o de novo como Administrador e o
agendamento volta exatamente como estava. Ele apaga qualquer versão antiga antes de
recriar, então rodar duas vezes não duplica nada.

Conferir se está ativa:

```powershell
Get-ScheduledTask -TaskName "Marketplace-iPhone13"
Get-ScheduledTaskInfo -TaskName "Marketplace-iPhone13"   # última e próxima execução
```

Rodar na hora, sem esperar o dia:

```powershell
Start-ScheduledTask -TaskName "Marketplace-iPhone13"
```

Desativar:

```powershell
.\agendar_rotina.ps1 -Remover
```

## Arquivos

| Arquivo | O que faz |
|---|---|
| `prompt_coleta.md` | As instruções da coleta. **Edite aqui** para mudar o modelo buscado ou os critérios. |
| `rodar_coleta.ps1` | Abre o Chrome se preciso, chama o Claude Code para coletar, gera a planilha. |
| `agendar_rotina.ps1` | Cria/recria/remove a tarefa semanal. Script de recuperação. |
| `gerar_excel.py` | Junta os dados brutos com as classificações e monta o Excel. |
| `dados/` | JSONs da coleta, backups e `log.txt`. |
| `planilhas/` | Planilhas por data + `historico_iphone13.xlsx` com a evolução. |

## Regras de pesquisa

**1. Localidades aceitas** — só entram na média:

> Palmas · Taquaralto · Taquaruçu · Porto Nacional · Paraíso do Tocantins

Taquaralto e Taquaruçu são distritos de Palmas; o Marketplace ora os chama de "Palmas, TO",
ora pelo nome próprio, então os três contam. Configurado em `REGIAO_PALMAS`
(`gerar_excel.py`).

**2. A média é por faixa** — em cada geração: **normal**, **Pro** e **Pro Max**, cada uma
com sua média. Abaixo, a planilha detalha por capacidade (128/256/512GB/1TB).

**3. Mínimo de 10 anúncios por faixa** — abaixo disso a média é sinalizada como frágil. Para
alcançar esse volume, a coleta roda **três buscas por geração** (`iphone NN`, `iphone NN pro`,
`iphone NN pro max`) — 15 buscas no total. Só a primeira de cada não traz Pro e Pro Max
suficientes.

**4. Média, não mediana** — média aritmética dos preços anunciados.

**5. Auditoria de títulos** — um agente lê todos os títulos e descarta o que contamina a
média: anúncios de vários modelos ao mesmo tempo ("Apple iphones 13,14,15,16"), outros
aparelhos que a busca misturou (12, 14, 15...), acessórios e preços que não são do aparelho.
Vão para `dados\descartes.json` com o motivo.

## As planilhas

Uma por geração, geradas na mesma execução:

```
planilhas\iphone13_palmas_<data>.xlsx   +  historico_iphone13.xlsx
planilhas\iphone14_palmas_<data>.xlsx   +  historico_iphone14.xlsx
planilhas\iphone15_palmas_<data>.xlsx   +  historico_iphone15.xlsx
planilhas\iphone16_palmas_<data>.xlsx   +  historico_iphone16.xlsx
planilhas\iphone17_palmas_<data>.xlsx   +  historico_iphone17.xlsx
```

**Aba Resumo** — três tabelas:
1. *Preço médio por faixa*, todos os estados;
2. *Preço médio por faixa*, só novo/seminovo com bateria ≥ 85%;
3. *Detalhamento por capacidade*.

Linhas em amarelo têm amostra suficiente. Linhas em cinza-itálico marcadas "amostra pequena"
não atingiram o mínimo — trate como indício, não como referência de preço.

**Aba Anuncios** — todos em ordem decrescente de preço, com descrição integral e link
clicável. **Cinza** = fora das localidades aceitas. **Vermelho claro** = reprovado na
auditoria de títulos (a coluna "Descartado por" diz o motivo). Nenhum dos dois entra em
média alguma.

**historico_iphone13.xlsx** — uma linha por execução, com média **e quantidade** de cada
faixa. É o que mostra se o preço subiu ou caiu entre uma semana e outra; a coluna de
quantidade avisa quando a média daquela semana ficou fraca. `R$ 0` = nenhum anúncio da
faixa naquela semana.

## Duas coisas que você precisa saber

**1. O Facebook ignora o raio que você pediu.** A busca está configurada em *Palmas ·
120 km*, mas quando os resultados locais acabam ele emenda anúncios de Araguaína, Gurupi,
Marabá/PA, Balsas/MA, até Barreiras/BA — na primeira coleta, **45 dos 78 anúncios eram de
fora**. Por isso a localidade é decidida por lista explícita, e não pelo que o Facebook diz.
Os de fora ficam na planilha marcados como "Na regiao = Nao" e não entram em média nenhuma.

**2. A rotina depende do Chrome logado.** Não existe API pública do Marketplace, e os
Termos da Meta proíbem coleta automatizada. Esta rotina roda no seu Chrome real, uma vez
por semana, em ritmo humano — é por isso que ela não dispara o antifraude. Não transforme
em um raspador 24/7: aí a sessão cai em verificação. Se a sessão do Facebook expirar, a
coleta volta vazia e `dados\log.txt` registra o motivo.

## Ajustes comuns

- **Incluir/remover uma cidade**: lista `REGIAO_PALMAS` em `gerar_excel.py` (use o nome sem
  acento e em minúsculas na chave).
- **Incluir outra geração** (iPhone 18...): adicione à lista `GERACOES` em `gerar_excel.py`
  e às buscas do `prompt_coleta.md`, passo 2.
- **Mudar o mínimo de anúncios por faixa**: `AMOSTRA_MINIMA` em `gerar_excel.py`.
- **Outro critério de "bom estado"**: função `eh_bom_estado()` em `gerar_excel.py`.
