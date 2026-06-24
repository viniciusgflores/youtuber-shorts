# -*- coding: utf-8 -*-
"""
Login OAuth do TikTok (fluxo em 2 passos, com redirect HTTPS).

O TikTok nao aceita redirect http://localhost -> usamos a pagina HTTPS do GitHub Pages
(docs/callback.html), que apenas MOSTRA o codigo de autorizacao na tela.

PRE-REQUISITOS (uma vez, em developers.tiktok.com):
  - App com Login Kit + Content Posting API (Direct Post)
  - Escopos: user.info.basic, video.publish, video.upload
  - Redirect URI cadastrado EXATAMENTE:
        https://viniciusgflores.github.io/youtuber-shorts/callback.html
  - Crie tiktok_client.json com:
        { "client_key": "SEU_CLIENT_KEY", "client_secret": "SEU_CLIENT_SECRET" }

COMO USAR (2 passos):
  Passo 1 - gerar o link de autorizacao:
        python tiktok_login.py
     Abra o link no navegador, autorize, e a pagina vai MOSTRAR um codigo. Copie-o.

  Passo 2 - trocar o codigo por token:
        python tiktok_login.py "CODIGO_QUE_VOCE_COPIOU"
     Isso salva o tiktok_token.json. Pronto.
"""

import sys
import json
import time
import urllib.parse
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
CLIENT_FILE = BASE / "tiktok_client.json"
TOKEN_FILE = BASE / "tiktok_token.json"

REDIRECT_URI = "https://viniciusgflores.github.io/youtuber-shorts/callback.html"
SCOPES = "user.info.basic,video.publish,video.upload"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def carregar_cred():
    if not CLIENT_FILE.exists():
        print(f"ERRO: nao encontrei {CLIENT_FILE.name}.")
        print('Crie: {"client_key": "...", "client_secret": "..."}')
        sys.exit(1)
    return json.loads(CLIENT_FILE.read_text(encoding="utf-8"))


def gerar_link():
    cred = carregar_cred()
    query = urllib.parse.urlencode({
        "client_key": cred["client_key"],
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": "tiktokstate",
    })
    print("\n=== PASSO 1 — abra este link no navegador e autorize ===\n")
    print(f"{AUTH_URL}?{query}\n")
    print("Depois de autorizar, a pagina vai MOSTRAR um codigo.")
    print("Copie o codigo e rode:\n")
    print('   python tiktok_login.py "CODIGO_COPIADO"\n')


def trocar_codigo(code):
    cred = carregar_cred()
    # o TikTok costuma devolver o code com sufixo "*..."; corta no primeiro "*"
    code = code.split("*")[0].strip()
    resp = requests.post(TOKEN_URL, data={
        "client_key": cred["client_key"],
        "client_secret": cred["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    dados = resp.json()
    if "access_token" not in dados:
        print("ERRO ao obter token:")
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        sys.exit(1)

    agora = int(time.time())
    dados["_obtido_em"] = agora
    dados["_expira_em"] = agora + int(dados.get("expires_in", 0))
    TOKEN_FILE.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    print(f"\nOK! Token salvo em {TOKEN_FILE.name}.")
    print("Agora suba nos GitHub Secrets:")
    print("  TIKTOK_CLIENT_JSON = conteudo do tiktok_client.json")
    print("  TIKTOK_TOKEN_JSON  = conteudo do tiktok_token.json")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        trocar_codigo(sys.argv[1])
    else:
        gerar_link()
