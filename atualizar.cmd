@echo off
rem Chamado pelo Agendador de Tarefas (agendar_atualizacao.ps1).
rem   atualizar.cmd novos    -> ate 5 anuncios novos de cada projeto (iPhone/TV/videogame e aluguel)
rem   atualizar.cmd diario   -> compilado do dia dos dois projetos, publicado no GitHub
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist dados mkdir dados
echo ==== %date% %time% %1 >> dados\atualizar_saida.txt
python atualizar.py %1 --proj iphone >> dados\atualizar_saida.txt 2>&1
python atualizar.py %1 --proj aluguel >> dados\atualizar_saida.txt 2>&1
