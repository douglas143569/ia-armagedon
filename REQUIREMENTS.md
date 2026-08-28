# ARMAGEDON — Requisitos do Projeto

> IA local, própria, rodando em casa, com modelos abertos que eu possa entender e modificar.
> Documento levantado em 2026-08-27, pra setup inicial.

## Identidade

- **Nome**: ARMAGEDON
- **Dono/usuário**: Douglas (uso pessoal exclusivo)

## Objetivo geral

Ter uma IA pessoal que:
- Roda 100% local (sem depender de assinatura/API paga, uso ilimitado)
- Usa modelos abertos, que eu possa inspecionar e adaptar
- Integra com meus próprios projetos de código
- Eventualmente reconhece minha voz e executa comandos
- Eventualmente gera imagem e vídeo
- Serve também como forma de aprender como IA funciona de verdade, do zero

## Arquitetura: um só ponto de entrada, vários modelos por trás

Eu (Douglas) só converso com o **ARMAGEDON**, num lugar só (chat/hub — Fase 2.5). Por trás, um roteador (Fase 7) decide qual modelo especializado usar pra cada pedido, sem eu precisar escolher manualmente:

| Tipo de pedido | Modelo usado |
|---|---|
| Dia a dia / código | Qwen3 ou Phi-4-mini |
| Escrita criativa sem restrição | Dolphin |
| Raciocínio complexo (lógica/matemática) | Modelo de raciocínio (DeepSeek-R1/QwQ) |
| Gerar imagem | Stable Diffusion/SDXL (Fase 4) |
| Gerar vídeo | Modelo de vídeo (Fase 5) |
| Comando de voz | Pipeline STT → um dos modelos acima |
| Tarefa complexa demais pro local | Escala pro Claude (Fase 6.5) |

## Situação de hardware (ponto de partida)

**Máquina de Douglas (lida direto do sistema em 2026-08-27)**:
- CPU: AMD Ryzen 5 2400G (APU, 4 cores / 8 threads, até 3.6 GHz)
- RAM: 16 GB físicos (2× 8 GB DDR4 @ 2667 MHz); ~14 GB utilizáveis (≈2 GB reservados para a GPU integrada)
- Armazenamento: C: 476 GB (386 livre) · D: 931 GB (690 livre) · E: 894 GB (498 livre) — espaço sobrando
- GPU: AMD Radeon RX Vega 11 **integrada** (compartilha a RAM do sistema, ~2 GB alocados). Sem CUDA; ROCm não suporta essa iGPU no Windows → **inferência roda em CPU**
- SO: Windows 10 Pro (build 19045)

**Implicações**:
- Texto/chat: viável com modelos 3B–8B quantizados (Q4). Um modelo 7B ocupa ~5 GB de RAM — dá pra rodar um de cada vez com folga; carregar dois grandes ao mesmo tempo ou passar de ~13B fica apertado nos 14 GB
- Imagem: só CPU — funciona, mas **~7 min por imagem 512×512** (20 steps), medido nesta máquina
- Vídeo: inviável localmente para uso real (cada clipe = dezenas de frames = dezenas de minutos). Vai precisar de GPU alugada
- Upgrade que muda o jogo: GPU discreta NVIDIA (CUDA) — ex: RTX 3060 12 GB usada — e/ou aluguel de GPU por hora (RunPod/Vast.ai) para vídeo e fine-tuning
- Modelos 1-bit / BitNet (ver "Descobertas recentes") são especialmente relevantes aqui pela RAM limitada e ausência de GPU

## Fases do projeto

### Fase 1 — Assistente de texto local (base de tudo)
- [x] Instalar Ollama (v0.33.1 instalado em 2026-08-27)
- [x] Baixar modelo de uso geral (`Qwen2.5 7B` — 4.7GB, atualizado em ago/2026) para tarefas do dia a dia / dev
- [x] Baixar modelo "uncensored" para escrita criativa (`dolphin-llama3` — 4.7GB)
  - **Upgrade 2026-08-28**: `Modelfile-livre` → modelo `armagedon-livre` com system prompt sem restrições (nunca recusa, sem sermão, sem disclaimer). É o alvo criativo do roteador. Opção "🔓 ARMAGEDON Livre" no dropdown.
  - Base do `armagedon-livre`: **`huihui_ai/dolphin3-abliterated`** (Dolphin 3.0 uncensored + abliteration = recusa removida dos pesos). `hermes3:8b` e `dolphin-llama3` ficam de reserva. (Merge real via mergekit foi descartado — inviável nos 14 GB de RAM.)
