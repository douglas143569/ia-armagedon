# minhaIA — Requisitos do Projeto

> IA local, própria, rodando em casa, com modelos abertos que eu possa entender e modificar.
> Documento levantado em 2026-08-25, pra retomar o setup de casa.

## Identidade

- **Nome**: Ayran
- **Gênero/voz**: masculino
- **Dono/usuário**: Gabriel (uso pessoal exclusivo)

## Objetivo geral

Ter uma IA pessoal que:
- Roda 100% local (sem depender de assinatura/API paga, uso ilimitado)
- Usa modelos abertos, que eu possa inspecionar e adaptar
- Integra com meus próprios projetos de código
- Eventualmente reconhece minha voz e executa comandos
- Eventualmente gera imagem e vídeo
- Serve também como forma de aprender como IA funciona de verdade, do zero

## Arquitetura: um só ponto de entrada, vários modelos por trás

Eu (Gabriel) só converso com o **Ayran**, num lugar só (chat/hub — Fase 2.5). Por trás, um roteador (Fase 7) decide qual modelo especializado usar pra cada pedido, sem eu precisar escolher manualmente:

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

- Computador de casa: **CPU apenas, sem GPU dedicada**
- Implicações:
  - Texto/chat: viável, boa velocidade com modelos de 3B-8B
  - Imagem: viável mas lenta (minutos por imagem)
  - Vídeo: praticamente inviável sem GPU
- Upgrade futuro considerado: GPU usada (ex: RTX 3060 12GB) e/ou aluguel de GPU por hora (RunPod/Vast.ai) para tarefas pesadas pontuais (vídeo, fine-tuning)

## Fases do projeto

### Fase 1 — Assistente de texto local (base de tudo)
- [ ] Instalar Ollama
- [ ] Baixar modelo de uso geral (ex: `Qwen3` ou `Phi-4-mini-instruct`, 3B-8B — atualizado em ago/2026, ver "Descobertas recentes") para tarefas do dia a dia / dev
- [ ] Baixar modelo "uncensored" para escrita criativa (ex: `dolphin-llama3`)
- [ ] Testar ambos via terminal (`ollama run`)
- [ ] Instalar Open WebUI (interface de chat local, tipo ChatGPT) por cima do Ollama

### Fase 2 — Customização (deixar a IA "minha")
- [ ] Criar Modelfile próprio (system prompt definindo o Ayran como assistente masculino, personalidade, parâmetros) em cima do modelo base
- [ ] Montar RAG — dar acesso aos meus próprios documentos/notas/projetos como contexto
- [ ] Montar tool calling / agentes — conectar a IA a funções/scripts reais (rodar comandos, consultar meus projetos, etc.), no mesmo padrão de agentes tipo Claude Code
  - [ ] Ferramenta de histórico de trabalho: consultar `git log` de um projeto por período (ex: "o que eu fiz ontem no projeto X") — precisa de um mapeamento nome do projeto → caminho da pasta
  - [ ] Ferramenta de resumo de redes sociais: Instagram, Facebook, LinkedIn (+ outra a confirmar) via API oficial de cada plataforma — **somente leitura/resumo**, sem publicar ou responder automaticamente

### Fase 2.5 — Interface gráfica personalizada (hub central do computador)
- [ ] Decidir stack de empacotamento: **Tauri** (recomendado — leve, frontend em HTML/CSS/JS) ou Electron (100% JS, mais pesado)
- [ ] Frontend de chat consumindo a API local do Ollama diretamente (HTTP)
- [ ] Painel de status: voz ativa, automação residencial, últimas ações do Ayran
- [ ] Ícone na bandeja do sistema + atalho de teclado global pra abrir
- [ ] Iniciar junto com o Windows (autostart)
- [ ] Extensão do VS Code — Ayran dentro do editor (TypeScript, API de extensões do VS Code)
  - [ ] Painel lateral de chat (Webview), reaproveitando a UI do hub central
  - [ ] Acesso ao contexto do editor (arquivo aberto, seleção, workspace)
  - [ ] Comandos customizados na paleta (ex: "Ayran: explicar", "Ayran: corrigir")
  - [ ] Edição de arquivo direto pelo Ayran
  - [ ] Uso local/privado, sem necessidade de publicar na Marketplace

