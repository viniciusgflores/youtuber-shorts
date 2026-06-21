# Fábrica de Shorts para o YouTube (100% grátis)

Dois scripts que, juntos, criam e publicam Shorts faceless (narração + fundo
animado + legendas) sem nenhum custo.

```
roteiros/*.txt  →  python gerar_short.py  →  videos/*.mp4  →  python upload.py  →  YouTube
```

---

## PASSO 1 — Escrever o roteiro

Crie um arquivo `.txt` dentro de `roteiros/` (copie `exemplo-curiosidade.txt`):

```
titulo: Você sabia disso sobre o Brasil?
voz: Antonio          # Antonio (masc) | Francisca (fem) | Thalita
tags: curiosidades, brasil, você sabia
roteiro:
Primeira frase narrada (vira fala + legenda).
Segunda frase.
Segue o canal para mais!
```

Pode colocar quantos roteiros quiser na pasta — o script gera todos de uma vez.

## PASSO 2 — Gerar os vídeos

```
python gerar_short.py
```

- Cria a narração em português (voz da Microsoft, grátis, sem chave).
- Monta o vídeo vertical 1080x1920 com fundo animado e legendas em caixa.
- Salva o `.mp4` + um `.txt` de metadados em `videos/`.
- Move o roteiro usado para `roteiros/feitos/`.

## PASSO 3 — Enviar ao YouTube

```
python upload.py
```

- Na **primeira vez**, abre o navegador para você autorizar a conta (só uma vez).
- Sobe cada vídeo como **rascunho privado** (você revisa antes de publicar).
- Move o que foi enviado para `enviados/` e registra tudo em `log.txt`.

> Para publicar direto ou agendar, edite o `.txt` do vídeo em `videos/`:
> mude `privacidade: private` para `public`, ou adicione
> `publicar_em: 2026-06-25 18:00` para agendar.

---

## Observações importantes

- **Tudo grátis:** voz (edge-tts), vídeo (ffmpeg) e upload (YouTube Data API) não custam nada.
- **Cota de upload:** ~6 vídeos por dia (limite gratuito da API). O script avisa se passar.
- **Monetização:** o YouTube desmonetiza conteúdo de IA repetitivo/em massa.
  Use roteiros próprios e com curadoria — qualidade e tema definido importam.
- **Segurança:** `client_secret.json` e `token.json` são suas chaves. Não compartilhe.

## Arquivos do projeto

- `gerar_short.py` ... cria os Shorts a partir dos roteiros
- `upload.py` ........ envia os vídeos ao YouTube
- `roteiros/` ........ seus roteiros (.txt) entram aqui
- `roteiros/feitos/` . roteiros já usados
- `videos/` .......... vídeos prontos esperando upload
- `enviados/` ........ vídeos já publicados
- `client_secret.json` credencial do Google (já configurada)
- `log.txt` .......... registro dos uploads
