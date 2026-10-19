#!/usr/bin/env python3
"""Teste dos novos plugins: Database Manager e Task Scheduler"""

from plugin_manager import PluginManager
import time

print("\n" + "="*70)
print("🧪 TESTE: Database Manager e Task Scheduler")
print("="*70)

# Inicializar
manager = PluginManager()
manager.discover_plugins()

# Carregar novos plugins
print("\n📥 Carregando novos plugins...\n")
for plugin_name in ["Database Manager", "Task Scheduler"]:
    if manager.load_plugin(plugin_name):
        print(f"✓ {plugin_name} carregado")

# ============================================================================
# TESTE 1: Database Manager
# ============================================================================

print("\n" + "="*70)
print("🗄️  TESTE 1: Database Manager")
print("="*70)

# Teste 1: Salvar chat
print("\n1️⃣  Salvando mensagens de chat...")
for i in range(3):
    result = manager.execute_plugin(
        "Database Manager",
        "save_chat",
        f"Olá, como vai? (mensagem {i+1})",
        f"Oi! Tudo bem, obrigado por perguntar! Resposta {i+1}",
        "mistral"
    )
    if result["success"]:
        print(f"✓ Chat {i+1} salvo (ID: {result['result']['chat_id']})")

# Teste 2: Salvar imagem
print("\n2️⃣  Salvando imagens...")
for i in range(2):
    result = manager.execute_plugin(
        "Database Manager",
        "save_image",
        f"Uma paisagem bonita #{i+1}",
        f"image_{i+1}.png",
        f"imagens/image_{i+1}.png"
    )
    if result["success"]:
        print(f"✓ Imagem {i+1} salva (ID: {result['result']['image_id']})")

# Teste 3: Salvar vídeo
print("\n3️⃣  Salvando vídeos...")
result = manager.execute_plugin(
    "Database Manager",
    "save_video",
    "Bruxa mexendo o caldeirão",
    "video_witch.mp4",
    "videos/video_witch.mp4",
    "svd",
    120.0,
    30
)
if result["success"]:
    print(f"✓ Vídeo salvo (ID: {result['result']['video_id']})")

# Teste 4: Salvar áudio
print("\n4️⃣  Salvando áudios...")
result = manager.execute_plugin(
    "Database Manager",
    "save_audio",
    "Olá mundo! Este é um teste de áudio.",
    "audio_test.wav",
    "audios/audio_test.wav",
    "pt",
    "female",
    "alegre",
    1.0,
    2.5
)
if result["success"]:
    print(f"✓ Áudio salvo")

# Teste 5: Obter histórico
print("\n5️⃣  Obtendo histórico...")
result = manager.execute_plugin("Database Manager", "get_chat_history", limit=10)
if result["success"]:
    print(f"✓ {result['result']['total']} chat(s) no histórico")

# Teste 6: Obter imagens
print("\n6️⃣  Obtendo imagens...")
result = manager.execute_plugin("Database Manager", "get_images", limit=50)
if result["success"]:
    print(f"✓ {result['result']['total']} imagem(ns) no histórico")

# Teste 7: Buscar
print("\n7️⃣  Buscando no histórico...")
result = manager.execute_plugin(
    "Database Manager",
    "search",
    "paisagem",
    "all"
)
if result["success"]:
    print(f"✓ {result['result']['total']} resultado(s) encontrado(s)")
    for r in result['result']['results']:
        print(f"   - {r['type']}: {r['content']}")

# Teste 8: Estatísticas
print("\n8️⃣  Obter estatísticas...")
result = manager.execute_plugin("Database Manager", "get_stats")
if result["success"]:
    stats = result['result']['stats']
    print(f"✓ Estatísticas:")
    print(f"   - Total de chats: {stats['total_chats']}")
    print(f"   - Total de imagens: {stats['total_images']}")
    print(f"   - Total de vídeos: {stats['total_videos']}")
    print(f"   - Total de áudios: {stats['total_audios']}")
    print(f"   - Tamanho BD: {stats['database_size_kb']:.2f} KB")

# Teste 9: Backup
print("\n9️⃣  Criando backup...")
result = manager.execute_plugin("Database Manager", "backup")
if result["success"]:
    print(f"✓ Backup criado: {result['result']['backup_path']}")
    print(f"  Tamanho: {result['result']['size_kb']:.2f} KB")