### Fase 3 — Assistente de voz ("Jarvis" caseiro)
- [ ] Wake word (ex: `openWakeWord`) — detecção de palavra de ativação
- [ ] STT — Speech to Text (Whisper local) — transcrever minha fala
- [ ] Ligar transcrição → LLM local com tool calling (Fase 2)
- [ ] TTS — Text to Speech (ex: Kokoro-82M — líder em eficiência em 2026, ou Piper como alternativa) — resposta falada, com voz masculina em português (opcional)
- [ ] Domótica/automação residencial — comandos de voz controlando dispositivos reais
  - [ ] Instalar Home Assistant (hub open-source, local, integra com a maioria das marcas)
  - [ ] Adquirir dispositivos inteligentes (tomadas/lâmpadas — Tuya/Smart Life ou Zigbee)
  - [ ] Criar tools que conectam o LLM ao Home Assistant (ex: `ligar_luz(comodo)`, `criar_rotina(nome)`)
  - [ ] Rotina exemplo: "olá [nome], deixa o escritório pronto" → dispara várias ações de uma vez (luz, música, etc.)

### Fase 4 — Geração de imagem
- [ ] Avaliar necessidade de GPU (CPU vai ser lento)
- [ ] Instalar ComfyUI
- [ ] Baixar modelo aberto (Stable Diffusion / SDXL / Flux)
- [ ] Testar geração local

### Fase 5 — Geração de vídeo
- [ ] Decidir caminho: comprar GPU vs. alugar GPU na nuvem por hora
- [ ] Avaliar modelos abertos disponíveis no momento (CogVideoX, HunyuanVideo, LTX-Video, ou o que for atual)

### Fase 6.5 — Modo híbrido (opcional): escalar para Claude quando necessário
- [ ] Ferramenta `perguntar_claude(pergunta)` — chama a API da Anthropic para tarefas complexas demais pro modelo local
- [ ] Para tarefas de código/projeto pesadas, considerar disparar uma sessão de Claude Code via linha de comando como ferramenta do Ayran
- [ ] **Trade-off**: quebra parcialmente o "ilimitado e grátis" — API é paga por uso (tokens). Usar só como escalonamento pontual, não como padrão

### Fase 6 — Fine-tuning (aprendizado avançado)
- [ ] Aprender base de Python + Hugging Face `transformers`
- [ ] Fazer um fine-tuning leve (LoRA/QLoRA) com dados próprios, num modelo pequeno
- [ ] (Opcional, longo prazo) Estudar arquitetura Transformer a fundo (paper "Attention Is All You Need", série do Andrej Karpathy construindo um GPT do zero)
- [ ] Ciclo de melhoria contínua do Ayran (não é aprendizado em tempo real — o modelo não muda durante a conversa; é um processo deliberado e periódico):
  - [ ] Feedback 👍/👎 nas respostas, virando dataset de correções
  - [ ] Rodar novo fine-tuning (LoRA) periodicamente incorporando esse feedback
  - [ ] Revisar/trocar o modelo base conforme saem versões melhores (ver "Descobertas recentes" abaixo)

### Fase 7 — Técnicas avançadas para maximizar a inteligência
- [ ] Modelo de raciocínio (reasoning model) para tarefas complexas — ex: DeepSeek-R1 destilado ou QwQ — "pensa" passo a passo antes de responder, mais preciso em lógica/matemática/código (mais lento, mas não exige mais memória)
- [ ] RAG avançado com banco vetorial (embeddings) — ex: ChromaDB ou Qdrant, local — busca semântica de verdade, não só palavra-chave
- [ ] Memória de longo prazo — Ayran lembra fatos/preferências/histórico entre sessões, mesmo princípio da memória do Claude
- [ ] Roteamento de modelos — modelo pequeno/rápido para perguntas simples, modelo de raciocínio (ou escalar pro Claude, Fase 6.5) só quando a tarefa for complexa
- [ ] Orquestração multi-agente — modelos/instâncias especializadas colaborando (planeja / executa / revisa) em vez de um modelo genérico fazendo tudo
- [ ] Adotar MCP (Model Context Protocol) como padrão de ferramentas — protocolo aberto para conectar a IA a ferramentas/dados de forma padronizada, em vez de solução caseira

