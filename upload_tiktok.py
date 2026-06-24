# -*- coding: utf-8 -*-
"""
Upload automatico de videos para o TikTok via Content Posting API (Direct Post).

Le os mesmos videos da pasta "videos/" e os metadados .txt (mesmo formato do upload.py).
NAO move os arquivos -- quem move para "enviados/" continua sendo o upload.py do YouTube,
que roda depois. Assim o mesmo MP4 vai para os dois canais.

Fluxo da API (v2):
  1. Renova o access_token se preciso (refresh_token).
  2. creator_info/query  -> descobre quais niveis de privacidade a conta permite.
  3. video/init          -> cria o post e devolve um upload_url.
  4. PUT do arquivo       -> envia os bytes do MP4.
  5. status/fetch (poll)  -> espera o TikTok processar e publicar.

OBS sobre auditoria: enquanto o app NAO foi aprovado pela ByteDance, o TikTok so
permite privacidade SELF_ONLY (so voce ve). Este script detecta isso automaticamente
pelo creator_info e cai para SELF_ONLY com um aviso. Apos a aprovacao, ele publica
em PUBLIC_TO_EVERYONE.

Segredos necessarios (na nuvem, como GitHub Secrets):
  TIKTOK_CLIENT_JSON  -> conteudo do tiktok_client.json
  TIKTOK_TOKEN_JSON   -> conteudo do tiktok_token.json (gerado pelo tiktok_login.py)
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
PASTA_VIDEOS = BASE / "videos"
ARQUIVO_LOG = BASE / "log.txt"
CLIENT_FILE = BASE / "tiktok_client.json"
TOKEN_FILE = BASE / "tiktok_token.json"

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

EXTENSOES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def log(msg):
    carimbo = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{carimbo}] [tiktok] {msg}"
    print(linha)
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def carregar_token():
    if not TOKEN_FILE.exists():
        log("ERRO: tiktok_token.json nao encontrado. Rode tiktok_login.py uma vez.")
        sys.exit(1)
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


def salvar_token(dados):
    TOKEN_FILE.write_text(json.dumps(dados, indent=2), encoding="utf-8")


def garantir_token_valido(token):
    """Renova o access_token se estiver perto de expirar (margem de 5 min)."""
    agora = int(time.time())
    if token.get("_expira_em", 0) - agora > 300:
        return token  # ainda valido

    log("Access token expirado/perto de expirar. Renovando com refresh_token...")
    cred = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    resp = requests.post(TOKEN_URL, data={
        "client_key": cred["client_key"],
        "client_secret": cred["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    novo = resp.json()
    if "access_token" not in novo:
        log("ERRO ao renovar token: " + json.dumps(novo, ensure_ascii=False))
        sys.exit(1)
    novo["_obtido_em"] = agora
    novo["_expira_em"] = agora + int(novo.get("expires_in", 0))
    salvar_token(novo)
    log("Token renovado. (Na nuvem, atualize o Secret TIKTOK_TOKEN_JSON ~1x/ano.)")
    return novo


def headers_auth(token):
    return {"Authorization": f"Bearer {token['access_token']}"}


# ---------------------------------------------------------------------------
# Metadados (mesmo formato do upload.py do YouTube)
# ---------------------------------------------------------------------------
def ler_metadados(arquivo_txt, nome_padrao):
    meta = {"titulo": nome_padrao, "descricao": "", "tags": []}
    if not arquivo_txt.exists():
        return meta
    linhas = arquivo_txt.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(linhas):
        sep = linhas[i].find(":")
        if sep != -1:
            chave = linhas[i][:sep].strip().lower()
            valor = linhas[i][sep + 1:].strip()
            if chave == "descricao":
                meta["descricao"] = "\n".join(linhas[i + 1:]).strip()
                break
            elif chave == "titulo":
                meta["titulo"] = valor
            elif chave == "tags":
                meta["tags"] = [t.strip() for t in valor.split(",") if t.strip()]
        i += 1
    return meta


def montar_legenda(meta):
    """TikTok usa um campo unico (caption). Junta titulo + hashtags das tags."""
    legenda = meta["titulo"].strip()
    hashtags = " ".join("#" + t.replace(" ", "") for t in meta["tags"][:8])
    if hashtags:
        legenda = f"{legenda}\n\n{hashtags}"
    return legenda[:2150]  # limite seguro abaixo dos 2200 do TikTok


# ---------------------------------------------------------------------------
# Publicacao
# ---------------------------------------------------------------------------
def consultar_creator_info(token):
    resp = requests.post(CREATOR_INFO_URL, headers=headers_auth(token))
    dados = resp.json()
    if dados.get("error", {}).get("code") not in (None, "ok"):
        log("AVISO creator_info: " + json.dumps(dados.get("error"), ensure_ascii=False))
    return dados.get("data", {})


def escolher_privacidade(creator_info):
    """Usa PUBLIC se a conta permitir (app auditado), senao cai para SELF_ONLY."""
    opcoes = creator_info.get("privacy_level_options", [])
    if "PUBLIC_TO_EVERYONE" in opcoes:
        return "PUBLIC_TO_EVERYONE"
    if "SELF_ONLY" in opcoes:
        log("AVISO: conta/app ainda nao permite publico. Postando como SELF_ONLY "
            "(privado). Apos a auditoria da ByteDance, vira publico automaticamente.")
        return "SELF_ONLY"
    return opcoes[0] if opcoes else "SELF_ONLY"


def publicar(token, video_path, legenda, privacidade):
    tamanho = video_path.stat().st_size

    body_init = {
        "post_info": {
            "title": legenda,
            "privacy_level": privacidade,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": tamanho,
            "chunk_size": tamanho,        # arquivo pequeno: 1 chunk so
            "total_chunk_count": 1,
        },
    }
    h = headers_auth(token)
    h["Content-Type"] = "application/json; charset=UTF-8"
    resp = requests.post(INIT_URL, headers=h, data=json.dumps(body_init))
    dados = resp.json()
    if dados.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError("Falha no init: " + json.dumps(dados["error"], ensure_ascii=False))

    publish_id = dados["data"]["publish_id"]
    upload_url = dados["data"]["upload_url"]
    log(f"  init OK. publish_id={publish_id}")

    # Envia os bytes do video
    with open(video_path, "rb") as f:
        conteudo = f.read()
    put_headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(tamanho),
        "Content-Range": f"bytes 0-{tamanho - 1}/{tamanho}",
    }
    log(f"  Enviando {tamanho/1_000_000:.1f} MB ...")
    r = requests.put(upload_url, headers=put_headers, data=conteudo)
    if r.status_code not in (200, 201, 206):
        raise RuntimeError(f"Falha no PUT do video: HTTP {r.status_code} {r.text[:300]}")

    # Acompanha o processamento
    return acompanhar_status(token, publish_id)


def acompanhar_status(token, publish_id):
    h = headers_auth(token)
    h["Content-Type"] = "application/json; charset=UTF-8"
    for _ in range(30):  # ~ ate 2,5 min
        time.sleep(5)
        resp = requests.post(STATUS_URL, headers=h,
                             data=json.dumps({"publish_id": publish_id}))
        dados = resp.json().get("data", {})
        status = dados.get("status")
        if status == "PUBLISH_COMPLETE":
            log("  OK! Publicado no TikTok.")
            return True
        if status == "FAILED":
            log("  FALHOU no TikTok: " + json.dumps(dados, ensure_ascii=False))
            return False
        log(f"  status: {status} ...")
    log("  AVISO: tempo esgotado aguardando o TikTok processar (pode concluir sozinho).")
    return False


def main():
    if not PASTA_VIDEOS.exists():
        log(f"Pasta '{PASTA_VIDEOS.name}/' nao existe. Nada a fazer.")
        return
    videos = sorted([p for p in PASTA_VIDEOS.iterdir()
                     if p.suffix.lower() in EXTENSOES_VIDEO])
    if not videos:
        log("Nenhum video em videos/. Nada a fazer.")
        return

    token = garantir_token_valido(carregar_token())
    creator = consultar_creator_info(token)
    privacidade = escolher_privacidade(creator)

    for video in videos:
        log(f"- Processando: {video.name}")
        meta = ler_metadados(video.with_suffix(".txt"), nome_padrao=video.stem)
        legenda = montar_legenda(meta)
        try:
            publicar(token, video, legenda, privacidade)
        except Exception as e:
            log(f"  ERRO em {video.name}: {e}")


if __name__ == "__main__":
    main()
