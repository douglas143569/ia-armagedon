#!/usr/bin/env python3
"""
Sentiment Analyzer Plugin - Analisa tom emocional de textos
"""

import re


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Sentiment Analyzer")
        print(f"✓ {self.name} inicializado")

        # Palavras por sentimento (PT-BR)
        self.positive_words = [
            "ótimo", "excelente", "maravilhoso", "incrível", "fantástico",
            "perfeito", "adorei", "amor", "feliz", "alegre", "legal",
            "show", "demais", "sensacional", "espetacular"
        ]

        self.negative_words = [
            "horrível", "péssimo", "terrível", "ruim", "odeio", "ódio",
            "triste", "infeliz", "problema", "erro", "fracasso", "decepção",
            "decepcionante", "chato", "desagradável", "nojento"
        ]

        self.neutral_words = [
            "ok", "normal", "médio", "aceitável", "razoável", "meh"
        ]

    def analyze(self, text):
        """Analisa o sentimento de um texto."""
        text_lower = text.lower()

        # Contar palavras de cada sentimento
        positive_count = sum(1 for word in self.positive_words if word in text_lower)
        negative_count = sum(1 for word in self.negative_words if word in text_lower)
        neutral_count = sum(1 for word in self.neutral_words if word in text_lower)

        total = positive_count + negative_count + neutral_count

        if total == 0:
            sentiment = "neutro"
            score = 0.0
        else:
            # Calcular score (-1 a 1)
            score = (positive_count - negative_count) / total

            if score > 0.3:
                sentiment = "positivo"
            elif score < -0.3:
                sentiment = "negativo"
            else:
                sentiment = "neutro"

        return {
            "sentiment": sentiment,
            "score": round(score, 2),
            "positive_words": positive_count,
            "negative_words": negative_count,
            "confidence": round(abs(score), 2)
        }

    def on_message_received(self, data):
        """Webhook: executado quando uma mensagem é recebida."""
        if isinstance(data, dict) and "text" in data:
            result = self.analyze(data["text"])
            print(f"📊 Sentimento detectado: {result['sentiment']} ({result['score']})")
            return result
        return None

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author")
        }