- [x] Testar ambos via terminal (`ollama run`) — ✅ Qwen2.5 respondendo em português com latência aceitável
- [x] Instalar Open WebUI (interface de chat local, tipo ChatGPT) por cima do Ollama
  - Instalado via npm (131 packages)
  - Disponível em http://localhost:8000
  - Integrado com Ollama local
  - Script de inicialização criado: `start-webui.ps1`

### Fase 2 — Customização (deixar a IA "minha")
- [x] Criar Modelfile próprio (system prompt definindo o ARMAGEDON como assistente pessoal, personalidade, parâmetros) em cima do modelo Qwen2.5 7B
  - System prompt: identidade, objetivo, estilo (amigável/profissional), especialidades em código/dados/criatividade
  - Parâmetros otimizados: temperature 0.7, top_p 0.9, repeat_penalty 1.1
  - ✅ Testado e respondendo com personalidade customizada em português
- [x] Montar RAG — dar acesso aos meus próprios documentos/notas/projetos como contexto
  - Serviço `armagedon_brain.py` (porta 5002): pasta `documentos/` (.txt/.md/.pdf) → chunks de ~1000 chars → embeddings via `nomic-embed-text` (no Ollama) → ChromaDB em `brain_data/` (fallback numpy se o Chroma falhar)
  - O hub (`server.js`) chama `/augment` antes de mandar pro Ollama e injeta os trechos + memória no prompt; devolve as fontes no header `X-Rag-Sources`
  - Interface: botão "🧠 Conhecimento" (reindexar, ver docs, toggle "usar nas respostas"); a resposta mostra "📄 Fontes: ..."
  - Testado 2026-08-28: pergunta sobre um doc → modelo respondeu citando o arquivo correto
- [ ] Montar tool calling / agentes — conectar a IA a funções/scripts reais (rodar comandos, consultar meus projetos, etc.), no mesmo padrão de agentes tipo Claude Code
  - [ ] Ferramenta de histórico de trabalho: consultar `git log` de um projeto por período (ex: "o que eu fiz ontem no projeto X") — precisa de um mapeamento nome do projeto → caminho da pasta
  - [ ] Ferramenta de resumo de redes sociais: Instagram, Facebook, LinkedIn (+ outra a confirmar) via API oficial de cada plataforma — **somente leitura/resumo**, sem publicar ou responder automaticamente

### Fase 2.5 — Interface gráfica personalizada (hub central do computador)
- [x] **Launcher único + supervisor** (`armagedon.ps1` / `ARMAGEDON.bat`) — sobe os 5 serviços na ordem, espera cada health check, abre o navegador e reinicia sozinho o que cair (checa a cada 15s). Flags `-Stop`, `-WithVideo`, `-Once`, `-NoBrowser`. Status ao vivo no painel lateral (`GET /api/status`). Logs em `logs/`. Ver `INICIAR.md`. Falta: entrada no Agendador de Tarefas p/ subir no logon (instruções no `INICIAR.md`).
- [ ] Decidir stack de empacotamento: **Tauri** (recomendado — leve, frontend em HTML/CSS/JS) ou Electron (100% JS, mais pesado)
- [ ] Frontend de chat consumindo a API local do Ollama diretamente (HTTP)
- [ ] Painel de status: voz ativa, automação residencial, últimas ações do ARMAGEDON
- [ ] Ícone na bandeja do sistema + atalho de teclado global pra abrir
- [ ] Iniciar junto com o Windows (autostart)
- [ ] Extensão do VS Code — ARMAGEDON dentro do editor (TypeScript, API de extensões do VS Code)
  - [ ] Painel lateral de chat (Webview), reaproveitando a UI do hub central
  - [ ] Acesso ao contexto do editor (arquivo aberto, seleção, workspace)
  - [ ] Comandos customizados na paleta (ex: "ARMAGEDON: explicar", "ARMAGEDON: corrigir")
  - [ ] Edição de arquivo direto pelo Ayran
  - [ ] Uso local/privado, sem necessidade de publicar na Marketplace

