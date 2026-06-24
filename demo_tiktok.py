# -*- coding: utf-8 -*-
"""
Painel web de DEMONSTRACAO da integracao com o TikTok.

Serve apenas para gravar o video de auditoria (mostra Login Kit + Content Posting API
e os escopos user.info.basic / video.upload / video.publish em acao).

COMO RODAR:
  1. Tenha o tiktok_client.json com client_key/client_secret do SANDBOX.
  2. pip install flask requests
  3. python demo_tiktok.py
  4. Abra http://localhost:5000 no navegador e siga os botoes.

Fluxo demonstrado na tela:
  [Conectar com TikTok]  -> OAuth (Login Kit) -> autoriza -> volta conectado
  Mostra a conta conectada (user.info.basic via creator_info)
  [Publicar video]       -> upload do MP4 (video.upload) + publicacao (video.publish)
"""

import os
import json
import time
from pathlib import Path

import requests
from flask import Flask, request, redirect, render_template_string

BASE = Path(__file__).resolve().parent
CLIENT_FILE = BASE / "tiktok_client.json"
TOKEN_FILE = BASE / "tiktok_token.json"
PASTA_VIDEOS = BASE / "videos"

REDIRECT_URI = "https://viniciusgflores.github.io/youtuber-shorts/callback.html"
SCOPES = "user.info.basic,video.publish,video.upload"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

app = Flask(__name__)

PAGINA = """
<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Tudo é Curioso — Publicador TikTok</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:680px;
      margin:40px auto;padding:0 20px;line-height:1.6;color:#161823}
 h1{font-size:1.6rem}
 .btn{display:inline-block;padding:14px 22px;border:0;border-radius:10px;font-size:1.05rem;
      cursor:pointer;text-decoration:none;color:#fff;background:#FE2C55}
 .btn.dark{background:#161823}
 .card{border:1px solid #eee;border-radius:12px;padding:20px;margin:18px 0;background:#fafafa}
 .ok{color:#2E7D32;font-weight:bold}.err{color:#C62828;font-weight:bold}
 .muted{color:#666;font-size:.9rem}
 select{padding:10px;font-size:1rem;border-radius:8px;border:1px solid #ccc;width:100%}
 pre{background:#f2f2f2;padding:12px;border-radius:8px;white-space:pre-wrap;font-size:.85rem}
</style></head><body>
<h1>🔎 Tudo é Curioso — Publicador automático no TikTok</h1>
<p class=muted>Painel da integração oficial (Login Kit + Content Posting API).</p>

{% if not conectado %}
  <div class=card>
    <p>Para publicar, conecte a conta do canal <b>@tudoecuriosovideos</b>.</p>
    <a class=btn href="/login">Conectar com TikTok</a>
  </div>
{% else %}
  <div class=card>
    <p class=ok>✅ Conta conectada</p>
    <p><b>Apelido do criador:</b> {{ creator.get('creator_nickname','(n/d)') }}</p>
    <p class=muted>Escopo usado: <code>user.info.basic</code> (via creator_info)</p>
  </div>

  <div class=card>
    <form method=post action="/publish">
      <p><b>Publicar um vídeo</b> (escopos <code>video.upload</code> + <code>video.publish</code>):</p>
      {% if videos %}
        <select name=video>
          {% for v in videos %}<option value="{{v}}">{{v}}</option>{% endfor %}
        </select>
        <p class=muted>Privacidade: {{ privacidade }}</p>
        <br><button class=btn type=submit>Enviar e publicar no TikTok</button>
      {% else %}
        <p class=err>Nenhum vídeo na pasta videos/. Gere um Short primeiro.</p>
      {% endif %}
    </form>
  </div>
{% endif %}

{% if resultado %}<div class=card><b>Resultado:</b><pre>{{ resultado }}</pre></div>{% endif %}
</body></html>
"""


def carregar_cred():
    return json.loads(CLIENT_FILE.read_text(encoding="utf-8"))


def carregar_token():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    return None


