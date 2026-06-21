# -*- coding: utf-8 -*-
"""
Upload automatico de videos para o YouTube.

Como usar:
  1. Coloque os videos (.mp4, .mov, etc.) na pasta "videos/".
  2. Para cada video, crie um arquivo .txt com o MESMO nome contendo os metadados.
     Ex.: videos/meu_video.mp4  ->  videos/meu_video.txt
     (Se nao houver .txt, o video sobe como rascunho privado com o nome do arquivo.)
  3. (Opcional) Coloque uma thumbnail com o mesmo nome: videos/meu_video.jpg
  4. Rode:  python upload.py
     - Na primeira vez, abre o navegador para voce autorizar (uma unica vez).

Formato do arquivo .txt de metadados (descricao deve ser a ULTIMA chave):

    titulo: Meu titulo aqui
    tags: tag1, tag2, tag3
    privacidade: private        # private | unlisted | public
    categoria: 22               # 22 = Pessoas e Blogs, 27 = Educacao, 28 = Ciencia e Tec
    publicar_em: 2026-06-25 18:00   # opcional: agenda a publicacao (horario local)
    descricao:
    Tudo que vier daqui pra baixo
    vira a descricao do video,
    inclusive varias linhas.
"""

import os
import sys
import time
import shutil
import datetime
from pathlib import Path

import google.auth.transport.requests
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuracao de pastas
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
PASTA_VIDEOS = BASE / "videos"          # de onde os videos sao lidos
PASTA_ENVIADOS = BASE / "enviados"      # para onde vao depois de enviar
ARQUIVO_LOG = BASE / "log.txt"

CLIENT_SECRET = BASE / "client_secret.json"
TOKEN = BASE / "token.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

