# -*- coding: utf-8 -*-
"""
Gera Shorts faceless (narracao + fundo animado + legendas) 100% de graca.

Fluxo:
  1. Escreva um roteiro em roteiros/ (use 'exemplo-curiosidade.txt' como modelo).
  2. Rode:  python gerar_short.py
  3. Os Shorts prontos (.mp4 vertical 1080x1920) caem em videos/,
     junto com um .txt de metadados pronto para o upload.py.
  4. Os roteiros usados vao para roteiros/feitos/.

Depois e so rodar 'python upload.py' para enviar ao YouTube.

Formato do roteiro (.txt):

    titulo: Texto que vai como titulo do video no YouTube
    voz: Antonio          # Antonio (masc) | Francisca (fem) | Thalita
    tags: tag1, tag2      # opcional
    roteiro:
    Primeira frase narrada.
    Segunda frase narrada.
    (cada linha vira narracao + legenda na tela)
"""

import asyncio
import subprocess
import shutil
from pathlib import Path

import edge_tts
import imageio_ffmpeg

BASE = Path(__file__).resolve().parent
PASTA_ROTEIROS = BASE / "roteiros"
PASTA_FEITOS = PASTA_ROTEIROS / "feitos"
PASTA_VIDEOS = BASE / "videos"
TMP = BASE / "_tmp"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

VOZES = {
    "antonio": "pt-BR-AntonioNeural",
    "francisca": "pt-BR-FranciscaNeural",
    "thalita": "pt-BR-ThalitaMultilingualNeural",
}

# Paletas de fundo (gradiente animado) que giram a cada video, por variedade.
PALETAS = [
    ("0x0f2027", "0x203a43", "0x2c5364"),  # azul petroleo
    ("0x1a2a6c", "0x2a5298", "0x1a2a6c"),  # azul royal
    ("0x232526", "0x414345", "0x232526"),  # grafite
    ("0x3a1c71", "0x462a6e", "0x5a2a6e"),  # roxo
    ("0x134e5e", "0x1d6a5e", "0x2a8a6e"),  # verde escuro
    ("0x42275a", "0x734b6d", "0x42275a"),  # vinho/roxo
]

# Estilo das legendas (formato ASS do filtro subtitles do ffmpeg)
# Estilo "caixa": texto branco em caixa preta semitransparente (limpo e legivel)
ESTILO_LEGENDA = (
    "FontName=Arial,FontSize=16,Bold=1,"
    "PrimaryColour=&H00FFFFFF,BackColour=&HA0000000,BorderStyle=3,"
    "Outline=6,Shadow=0,Alignment=2,MarginV=140"
)


def parse_roteiro(arquivo):
    meta = {"titulo": arquivo.stem, "voz": "antonio", "tags": [], "roteiro": ""}
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        sep = linha.find(":")
        if sep != -1:
            chave = linha[:sep].strip().lower()
            valor = linha[sep + 1:].strip()
            if chave == "roteiro":
                meta["roteiro"] = "\n".join(
                    l.strip() for l in linhas[i + 1:] if l.strip()
                )
                break
            elif chave == "titulo":
                meta["titulo"] = valor
            elif chave == "voz":
                meta["voz"] = valor.lower()
            elif chave == "tags":
                meta["tags"] = [t.strip() for t in valor.split(",") if t.strip()]
        i += 1
    return meta


async def gerar_audio_e_legendas(texto, voz_short, mp3_path, srt_path):
    voice = VOZES.get(voz_short, VOZES["antonio"])
    communicate = edge_tts.Communicate(texto, voice)
    submaker = edge_tts.SubMaker()
    with open(mp3_path, "wb") as f:
        async for ch in communicate.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(ch)
    srt_path.write_text(submaker.get_srt(), encoding="utf-8")


def renderizar(mp3_path, srt_path, paleta, saida):
    c0, c1, c2 = paleta
    fundo = (
        f"gradients=s=1080x1920:c0={c0}:c1={c1}:c2={c2}"
        f":x0=0:y0=0:x1=1080:y1=1920:duration=600:speed=0.012"
    )
    # rodamos com cwd = TMP e usamos so o nome do .srt (evita problema de
    # caminho com ':' do Windows dentro do filtro subtitles)
    filtro = f"[0:v]subtitles={srt_path.name}:force_style='{ESTILO_LEGENDA}'[v]"
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", fundo,
        "-i", str(mp3_path),
        "-filter_complex", filtro,
        "-map", "[v]", "-map", "1:a",
        "-shortest", "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(saida),
    ]
    subprocess.run(cmd, cwd=str(TMP), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def escrever_metadados_upload(meta, destino_txt):
    tags = list(meta["tags"]) + ["shorts"]
    descricao = meta["roteiro"] + "\n\n#Shorts " + " ".join(
        "#" + t.replace(" ", "") for t in meta["tags"]
    )
    conteudo = (
        f"titulo: {meta['titulo']} #Shorts\n"
        f"tags: {', '.join(tags)}\n"
        f"privacidade: public\n"
        f"categoria: 24\n"
        f"descricao:\n{descricao}\n"
    )
    destino_txt.write_text(conteudo, encoding="utf-8")


def main():
    PASTA_VIDEOS.mkdir(exist_ok=True)
    PASTA_FEITOS.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(exist_ok=True)

    roteiros = sorted(p for p in PASTA_ROTEIROS.glob("*.txt"))
    if not roteiros:
        print("Nenhum roteiro em 'roteiros/'. Crie um .txt e rode de novo.")
        return

    print(f"{len(roteiros)} roteiro(s) na fila.\n")
    for idx, arquivo in enumerate(roteiros):
        meta = parse_roteiro(arquivo)
        if not meta["roteiro"]:
            print(f"- PULANDO {arquivo.name}: sem texto em 'roteiro:'")
            continue

        nome = arquivo.stem
        print(f"- Gerando: {nome}  (voz: {meta['voz']})")
        mp3 = TMP / f"{nome}.mp3"
        srt = TMP / f"{nome}.srt"
        saida = PASTA_VIDEOS / f"{nome}.mp4"

        try:
            asyncio.run(gerar_audio_e_legendas(meta["roteiro"], meta["voz"], mp3, srt))
            paleta = PALETAS[idx % len(PALETAS)]
            renderizar(mp3, srt, paleta, saida)
            escrever_metadados_upload(meta, PASTA_VIDEOS / f"{nome}.txt")
            shutil.move(str(arquivo), str(PASTA_FEITOS / arquivo.name))
            print(f"  OK -> videos/{saida.name}")
        except subprocess.CalledProcessError as e:
            erro = e.stderr.decode("utf-8", "ignore")[-500:] if e.stderr else str(e)
            print(f"  FALHA no ffmpeg: {erro}")
        except Exception as e:
            print(f"  ERRO: {e}")
        finally:
            mp3.unlink(missing_ok=True)
            srt.unlink(missing_ok=True)

    print("\nConcluido. Confira a pasta 'videos/'. Depois rode: python upload.py")


if __name__ == "__main__":
    main()
