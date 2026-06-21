# -*- coding: utf-8 -*-
"""
Gerador de Shorts estilo InVideo (footage real + voz + legendas + musica).

100% gratis: footage do Pexels (chave gratis), voz edge-tts, montagem ffmpeg.

PRE-REQUISITO: coloque sua chave do Pexels no arquivo 'pexels_key.txt'
(pegue em https://www.pexels.com/api/ - gratis).

Uso:
    python gerar_invideo.py                 # processa roteiros de roteiros_invideo/
    python gerar_invideo.py meu_roteiro.txt # processa um roteiro especifico

Formato do roteiro (cada cena = [palavra-chave em INGLÊS] + narração em PT):

    titulo: Como ficar rico com pouco dinheiro
    voz: Antonio          # Antonio | Francisca | Thalita
    tags: dinheiro, investimento
    cenas:
    [money cash] Você sabia que dá pra ficar rico começando com pouco?
    [stock market chart] O segredo são os juros compostos.
    [happy person success] Quem começa cedo, ganha muito mais no fim.

A [palavra-chave] busca o vídeo de fundo no Pexels (use termos em inglês,
que tem muito mais resultados). O resto da linha é narrado e vira legenda.

Música de fundo (opcional): coloque um arquivo 'musica.mp3' na pasta do projeto.
"""

import re
import sys
import json
import asyncio
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.parse
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image

BASE = Path(__file__).resolve().parent
PASTA_ROTEIROS = BASE / "roteiros_invideo"
PASTA_FEITOS = PASTA_ROTEIROS / "feitos"
VIDEOS = BASE / "videos"
CHAVE_FILE = BASE / "pexels_key.txt"
MUSICA = BASE / "musica.mp3"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H, FPS = 1080, 1920, 30
VOZES = {
    "antonio": "pt-BR-AntonioNeural",
    "francisca": "pt-BR-FranciscaNeural",
    "thalita": "pt-BR-ThalitaMultilingualNeural",
}
# Legenda moderna: texto limpo, contorno fino (sem aparencia de caixa/fundo),
# apoiado no scrim para legibilidade. Parte central inferior (MarginV menor = mais baixo).
TAMANHO_LEGENDA = 15   # ajuste aqui o tamanho da letra
ESTILO_LEGENDA = (
    f"FontName=Arial Black,FontSize={TAMANHO_LEGENDA},Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
    "BorderStyle=1,Outline=2,Shadow=2,Alignment=2,MarginV=70"
)
# privacidade dos uploads: "public" | "unlisted" | "private"
PRIVACIDADE = "public"
# Chamada pra acao (CTA): cena final fixa (fala+legenda) + linha na descricao
CTA_FALA = "Gostou? Deixa o like, comenta e compartilha. Ajuda demais o canal."
CTA_KEYWORD = "social media smartphone"
CTA_DESCRICAO = ("👍 Curtiu? Curte, compartilha e comenta — é assim que a "
                 "informação se propaga e chega em mais gente.")
# cor de destaque (verde) para a barra de progresso
COR_PROGRESSO = "0x2ED573"
# tamanho do bloco de legenda (palavras por vez) - ritmo rapido moderno
PALAVRAS_POR_BLOCO = 3


def carregar_chave():
    if not CHAVE_FILE.exists():
        print(f"ERRO: crie o arquivo '{CHAVE_FILE.name}' com sua chave do Pexels.")
        print("Pegue gratis em: https://www.pexels.com/api/")
        sys.exit(1)
    chave = CHAVE_FILE.read_text(encoding="utf-8").strip()
    if not chave:
        print(f"ERRO: '{CHAVE_FILE.name}' está vazio.")
        sys.exit(1)
    return chave


