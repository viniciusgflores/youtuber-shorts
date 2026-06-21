# -*- coding: utf-8 -*-
"""
Gerador de Short de DINHEIRO com motion graphics (desafio do centavo).

Desenha quadro a quadro (Pillow): contador de dias, valor em R$ explodindo
e uma barra de crescimento. Junta com narracao (edge-tts) e legendas (ffmpeg).

Uso:
    python gerar_dinheiro.py

Saida: videos/desafio-centavo.mp4 + .txt de metadados (pronto p/ upload.py).
"""

import asyncio
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
VIDEOS = BASE / "videos"
# pasta de trabalho FORA do OneDrive (evita lock de sincronizacao)
TMP = Path(tempfile.gettempdir()) / "yt_dinheiro"
FRAMES = TMP / "frames"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H = 1080, 1920
FPS = 30
VOZ = "pt-BR-AntonioNeural"

# ---- Conteudo (roteiro narrado, sincroniza com a animacao) ----
TITULO = "O centavo que vira 5 milhões em 30 dias"
TAGS = ["dinheiro", "juros compostos", "financas", "investimento", "rico", "voce sabia"]
ROTEIRO = [
    "1 centavo. 30 dias. Presta atenção nisso.",
    "Imagina dobrar 1 centavo todos os dias.",
    "No dia 10, são só 5 reais.",
    "No dia 20, já são 5 mil reais.",
    "Mas no dia 30?",
    "Mais de 5 milhões de reais.",
    "Isso é o poder dos juros compostos.",
    "A maioria das pessoas nunca vai entender isso.",
    "Comenta aí: em que dia você teria desistido?",
]

# ---- Cores ----
FUNDO_TOPO = (8, 30, 22)
FUNDO_BASE = (4, 14, 11)
VERDE = (46, 213, 115)
VERDE_ESC = (24, 110, 70)
DOURADO = (255, 209, 102)
BRANCO = (245, 245, 245)
CINZA = (140, 150, 145)

# ---- Fontes ----
def fonte(caminho, tam):
    return ImageFont.truetype(caminho, tam)

F_BLACK = "C:/Windows/Fonts/ariblk.ttf"
F_BOLD = "C:/Windows/Fonts/arialbd.ttf"
F_REG = "C:/Windows/Fonts/arial.ttf"


def brl(valor):
    """Formata em R$ no padrao brasileiro: 5.368.709,12"""
    inteiro, dec = f"{valor:,.2f}".split(".")
    inteiro = inteiro.replace(",", ".")
    return f"R$ {inteiro},{dec}"


def fundo_base():
    # gradiente vertical rapido: cria 1px de largura e estica
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        t = y / H
        px[0, y] = (
            int(FUNDO_TOPO[0] * (1 - t) + FUNDO_BASE[0] * t),
            int(FUNDO_TOPO[1] * (1 - t) + FUNDO_BASE[1] * t),
            int(FUNDO_TOPO[2] * (1 - t) + FUNDO_BASE[2] * t),
        )
    return col.resize((W, H))


def centralizar(draw, texto, font, y, cor):
    bbox = draw.textbbox((0, 0), texto, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, y), texto, font=font, fill=cor)
    return bbox[3] - bbox[1]


def desenhar_frame(base, dia, valor, brilho):
    img = base.copy()
    d = ImageDraw.Draw(img)

    # Cabecalho
    centralizar(d, "DESAFIO DO CENTAVO", fonte(F_BOLD, 46), 190, VERDE)

    # Contador de dias
    centralizar(d, f"DIA {dia:02d} / 30", fonte(F_BOLD, 64), 275, CINZA)

    # Barra de progresso (escala log para caber de 0,01 a 5,3 milhoes)
    bx0, bx1 = 150, W - 150
    by1 = 1010
    by0 = 460
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=24, outline=VERDE_ESC, width=4)
    lo, hi = math.log10(0.01), math.log10(5_368_709.12)
    frac = (math.log10(max(valor, 0.01)) - lo) / (hi - lo)
    frac = max(0.0, min(1.0, frac))
    fill_bottom = by1 - 6
    altura_max = (by1 - by0) - 12
    fill_top = fill_bottom - altura_max * frac
    cor_barra = DOURADO if dia >= 30 else VERDE
    if fill_bottom - fill_top >= 4:
        raio = int(min(18, (fill_bottom - fill_top) / 2))
        d.rounded_rectangle([bx0 + 6, fill_top, bx1 - 6, fill_bottom],
                            radius=raio, fill=cor_barra)

    # Valor gigante (com leve pulso/brilho no clique do dia)
    tam = int(116 + 16 * brilho)
    cor_valor = DOURADO if dia >= 30 else BRANCO
    centralizar(d, brl(valor), fonte(F_BLACK, tam), 1120, cor_valor)

    return img


