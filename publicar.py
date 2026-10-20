"""
Manda para o GitHub o que mudou na pasta do projeto (histórico e scripts).
A página (index.html + s/) é publicada dentro do app da agenda: LGRSV/agenda-iphone, pasta marketplace/
(https://lgrsv.github.io/agenda-iphone/marketplace/). O repositório marketplace não publica mais a página.
dados/, fotos/, planilhas/, index.html e s/ ficam fora pelo .gitignore.

    python publicar.py ["mensagem"] [--proj PASTA]
"""

import argparse
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


AGENDA = os.path.join(os.path.dirname(AQUI), "agenda-iphone")  # LGRSV/agenda-iphone: a página mora em marketplace/
# Worktree só de publicação, sempre na main (o clone acima muda de branch quando alguém desenvolve; em 19/10 isso travou os pushes)
PUBLICAR = os.path.join(os.path.expanduser("~"), "agenda-iphone-publicar")
if os.path.exists(os.path.join(PUBLICAR, ".git")):
    AGENDA = PUBLICAR
PASTA_AGENDA = "marketplace"


def publicar_na_agenda(proj, msg):
    """Copia index.html e as tiras s/ para agenda-iphone/marketplace/ e manda só essa pasta para o GitHub."""
    destino = os.path.join(AGENDA, PASTA_AGENDA)
    if not os.path.exists(os.path.join(AGENDA, ".git")):  # num worktree .git é arquivo
        print("Agenda: clone de agenda-iphone não encontrado em", AGENDA)
        return 1
    git = lambda *a: subprocess.run(["git", "-C", AGENDA, *a], capture_output=True, text=True, encoding="utf-8")
    git("pull", "--rebase", "--autostash")  # o app recebe commits de outros lugares o tempo todo
    os.makedirs(os.path.join(destino, "s"), exist_ok=True)
    shutil.copyfile(os.path.join(proj, "index.html"), os.path.join(destino, "index.html"))
    tiras = set(os.listdir(os.path.join(proj, "s")))
    for f in tiras:
        alvo = os.path.join(destino, "s", f)
        if not os.path.exists(alvo):  # tira não muda depois de criada
            shutil.copyfile(os.path.join(proj, "s", f), alvo)
    for f in set(os.listdir(os.path.join(destino, "s"))) - tiras:
        os.remove(os.path.join(destino, "s", f))
    git("add", "-A", "--", PASTA_AGENDA)
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("Agenda: nada mudou.")
        return 0
    c = git("commit", "-m", "Marketplace: " + msg.split("\n")[0], "--", PASTA_AGENDA)
    if c.returncode:
        print("Agenda: commit falhou:", c.stderr or c.stdout)
        return 1
    for _ in range(3):  # outro push no meio do caminho: busca de novo e tenta outra vez
        r = git("push", "origin", "HEAD:main")
        if r.returncode == 0:
            print("Agenda: publicado.")
            return 0
        git("pull", "--rebase", "--autostash")
    print("Agenda: push falhou:", r.stderr.strip())
    return r.returncode


def publicar(proj, msg):
    erro_agenda = 0
    if os.path.abspath(proj) == AQUI:  # só o projeto iPhone/TV/videogame; o aluguel continua no repositório dele
        erro_agenda = publicar_na_agenda(proj, msg)  # falha aqui não pode mais passar em silêncio (tarefa saía 0x0)
    git = lambda *a: subprocess.run(["git", "-C", proj, *a], capture_output=True, text=True, encoding="utf-8")
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("GitHub: nada mudou.")
        return erro_agenda
    c = git("commit", "-m", msg)
    if c.returncode:
        print("GitHub: commit falhou:", c.stderr or c.stdout)
        return 1
    git("pull", "--rebase", "-X", "theirs")  # se a página foi mexida direto no GitHub, mantém a nossa
    r = git("push", "origin", "HEAD:main")
    print("GitHub:", "publicado." if r.returncode == 0 else "push falhou: " + r.stderr.strip())
    return r.returncode or erro_agenda


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("msg", nargs="?", default="Atualização da coleta")
    ap.add_argument("--proj", default=AQUI)
    a = ap.parse_args()
    sys.exit(publicar(a.proj, a.msg))
