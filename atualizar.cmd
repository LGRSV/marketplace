@echo off
rem Chamado pelo Agendador de Tarefas (agendar_atualizacao.ps1).
rem   atualizar.cmd novos    -> ate 5 anuncios novos (iPhone, Galaxy, TV e videogame)
rem   atualizar.cmd diario   -> compilado do dia, publicado no GitHub
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist dados mkdir dados
echo ==== %date% %time% %1 >> dados\atualizar_saida.txt
python atualizar.py %1 --proj iphone >> dados\atualizar_saida.txt 2>&1
rem aluguel pausado em 10/10/2026; para voltar, tire o "rem" do comeco da linha abaixo
rem python atualizar.py %1 --proj aluguel >> dados\atualizar_saida.txt 2>&1