async def gerar_audio_srt(mp3, srt):
    texto = "\n".join(ROTEIRO)
    c = edge_tts.Communicate(texto, VOZ)
    sm = edge_tts.SubMaker()
    with open(mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                sm.feed(ch)
    srt.write_text(sm.get_srt(), encoding="utf-8")


def duracao_audio(mp3):
    r = subprocess.run([FFMPEG, "-i", str(mp3)], stderr=subprocess.PIPE)
    txt = r.stderr.decode("utf-8", "ignore")
    for linha in txt.splitlines():
        if "Duration" in linha:
            hms = linha.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 30.0


def renderizar_frames(dur):
    FRAMES.mkdir(parents=True, exist_ok=True)
    base = fundo_base()
    total = int(dur * FPS)
    # fase A: dia 1->30 nos primeiros 65%; fase B: segura no climax
    fim_subida = 0.65
    ultimo_dia_tick = 0
    tick_frame = 0
    for i in range(total):
        t = i / total
        if t < fim_subida:
            prog = t / fim_subida
            dia_f = 1 + 29 * prog
        else:
            dia_f = 30
        dia = int(round(dia_f))
        valor = 0.01 * (2 ** (dia_f - 1))
        # brilho/pulso a cada virada de dia
        if dia != ultimo_dia_tick:
            ultimo_dia_tick = dia
            tick_frame = i
        brilho = max(0.0, 1 - (i - tick_frame) / 6)
        frame = desenhar_frame(base, min(dia, 30), valor, brilho)
        frame.save(FRAMES / f"f{i:05d}.png")
        if i % 60 == 0:
            print(f"  frames: {i}/{total}")
    print(f"  frames: {total}/{total} (ok)")
    return total


def montar(mp3, srt, saida):
    estilo = ("FontName=Arial,FontSize=14,Bold=1,PrimaryColour=&H00FFFFFF,"
              "BackColour=&HA0000000,BorderStyle=3,Outline=5,Shadow=0,"
              "Alignment=2,MarginV=60")
    cmd = [
        FFMPEG, "-y",
        "-framerate", str(FPS), "-i", "frames/f%05d.png",
        "-i", str(mp3),
        "-filter_complex", f"[0:v]subtitles=mov.srt:force_style='{estilo}'[v]",
        "-map", "[v]", "-map", "1:a",
        "-shortest", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(saida),
    ]
    subprocess.run(cmd, cwd=str(TMP), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def escrever_meta(saida_txt):
    desc = "\n".join(ROTEIRO) + "\n\n#Shorts " + " ".join("#" + t.replace(" ", "") for t in TAGS)
    conteudo = (
        f"titulo: {TITULO} #Shorts\n"
        f"tags: {', '.join(TAGS + ['shorts'])}\n"
        f"privacidade: public\n"
        f"categoria: 24\n"
        f"descricao:\n{desc}\n"
    )
    saida_txt.write_text(conteudo, encoding="utf-8")


def main():
    VIDEOS.mkdir(exist_ok=True)
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    mp3 = TMP / "mov.mp3"
    srt = TMP / "mov.srt"
    saida = VIDEOS / "desafio-centavo.mp4"

    print("1/4 Gerando narração e legendas...")
    asyncio.run(gerar_audio_srt(mp3, srt))
    dur = duracao_audio(mp3)
    print(f"    duração do áudio: {dur:.1f}s")

    print("2/4 Renderizando frames da animação...")
    renderizar_frames(dur)

    print("3/4 Montando vídeo (animação + voz + legendas)...")
    montar(mp3, srt, saida)

    print("4/4 Gerando metadados...")
    escrever_meta(VIDEOS / "desafio-centavo.txt")

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\nPronto -> videos/{saida.name}")


if __name__ == "__main__":
    main()
