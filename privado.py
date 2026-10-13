"""
Acesso restrito à página publicada: os anúncios vão criptografados dentro do index.html (AES-256-GCM) e só abrem
com a senha de uma das pessoas liberadas. As senhas ficam só neste PC, em dados/acessos_marketplace.json (fora do git):
    {"pessoas": {"joao": {"senha": "...", "salt": "..."}, "carlos": {...}}, "segredo": "..."}
Cada pessoa tem um "slot" com a chave dos dados embrulhada pela senha dela (PBKDF2-SHA256); a chave dos dados muda
a cada publicação. O salt de cada pessoa é fixo, para o "lembrar neste aparelho" continuar valendo.
As fotos (s/) não são criptografadas, mas o nome do arquivo não revela o anúncio (HMAC com o segredo).

    python privado.py                  # lista quem tem acesso
    python privado.py liberar NOME     # cria acesso com senha nova (aparece na tela e fica no arquivo)
    python privado.py remover NOME     # tira o acesso a partir da próxima publicação
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ARQ = Path(__file__).resolve().parent / "dados" / "acessos_marketplace.json"
ITER = 600_000
PALAVRAS = ("abacaxi amora areia arara azul baleia banana barco bigode bolo bota brisa cacau cadeira caju calor "
            "caneca canoa capivara carambola cenoura cereja chuva cipreste cobra coruja cuia doce dourado escada "
            "estrela farol feijão festa figo floresta foguete fumaça gato girafa goiaba grama ilha jabuti jacaré "
            "janela jardim lagoa laranja leão limão lua macaco mamão mandioca manga mar melancia mel montanha "
            "morango nuvem onça ouro palmeira panela papagaio pato peixe pena pipoca pitanga ponte praia quati "
            "raio rede rio sabiá serra sol tamanduá tatu tucano urso vento verde vulcão")
PALAVRAS = [p for p in PALAVRAS.split() if p.isascii()]

b64 = lambda b: base64.b64encode(b).decode()


def carregar():
    try:
        A = json.loads(ARQ.read_text(encoding="utf-8"))
    except FileNotFoundError:
        A = {}
    A.setdefault("pessoas", {})
    if not A.get("segredo"):
        A["segredo"] = secrets.token_hex(32)
        salvar(A)
    return A


def salvar(A):
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(A, ensure_ascii=False, indent=1), encoding="utf-8")


def senha_nova():
    return "-".join(secrets.choice(PALAVRAS) for _ in range(4)) + "-" + str(secrets.randbelow(9000) + 1000)


def liberar(nome):
    A = carregar()
    p = A["pessoas"].setdefault(nome.lower(), {})
    p["senha"], p["salt"] = senha_nova(), b64(secrets.token_bytes(16))
    salvar(A)
    return p["senha"]


def nome_tira(id_anuncio, A=None):
    A = A or carregar()
    return hmac.new(A["segredo"].encode(), str(id_anuncio).encode(), hashlib.sha256).hexdigest()[:24]


def cifrar(dados):
    """dados (qualquer JSON) -> cofre {v, iter, iv, ct, slots}, para o template decifrar no navegador."""
    A = carregar()
    if not A["pessoas"]:
        raise SystemExit("privado: ninguém liberado em " + str(ARQ) + " (python privado.py liberar NOME)")
    chave = AESGCM.generate_key(bit_length=256)
    iv = secrets.token_bytes(12)
    ct = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False).encode(), None)
    slots = []
    for p in A["pessoas"].values():
        salt = base64.b64decode(p["salt"])
        kek = hashlib.pbkdf2_hmac("sha256", p["senha"].encode(), salt, ITER, 32)
        iv_s = secrets.token_bytes(12)
        slots.append({"salt": p["salt"], "iv": b64(iv_s), "k": b64(AESGCM(kek).encrypt(iv_s, chave, None))})
    secrets.SystemRandom().shuffle(slots)  # a ordem não entrega quem é quem
    return {"v": 1, "iter": ITER, "iv": b64(iv), "ct": b64(ct), "slots": slots}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    acao = sys.argv[1] if len(sys.argv) > 1 else "listar"
    if acao == "liberar" and len(sys.argv) > 2:
        print(f"{sys.argv[2]}: senha {liberar(sys.argv[2])}  (vale a partir da próxima publicação)")
    elif acao == "remover" and len(sys.argv) > 2:
        A = carregar()
        print("removido" if A["pessoas"].pop(sys.argv[2].lower(), None) else "não encontrado")
        salvar(A)
    else:
        print("Com acesso:", ", ".join(carregar()["pessoas"]) or "ninguém")
