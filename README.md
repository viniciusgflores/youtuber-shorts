# 🎬 Fábrica de YouTube Shorts (faceless, 100% grátis)

Pipeline em Python que transforma um roteiro de texto em um Short vertical
pronto e publicado no YouTube — com footage real, narração de IA em português,
legendas modernas, música e chamada pra ação. Tudo local, sem ferramentas pagas.

```
roteiro (.txt)  →  python gerar_*.py  →  videos/*.mp4  →  python upload.py  →  YouTube
```

## Geradores

| Script | Estilo |
|---|---|
| `gerar_invideo.py` | Footage real (Pexels) + legendas + música + CTA (principal) |
| `gerar_dinheiro.py` | Motion graphics (contador/barra animada) |
| `gerar_short.py` | Fundo gradiente simples + legendas |
| `upload.py` | Publicação no YouTube (Data API v3 / OAuth) |

## Como usar

1. Escreva um roteiro em `roteiros_invideo/<nome>.txt`:
   ```
   titulo: <gancho de curiosidade>
   descricao: <copy de engajamento com CTA>
   hashtags: tag1, tag2, ...
   voz: Antonio
   cenas:
   [english keyword] Frase narrada da cena 1.
   [english keyword] Frase narrada da cena 2.
   ```
2. Gere: `python gerar_invideo.py`
3. Publique: `python upload.py`

### Convenções de roteiro

- **Séculos sempre em algarismos romanos** (ex.: `século XIV`, `Século XIX`),
  nunca por extenso. A legenda exibe o romano; o gerador converte para extenso
  só na narração (a voz lê "século catorze"), então áudio e legenda ficam
  corretos. Use só para século específico — "por séculos" (genérico) permanece.
- **Título e descrição diferentes da narração** — são a isca de cliques, não a
  transcrição. A narração (em `cenas:`) é o conteúdo.
- **Palavra-chave da cena em inglês e específica** (ex.: `giza pyramids egypt`).

## Setup (chaves necessárias — NÃO versionadas)

Veja o passo a passo completo em **`LEIA-ME.md`**. Em resumo, na pasta do
projeto você precisa de:

- `client_secret.json` — credencial OAuth do YouTube (Google Cloud)
- `pexels_key.txt` — chave grátis da API do Pexels (footage)
- `musica.mp3` *(opcional)* — trilha de fundo royalty-free

Instale as dependências:

```
python -m pip install edge-tts imageio-ffmpeg Pillow google-api-python-client google-auth-oauthlib google-auth-httplib2
```

## ⚠️ Segurança

`client_secret.json`, `token.json` e `pexels_key.txt` são **segredos** e estão
no `.gitignore` — nunca suba esses arquivos para o repositório.
