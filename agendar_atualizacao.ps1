# =====================================================================
#  Agenda a atualização contínua do Marketplace (não precisa de Administrador):
#    "Marketplace-Novos"     a cada 2 horas, das 07:00 às 21:00: até 5 anúncios novos por projeto
#    "Marketplace-Compilado" todo dia às 12:00: confere vendidos, gera a página e publica no GitHub
#
#  Rodar de novo recria as duas tarefas (serve de recuperação).
#      .\agendar_atualizacao.ps1
#      .\agendar_atualizacao.ps1 -Almoco 12:30
#      .\agendar_atualizacao.ps1 -Remover
#  As tarefas só rodam com o usuário logado (o Chrome precisa de uma sessão aberta).
# =====================================================================
param([string]$Almoco = "12:00", [switch]$Remover)
$ErrorActionPreference = "Stop"
$Base = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cmd = Join-Path $Base "atualizar.cmd"

foreach ($n in "Marketplace-Novos", "Marketplace-Compilado") {
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
}
if ($Remover) { Write-Host "Tarefas removidas."; return }

$cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
$quem = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$t = New-ScheduledTaskTrigger -Daily -At "07:00"
$t.Repetition = (New-ScheduledTaskTrigger -Once -At "07:00" -RepetitionInterval (New-TimeSpan -Hours 2) `
                  -RepetitionDuration (New-TimeSpan -Hours 14 -Minutes 30)).Repetition
Register-ScheduledTask -TaskName "Marketplace-Novos" -Trigger $t -Settings $cfg -Principal $quem `
    -Action (New-ScheduledTaskAction -Execute $Cmd -Argument "novos" -WorkingDirectory $Base) `
    -Description "Até 5 anúncios novos do Marketplace por projeto, a cada 2 horas (07h-21h)" | Out-Null

Register-ScheduledTask -TaskName "Marketplace-Compilado" -Trigger (New-ScheduledTaskTrigger -Daily -At $Almoco) `
    -Settings $cfg -Principal $quem `
    -Action (New-ScheduledTaskAction -Execute $Cmd -Argument "diario" -WorkingDirectory $Base) `
    -Description "Compilado diário do Marketplace: vendidos, página e GitHub" | Out-Null

Get-ScheduledTask -TaskName "Marketplace-*" | Get-ScheduledTaskInfo |
    Select-Object TaskName, NextRunTime | Format-Table -AutoSize
