# -*- coding: utf-8 -*-
"""
Login OAuth do TikTok (rode UMA vez, localmente).

Gera o arquivo tiktok_token.json com access_token + refresh_token.
Depois disso, o upload_tiktok.py (e a nuvem) usam esse token sem precisar logar de novo.

PRE-REQUISITOS (voce faz uma vez no site developers.tiktok.com):
  1. Crie um app e ative o produto "Content Posting API" (com Direct Post).
  2. Adicione os escopos: user.info.basic, video.publish, video.upload
  3. Em "Login Kit", cadastre o Redirect URI EXATAMENTE como:
        http://localhost:8080/callback
  4. Pegue o Client Key e o Client Secret e coloque num arquivo tiktok_client.json:
        { "client_key": "SEU_CLIENT_KEY", "client_secret": "SEU_CLIENT_SECRET" }

COMO RODAR:
    python tiktok_login.py
  Abre o navegador, voce autoriza, e o token e salvo. Pronto.
"""

import json
import time
import secrets
import webbrowser
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests

BASE = Path(__file__).resolve().parent
CLIENT_FILE = BASE / "tiktok_client.json"
TOKEN_FILE = BASE / "tiktok_token.json"

REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "user.info.basic,video.publish,video.upload"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

_codigo_recebido = {"code": None, "state": None}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _codigo_recebido["code"] = params.get("code", [None])[0]
        _codigo_recebido["state"] = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<h2>Pronto! Pode fechar esta aba e voltar ao terminal.</h2>".encode("utf-8")
        )

    def log_message(self, *args):
        pass  # silencia o log do servidorzinho


def main():
    if not CLIENT_FILE.exists():
        print(f"ERRO: nao encontrei {CLIENT_FILE.name}.")
        print('Crie o arquivo com: {"client_key": "...", "client_secret": "..."}')
        return

    cred = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    client_key = cred["client_key"]
    client_secret = cred["client_secret"]

    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode({
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    })
    url = f"{AUTH_URL}?{query}"

    print("Abrindo o navegador para autorizar o TikTok...")
    print("Se nao abrir, cole esta URL no navegador:\n")
    print(url, "\n")
    webbrowser.open(url)

    # Sobe um servidorzinho local so para capturar o ?code= do redirect
    servidor = HTTPServer(("localhost", 8080), Handler)
    print("Aguardando autorizacao em http://localhost:8080/callback ...")
    while _codigo_recebido["code"] is None:
        servidor.handle_request()

    if _codigo_recebido["state"] != state:
        print("ERRO: state nao confere (possivel ataque CSRF). Abortando.")
        return

    code = _codigo_recebido["code"]
    print("Codigo recebido. Trocando por token...")

    resp = requests.post(TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    dados = resp.json()
    if "access_token" not in dados:
        print("ERRO ao obter token:", json.dumps(dados, indent=2, ensure_ascii=False))
        return

    # carimba quando expira (epoch em segundos)
    agora = int(time.time())
    dados["_obtido_em"] = agora
    dados["_expira_em"] = agora + int(dados.get("expires_in", 0))

    TOKEN_FILE.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    print(f"\nOK! Token salvo em {TOKEN_FILE.name}.")
    print("Agora suba o conteudo desse arquivo no GitHub Secret TIKTOK_TOKEN_JSON")
    print("e o tiktok_client.json no Secret TIKTOK_CLIENT_JSON.")


if __name__ == "__main__":
    main()
