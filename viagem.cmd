@echo off
rem Tela temporaria da viagem (viagem.py). Chamado pela tarefa Marketplace-Viagem (agendar_viagem.ps1), se ela for criada.
rem   viagem.cmd            -> coleta so por HTTP, gera e publica marketplace/viagem/
rem   viagem.cmd --remover  -> tira a tela do site
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist dados mkdir dados
echo ==== %date% %time% %1 >> dados\viagem_saida.txt
python viagem.py %1 >> dados\viagem_saida.txt 2>&1