### Fase 3 — Assistente de voz ("Jarvis" caseiro)
- [ ] Wake word (ex: `openWakeWord`) — detecção de palavra de ativação
- [ ] STT — Speech to Text (Whisper local) — transcrever minha fala
- [ ] Ligar transcrição → LLM local com tool calling (Fase 2)
- [ ] TTS — Text to Speech (ex: Kokoro-82M — líder em eficiência em 2026, ou Piper como alternativa) — resposta falada em português (opcional)
- [ ] Domótica/automação residencial — comandos de voz controlando dispositivos reais
  - [ ] Instalar Home Assistant (hub open-source, local, integra com a maioria das marcas)
  - [ ] Adquirir dispositivos inteligentes (tomadas/lâmpadas — Tuya/Smart Life ou Zigbee)
  - [ ] Criar tools que conectam o LLM ao Home Assistant (ex: `ligar_luz(comodo)`, `criar_rotina(nome)`)
  - [ ] Rotina exemplo: "olá Douglas, deixa o escritório pronto" → dispara várias ações de uma vez (luz, música, etc.)

### Fase 4 — Geração de imagem
- [x] Avaliar necessidade de GPU (CPU vai ser lento) — confirmado: roda em CPU, mas ~7 min por imagem 512×512 (20 steps) no Ryzen 5 2400G. Aceitável para uso pontual; GPU discreta (CUDA) seria upgrade desejável.
- [ ] Instalar ComfyUI — não usado; implementação atual usa `diffusers` direto (`image_generator_final.py`, servidor HTTP na porta 5000)
- [x] Baixar modelo aberto (Stable Diffusion / SDXL / Flux) — Stable Diffusion v1.5 via `diffusers` (repo `runwayml/stable-diffusion-v1-5`, hoje redireciona p/ `stable-diffusion-v1-5/stable-diffusion-v1-5`), cache em `~/.cache/huggingface`
- [x] Testar geração local — ✅ imagem gerada e salva em `images_generated/` (2026-08-27)
- [x] Modo rápido **SD-Turbo** (`stabilityai/sd-turbo`) como opção "⚡ Turbo" na interface — 4 steps, guidance 0.0. Medido: **39 s por imagem** vs ~7 min do SD-1.5 (~10× mais rápido). Só um modelo fica na RAM por vez (troca recarrega, ~1-2 min). Vale para imagem e vídeo.
- Geração agora é **serializada** (1 job por vez / fila) e cada job tem **cancelamento** no meio da geração; painel "⚙️ Processos" na interface lista e cancela jobs. Endpoints novos nos geradores: `/jobs`, `/cancel/<id>`, `/status/<id>`; no hub: `/api/processes`, `/api/cancel`.

**Setup instalado em 2026-08-27** (venv `venv_images`, Python 3.12 — torch não tem wheel p/ o Python 3.14 do sistema):
`torch 2.13.0+cpu`, `torchvision 0.28.0+cpu`, `diffusers 0.40.0`, `transformers 5.16.1`, `accelerate 1.14.0`, `flask 3.1.3`, `pillow 12.3.0`, `safetensors 0.8.0`.
Node.js 24.19 e Ollama 0.33.1 instalados via winget. Modelos Ollama: `qwen2.5:7b`, `dolphin-llama3`, `armagedon` (do Modelfile) — todos testados OK.

### Fase 5 — Geração de vídeo
- [ ] Decidir caminho: comprar GPU vs. alugar GPU na nuvem por hora
- [ ] Avaliar modelos abertos disponíveis no momento (CogVideoX, HunyuanVideo, LTX-Video, ou o que for atual)

**Solução provisória em CPU (`video_generator_flask.py`, porta 5001)** — GIF, não vídeo real. 3 modos, medidos nesta máquina:
| Modo | Como funciona | Tempo (2s @ 8fps, Turbo, 384px) |
|---|---|---|
| `camera` (Ken Burns) | 1 imagem SD-Turbo + zoom/pan por frame (recorte, ~grátis) | **~40 s** (16 frames) |
| `evolucao` (img2img) | frame 1 completo, seguintes por img2img `strength 0.45` a partir do anterior | ~30 s + ~25 s/frame |
| `frames` | N imagens txt2img independentes (conteúdo varia, não é animação) | lento: ~gen completa × N |
Parâmetros expostos na interface: modo, resolução (512/384), steps (auto/1–30), Turbo. Para vídeo de verdade continua sendo GPU alugada.

