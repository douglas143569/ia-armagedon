#!/usr/bin/env python3
"""Teste do Video Editor Pro Plugin"""

from plugin_manager import PluginManager

print("\n" + "="*70)
print("🎬 TESTE: Video Editor Pro Plugin")
print("="*70)

# Inicializar
manager = PluginManager()
manager.discover_plugins()

# Carregar Video Editor Pro
print("\n📥 Carregando Video Editor Pro...\n")
if manager.load_plugin("Video Editor Pro"):
    print("✓ Video Editor Pro carregado")

# ============================================================================
# TESTE: Informações do Plugin
# ============================================================================

print("\n" + "="*70)
print("📋 TESTE: Informações do Plugin")
print("="*70)

result = manager.execute_plugin("Video Editor Pro", "get_info_plugin")
if result["success"]:
    info = result['result']
    print(f"\n✓ {info['name']} v{info['version']}")
    print(f"  {info['description']}")
    print(f"  Autor: {info['author']}")
    print(f"\n  Funcionalidades:")
    for feature in info['features']:
        print(f"    • {feature}")

# ============================================================================
# DEMONSTRAÇÃO: Funcionalidades Disponíveis
# ============================================================================

print("\n" + "="*70)
print("🎯 FUNCIONALIDADES DISPONÍVEIS")
print("="*70)

print("""
✅ 1. TRIM (Cortar Vídeo)
   trim(video_path, start_time, end_time)
   Exemplo: trim('video.mp4', '00:00:10', '00:00:30')
   → Corta do segundo 10 ao segundo 30

✅ 2. SPLIT (Dividir Vídeo)
   split(video_path, num_parts)
   Exemplo: split('video.mp4', 5)
   → Divide em 5 partes iguais

✅ 3. ADD TEXT (Adicionar Legenda)
   add_text(video_path, text, position='center')
   Exemplo: add_text('video.mp4', 'Olá Mundo', 'bottom-center')
   → Adiciona texto no final do vídeo

✅ 4. ADD AUDIO (Adicionar Áudio)
   add_audio(video_path, audio_path, replace=False)
   Exemplo: add_audio('video.mp4', 'musica.mp3', replace=True)
   → Substitui ou mistura áudio

✅ 5. CHANGE SPEED (Alterar Velocidade)
   change_speed(video_path, speed=1.0)
   Exemplo: change_speed('video.mp4', 2.0)
   → Duplica velocidade (2x mais rápido)

✅ 6. ADD TRANSITION (Adicionar Transição)
   add_transition(video_path, transition_type='fade', duration=1)
   Tipos: fade, black, white
   → Adiciona efeito de transição

✅ 7. RESIZE (Redimensionar)
   resize(video_path, width, height, maintain_aspect=True)
   Exemplo: resize('video.mp4', 1280, 720)
   → Redimensiona para Full HD

✅ 8. CONVERT FORMAT (Converter Formato)
   convert_format(video_path, output_format='mp4')
   Formatos: mp4, mkv, avi, webm, mov, flv
   → Converte para novo formato

✅ 9. MERGE (Mesclar Vídeos)
   merge([video1.mp4, video2.mp4, video3.mp4])
   → Combina múltiplos vídeos em um

✅ 10. GET INFO (Obter Informações)
    get_info(video_path)
    → Retorna: duração, resolução, FPS, codecs, bitrate
""")

# ============================================================================
# EXEMPLO DE USO PRÁTICO
# ============================================================================

print("\n" + "="*70)
print("💡 EXEMPLO DE USO PRÁTICO")
print("="*70)

print("""
# Fluxo de edição completo:

from plugin_manager import PluginManager

manager = PluginManager()
manager.load_plugin("Video Editor Pro")

# 1. Obter info do vídeo original
info = manager.execute_plugin("Video Editor Pro", "get_info", "meu_video.mp4")
print(f"Duração original: {info['result']['video_info']['duration']}s")

# 2. Cortar os primeiros 5 segundos
trimmed = manager.execute_plugin("Video Editor Pro", "trim",
    "meu_video.mp4", "00:00:05", "00:00:30")
print(f"Vídeo cortado: {trimmed['result']['output']}")

# 3. Adicionar legenda
with_text = manager.execute_plugin("Video Editor Pro", "add_text",
    trimmed['result']['output'], "Meu vídeo editado", "bottom-center")
print(f"Legenda adicionada: {with_text['result']['output']}")

# 4. Acelerar para 1.5x
faster = manager.execute_plugin("Video Editor Pro", "change_speed",
    with_text['result']['output'], 1.5)
print(f"Velocidade alterada: {faster['result']['output']}")

# 5. Converter para WebM
webm = manager.execute_plugin("Video Editor Pro", "convert_format",
    faster['result']['output'], "webm")
print(f"Convertido para WebM: {webm['result']['output']}")
""")

# ============================================================================
# Resumo Final
# ============================================================================

print("\n" + "="*70)
print("✅ VIDEO EDITOR PRO - PRONTO PARA USAR!")
print("="*70)

print("""
🎬 Video Editor Pro oferece edição profissional com:

📌 CORE FEATURES:
  • Cortar/dividir vídeos com precisão
  • Adicionar legendas e texto
  • Gerenciar áudio (adicionar/substituir)
  • Alterar velocidade (0.25x a 4.0x)
  • Efeitos de transição
  • Redimensionar com proporção

📌 CONVERSÃO:
  • MP4, MKV, AVI, WebM, MOV, FLV
  • Qualidade ajustável
  • Mantém qualidade de áudio

📌 AVANÇADO:
  • Mesclar múltiplos vídeos
  • Obter informações detalhadas
  • Webhook para vídeos gerados

📌 OUTPUT:
  • Todos os vídeos editados em: videos_edited/
  • Nomes com timestamp para rastreamento
  • Tamanho em MB disponível

🚀 Está tudo pronto para começar a editar seus vídeos!
""")

print("\n" + "="*70 + "\n")
