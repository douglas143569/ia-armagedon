#!/usr/bin/env python3
import pyttsx3

engine = pyttsx3.init()
voices = engine.getProperty('voices')

print("=" * 70)
print("VOZES DISPONÍVEIS NO SISTEMA")
print("=" * 70)

for i, voice in enumerate(voices, 1):
    gender = "MASCULINO" if 'male' in voice.name.lower() else "FEMININO" if 'female' in voice.name.lower() else "INDEFINIDO"
    print(f"\n[{i}] {voice.name}")
    print(f"    ID: {voice.id}")
    print(f"    Gênero: {gender}")

print("\n" + "=" * 70)
print(f"Total de vozes: {len(voices)}")
print("=" * 70)