EXTENSOES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}
EXTENSOES_THUMB = [".jpg", ".jpeg", ".png"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def log(msg):
    carimbo = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{carimbo}] {msg}"
    print(linha)
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def autenticar():
    """Faz login (uma vez) e devolve o servico autenticado do YouTube."""
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            if os.environ.get("YT_NONINTERACTIVE"):
                log("ERRO: token.json invalido/expirado e modo nao-interativo (nuvem). "
                    "Gere um token.json novo localmente e atualize o secret TOKEN_JSON. "
                    "Dica: publique o app OAuth em 'Producao' para o refresh token nao expirar.")
                sys.exit(1)
            if not CLIENT_SECRET.exists():
                log(f"ERRO: nao encontrei {CLIENT_SECRET.name}. "
                    "Baixe a credencial OAuth do Google Cloud e coloque nesta pasta.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        log("Autenticacao salva em token.json (nao precisa logar de novo).")

    return build("youtube", "v3", credentials=creds)


def ler_metadados(arquivo_txt, nome_padrao):
    """Le o .txt de metadados. Devolve um dicionario com defaults sensatos."""
    meta = {
        "titulo": nome_padrao,
        "descricao": "",
        "tags": [],
        "privacidade": "private",
        "categoria": "22",
        "publicar_em": None,
    }
    if not arquivo_txt.exists():
        return meta

    conteudo = arquivo_txt.read_text(encoding="utf-8")
    linhas = conteudo.splitlines()

    chaves_simples = {"titulo", "tags", "privacidade", "categoria", "publicar_em"}
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        sep = linha.find(":")
        if sep != -1:
            chave = linha[:sep].strip().lower()
            valor = linha[sep + 1:].strip()
            if chave == "descricao":
                # tudo daqui pra baixo eh a descricao
                meta["descricao"] = "\n".join(linhas[i + 1:]).strip()
                break
            elif chave in chaves_simples:
                if chave == "tags":
                    meta["tags"] = [t.strip() for t in valor.split(",") if t.strip()]
                elif chave == "publicar_em":
                    meta["publicar_em"] = valor if valor else None
                else:
                    meta[chave] = valor
        i += 1

    return meta


def converter_para_utc(texto):
    """Converte 'YYYY-MM-DD HH:MM' (horario local) para RFC3339 em UTC."""
    try:
        dt = datetime.datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        log(f"AVISO: data '{texto}' invalida (use YYYY-MM-DD HH:MM). Ignorando agendamento.")
        return None
    # interpreta como horario local da maquina e converte para UTC
    dt_local = dt.astimezone()  # anexa o fuso local
    dt_utc = dt_local.astimezone(datetime.timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def encontrar_thumbnail(video_path):
    for ext in EXTENSOES_THUMB:
        cand = video_path.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def enviar_video(youtube, video_path, meta):
    body = {
        "snippet": {
            "title": meta["titulo"][:100],          # YouTube limita o titulo a 100 chars
            "description": meta["descricao"],
            "tags": meta["tags"],
            "categoryId": str(meta["categoria"]),
        },
        "status": {
            "privacyStatus": meta["privacidade"],
            "selfDeclaredMadeForKids": False,
        },
    }

    # Agendamento: exige privacidade 'private' ate a hora marcada
    if meta["publicar_em"]:
        publish_utc = converter_para_utc(meta["publicar_em"])
        if publish_utc:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = publish_utc
            log(f"  Agendado para {meta['publicar_em']} (local) -> {publish_utc} (UTC)")

    media = MediaFileUpload(str(video_path), chunksize=1024 * 1024 * 8, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log(f"  Enviando '{video_path.name}' ...")
    resposta = None
    tentativas = 0
    while resposta is None:
        try:
            status, resposta = request.next_chunk()
            if status:
                print(f"\r  Progresso: {int(status.progress() * 100)}%", end="", flush=True)
        except HttpError as e:
            tentativas += 1
            if e.resp.status in (500, 502, 503, 504) and tentativas <= 5:
                espera = 2 ** tentativas
                log(f"\n  Erro temporario ({e.resp.status}). Tentando de novo em {espera}s...")
                time.sleep(espera)
            else:
                raise
    print()  # quebra a linha do progresso
    video_id = resposta["id"]
    log(f"  OK! Video publicado/enviado. ID: {video_id}  ->  https://youtu.be/{video_id}")

    # Thumbnail (opcional)
    thumb = encontrar_thumbnail(video_path)
    if thumb:
        try:
            youtube.thumbnails().set(videoId=video_id,
                                     media_body=MediaFileUpload(str(thumb))).execute()
            log(f"  Thumbnail definida: {thumb.name}")
        except HttpError as e:
            log(f"  AVISO: nao foi possivel definir a thumbnail ({e}). "
                "(Pode exigir conta verificada por telefone.)")

    return video_id


def mover_para_enviados(video_path, txt_path, thumb_path):
    PASTA_ENVIADOS.mkdir(exist_ok=True)
    for p in [video_path, txt_path, thumb_path]:
        if p and p.exists():
            shutil.move(str(p), str(PASTA_ENVIADOS / p.name))


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main():
    PASTA_VIDEOS.mkdir(exist_ok=True)
    log("=" * 60)
    log("Iniciando rotina de upload.")

    videos = sorted([p for p in PASTA_VIDEOS.iterdir()
                     if p.suffix.lower() in EXTENSOES_VIDEO])

    if not videos:
        log(f"Nenhum video encontrado em '{PASTA_VIDEOS.name}/'. Nada a fazer.")
        return

    youtube = autenticar()
    log(f"{len(videos)} video(s) na fila.")

    enviados = 0
    for video in videos:
        log(f"- Processando: {video.name}")
        txt = video.with_suffix(".txt")
        meta = ler_metadados(txt, nome_padrao=video.stem)
        thumb = encontrar_thumbnail(video)
        try:
            enviar_video(youtube, video, meta)
            mover_para_enviados(video, txt, thumb)
            enviados += 1
        except HttpError as e:
            log(f"  FALHA no upload de {video.name}: {e}")
            if "quotaExceeded" in str(e):
                log("  >> Cota diaria da API esgotada. Tente novamente amanha.")
                break
        except Exception as e:
            log(f"  ERRO inesperado em {video.name}: {e}")

    log(f"Concluido. {enviados}/{len(videos)} enviado(s).")
    log("=" * 60)


if __name__ == "__main__":
    main()