## Descobertas recentes (pesquisado em 2026-08-25)

- **BitNet / quantização 1-bit (Microsoft)** — pesos reduzidos a 3 valores possíveis (-1, 0, 1), permite rodar modelos bem maiores em CPU puro com bem menos RAM. Modelo `Bonsai 8B` (abr/2026) roda em ~1GB. **É a tecnologia mais relevante pra minha situação (CPU sem GPU) — acompanhar de perto.**
- **Phi-4-mini-instruct** (Microsoft, 3.8B, ~4GB RAM, contexto de 128K) e **Qwen3.5-0.8B** (multimodal, Apache 2.0) — novas opções pequenas e fortes pra CPU, substituem a recomendação antiga de Qwen2.5/Llama 3.2
- **Qwen3** — família que virou o padrão geral pra rodar localmente (1.7B a 235B, licença livre)
- **Kokoro-82M** — novo líder em eficiência entre TTS locais, boa opção pra Fase 3 além do Piper
- **NVIDIA Parakeet TDT** e **Silero VAD v5** — alternativas ao Whisper para transcrição/detecção de voz
- **MCP spec 2026-07-28** — protocolo migrou de stateful pra stateless, facilitando escalar agentes
- Topo absoluto do mercado aberto hoje: **Kimi K3** (2.8T parâmetros) e **GLM-5.2** — grandes demais pro meu hardware atual, relevantes só se usar cloud rental no futuro

## Stack técnica resumida

| Componente | Ferramenta |
|---|---|
| Runtime de modelo de texto | Ollama |
| Interface de chat (rápida, genérica) | Open WebUI |
| Interface personalizada (hub central) | Tauri (frontend HTML/CSS/JS) |
| Modelo geral | Qwen2.5 / Llama 3.2 (3B–8B) |
| Modelo uncensored/criativo | Dolphin (`dolphin-llama3`) |
| STT (voz → texto) | Whisper (local) |
| TTS (texto → voz) | Piper |
| Wake word | openWakeWord |
| Automação residencial | Home Assistant |
| Redes sociais (leitura/resumo) | APIs oficiais (Meta Graph API p/ Instagram e Facebook, LinkedIn API) + outra a definir |
| Geração de imagem | ComfyUI + Stable Diffusion/SDXL/Flux |
| Geração de vídeo | A definir na Fase 5 (depende de GPU disponível na época) |
| Fine-tuning | Hugging Face `transformers` + LoRA/QLoRA |

## Notas e responsabilidades

- Modelos "uncensored" (Dolphin e similares) não recusam pedidos — inclui liberdade criativa legítima, mas também remove proteções contra conteúdo genuinamente prejudicial. Responsabilidade de uso é minha, não do modelo.
- Nenhum peso de modelo (arquivos `.gguf`, `.safetensors`, etc.) deve ir pro git — são arquivos de vários GB, baixados sob demanda por cada ferramenta (Ollama, ComfyUI). Ver `.gitignore`.

## Referência: conceitos aprendidos até aqui

- Como um LLM funciona (tokens, pesos, transformer/atenção, pré-treino → instruction tuning → RLHF)
- Como modelos de imagem/vídeo funcionam (difusão: remover ruído gradualmente guiado por texto)
- Camadas de "adaptar" uma IA pronta: prompt → RAG → tool calling/agentes → fine-tuning (LoRA) → re-treino do zero (inviável para indivíduo)
- Diferença entre treino (caro, feito uma vez pelo laboratório) e inferência (rodar o modelo pronto, barato — é o que fazemos localmente)