def salvar_token(t):
    TOKEN_FILE.write_text(json.dumps(t, indent=2), encoding="utf-8")


def listar_videos():
    if not PASTA_VIDEOS.exists():
        return []
    return sorted(p.name for p in PASTA_VIDEOS.iterdir()
                  if p.suffix.lower() in {".mp4", ".mov"})


def creator_info(token):
    r = requests.post(CREATOR_INFO_URL,
                      headers={"Authorization": f"Bearer {token['access_token']}"})
    return r.json().get("data", {})


def escolher_privacidade(info):
    ops = info.get("privacy_level_options", [])
    if "PUBLIC_TO_EVERYONE" in ops:
        return "PUBLIC_TO_EVERYONE"
    return "SELF_ONLY" if "SELF_ONLY" in ops else (ops[0] if ops else "SELF_ONLY")


@app.route("/")
def home():
    token = carregar_token()
    ctx = {"conectado": False, "videos": listar_videos(), "resultado": None}
    if token:
        info = creator_info(token)
        ctx.update(conectado=True, creator=info,
                   privacidade=escolher_privacidade(info))
    return render_template_string(PAGINA, **ctx)


@app.route("/login")
def login():
    cred = carregar_cred()
    from urllib.parse import urlencode
    q = urlencode({"client_key": cred["client_key"], "scope": SCOPES,
                   "response_type": "code", "redirect_uri": REDIRECT_URI,
                   "state": "demo"})
    return redirect(f"{AUTH_URL}?{q}")


@app.route("/token")
def token():
    code = request.args.get("code", "").split("*")[0]
    cred = carregar_cred()
    r = requests.post(TOKEN_URL, data={
        "client_key": cred["client_key"], "client_secret": cred["client_secret"],
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    d = r.json()
    if "access_token" in d:
        agora = int(time.time())
        d["_obtido_em"] = agora
        d["_expira_em"] = agora + int(d.get("expires_in", 0))
        salvar_token(d)
    return redirect("/")


@app.route("/publish", methods=["POST"])
def publish():
    token = carregar_token()
    video = PASTA_VIDEOS / request.form["video"]
    info = creator_info(token)
    priv = escolher_privacidade(info)
    tamanho = video.stat().st_size
    h = {"Authorization": f"Bearer {token['access_token']}",
         "Content-Type": "application/json; charset=UTF-8"}
    body = {
        "post_info": {"title": "Curiosidade do dia 🔎 #curiosidades #voceSabia",
                      "privacy_level": priv, "disable_comment": False,
                      "disable_duet": False, "disable_stitch": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": tamanho,
                        "chunk_size": tamanho, "total_chunk_count": 1},
    }
    init = requests.post(INIT_URL, headers=h, data=json.dumps(body)).json()
    if init.get("error", {}).get("code") not in (None, "ok"):
        return render_template_string(PAGINA, conectado=True, creator=info,
                                       privacidade=priv, videos=listar_videos(),
                                       resultado="Falha no init: " + json.dumps(init["error"], ensure_ascii=False))
    publish_id = init["data"]["publish_id"]
    upload_url = init["data"]["upload_url"]
    requests.put(upload_url, headers={"Content-Type": "video/mp4",
                 "Content-Range": f"bytes 0-{tamanho-1}/{tamanho}"},
                 data=video.read_bytes())
    # acompanha
    status = "PROCESSING"
    for _ in range(20):
        time.sleep(4)
        s = requests.post(STATUS_URL, headers=h,
                          data=json.dumps({"publish_id": publish_id})).json()
        status = s.get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            break
    msg = (f"publish_id: {publish_id}\nprivacidade: {priv}\nstatus final: {status}\n"
           + ("✅ Publicado/enviado para o TikTok!" if status == "PUBLISH_COMPLETE"
              else "Veja o status acima."))
    return render_template_string(PAGINA, conectado=True, creator=info,
                                   privacidade=priv, videos=listar_videos(),
                                   resultado=msg)


if __name__ == "__main__":
    app.run(port=5000, debug=False)
