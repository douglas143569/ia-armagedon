# 🔌 ARMAGEDON - Sistema de Plugins

Sistema extensível que permite adicionar funcionalidades customizadas ao ARMAGEDON sem modificar o código principal.

## **📁 Estrutura de um Plugin**

```
plugins/
├── meu_plugin/
│   ├── plugin.json          # Metadados
│   ├── main.py              # Código principal
│   ├── requirements.txt      # Dependências Python
│   └── config.json           # Configurações (opcional)
```

## **📝 Arquivo plugin.json**

```json
{
  "name": "Meu Plugin",
  "version": "1.0.0",
  "description": "Descrição do que faz",
  "author": "Seu Nome",
  "enabled": true,
  "hooks": [
    {
      "event": "chat_message",
      "method": "on_message"
    },
    {
      "event": "image_generated",
      "method": "on_image"
    }
  ],
  "endpoints": [
    {
      "path": "/api/meu_plugin/acao",
      "method": "POST",
      "description": "Descrição da ação"
    }
  ]
}
```

### **Eventos Disponíveis (Hooks)**

- `chat_message` - Disparado quando uma mensagem é enviada no chat
- `image_generated` - Disparado quando uma imagem é gerada
- `video_generated` - Disparado quando um vídeo é gerado
- `voice_generated` - Disparado quando um áudio é gerado
- `plugin_loaded` - Disparado quando o plugin é carregado
- `plugin_unloaded` - Disparado quando o plugin é descarregado

## **💻 Arquivo main.py**

```python
#!/usr/bin/env python3
"""Meu Plugin de Exemplo"""

class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Meu Plugin")
        print(f"✓ {self.name} inicializado")

    def on_message(self, data):
        """Recebe dados quando um webhook é disparado."""
        print(f"Mensagem recebida: {data}")
        return {"status": "processado"}

    def on_image(self, data):
        """Processamento de imagem gerada."""
        return {"processed": True}

    def my_custom_method(self, param1, param2):
        """Métodos customizados que podem ser chamados via API."""
        result = f"Processando {param1} e {param2}"
        return {"result": result}

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version"),
            "status": "ativo"
        }
```

## **🚀 Exemplos de Plugins**

### **1. Sentiment Analyzer (Análise de Sentimento)**

Já incluído em `plugins/sentiment_analyzer/`

```bash
POST /api/plugins/sentiment_analyzer/analyze
{
  "text": "Que dia fantástico!"
}

# Resposta:
{
  "sentiment": "positivo",
  "score": 0.75,
  "confidence": 0.75
}
```

### **2. Web Search (Busca na Web)**

Já incluído em `plugins/web_search/`

```bash
POST /api/plugins/web_search/search
{
  "query": "Python tutorials"
}
```

## **🔗 API REST de Plugins**

### **Listar Plugins**

```bash
GET /api/plugins

# Resposta:
{
  "plugins": [
    {
      "id": "sentiment_analyzer",
      "name": "Sentiment Analyzer",
      "version": "1.0.0",
      "enabled": true
    },
    {
      "id": "web_search",
      "name": "Web Search",
      "version": "1.0.0",
      "enabled": false
    }
  ]
}
```

### **Executar Plugin**

```bash
POST /api/plugins/{plugin_id}/{method}
Content-Type: application/json

{
  "param1": "valor1",
  "param2": "valor2"
}
```

## **🎯 Criando seu Primeiro Plugin**

### **Passo 1: Criar estrutura**

```bash
mkdir plugins/meu_plugin
cd plugins/meu_plugin
```

### **Passo 2: Criar plugin.json**

```json
{
  "name": "Meu Primeiro Plugin",
  "version": "1.0.0",
  "description": "Um plugin de exemplo",
  "author": "Seu Nome",
  "enabled": true
}
```

### **Passo 3: Criar main.py**

```python
class Plugin:
    def __init__(self, config):
        self.config = config

    def hello(self, name):
        return f"Olá, {name}!"

    def get_info(self):
        return {"name": self.config.get("name")}
```

### **Passo 4: Testar**

```bash
python plugin_manager.py
```

Você verá:
```
✓ Plugin encontrado: Meu Primeiro Plugin
✓ Plugin 'Meu Primeiro Plugin' carregado com sucesso
```

### **Passo 5: Usar via API**

```bash
curl -X POST http://localhost:3000/api/plugins/meu_plugin/hello \
  -H "Content-Type: application/json" \
  -d '{"name": "Douglas"}'
```

## **📦 Plugin com Dependências**

Se seu plugin precisa de bibliotecas externas:

1. Criar `requirements.txt`:
```
requests==2.28.1
beautifulsoup4==4.11.1
```

2. Instalar:
```bash
pip install -r plugins/meu_plugin/requirements.txt
```

3. Importar no `main.py`:
```python
import requests
from bs4 import BeautifulSoup

class Plugin:
    def fetch_page(self, url):
        response = requests.get(url)
        return response.text
```

## **🔐 Segurança**

- Plugins rodam no mesmo processo Python
- Validar sempre entrada de dados
- Usar try/except para evitar crashes
- Não expor dados sensíveis via API

## **📊 Webhooks em Ação**

Quando um evento ocorre no ARMAGEDON:

```python
# Sistema core dispara webhook
plugin_manager.trigger_webhook('chat_message', {
    'text': 'Olá',
    'user': 'douglas',
    'timestamp': '2026-09-01T15:45:00'
})

# Seu plugin recebe via método on_message:
def on_message(self, data):
    print(f"Nova mensagem: {data['text']}")
    return {"status": "processada"}
```

## **🧪 Testando Plugins Localmente**

```python
from plugin_manager import PluginManager

manager = PluginManager()
manager.discover_plugins()
manager.load_plugin("sentiment_analyzer")

result = manager.execute_plugin(
    "sentiment_analyzer",
    "analyze",
    "Adorei esse produto!"
)

print(result)
```

## **❓ FAQ**

**P: Posso desabilitar um plugin?**
R: Sim, defina `"enabled": false` no `plugin.json`

**P: Posso recarregar plugins sem reiniciar?**
R: Em desenvolvimento. Por enquanto, reinicie o ARMAGEDON.

**P: Múltiplos plugins podem responder ao mesmo webhook?**
R: Sim! Todos registrados para o evento serão acionados.

**P: Como passar dados entre plugins?**
R: Via cache em memória ou arquivo (não recomendado ainda).

---

**Divirta-se criando plugins! 🎉**
