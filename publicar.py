"""
Manda para o GitHub o que mudou na pasta do projeto (página, histórico e scripts).
dados/, fotos/ e planilhas/ ficam fora pelo .gitignore.

    python publicar.py ["mensagem"] [--proj PASTA]
"""

import argparse
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def publicar(proj, msg):
    git = lambda *a: subprocess.run(["git", "-C", proj, *a], capture_output=True, text=True, encoding="utf-8")
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("GitHub: nada mudou.")
        return 0
    c = git("commit", "-m", msg)
    if c.returncode:
        print("GitHub: commit falhou:", c.stderr or c.stdout)
        return 1
    git("pull", "--rebase", "-X", "theirs")  # se a página foi mexida direto no GitHub, mantém a nossa
    r = git("push", "origin", "HEAD:main")
    print("GitHub:", "publicado." if r.returncode == 0 else "push falhou: " + r.stderr.strip())
    return r.returncode


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("msg", nargs="?", default="Atualização da coleta")
    ap.add_argument("--proj", default=AQUI)
    a = ap.parse_args()
    sys.exit(publicar(a.proj, a.msg))
