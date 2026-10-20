# =====================================================================
#  Tarefa "Marketplace-Viagem" (nao precisa de Administrador; NAO foi criada: rodar so com o OK do Joao):
#    a cada 3 h (07:40, 10:40, 13:40, 16:40, 19:40, 22:40), longe das rodadas Novos (horas impares) e do
#    Compilado (12:00), ate a data final de dados\viagem.json; no dia seguinte as 08:00 o viagem.py ve a data
#    vencida e tira a tela do site; a tarefa se apaga 1 dia depois do ultimo gatilho.
#      powershell -NoProfile -ExecutionPolicy Bypass -File agendar_viagem.ps1
#      powershell -NoProfile -ExecutionPolicy Bypass -File agendar_viagem.ps1 -Remover
#  As datas ficam so em dados\viagem.json (fora do git).
# =====================================================================
param([switch]$Remover)
$ErrorActionPreference = "Stop"
$Base = Split-Path -Parent $MyInvocation.MyCommand.Path
$Nome = "Marketplace-Viagem"
Unregister-ScheduledTask -TaskName $Nome -Confirm:$false -ErrorAction SilentlyContinue
if ($Remover) { Write-Host "Tarefa removida."; return }

$v = Get-Content (Join-Path $Base "dados\viagem.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$ate = [datetime]::ParseExact($v.ate, "yyyy-MM-dd", $null)

$cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -DeleteExpiredTaskAfter (New-TimeSpan -Days 1)
$quem = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$t1 = New-ScheduledTaskTrigger -Daily -At "07:40"
$t1.Repetition = (New-ScheduledTaskTrigger -Once -At "07:40" -RepetitionInterval (New-TimeSpan -Hours 3) `
                   -RepetitionDuration (New-TimeSpan -Hours 15)).Repetition
$t1.EndBoundary = $ate.ToString("yyyy-MM-dd") + "T23:59:00"
$t2 = New-ScheduledTaskTrigger -Once -At $ate.AddDays(1).Date.AddHours(8)
$t2.EndBoundary = $ate.AddDays(1).Date.AddHours(20).ToString("yyyy-MM-ddTHH:mm:ss")

Register-ScheduledTask -TaskName $Nome -Trigger $t1, $t2 -Settings $cfg -Principal $quem `
    -Action (New-ScheduledTaskAction -Execute (Join-Path $Base "viagem.cmd") -WorkingDirectory $Base) `
    -Description "Tela temporaria do Marketplace (viagem.py), so HTTP" | Out-Null
Get-ScheduledTask -TaskName $Nome | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime | Format-Table -AutoSize
