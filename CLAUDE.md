# minhaIA — Ayran

Projeto de IA pessoal local. Antes de qualquer ação, leia **REQUIREMENTS.md** inteiro — é a fonte de verdade do projeto (objetivo, arquitetura, fases, stack técnica, descobertas recentes).

## Contexto essencial

- **Dono**: Gabriel, uso pessoal exclusivo
- **Nome da IA**: Ayran (masculino, voz masculina)
- **Hardware**: computador de casa — confirmar RAM/armazenamento reais e atualizar a seção "Situação de hardware" do REQUIREMENTS.md se ainda não tiver sido feito
- **Arquitetura**: um só ponto de entrada (chat/hub), um roteador escolhe o modelo certo por trás (texto geral, uncensored, raciocínio, imagem, vídeo, voz, ou escala pro Claude) — ver seção "Arquitetura" no REQUIREMENTS.md

## Como continuar o trabalho

1. Seguir as fases do REQUIREMENTS.md **em ordem**, começando pela primeira ainda não concluída
2. Ao completar um item, marcar o checkbox (`- [ ]` → `- [x]`) no REQUIREMENTS.md e commitar junto com o trabalho feito
3. Se surgir um requisito novo durante a conversa, registrar no REQUIREMENTS.md antes de implementar (mesmo padrão usado até aqui)
4. Nunca commitar pesos de modelo (`.gguf`, `.safetensors`, etc.) — já cobertos no `.gitignore`

## Status atual

Levantamento de requisitos completo. Nenhuma fase de implementação iniciada ainda — próximo passo é a **Fase 1** (instalar Ollama, baixar os modelos definidos, testar via terminal, instalar Open WebUI).