### Fase 6.5 — Modo híbrido (opcional): escalar para Claude quando necessário
- [ ] Ferramenta `perguntar_claude(pergunta)` — chama a API da Anthropic para tarefas complexas demais pro modelo local
- [ ] Para tarefas de código/projeto pesadas, considerar disparar uma sessão de Claude Code via linha de comando como ferramenta do Ayran
- [ ] **Trade-off**: quebra parcialmente o "ilimitado e grátis" — API é paga por uso (tokens). Usar só como escalonamento pontual, não como padrão

### Fase 6 — Fine-tuning (aprendizado avançado)
Pipeline montado 2026-08-28 — ver **`FASE-6-FINETUNING.md`**. Pasta `finetune/`.
- [ ] Aprender base de Python + Hugging Face `transformers` (contínuo)
- [x] Fazer um fine-tuning leve (LoRA/QLoRA) com dados próprios, num modelo pequeno
  - `finetune/train_lora.py` — LoRA via `peft`+`trl`, roda em CPU (modelo 0.5–1.5B) ou GPU alugada (7B+). Instalado no venv: `peft 0.20`, `datasets 5.0`, `trl 1.12`.
  - `finetune/build_dataset.py` — `brain_data/feedback.jsonl` → `finetune/dataset.jsonl` (formato chat)
  - `finetune/to_ollama.py` — merge do LoRA + conversão GGUF (via llama.cpp) + `ollama create armagedon-tuned`
- [ ] (Opcional, longo prazo) Estudar arquitetura Transformer a fundo (paper "Attention Is All You Need", série do Andrej Karpathy construindo um GPT do zero)
- [~] Ciclo de melhoria contínua (não é tempo real — processo deliberado e periódico):
  - [x] Feedback 👍/👎 nas respostas virando dataset — botões na interface sob cada resposta; no 👎 abre campo "como deveria ter respondido"; salva em `brain_data/feedback.jsonl` via `POST /api/brain/feedback`. Painel 🧠 Conhecimento mostra a contagem.
  - [ ] Rodar o fine-tuning periodicamente incorporando o feedback (manual, quando tiver ~30+ exemplos)
  - [ ] Revisar/trocar o modelo base conforme saem versões melhores (ver "Descobertas recentes" abaixo)

### Fase 7 — Técnicas avançadas para maximizar a inteligência
- [x] Modelo de raciocínio (reasoning model) para tarefas complexas — `deepseek-r1:7b` no Ollama (2026-08-28). O Ollama 0.33 separa o raciocínio no campo `thinking` da resposta (não vem `<think>` inline); a interface mostra num "🧠 raciocínio" recolhível. Medido: pergunta de matemática ~1 min, problema de várias etapas ~5 min na CPU — por isso só via roteador
- [x] RAG avançado com banco vetorial (embeddings) — ChromaDB local + `nomic-embed-text`, busca por similaridade de cosseno (`armagedon_brain.py`). Falta: re-ranking, chunking mais esperto, ingestão incremental (hoje reindexa tudo)
- [x] **Busca na web / informação em tempo real** — `armagedon_brain.py`: DuckDuckGo (`ddgs`, sem API key) + extração de texto das páginas (`trafilatura`), injetado no prompt igual ao RAG. Dispara por heurística (`precisa_web()` — "hoje", "cotação", "última versão", "notícia", anos ≥ 2026...) ou pelo seletor 🌐 auto/sempre/nunca no painel. Header `X-Web-Used`; a resposta mostra "🌐 Web:" com links. Testado 2026-08-28 (cotação do dólar → respondeu citando a URL).
- [x] Memória de longo prazo — SQLite `brain_data/memoria.db` (tabela `fatos`: categoria + texto), injetada no prompt a cada pergunta. CRUD pela interface. Endpoint `/memory/extract` usa o LLM pra extrair fatos duráveis de um texto. Falta: extração automática ao fim de cada conversa
- [x] Roteamento de modelos — `route_model()` em `armagedon_brain.py` (heurística por regex, sem custo): matemática/lógica → `deepseek-r1:7b`, escrita criativa → `dolphin-llama3`, resto → `armagedon`. O hub aplica quando o modelo escolhido na interface é "🤖 Automático" e devolve `X-Router-Model`/`X-Router-Reason`; a interface mostra "🧭 roteado para ...". Dropdown ainda permite forçar um modelo. Falta: classificador via LLM p/ casos ambíguos, rotear "gerar imagem/vídeo" (depende de tool calling)
- [ ] Orquestração multi-agente — modelos/instâncias especializadas colaborando (planeja / executa / revisa) em vez de um modelo genérico fazendo tudo
- [ ] Adotar MCP (Model Context Protocol) como padrão de ferramentas — protocolo aberto para conectar a IA a ferramentas/dados de forma padronizada, em vez de solução caseira

