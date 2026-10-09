# =====================================================================
#  Coleta semanal de iPhone 13 no Facebook Marketplace - regiao de Palmas/TO
#
#  Executa a coleta via Claude Code (que dirige o Chrome ja logado) e
#  gera a planilha Excel.
#
#  Uso manual:  .\rodar_coleta.ps1
#  Agendado:    chamado pelo Task Scheduler (ver agendar_rotina.ps1)
# =====================================================================

$ErrorActionPreference = "Stop"

$Base    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dados   = Join-Path $Base "dados"
$Log     = Join-Path $Dados "log.txt"
$Prompt  = Join-Path $Base "prompt_coleta.md"

function Registrar($msg) {
    $linha = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $linha
    Add-Content -Path $Log -Value $linha -Encoding utf8
}

New-Item -ItemType Directory -Force -Path $Dados | Out-Null
Registrar "=== inicio da coleta semanal ==="

# ---------------------------------------------------------------- 1. Chrome
# A coleta depende da sessao logada do Facebook no Chrome real.
$chrome = Get-Process chrome -ErrorAction SilentlyContinue
if (-not $chrome) {
    Registrar "Chrome fechado - abrindo"
    $exe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    if (-not (Test-Path $exe)) {
        $exe = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    }
    if (Test-Path $exe) {
        Start-Process $exe
        Start-Sleep -Seconds 12   # tempo para a extensao do Claude subir
    } else {
        Registrar "ERRO: chrome.exe nao encontrado - abortando"
        exit 1
    }
} else {
    Registrar "Chrome ja esta aberto"
}

# ---------------------------------------------------------------- 2. backup
$antigo = Join-Path $Dados "lote_completo.json"
if (Test-Path $antigo) {
    $bkp = Join-Path $Dados ("lote_completo_" + (Get-Date -Format "yyyy-MM-dd") + ".bak.json")
    Copy-Item $antigo $bkp -Force
    Registrar "backup da coleta anterior: $(Split-Path $bkp -Leaf)"
}

# ---------------------------------------------------------------- 3. coleta
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Registrar "ERRO: comando 'claude' nao encontrado no PATH - abortando"
    exit 1
}

Registrar "chamando Claude Code para executar prompt_coleta.md"
Push-Location $Base
try {
    $instrucao = "Leia o arquivo prompt_coleta.md nesta pasta e execute exatamente o que ele descreve, do inicio ao fim."
    claude -p $instrucao 2>&1 | Tee-Object -Variable saida | Out-Null
    Registrar "Claude Code finalizou"
    Add-Content -Path $Log -Value $saida -Encoding utf8
} catch {
    Registrar "ERRO durante a coleta: $($_.Exception.Message)"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 4. planilha
# Roda de novo por seguranca: se o Claude ja gerou, apenas regera com os
# mesmos dados; se ele parou antes do passo 7, isso conclui o trabalho.
Registrar "gerando planilha"
Push-Location $Base
try {
    $py = python gerar_excel.py 2>&1
    Add-Content -Path $Log -Value $py -Encoding utf8
    Registrar "planilha gerada"
} catch {
    Registrar "ERRO ao gerar planilha: $($_.Exception.Message)"
} finally {
    Pop-Location
}

Registrar "=== fim da coleta semanal ==="