def parse_roteiro(arquivo):
    meta = {"titulo": arquivo.stem, "voz": "antonio",
            "descricao": "", "hashtags": [], "cenas": []}
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        low = linha.lower()
        if low.startswith("titulo:"):
            meta["titulo"] = linha.split(":", 1)[1].strip()
        elif low.startswith("voz:"):
            meta["voz"] = linha.split(":", 1)[1].strip().lower()
        elif low.startswith("descricao:"):
            meta["descricao"] = linha.split(":", 1)[1].strip()
        elif low.startswith("hashtags:"):
            raw = linha.split(":", 1)[1]
            meta["hashtags"] = [h.strip().lstrip("#")
                                for h in re.split(r"[,\s]+", raw) if h.strip().lstrip("#")]
        elif low.startswith("tags:"):  # legado: vira hashtags se nao houver
            if not meta["hashtags"]:
                meta["hashtags"] = [t.strip() for t in linha.split(":", 1)[1].split(",") if t.strip()]
        elif low.startswith("cenas:"):
            for l in linhas[i + 1:]:
                l = l.strip()
                if not l:
                    continue
                if l.startswith("[") and "]" in l:
                    kw = l[1:l.index("]")].strip()
                    texto = l[l.index("]") + 1:].strip()
                    meta["cenas"].append({"kw": kw, "texto": texto})
            break
        i += 1
    return meta


