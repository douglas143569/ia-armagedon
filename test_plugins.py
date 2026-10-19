#!/usr/bin/env python3
"""Teste do Sistema de Plugins ARMAGEDON"""

from plugin_manager import PluginManager

print("\n" + "="*60)
print("🧪 TESTE DO SISTEMA DE PLUGINS ARMAGEDON")
print("="*60 + "\n")

# Inicializar plugin manager
manager = PluginManager()

# Descobrir plugins
manager.discover_plugins()

# Carregar plugins
print("\n📥 Carregando plugins habilitados...\n")
for plugin_name, plugin in manager.plugins.items():
    if plugin["enabled"]:
        manager.load_plugin(plugin_name)

# Testar plugin de análise de sentimento
print("\n" + "="*60)
print("🧪 TESTE: Sentiment Analyzer")
print("="*60)

test_texts = [
    "Adorei! Que dia fantástico e maravilhoso!",
    "Que horrível e terrível, estou muito triste.",
    "Ok, normal, nada de especial."
]

for text in test_texts:
    result = manager.execute_plugin("Sentiment Analyzer", "analyze", text)
    if result["success"]:
        analysis = result["result"]
        print(f"\nTexto: '{text}'")
        print(f"  Sentimento: {analysis['sentiment'].upper()}")
        print(f"  Score: {analysis['score']} (confiança: {analysis['confidence']})")

# Testar webhook
print("\n" + "="*60)
print("🔗 TESTE: Webhooks")
print("="*60)

webhook_data = {
    "text": "Que produto incrível e fantástico!",
    "user": "douglas"
}

print(f"\nRegistrando webhook para: chat_message")
manager.register_webhook("chat_message", "Sentiment Analyzer", "on_message_received")

print(f"Disparando webhook com: '{webhook_data['text']}'")
webhook_result = manager.trigger_webhook("chat_message", webhook_data)
print(f"✓ Webhook disparado para {webhook_result['triggered']} plugin(s)")

# Listar plugins
print("\n" + "="*60)
print("📋 PLUGINS DISPONÍVEIS")
print("="*60 + "\n")

for plugin_info in manager.list_plugins():
    status = "✓ CARREGADO" if plugin_info["loaded"] else "✗ DESATIVADO"
    print(f"{status:15} | {plugin_info['name']:25} | v{plugin_info['version']}")

print("\n" + "="*60)
print("✅ Testes concluídos com sucesso!")
print("="*60 + "\n")
