# Modelos de vídeo — qual preset usar por GPU

| preset | modelo | qualidade | VRAM confortável | GPU típica p/ alugar | clipe ~5s (aprox.) |
|---|---|---|---|---|---|
| `ltx` | LTX-Video | média, **muito rápido** | 12–24 GB | RTX 4090 (~$0,3–0,5/h) | ~20–60 s |
| `cogvideox` | CogVideoX-5b-I2V | média-alta | 16–24 GB | RTX 4090 / L4 | ~2–5 min |
| `wan` | Wan 2.1 I2V 14B 720p | alta | 40–48 GB | A100 40/80, L40S (~$1–1,9/h) | ~3–6 min |
| `hunyuan` | HunyuanVideo I2V | topo aberto | 48–80 GB | A100 80, H100 (~$2–3/h) | ~4–8 min |

## Como escolher
- **Rascunhos / testar prompt**: `ltx` num 4090 barato.
- **Resultado final bom**: `wan` (A100 80) ou `hunyuan` (H100). H100 custa mais/h mas rende
  mais minutos de vídeo por real — menos tempo pagando GPU parada.

## Trocar de preset
Edite `preset:` no `config.yaml`. Se a GPU já tinha outro modelo baixado, rode de novo:
`python -c "from pipeline import preload; preload()"`

## Custo estimado — vídeo de 1 min
- 1 min = ~12 clipes de 5 s.
- `ltx` no 4090: ~10–20 min de geração → **~US$ 0,10–0,30** de GPU.
- `hunyuan` no H100: ~1–2 h → **~US$ 3–8** de GPU.
- Isso é só a geração; some iteração/reprocessamento.

## Ajustes finos (config.yaml → presets)
- `steps` menor = mais rápido, menos detalhe. `guidance` maior = segue mais o prompt (pode "fritar").
- `width`/`height` — cair de 720p pra 480p reduz MUITO o tempo e a VRAM.
- `per_clip_seconds` — 5 é seguro; passar de 6–8 costuma degradar a coerência.
- `interpolate: true` sobe o fps final sem gerar mais frames pesados (via ffmpeg).

## Limites honestos
- Encadear clipes acumula "deriva" (a cena vai mudando). Até ~1 min fica ok com prompt estável;
  além disso o ideal é gerar por cena e cortar num editor.
- Áudio não sai do modelo: adicione trilha/locução com `audio: file:trilha.mp3` ou no editor.
