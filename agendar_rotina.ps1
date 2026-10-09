# =====================================================================
#  Cria (ou recria) a tarefa semanal no Agendador de Tarefas do Windows.
#
#  ESTE E O SCRIPT DE RECUPERACAO: se a rotina sumir, se o agendamento
#  for apagado ou se voce trocar de maquina, basta rodar este arquivo
#  novamente que tudo volta ao normal.
#
#  Uso:
#      .\agendar_rotina.ps1                      # segunda-feira, 09:00
#      .\agendar_rotina.ps1 -Dia Sexta -Hora 20:00
#      .\agendar_rotina.ps1 -Remover             # apaga a tarefa
#
#  Precisa ser executado em um PowerShell COMO ADMINISTRADOR.
# =====================================================================

param(
    [ValidateSet("Domingo","Segunda","Terca","Quarta","Quinta","Sexta","Sabado")]
    [string]$Dia = "Segunda",

    [string]$Hora = "09:00",

    [switch]$Remover
)

$ErrorActionPreference = "Stop"

$Nome   = "Marketplace-iPhone13"
$Base   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Base "rodar_coleta.ps1"

# ---------------------------------------------------------------- remover
if ($Remover) {
    try {
        Unregister-ScheduledTask -TaskName $Nome -Confirm:$false
        Write-Host "Tarefa '$Nome' removida." -ForegroundColor Yellow
    } catch {
        Write-Host "Nao havia tarefa '$Nome' para remover." -ForegroundColor Yellow
    }
    return
}

# ---------------------------------------------------------------- checagens
if (-not (Test-Path $Script)) {
    throw "Nao encontrei rodar_coleta.ps1 em $Base"
}

$admin = ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    throw "Rode este script como Administrador (botao direito no PowerShell > Executar como administrador)."
}

$mapa = @{
    "Domingo"="Sunday"; "Segunda"="Monday"; "Terca"="Tuesday"; "Quarta"="Wednesday"
    "Quinta"="Thursday"; "Sexta"="Friday"; "Sabado"="Saturday"
}

# ---------------------------------------------------------------- criar
$acao = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`"" `
    -WorkingDirectory $Base

$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $mapa[$Dia] -At $Hora

# StartWhenAvailable: se o PC estiver desligado na hora marcada, roda assim que ligar.
# WakeToRun: tenta acordar a maquina caso ela esteja suspensa.
$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 30)

# Roda na sessao do usuario (Interactive): a coleta precisa do Chrome com a
# sessao do Facebook aberta, entao NAO pode rodar como SYSTEM.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

try { Unregister-ScheduledTask -TaskName $Nome -Confirm:$false } catch {}

Register-ScheduledTask `
    -TaskName    $Nome `
    -Action      $acao `
    -Trigger     $gatilho `
    -Settings    $config `
    -Principal   $principal `
    -Description "Coleta semanal de anuncios de iPhone 13 no Facebook Marketplace (regiao de Palmas/TO) e gera planilha Excel." `
    | Out-Null

Write-Host ""
Write-Host "Tarefa '$Nome' criada." -ForegroundColor Green
Write-Host "  Quando .......: toda $Dia as $Hora"
Write-Host "  Script .......: $Script"
Write-Host ""

$t = Get-ScheduledTaskInfo -TaskName $Nome
Write-Host "  Proxima execucao: $($t.NextRunTime)"
Write-Host ""
Write-Host "Para rodar agora, sem esperar:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName $Nome"
Write-Host ""
Write-Host "IMPORTANTE: a coleta precisa do PC ligado e do Chrome com a sessao" -ForegroundColor Yellow
Write-Host "do Facebook valida. Se a sessao expirar, o log em dados\log.txt avisa." -ForegroundColor Yellow
