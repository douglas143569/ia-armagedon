# Como ligar o ARMAGEDON

## Uso normal
**Duplo-clique em `ARMAGEDON.bat`.**

Ele sobe tudo na ordem (Ollama → Cérebro → Hub → Gerador de imagens), espera cada
serviço ficar pronto, abre o navegador em http://localhost:3000 e **fica vigiando**:
se algum serviço cair, reinicia sozinho em ~15 s. Deixe essa janela aberta enquanto usa.
Para desligar: feche a janela e rode `ARMAGEDON.bat -Stop` (ou `armagedon.ps1 -Stop`).

## Opções (linha de comando)
```
armagedon.ps1              # essenciais + gerador de imagens, com supervisor
armagedon.ps1 -WithVideo   # inclui o gerador de vídeo (pesado; só se for usar)
armagedon.ps1 -Once        # só inicia, sem ficar supervisionando
armagedon.ps1 -NoBrowser   # não abre o navegador
armagedon.ps1 -Stop        # mata hub/cérebro/geradores (deixa o Ollama)
```

## Iniciar junto com o Windows (opcional)
Agendador de Tarefas → Criar Tarefa Básica → disparo "Ao fazer logon" →
ação: iniciar programa `powershell.exe`, argumentos:
`-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Users\douglas\Desktop\ArmagedonIA\ia-armagedon\armagedon.ps1" -NoBrowser`

## Serviços e portas
| Serviço | Porta | O que é |
|---|---|---|
| Ollama | 11434 | roda os modelos de texto |
| Cérebro | 5002 | RAG (documentos) + memória + roteador + busca na web + feedback |
| Hub | 3000 | interface web + proxy pra todo o resto |
| Gerador de imagens | 5000 | Stable Diffusion / SD-Turbo |
| Gerador de vídeos | 5001 | GIF (3 modos) — só sobe com `-WithVideo` |

Status ao vivo aparece no painel lateral da interface. Logs em `logs/`.
