# Pasta de documentos do ARMAGEDON (RAG)

Coloque aqui os arquivos que você quer que o ARMAGEDON consulte nas respostas:

- Formatos aceitos: `.txt`, `.md`, `.pdf`
- Subpastas são lidas também
- Depois de adicionar/alterar arquivos, abra a interface → botão **🧠 Conhecimento** → **Reindexar documentos**
  (ou chame `POST http://localhost:5002/ingest`)

Como funciona: cada arquivo é quebrado em trechos (~1000 caracteres), cada trecho vira
um vetor via `nomic-embed-text` (roda no Ollama) e é guardado no ChromaDB em `brain_data/`.
Quando você pergunta algo, os trechos mais parecidos com a pergunta são injetados no
prompt antes de mandar pro modelo.

Este arquivo (`LEIA-ME.md`) também será indexado — pode apagar se quiser.
