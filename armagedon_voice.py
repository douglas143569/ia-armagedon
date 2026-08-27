#!/usr/bin/env python3
"""
ARMAGEDON — Assistente de Voz
STT (Whisper) → LLM (Ollama) → TTS (Piper)
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path

try:
    import whisper
    import pyaudio
    import wave
    import numpy as np
except ImportError as e:
    print(f"❌ Dependência faltando: {e}")
    print("Execute: pip install openai-whisper pyaudio numpy")
    sys.exit(1)


class ARMAGEDONVoice:
    def __init__(self, model_name="base", language="pt"):
        """Inicializar assistente de voz"""
        print("🎤 ARMAGEDON — Assistente de Voz")
        print("=" * 50)

        self.model_name = model_name
        self.language = language
        self.recording = False

        # Carregar modelo Whisper
        print(f"📥 Carregando Whisper ({model_name})...")
        self.whisper_model = whisper.load_model(model_name)
        print("✅ Whisper carregado\n")

    def record_audio(self, duration=5, filename="temp_audio.wav"):
        """Gravar áudio do microfone"""
        print(f"🎙️  Gravando por {duration} segundos... (fale agora!)")

        CHUNK = 1024
        FORMAT = pyaudio.paFloat32
        CHANNELS = 1
        RATE = 16000

        p = pyaudio.PyAudio()

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

        frames = []
        for _ in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK)
            frames.append(np.frombuffer(data, dtype=np.float32))

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Salvar WAV
        audio_data = np.concatenate(frames)
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())

        print(f"✅ Áudio salvo: {filename}\n")
        return filename

    def transcribe(self, audio_file):
        """Transcrever áudio para texto (Whisper)"""
        print("🔊 Transcrevendo áudio...")
        result = self.whisper_model.transcribe(
            audio_file,
            language=self.language,
            fp16=False  # CPU mode
        )
        text = result["text"].strip()
        print(f"📝 Você disse: '{text}'\n")
        return text

    def query_ollama(self, text):
        """Enviar pergunta pro ARMAGEDON (Ollama)"""
        print("🤖 ARMAGEDON pensando...")
        try:
            result = subprocess.run(
                ["ollama", "run", "armagedon", text],
                capture_output=True,
                text=True,
                timeout=30
            )
            response = result.stdout.strip()
            print(f"💬 ARMAGEDON: {response}\n")
            return response
        except Exception as e:
            print(f"❌ Erro ao chamar Ollama: {e}")
            return "Desculpe, tive um problema."

    def speak(self, text, output_file="response.wav"):
        """Converter texto em voz (Piper TTS)"""
        print("🔊 Gerando áudio...")
        try:
            # Usar piper via subprocess
            process = subprocess.Popen(
                ["piper", "--model", "pt_BR-faber-medium", "--output_file", output_file],
                stdin=subprocess.PIPE,
                text=True
            )
            process.communicate(input=text)

            if os.path.exists(output_file):
                print(f"✅ Áudio gerado: {output_file}")
                # Reproduzir áudio
                self.play_audio(output_file)
                return output_file
            else:
                print("⚠️  Piper TTS não disponível. Pulando áudio.")
                print(f"   Resposta: {text}")
                return None
        except FileNotFoundError:
            print("⚠️  Piper não instalado. Use: pip install piper-tts")
            print(f"   Resposta: {text}")
            return None

    def play_audio(self, filename):
        """Reproduzir arquivo de áudio"""
        try:
            # Windows
            os.startfile(filename)
        except AttributeError:
            # Linux/Mac
            subprocess.run(["play", filename], check=False)

    def interactive_loop(self, max_iterations=5):
        """Loop interativo: gravar → transcrever → responder → falar"""
        print("🎙️  Modo Interativo (ARMAGEDON Assistente de Voz)")
        print("=" * 50)
        print("Pressione Enter para gravar, ou 'sair' para terminar\n")

        for i in range(max_iterations):
            user_input = input(f"[{i+1}] Pronto? (Enter/sair): ").strip().lower()

            if user_input == "sair":
                print("\n👋 Até logo, Douglas!")
                break

            # 1. Gravar áudio
            audio_file = self.record_audio(duration=5, filename=f"input_{i}.wav")

            # 2. Transcrever
            transcribed = self.transcribe(audio_file)

            # 3. Consultar ARMAGEDON
            response = self.query_ollama(transcribed)

            # 4. Falar resposta
            self.speak(response, output_file=f"output_{i}.wav")

            print("-" * 50 + "\n")

            # Limpar arquivos temp
            try:
                os.remove(audio_file)
            except:
                pass


def main():
    """Ponto de entrada"""
    print("\n🚀 Iniciando ARMAGEDON — Assistente de Voz\n")

    # Verificar se Ollama está rodando
    print("Verificando Ollama...")
    result = subprocess.run(["ollama", "list"], capture_output=True)
    if result.returncode != 0:
        print("❌ Ollama não está rodando!")
        print("   Execute: ollama serve")
        sys.exit(1)
    print("✅ Ollama rodando\n")

    # Inicializar
    voice = ARMAGEDONVoice(model_name="base", language="pt")

    # Loop interativo
    voice.interactive_loop(max_iterations=5)


if __name__ == "__main__":
    main()