def buscar_video_pexels(chave, query):
    url = ("https://api.pexels.com/videos/search?"
           + urllib.parse.urlencode({"query": query, "orientation": "portrait",
                                     "per_page": 10, "size": "medium"}))
    req = urllib.request.Request(
        url, headers={"Authorization": chave, "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        dados = json.load(r)
    videos = dados.get("videos", [])
    if not videos:
        return None
    # escolhe o primeiro video com um arquivo vertical de boa resolucao
    for v in videos:
        arquivos = sorted(v["video_files"],
                          key=lambda f: (f.get("height") or 0), reverse=True)
        for f in arquivos:
            h = f.get("height") or 0
            w = f.get("width") or 0
            if h >= w and h <= 2200:  # vertical, sem exagero de resolucao
                return f["link"]
        if arquivos:
            return arquivos[0]["link"]
    return None


def baixar(url, destino):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duracao(arquivo):
    r = subprocess.run([FFMPEG, "-i", str(arquivo)], stderr=subprocess.PIPE)
    txt = r.stderr.decode("utf-8", "ignore")
    for linha in txt.splitlines():
        if "Duration" in linha:
            hms = linha.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


async def tts(texto, voz_short, mp3):
    voice = VOZES.get(voz_short, VOZES["antonio"])
    c = edge_tts.Communicate(texto, voice)
    with open(mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])


def seg_para_srt(t):
    ms = int((t - int(t)) * 1000)
    s = int(t) % 60
    m = (int(t) // 60) % 60
    h = int(t) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def blocos_de(texto, n=PALAVRAS_POR_BLOCO):
    """Divide em frases e depois em blocos curtos (sem cruzar fim de frase)."""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    blocos = []
    for fr in frases:
        palavras = fr.split()
        for i in range(0, len(palavras), n):
            blocos.append(" ".join(palavras[i:i + n]))
    return blocos or [texto]


# Séculos: o roteiro escreve em NUMERO ROMANO (a legenda mostra "SÉCULO XIV").
# Para a narração (TTS), convertemos para extenso senão a voz lê as letras erradas.
SECULOS_FALADOS = {
    "I": "primeiro", "II": "segundo", "III": "terceiro", "IV": "quarto",
    "V": "quinto", "VI": "sexto", "VII": "sétimo", "VIII": "oitavo",
    "IX": "nono", "X": "décimo", "XI": "onze", "XII": "doze", "XIII": "treze",
    "XIV": "catorze", "XV": "quinze", "XVI": "dezesseis", "XVII": "dezessete",
    "XVIII": "dezoito", "XIX": "dezenove", "XX": "vinte", "XXI": "vinte e um",
}


def falar_seculos(texto):
    """Converte 'século XIV' -> 'século catorze' APENAS para a narração (TTS).
    As legendas continuam mostrando o número romano (texto original)."""
    def repl(m):
        return f"{m.group(1)} {SECULOS_FALADOS.get(m.group(2).upper(), m.group(2))}"
    return re.sub(r"\b(s[ée]culos?)\s+([IVXLC]+)\b", repl, texto, flags=re.IGNORECASE)


def gerar_scrim(path):
    """Degrade transparente->escuro na metade inferior (legibilidade + profundidade)."""
    col = Image.new("RGBA", (1, H), (0, 0, 0, 0))
    px = col.load()
    inicio = int(H * 0.42)
    for y in range(inicio, H):
        t = (y - inicio) / (H - inicio)
        px[0, y] = (0, 0, 0, int(210 * (t ** 1.4)))
    col.resize((W, H)).save(path)


def processar_roteiro(arquivo, chave, tmp):
    meta = parse_roteiro(arquivo)
    if not meta["cenas"]:
        print(f"  PULANDO {arquivo.name}: nenhuma cena encontrada (use 'cenas:')")
        return None

    # cena final fixa de CTA (curtir/compartilhar/comentar)
    meta["cenas"].append({"kw": CTA_KEYWORD, "texto": CTA_FALA})

    nome = arquivo.stem
    cenas_mp4, audios, srt_cues = [], [], []
    t_acum = 0.0

    for idx, cena in enumerate(meta["cenas"]):
        print(f"  Cena {idx+1}/{len(meta['cenas'])}: [{cena['kw']}]")
        # 1) narracao
        a_mp3 = tmp / f"a{idx}.mp3"
        asyncio.run(tts(falar_seculos(cena["texto"]), meta["voz"], a_mp3))
        dur = duracao(a_mp3) + 0.3  # pequena folga
        audios.append(a_mp3)

        # 2) footage
        link = buscar_video_pexels(chave, cena["kw"])
        clip_out = tmp / f"c{idx}.mp4"
        if link:
            raw = tmp / f"raw{idx}.mp4"
            baixar(link, raw)
            run([FFMPEG, "-y", "-stream_loop", "-1", "-i", str(raw),
                 "-t", f"{dur:.3f}", "-an",
                 "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                        f"crop={W}:{H},setsar=1,fps={FPS}",
                 "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 str(clip_out)])
        else:
            print(f"    (sem footage p/ '{cena['kw']}', usando fundo escuro)")
            run([FFMPEG, "-y", "-f", "lavfi",
                 "-i", f"color=c=0x101418:s={W}x{H}:d={dur:.3f}:r={FPS}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_out)])
        cenas_mp4.append(clip_out)

        # 3) legendas desta cena em blocos curtos (ritmo rapido)
        blocos = blocos_de(cena["texto"])
        passo = dur / len(blocos)
        for j, bloco in enumerate(blocos):
            ini = t_acum + j * passo
            fim = t_acum + (j + 1) * passo
            srt_cues.append((ini, fim, bloco.upper()))
        t_acum += dur

    # concat dos clipes de video
    lista_v = tmp / "videos.txt"
    lista_v.write_text("".join(f"file '{c.name}'\n" for c in cenas_mp4), encoding="utf-8")
    video_all = tmp / "video_all.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "videos.txt",
         "-c", "copy", str(video_all)], cwd=str(tmp))

    # concat dos audios de narracao
    lista_a = tmp / "audios.txt"
    lista_a.write_text("".join(f"file '{a.name}'\n" for a in audios), encoding="utf-8")
    narr = tmp / "narr.mp3"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "audios.txt",
         "-c", "copy", str(narr)], cwd=str(tmp))

    # legendas (blocos curtos, numeradas)
    srt = tmp / "leg.srt"
    linhas_srt = []
    for n, (ini, fim, txt) in enumerate(srt_cues, 1):
        linhas_srt.append(f"{n}\n{seg_para_srt(ini)} --> {seg_para_srt(fim)}\n{txt}\n")
    srt.write_text("\n".join(linhas_srt), encoding="utf-8")

    # scrim (degrade escuro inferior, para legibilidade + profundidade)
    scrim = tmp / "scrim.png"
    gerar_scrim(scrim)

    # filtro de video: scrim + barra de progresso animada no topo + legendas
    TOT = f"{t_acum:.3f}"
    vf = (f"[0:v][2:v]overlay=0:0:shortest=1[bg];"
          f"[bg]drawbox=x=0:y=0:w=iw:h=12:color=white@0.22:t=fill,"
          f"drawbox=x=0:y=0:w=iw*t/{TOT}:h=12:color={COR_PROGRESSO}:t=fill[pb];"
          f"[pb]subtitles=leg.srt:force_style='{ESTILO_LEGENDA}'[v]")

    # montagem final (video + scrim + barra + narracao + musica opcional + legendas)
    saida = VIDEOS / f"{nome}.mp4"
    if MUSICA.exists():
        cmd = [FFMPEG, "-y", "-i", str(video_all), "-i", "narr.mp3",
               "-loop", "1", "-i", "scrim.png", "-stream_loop", "-1", "-i", str(MUSICA),
               "-filter_complex",
               vf + ";[3:a]volume=0.12[m];[1:a][m]amix=inputs=2:duration=first[a]",
               "-map", "[v]", "-map", "[a]", "-shortest",
               "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", str(saida)]
    else:
        cmd = [FFMPEG, "-y", "-i", str(video_all), "-i", "narr.mp3",
               "-loop", "1", "-i", "scrim.png",
               "-filter_complex", vf,
               "-map", "[v]", "-map", "1:a", "-shortest",
               "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", str(saida)]
    run(cmd, cwd=str(tmp))

    # metadados p/ upload: titulo + descricao PROPRIA (diferente da fala) + hashtags
    escrever_meta(meta, VIDEOS / f"{nome}.txt")
    return saida


def escrever_meta(meta, destino):
    hashtags = meta["hashtags"] or ["shorts"]
    linha_hash = "#Shorts " + " ".join("#" + h.replace(" ", "") for h in hashtags)
    blocos = [b for b in (meta["descricao"].strip(), CTA_DESCRICAO) if b]
    corpo = "\n\n".join(blocos)
    desc = (corpo + "\n\n" if corpo else "") + linha_hash
    tags_yt = ", ".join(dict.fromkeys(hashtags + ["shorts"]))  # sem duplicar
    destino.write_text(
        f"titulo: {meta['titulo']}\n"
        f"tags: {tags_yt}\n"
        f"privacidade: {PRIVACIDADE}\ncategoria: 24\n"
        f"descricao:\n{desc}\n", encoding="utf-8")


def main():
    chave = carregar_chave()
    VIDEOS.mkdir(exist_ok=True)
    PASTA_FEITOS.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        roteiros = [PASTA_ROTEIROS / sys.argv[1]]
    else:
        roteiros = sorted(PASTA_ROTEIROS.glob("*.txt"))

    if not roteiros or not roteiros[0].exists():
        print(f"Nenhum roteiro em '{PASTA_ROTEIROS.name}/'. Crie um .txt e rode de novo.")
        return

    for arquivo in roteiros:
        print(f"- {arquivo.name}")
        tmp = Path(tempfile.mkdtemp(prefix="yt_invideo_"))
        try:
            saida = processar_roteiro(arquivo, chave, tmp)
            if saida:
                shutil.move(str(arquivo), str(PASTA_FEITOS / arquivo.name))
                print(f"  OK -> videos/{saida.name}")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", "ignore")[-400:] if e.stderr else str(e)
            print(f"  FALHA ffmpeg: {err}")
        except Exception as e:
            print(f"  ERRO: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\nConcluído. Confira 'videos/' e rode: python upload.py")


if __name__ == "__main__":
    main()
