#!/usr/bin/env python3
"""
Database Manager Plugin - Gerenciador de banco de dados SQLite
Salva histórico de chats, imagens, vídeos e áudios
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Database Manager")
        self.db_type = config.get("config", {}).get("db_type", "sqlite")
        self.db_path = config.get("config", {}).get("db_path", "armagedon.db")
        self.auto_backup = config.get("config", {}).get("auto_backup", True)

        print(f"✓ {self.name} inicializado")
        print(f"  Banco: {self.db_path}")

        # Criar tabelas se não existirem
        self._init_database()

    def _init_database(self):
        """Inicializa o banco de dados com as tabelas necessárias."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Tabela de chats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_message TEXT NOT NULL,
                    assistant_response TEXT,
                    model TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tokens_used INTEGER,
                    processing_time REAL
                )
            """)

            # Tabela de imagens
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    filename TEXT,
                    filepath TEXT,
                    model TEXT,
                    resolution TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_time REAL,
                    quality TEXT
                )
            """)

            # Tabela de vídeos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    filename TEXT,
                    filepath TEXT,
                    model TEXT,
                    duration REAL,
                    fps INTEGER,
                    resolution TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_time REAL
                )
            """)

            # Tabela de áudios
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    filename TEXT,
                    filepath TEXT,
                    language TEXT,
                    gender TEXT,
                    emotion TEXT,
                    speed REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_time REAL,
                    duration REAL
                )
            """)

            # Tabela de stats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_type TEXT,
                    value TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
            print("✓ Banco de dados inicializado")
        except Exception as e:
            print(f"❌ Erro ao inicializar BD: {e}")

    def save_chat(self, user_message, assistant_response, model="mistral", tokens_used=0, processing_time=0):
        """Salva uma mensagem de chat no BD."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO chats (user_message, assistant_response, model, tokens_used, processing_time)
                VALUES (?, ?, ?, ?, ?)
            """, (user_message, assistant_response, model, tokens_used, processing_time))

            conn.commit()
            chat_id = cursor.lastrowid
            conn.close()

            return {
                "success": True,
                "chat_id": chat_id,
                "message": "Chat salvo com sucesso"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_image(self, prompt, filename, filepath, model="sd", resolution="512x512", processing_time=0, quality="high"):
        """Salva informações de imagem gerada."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO images (prompt, filename, filepath, model, resolution, processing_time, quality)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prompt, filename, filepath, model, resolution, processing_time, quality))

            conn.commit()
            image_id = cursor.lastrowid
            conn.close()

            return {"success": True, "image_id": image_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_video(self, prompt, filename, filepath, model="svd", duration=0, fps=15, resolution="512x512", processing_time=0):
        """Salva informações de vídeo gerado."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO videos (prompt, filename, filepath, model, duration, fps, resolution, processing_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (prompt, filename, filepath, model, duration, fps, resolution, processing_time))

            conn.commit()
            video_id = cursor.lastrowid
            conn.close()

            return {"success": True, "video_id": video_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_audio(self, text, filename, filepath, language="pt", gender="neutral", emotion="neutral", speed=1.0, processing_time=0, duration=0):
        """Salva informações de áudio gerado."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO audios (text, filename, filepath, language, gender, emotion, speed, processing_time, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (text, filename, filepath, language, gender, emotion, speed, processing_time, duration))

            conn.commit()
            audio_id = cursor.lastrowid
            conn.close()

            return {"success": True, "audio_id": audio_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_chat_history(self, limit=100, offset=0):
        """Retorna histórico de chats."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, user_message, assistant_response, model, timestamp, tokens_used
                FROM chats
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            chats = []
            for row in cursor.fetchall():
                chats.append({
                    "id": row[0],
                    "user": row[1],
                    "assistant": row[2],
                    "model": row[3],
                    "timestamp": row[4],
                    "tokens": row[5]
                })

            conn.close()
            return {"success": True, "total": len(chats), "chats": chats}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_images(self, limit=50, offset=0):
        """Retorna lista de imagens geradas."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, prompt, filename, resolution, timestamp, processing_time
                FROM images
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            images = []
            for row in cursor.fetchall():
                images.append({
                    "id": row[0],
                    "prompt": row[1],
                    "filename": row[2],
                    "resolution": row[3],
                    "timestamp": row[4],
                    "processing_time": row[5]
                })

            conn.close()
            return {"success": True, "total": len(images), "images": images}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_videos(self, limit=50, offset=0):
        """Retorna lista de vídeos gerados."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, prompt, filename, duration, fps, timestamp, processing_time
                FROM videos
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            videos = []
            for row in cursor.fetchall():
                videos.append({
                    "id": row[0],
                    "prompt": row[1],
                    "filename": row[2],
                    "duration": row[3],
                    "fps": row[4],
                    "timestamp": row[5],
                    "processing_time": row[6]
                })

            conn.close()
            return {"success": True, "total": len(videos), "videos": videos}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audios(self, limit=50, offset=0):
        """Retorna lista de áudios gerados."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, text, filename, language, emotion, timestamp, duration
                FROM audios
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            audios = []
            for row in cursor.fetchall():
                audios.append({
                    "id": row[0],
                    "text": row[1],
                    "filename": row[2],
                    "language": row[3],
                    "emotion": row[4],
                    "timestamp": row[5],
                    "duration": row[6]
                })

            conn.close()
            return {"success": True, "total": len(audios), "audios": audios}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(self, query, search_type="all"):
        """Busca em histórico (chats, imagens, vídeos, áudios)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            results = []

            search_term = f"%{query}%"

            # Buscar em chats
            if search_type in ["all", "chat"]:
                cursor.execute("""
                    SELECT 'chat' as type, id, user_message, timestamp
                    FROM chats
                    WHERE user_message LIKE ? OR assistant_response LIKE ?
                """, (search_term, search_term))
                results.extend([{"type": "chat", "id": r[1], "content": r[2], "timestamp": r[3]} for r in cursor.fetchall()])

            # Buscar em imagens
            if search_type in ["all", "image"]:
                cursor.execute("""
                    SELECT 'image' as type, id, prompt, timestamp
                    FROM images
                    WHERE prompt LIKE ?
                """, (search_term,))
                results.extend([{"type": "image", "id": r[1], "content": r[2], "timestamp": r[3]} for r in cursor.fetchall()])

            # Buscar em vídeos
            if search_type in ["all", "video"]:
                cursor.execute("""
                    SELECT 'video' as type, id, prompt, timestamp
                    FROM videos
                    WHERE prompt LIKE ?
                """, (search_term,))
                results.extend([{"type": "video", "id": r[1], "content": r[2], "timestamp": r[3]} for r in cursor.fetchall()])

            conn.close()
            return {"success": True, "query": query, "total": len(results), "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_stats(self):
        """Retorna estatísticas do sistema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Contar registros
            cursor.execute("SELECT COUNT(*) FROM chats")
            total_chats = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM images")
            total_images = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM videos")
            total_videos = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM audios")
            total_audios = cursor.fetchone()[0]

            # Tempo médio de processamento
            cursor.execute("SELECT AVG(processing_time) FROM images WHERE processing_time > 0")
            avg_image_time = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(processing_time) FROM videos WHERE processing_time > 0")
            avg_video_time = cursor.fetchone()[0] or 0

            # Total de tokens
            cursor.execute("SELECT SUM(tokens_used) FROM chats")
            total_tokens = cursor.fetchone()[0] or 0

            conn.close()

            return {
                "success": True,
                "stats": {
                    "total_chats": total_chats,
                    "total_images": total_images,
                    "total_videos": total_videos,
                    "total_audios": total_audios,
                    "avg_image_processing_time": round(avg_image_time, 2),
                    "avg_video_processing_time": round(avg_video_time, 2),
                    "total_tokens_used": total_tokens,
                    "database_size_kb": os.path.getsize(self.db_path) / 1024
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def backup(self):
        """Cria backup do banco de dados."""
        try:
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"armagedon_backup_{timestamp}.db")

            # Copiar arquivo
            with open(self.db_path, 'rb') as original:
                with open(backup_path, 'wb') as backup:
                    backup.write(original.read())

            return {
                "success": True,
                "backup_path": backup_path,
                "timestamp": timestamp,
                "size_kb": os.path.getsize(backup_path) / 1024
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def export_json(self, export_type="all"):
        """Exporta dados em formato JSON."""
        try:
            data = {}

            # Exportar chats
            if export_type in ["all", "chats"]:
                chats_result = self.get_chat_history(limit=10000)
                data["chats"] = chats_result.get("chats", [])

            # Exportar imagens
            if export_type in ["all", "images"]:
                images_result = self.get_images(limit=10000)
                data["images"] = images_result.get("images", [])

            # Exportar vídeos
            if export_type in ["all", "videos"]:
                videos_result = self.get_videos(limit=10000)
                data["videos"] = videos_result.get("videos", [])

            # Exportar áudios
            if export_type in ["all", "audios"]:
                audios_result = self.get_audios(limit=10000)
                data["audios"] = audios_result.get("audios", [])

            # Salvar JSON
            export_path = f"armagedon_export_{datetime.now():%Y%m%d_%H%M%S}.json"
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "export_path": export_path,
                "total_records": sum(len(v) if isinstance(v, list) else 0 for v in data.values())
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def on_chat_message(self, data):
        """Webhook: salva mensagem de chat automaticamente."""
        if isinstance(data, dict) and "text" in data:
            return self.save_chat(
                data.get("text", ""),
                data.get("response", ""),
                data.get("model", "mistral")
            )
        return None

    def on_image_generated(self, data):
        """Webhook: salva imagem automaticamente."""
        if isinstance(data, dict) and "filename" in data:
            return self.save_image(
                data.get("prompt", ""),
                data.get("filename", ""),
                data.get("filepath", "")
            )
        return None

    def on_video_generated(self, data):
        """Webhook: salva vídeo automaticamente."""
        if isinstance(data, dict) and "filename" in data:
            return self.save_video(
                data.get("prompt", ""),
                data.get("filename", ""),
                data.get("filepath", "")
            )
        return None

    def on_voice_generated(self, data):
        """Webhook: salva áudio automaticamente."""
        if isinstance(data, dict) and "filename" in data:
            return self.save_audio(
                data.get("text", ""),
                data.get("filename", ""),
                data.get("filepath", ""),
                data.get("language", "pt"),
                data.get("gender", "neutral"),
                data.get("emotion", "neutral")
            )
        return None

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author"),
            "database": self.db_path,
            "database_size_kb": os.path.getsize(self.db_path) / 1024 if os.path.exists(self.db_path) else 0
        }
