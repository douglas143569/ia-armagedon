#!/usr/bin/env python3
"""
Web Search Plugin - Busca informações na web (simulado)
"""


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Web Search")
        self.max_results = config.get("config", {}).get("max_results", 5)
        print(f"✓ {self.name} inicializado")

    def search(self, query):
        """Busca simulada (em produção, usaria API real como DuckDuckGo)."""
        # Simulação de resultados de busca
        results = [
            {
                "title": f"Resultado 1 para '{query}'",
                "url": "https://example.com/1",
                "snippet": "Este é um exemplo de resultado de busca."
            },
            {
                "title": f"Resultado 2 para '{query}'",
                "url": "https://example.com/2",
                "snippet": "Segundo resultado de busca simulado."
            }
        ]

        return {
            "query": query,
            "results": results[:self.max_results],
            "total": len(results)
        }

    def search_images(self, query):
        """Busca de imagens (simulado)."""
        return {
            "query": query,
            "images": [
                {"url": "https://example.com/img1.jpg", "title": f"Imagem 1 - {query}"},
                {"url": "https://example.com/img2.jpg", "title": f"Imagem 2 - {query}"}
            ]
        }

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "max_results": self.max_results
        }
