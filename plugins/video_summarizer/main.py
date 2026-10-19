#!/usr/bin/env python3
"""
Video Summarizer Plugin - Extração de frames e criação de resumos
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime
from PIL import Image


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Video Summarizer")
        self.output_dir = "video_summaries"
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ {self.name} inicializado")

    def get_duration(self, video_path):
        """Obtém duração do vídeo em segundos."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1:noesc=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            duration = float(result.stdout.strip())
            return {
                "success": True,
                "duration_seconds": duration,
                "duration_formatted": self._format_time(duration)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_frames(self, video_path, num_frames=5, output_format="png"):
        """Extrai N frames igualmente espaçados do vídeo."""
        try:
            duration = self.get_duration(video_path)
            if not duration["success"]:
                return duration

            total_duration = duration["duration_seconds"]
            interval = total_duration / (num_frames + 1)

            frames = []
            for i in range(1, num_frames + 1):
                timestamp = interval * i
                frame_file = os.path.join(
                    self.output_dir,
                    f"frame_{i:03d}_{datetime.now():%Y%m%d_%H%M%S}.{output_format}"
                )

                cmd = [
                    "ffmpeg",
                    "-i", video_path,
                    "-ss", str(timestamp),
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y",
                    frame_file
                ]

                subprocess.run(cmd, capture_output=True, timeout=30)

                if os.path.exists(frame_file):
                    frames.append({
                        "timestamp": timestamp,
                        "timestamp_formatted": self._format_time(timestamp),
                        "path": frame_file
                    })

            return {
                "success": True,
                "total_frames": len(frames),
                "frames": frames,
                "video_duration": duration["duration_formatted"]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def detect_scenes(self, video_path, threshold=27.0):
        """Detecta mudanças de cena no vídeo."""
        try:
            # Usar ffmpeg com filter de detecção de cena
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", f"select='gt(scene,{threshold/100})',scale=160:90",
                "-vsync", "0",
                "-f", "image2",
                "-y",
                os.path.join(self.output_dir, "scene_%03d.png")
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            # Contar frames gerados (= mudanças de cena detectadas)
            scene_files = sorted(Path(self.output_dir).glob("scene_*.png"))
            scenes = []

            for idx, scene_file in enumerate(scene_files):
                scenes.append({
                    "scene_number": idx + 1,
                    "path": str(scene_file)
                })

            return {
                "success": True,
                "scenes_detected": len(scenes),
                "threshold": threshold,
                "scenes": scenes
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_gif(self, video_path, duration_sec=5, fps=3):
        """Cria GIF resumido do vídeo."""
        try:
            # Extrair frames para o GIF
            temp_pattern = os.path.join(self.output_dir, "gif_frame_%03d.png")

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", "0",
                "-t", str(duration_sec),
                "-vf", f"fps={fps},scale=640:480:force_original_aspect_ratio=decrease",
                "-y",
                temp_pattern
            ]

            subprocess.run(cmd, capture_output=True, timeout=60)

            # Criar GIF
            gif_path = os.path.join(
                self.output_dir,
                f"summary_{datetime.now():%Y%m%d_%H%M%S}.gif"
            )

            frames = sorted(Path(self.output_dir).glob("gif_frame_*.png"))
            if frames:
                images = [Image.open(str(f)) for f in frames]
                images[0].save(
                    gif_path,
                    save_all=True,
                    append_images=images[1:],
                    duration=int(1000 / fps),
                    loop=0
                )

                # Limpar frames temporários
                for f in frames:
                    os.remove(f)

                return {
                    "success": True,
                    "gif_path": gif_path,
                    "duration": duration_sec,
                    "fps": fps,
                    "total_frames": len(images)
                }
            else:
                return {"success": False, "error": "Nenhum frame foi extraído"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_thumbnail(self, video_path, timestamp=None, width=320, height=240):
        """Cria thumbnail do vídeo."""
        try:
            # Se não especificado, usar 1/3 do vídeo
            if timestamp is None:
                duration = self.get_duration(video_path)
                if duration["success"]:
                    timestamp = duration["duration_seconds"] / 3
                else:
                    timestamp = 5

            thumbnail_path = os.path.join(
                self.output_dir,
                f"thumbnail_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            )

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(timestamp),
                "-vframes", "1",
                "-vf", f"scale={width}:{height}",
                "-y",
                thumbnail_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=30)

            if os.path.exists(thumbnail_path):
                return {
                    "success": True,
                    "thumbnail_path": thumbnail_path,
                    "timestamp": timestamp,
                    "timestamp_formatted": self._format_time(timestamp),
                    "dimensions": f"{width}x{height}"
                }
            else:
                return {"success": False, "error": "Falha ao criar thumbnail"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_metadata(self, video_path):
        """Extrai metadados do vídeo."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-print_section",
                "-of", "json",
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            metadata = json.loads(result.stdout)

            # Extrair informações relevantes
            video_stream = next(
                (s for s in metadata.get("streams", []) if s["codec_type"] == "video"),
                None
            )

            info = {
                "success": True,
                "duration": metadata.get("format", {}).get("duration", "N/A"),
                "size": metadata.get("format", {}).get("size", "N/A"),
                "bit_rate": metadata.get("format", {}).get("bit_rate", "N/A")
            }

            if video_stream:
                info.update({
                    "codec": video_stream.get("codec_name", "N/A"),
                    "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
                    "fps": eval(video_stream.get("r_frame_rate", "0/1"))
                })

            return info
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _format_time(self, seconds):
        """Formata segundos para HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def on_video_generated(self, data):
        """Webhook: executado quando vídeo é gerado."""
        if isinstance(data, dict) and "filename" in data:
            print(f"🎬 Vídeo gerado detectado: {data['filename']}")
            return {"status": "pronto para sumarizar"}
        return None

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author"),
            "features": self.config.get("features", [])
        }
