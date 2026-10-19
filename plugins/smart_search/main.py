#!/usr/bin/env python3
"""
Smart Search Plugin - Busca inteligente e semântica
Busca avançada em histórico de chats, imagens, vídeos e áudios
"""

import sqlite3
import re
from datetime import datetime, timedelta
from collections import Counter


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Smart Search")
        self.db_path = "armagedon.db"
        self.max_results = config.get("config", {}).get("max_results", 50)
        self.min_relevance = config.get("config", {}).get("min_relevance", 0.3)

        print(f"✓ {self.name} inicializado")

        # Sinônimos para busca semântica
        self.synonyms = {
            "imagem": ["foto", "picture", "image", "desenho", "ilustração"],
            "vídeo": ["filme", "video", "clip", "gravação"],
            "música": ["som", "audio", "áudio", "música", "música"],
            "chat": ["conversa", "diálogo", "mensagem", "texto"],
            "IA": ["inteligência artificial", "modelo", "assistente", "claude", "mistral"],
            "gerador": ["criar", "gerar", "produzir", "fazer"],
        }

    def search(self, query, search_type="all", limit=None):
        """Busca básica com filtro de tipo."""
        try:
            if limit is None:
                limit = self.max_results

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            results = []
            search_term = f"%{query}%"

            # Buscar em chats
            if search_type in ["all", "chat"]:
                cursor.execute("""
                    SELECT 'chat' as type, id, user_message, assistant_response, timestamp
                    FROM chats
                    WHERE user_message LIKE ? OR assistant_response LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (search_term, search_term, limit))
                results.extend([
                    {
                        "type": "chat",
                        "id": r[1],
                        "content": r[2],
                        "response": r[3],
                        "timestamp": r[4],
                        "relevance": 1.0
                    }
                    for r in cursor.fetchall()
                ])

            # Buscar em imagens
            if search_type in ["all", "image"]:
                cursor.execute("""
                    SELECT 'image' as type, id, prompt, filename, timestamp
                    FROM images
                    WHERE prompt LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (search_term, limit))
                results.extend([
                    {
                        "type": "image",
                        "id": r[1],
                        "prompt": r[2],
                        "filename": r[3],
                        "timestamp": r[4],
                        "relevance": 1.0
                    }
                    for r in cursor.fetchall()
                ])

            # Buscar em vídeos
            if search_type in ["all", "video"]:
                cursor.execute("""
                    SELECT 'video' as type, id, prompt, filename, timestamp
                    FROM videos
                    WHERE prompt LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (search_term, limit))
                results.extend([
                    {
                        "type": "video",
                        "id": r[1],
                        "prompt": r[2],
                        "filename": r[3],
                        "timestamp": r[4],
                        "relevance": 1.0
                    }
                    for r in cursor.fetchall()
                ])

            # Buscar em áudios
            if search_type in ["all", "audio"]:
                cursor.execute("""
                    SELECT 'audio' as type, id, text, filename, timestamp
                    FROM audios
                    WHERE text LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (search_term, limit))
                results.extend([
                    {
                        "type": "audio",
                        "id": r[1],
                        "text": r[2],
                        "filename": r[3],
                        "timestamp": r[4],
                        "relevance": 1.0
                    }
                    for r in cursor.fetchall()
                ])

            conn.close()

            # Ordenar por timestamp descendente
            results.sort(key=lambda x: x["timestamp"], reverse=True)

            return {
                "success": True,
                "query": query,
                "search_type": search_type,
                "total": len(results),
                "results": results[:limit]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def advanced_search(self, query, search_type="all", date_from=None, date_to=None, limit=None):
        """Busca avançada com filtros de data e tipo."""
        try:
            if limit is None:
                limit = self.max_results

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            results = []

            search_term = f"%{query}%"

            # Montar where clause para datas
            date_where = ""
            params = [search_term, search_term]

            if date_from:
                date_where += " AND timestamp >= ?"
                params.append(date_from)

            if date_to:
                date_where += " AND timestamp <= ?"
                params.append(date_to)

            # Buscar em chats
            if search_type in ["all", "chat"]:
                sql = f"""
                    SELECT 'chat' as type, id, user_message, timestamp
                    FROM chats
                    WHERE (user_message LIKE ? OR assistant_response LIKE ?) {date_where}
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                cursor.execute(sql, params + [limit])
                results.extend([
                    {
                        "type": "chat",
                        "id": r[1],
                        "content": r[2],
                        "timestamp": r[3],
                        "relevance": self._calculate_relevance(r[2], query)
                    }
                    for r in cursor.fetchall()
                ])

            # Similar para imagens, vídeos e áudios...

            conn.close()

            # Filtrar por relevance mínima e ordenar
            results = [r for r in results if r["relevance"] >= self.min_relevance]
            results.sort(key=lambda x: (-x["relevance"], -datetime.fromisoformat(x["timestamp"]).timestamp()))

            return {
                "success": True,
                "query": query,
                "filters": {
                    "type": search_type,
                    "date_from": date_from,
                    "date_to": date_to
                },
                "total": len(results),
                "results": results[:limit]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def suggest(self, partial_query, limit=10):
        """Sugestões baseadas no que você já buscou."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Buscar sugestões de chats
            cursor.execute("""
                SELECT DISTINCT SUBSTR(user_message, 1, 50) as suggestion
                FROM chats
                WHERE user_message LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{partial_query}%", limit))

            suggestions = [r[0] for r in cursor.fetchall()]

            # Buscar sugestões de imagens
            cursor.execute("""
                SELECT DISTINCT SUBSTR(prompt, 1, 50) as suggestion
                FROM images
                WHERE prompt LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{partial_query}%", limit))

            suggestions.extend([r[0] for r in cursor.fetchall()])

            conn.close()

            # Remover duplicatas e ordenar
            suggestions = list(set(suggestions))[:limit]

            return {
                "success": True,
                "query": partial_query,
                "suggestions": suggestions
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def trending_topics(self, days=7):
        """Tópicos em tendência baseado no histórico."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            date_threshold = (datetime.now() - timedelta(days=days)).isoformat()

            # Buscar palavras mais frequentes em chats
            cursor.execute("""
                SELECT user_message FROM chats
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (date_threshold,))

            all_text = " ".join([r[0] for r in cursor.fetchall()])

            # Extrair palavras (remover stopwords)
            stopwords = {"o", "a", "de", "e", "é", "que", "o", "a", "em", "um", "para", "com", "você"}
            words = re.findall(r'\b\w+\b', all_text.lower())
            words = [w for w in words if len(w) > 3 and w not in stopwords]

            # Contar frequências
            word_freq = Counter(words)
            trending = word_freq.most_common(20)

            conn.close()

            return {
                "success": True,
                "period_days": days,
                "trending_topics": [{"topic": word, "count": count} for word, count in trending]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_analytics(self):
        """Análise de padrões de busca e uso."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Contadores
            cursor.execute("SELECT COUNT(*) FROM chats")
            total_chats = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM images")
            total_images = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM videos")
            total_videos = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM audios")
            total_audios = cursor.fetchone()[0]

            # Médias de tamanho
            cursor.execute("SELECT AVG(LENGTH(user_message)) FROM chats")
            avg_chat_length = cursor.fetchone()[0] or 0

            # Horários mais ativos
            cursor.execute("""
                SELECT SUBSTR(timestamp, 12, 2) as hour, COUNT(*) as count
                FROM chats
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 5
            """)
            peak_hours = [{"hour": r[0], "count": r[1]} for r in cursor.fetchall()]

            conn.close()

            return {
                "success": True,
                "analytics": {
                    "total_chats": total_chats,
                    "total_images": total_images,
                    "total_videos": total_videos,
                    "total_audios": total_audios,
                    "avg_chat_length": round(avg_chat_length, 2),
                    "peak_hours": peak_hours,
                    "total_records": total_chats + total_images + total_videos + total_audios
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calculate_relevance(self, text, query):
        """Calcula score de relevância (0-1)."""
        if not text:
            return 0

        text_lower = text.lower()
        query_lower = query.lower()

        # Relevância exata
        if query_lower in text_lower:
            return 1.0

        # Relevância parcial
        query_words = query_lower.split()
        matched_words = sum(1 for word in query_words if word in text_lower)

        if matched_words > 0:
            return matched_words / len(query_words)

        # Relevância por sinônimos
        for key, syns in self.synonyms.items():
            if key in query_lower and any(syn in text_lower for syn in syns):
                return 0.7

        return 0

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author"),
            "features": self.config.get("features", [])
        }