## Descobertas recentes (pesquisado em 2026-08-25)

- **BitNet / quantização 1-bit (Microsoft)** — pesos reduzidos a 3 valores possíveis (-1, 0, 1), permite rodar modelos bem maiores em CPU puro com bem menos RAM. Modelo `Bonsai 8B` (abr/2026) roda em ~1GB. **É a tecnologia mais relevante pra situação de hardware (CPU sem GPU) — acompanhar de perto.**
- **Phi-4-mini-instruct** (Microsoft, 3.8B, ~4GB RAM, contexto de 128K) e **Qwen3.5-0.8B** (multimodal, Apache 2.0) — novas opções pequenas e fortes pra CPU, substituem a recomendação antiga de Qwen2.5/Llama 3.2
- **Qwen3** — família que virou o padrão geral pra rodar localmente (1.7B a 235B, licença livre)
- **Kokoro-82M** — novo líder em eficiência entre TTS locais, boa opção pra Fase 3 além do Piper
- **NVIDIA Parakeet TDT** e **Silero VAD v5** — alternativas ao Whisper para transcrição/detecção de voz
- **MCP spec 2026-07-28** — protocolo migrou de stateful pra stateless, facilitando escalar agentes
- Topo absoluto do mercado aberto hoje: **Kimi K3** (2.8T parâmetros) e **GLM-5.2** — grandes demais pro hardware atual de Douglas, relevantes só se usar cloud rental no futuro

## Stack técnica resumida

| Componente | Ferramenta |
|---|---|
| Runtime de modelo de texto | Ollama |
| Interface de chat (rápida, genérica) | Open WebUI |
| Interface personalizada (hub central) | Tauri (frontend HTML/CSS/JS) |
| Modelo geral | Qwen2.5 / Llama 3.2 (3B–8B) |
| Modelo uncensored/criativo | `armagedon-livre` (Hermes 3 8B + system prompt sem filtro); `dolphin-llama3` de reserva |
| STT (voz → texto) | Whisper (local) |
| TTS (texto → voz) | Piper |
| Wake word | openWakeWord |
| Automação residencial | Home Assistant |
| Redes sociais (leitura/resumo) | APIs oficiais (Meta Graph API p/ Instagram e Facebook, LinkedIn API) + outra a definir |
| Geração de imagem | ComfyUI + Stable Diffusion/SDXL/Flux |
| Geração de vídeo | A definir na Fase 5 (depende de GPU disponível na época) |
| Fine-tuning | Hugging Face `transformers` + LoRA/QLoRA |

## Notas e responsabilidades

- Modelos "uncensored" (Dolphin e similares) não recusam pedidos — inclui liberdade criativa legítima, mas também remove proteções contra conteúdo genuinamente prejudicial. Responsabilidade de uso é de Douglas, não do modelo.
- Nenhum peso de modelo (arquivos `.gguf`, `.safetensors`, etc.) deve ir pro git — são arquivos de vários GB, baixados sob demanda por cada ferramenta (Ollama, ComfyUI). Ver `.gitignore`.

## Referência: conceitos aprendidos até aqui

- Como um LLM funciona (tokens, pesos, transformer/atenção, pré-treino → instruction tuning → RLHF)
- Como modelos de imagem/vídeo funcionam (difusão: remover ruído gradualmente guiado por texto)
- Camadas de "adaptar" uma IA pronta: prompt → RAG → tool calling/agentes → fine-tuning (LoRA) → re-treino do zero (inviável para indivíduo)
- Diferença entre treino (caro, feito uma vez pelo laboratório) e inferência (rodar o modelo pronto, barato — é o que fazemos localmente)