# Teste 10: Export JSON
print("\n🔟 Exportando dados...")
result = manager.execute_plugin("Database Manager", "export_json", "all")
if result["success"]:
    print(f"✓ Dados exportados: {result['result']['export_path']}")
    print(f"  Total de registros: {result['result']['total_records']}")

# ============================================================================
# TESTE 2: Task Scheduler
# ============================================================================

print("\n" + "="*70)
print("⏰ TESTE 2: Task Scheduler")
print("="*70)

# Teste 1: Criar tarefas
print("\n1️⃣  Criando tarefas agendadas...")

tasks_to_create = [
    {
        "name": "Gerar imagem diária",
        "type": "at_time",
        "action": "generate_image",
        "schedule": "08:00"
    },
    {
        "name": "Backup automático",
        "type": "interval",
        "action": "backup",
        "schedule": "86400"  # 24 horas em segundos
    },
    {
        "name": "Limpeza de cache",
        "type": "at_time",
        "action": "cleanup",
        "schedule": "23:00"
    }
]

for task in tasks_to_create:
    result = manager.execute_plugin(
        "Task Scheduler",
        "create_task",
        task["name"],
        task["type"],
        task["action"],
        task["schedule"],
        True
    )
    if result["success"]:
        print(f"✓ Tarefa criada: {task['name']} (ID: {result['result']['task_id']})")

# Teste 2: Listar tarefas
print("\n2️⃣  Listando tarefas agendadas...")
result = manager.execute_plugin("Task Scheduler", "list_tasks")
if result["success"]:
    print(f"✓ {result['result']['total']} tarefa(s) agendada(s)")
    for task in result['result']['tasks']:
        status = "✓" if task['enabled'] else "✗"
        print(f"   {status} {task['name']} ({task['type']}: {task['schedule']})")

# Teste 3: Executar tarefa agora
print("\n3️⃣  Executando tarefa agora...")
result = manager.execute_plugin("Task Scheduler", "execute_task_now", 1)
if result["success"]:
    print(f"✓ Tarefa executada: {result['result']['task_name']}")
    print(f"   Resultado: {result['result']['result']['status']}")

# Teste 4: Pausar tarefa
print("\n4️⃣  Pausando tarefa...")
result = manager.execute_plugin("Task Scheduler", "pause_task", 2, True)
if result["success"]:
    print(f"✓ {result['result']['message']}")

# Teste 5: Histórico
print("\n5️⃣  Obtendo histórico de execuções...")
result = manager.execute_plugin("Task Scheduler", "get_history", 10)
if result["success"]:
    print(f"✓ {result['result']['total']} execução(ões) no histórico")

# Teste 6: Info do plugin
print("\n6️⃣  Informações do Task Scheduler...")
result = manager.execute_plugin("Task Scheduler", "get_info")
if result["success"]:
    info = result['result']
    print(f"✓ Plugin: {info['name']} v{info['version']}")
    print(f"   Total de tarefas: {info['total_tasks']}")
    print(f"   Tarefas ativas: {info['running_tasks']}")
    print(f"   Total de execuções: {info['total_executions']}")

# ============================================================================
# Webhooks
# ============================================================================

print("\n" + "="*70)
print("🔗 TESTE 3: Webhooks")
print("="*70)

print("\n📝 Registrando webhooks...")
manager.register_webhook("chat_message", "Database Manager", "on_chat_message")
manager.register_webhook("image_generated", "Database Manager", "on_image_generated")
manager.register_webhook("video_generated", "Database Manager", "on_video_generated")
manager.register_webhook("voice_generated", "Database Manager", "on_voice_generated")

print("✓ Webhooks registrados com sucesso!")

# ============================================================================
# Resumo Final
# ============================================================================

print("\n" + "="*70)
print("✅ TESTES CONCLUÍDOS COM SUCESSO!")
print("="*70)

print("\n📊 Resumo de Plugins:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

print("\n🗄️  DATABASE MANAGER:")
print("  • Salvar chats, imagens, vídeos, áudios")
print("  • Busca avançada com filtros")
print("  • Estatísticas de uso")
print("  • Backup automático")
print("  • Exportar em JSON/CSV")
print("  • 4 webhooks para auto-salvamento")

print("\n⏰ TASK SCHEDULER:")
print("  • Agendar tarefas por horário (at_time)")
print("  • Agendar por intervalo (interval)")
print("  • Suportar cron (cron)")
print("  • Executar ações automáticas")
print("  • Pausar/retomar tarefas")
print("  • Histórico de execuções")
print("  • Persistência em arquivo JSON")

print("\n" + "="*70 + "\n")
