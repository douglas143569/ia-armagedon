#!/usr/bin/env python3
"""Teste do Smart Search Plugin"""

from plugin_manager import PluginManager
import time

print("\n" + "="*70)
print("🔍 TESTE: Smart Search Plugin")
print("="*70)

# Inicializar
manager = PluginManager()
manager.discover_plugins()

# Carregar Smart Search
print("\n📥 Carregando Smart Search...\n")
if manager.load_plugin("Smart Search"):
    print("✓ Smart Search carregado")

# ============================================================================
# TESTE 1: Busca Básica
# ============================================================================

print("\n" + "="*70)
print("1️⃣  TESTE: Busca Básica")
print("="*70)

print("\n🔍 Buscando 'paisagem'...")
result = manager.execute_plugin("Smart Search", "search", "paisagem", "all", 10)
if result["success"]:
    print(f"✓ {result['result']['total']} resultado(s) encontrado(s)")
    for r in result['result']['results'][:3]:
        content = r.get('prompt') or r.get('content') or r.get('text', '')
        print(f"   [{r['type']}] {content[:50]}...")

print("\n🔍 Buscando 'chat'...")
result = manager.execute_plugin("Smart Search", "search", "teste", "chat", 5)
if result["success"]:
    print(f"✓ {result['result']['total']} chat(s) encontrado(s)")

print("\n🔍 Buscando 'imagem'...")
result = manager.execute_plugin("Smart Search", "search", "paisagem", "image", 5)
if result["success"]:
    print(f"✓ {result['result']['total']} imagem(ns) encontrada(s)")

# ============================================================================
# TESTE 2: Busca Avançada
# ============================================================================

print("\n" + "="*70)
print("2️⃣  TESTE: Busca Avançada com Filtros")
print("="*70)

print("\n🔍 Buscando 'paisagem' em últimos 7 dias...")
result = manager.execute_plugin(
    "Smart Search",
    "advanced_search",
    "paisagem",
    "all",
    date_from="2026-08-26",
    date_to="2026-09-02",
    limit=10
)
if result["success"]:
    print(f"✓ {result['result']['total']} resultado(s) com filtros")
    print(f"  Filtros aplicados: {result['result']['filters']}")

# ============================================================================
# TESTE 3: Sugestões
# ============================================================================

print("\n" + "="*70)
print("3️⃣  TESTE: Sugestões")
print("="*70)

print("\n💡 Sugestões para 'paisa...'")
result = manager.execute_plugin("Smart Search", "suggest", "paisa", 5)
if result["success"]:
    print(f"✓ {len(result['result']['suggestions'])} sugestão(ões):")
    for suggestion in result['result']['suggestions'][:3]:
        print(f"   • {suggestion}")

# ============================================================================
# TESTE 4: Tópicos em Tendência
# ============================================================================

print("\n" + "="*70)
print("4️⃣  TESTE: Tópicos em Tendência")
print("="*70)

print("\n📈 Tópicos mais frequentes (últimos 7 dias)...")
result = manager.execute_plugin("Smart Search", "trending_topics", 7)
if result["success"]:
    print(f"✓ Top tópicos:")
    for topic in result['result']['trending_topics'][:5]:
        print(f"   • {topic['topic']}: {topic['count']} menções")

# ============================================================================
# TESTE 5: Analytics
# ============================================================================

print("\n" + "="*70)
print("5️⃣  TESTE: Analytics de Busca")
print("="*70)

print("\n📊 Analisando padrões de uso...")
result = manager.execute_plugin("Smart Search", "search_analytics")
if result["success"]:
    analytics = result['result']['analytics']
    print(f"✓ Analytics:")
    print(f"   • Total de chats: {analytics['total_chats']}")
    print(f"   • Total de imagens: {analytics['total_images']}")
    print(f"   • Total de vídeos: {analytics['total_videos']}")
    print(f"   • Total de áudios: {analytics['total_audios']}")
    print(f"   • Total de registros: {analytics['total_records']}")
    print(f"   • Tamanho médio de chat: {analytics['avg_chat_length']:.0f} caracteres")
    if analytics['peak_hours']:
        print(f"   • Hora mais ativa: {analytics['peak_hours'][0]['hour']}:00 ({analytics['peak_hours'][0]['count']} chats)")

# ============================================================================
# TESTE 6: Info do Plugin
# ============================================================================

print("\n" + "="*70)
print("6️⃣  TESTE: Informações do Plugin")
print("="*70)

print("\n📋 Informações do Smart Search...")
result = manager.execute_plugin("Smart Search", "get_info")
if result["success"]:
    info = result['result']
    print(f"✓ {info['name']} v{info['version']}")
    print(f"   {info['description']}")
    print(f"   Autor: {info['author']}")

# ============================================================================
# Resumo Final
# ============================================================================

print("\n" + "="*70)
print("✅ TESTES CONCLUÍDOS!")
print("="*70)

print("\n🔍 Smart Search - Funcionalidades:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("\n✓ Busca Básica")
print("  • Por palavra-chave")
print("  • Filtrar por tipo (chat, image, video, audio)")
print("  • Ordenar por data")

print("\n✓ Busca Avançada")
print("  • Múltiplos filtros")
print("  • Filtro por período de data")
print("  • Ranking por relevância")

print("\n✓ Sugestões Inteligentes")
print("  • Auto-completar baseado no histórico")
print("  • Sugestões contextuais")

print("\n✓ Análise de Padrões")
print("  • Tópicos em tendência")
print("  • Horários mais ativos")
print("  • Estatísticas de uso")

print("\n" + "="*70 + "\n")
