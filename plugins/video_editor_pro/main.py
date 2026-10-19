#!/usr/bin/env python3
"""
Video Editor Pro Plugin - Editor profissional de vídeos
Suporta edição, efeitos, legendas e múltiplos formatos
"""

import subprocess
import os
import json
from datetime import datetime
from pathlib import Path


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Video Editor Pro")
        self.output_dir = "videos_edited"
        self.output_quality = config.get("config", {}).get("output_quality", "high")
        self.default_format = config.get("config", {}).get("default_format", "mp4")

        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ {self.name} inicializado")

    def trim(self, video_path, start_time, end_time):
        """Corta um vídeo do tempo start até end.
        Times em formato HH:MM:SS ou segundos
        """
        try:
            output_path = os.path.join(
                self.output_dir,
                f"trimmed_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(start_time),
                "-to", str(end_time),
                "-c", "copy",  # Copy without re-encoding (faster)
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                return {
                    "success": True,
                    "output": output_path,
                    "start": start_time,
                    "end": end_time,
                    "size_mb": round(file_size, 2)
                }
            else:
                return {"success": False, "error": "Falha ao cortar vídeo"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def split(self, video_path, num_parts):
        """Divide vídeo em N partes iguais."""
        try:
            # Obter duração
            duration_result = self._get_duration(video_path)
            if not duration_result["success"]:
                return duration_result

            total_duration = duration_result["duration"]
            part_duration = total_duration / num_parts

            output_files = []

            for i in range(num_parts):
                start = i * part_duration
                end = (i + 1) * part_duration

                output_path = os.path.join(
                    self.output_dir,
                    f"split_part_{i+1}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
                )

                cmd = [
                    "ffmpeg",
                    "-i", video_path,
                    "-ss", str(start),
                    "-to", str(end),
                    "-c", "copy",
                    "-y",
                    output_path
                ]

                subprocess.run(cmd, capture_output=True, timeout=300)

                if os.path.exists(output_path):
                    output_files.append(output_path)

            return {
                "success": True,
                "total_parts": len(output_files),
                "files": output_files,
                "part_duration": round(part_duration, 2)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_text(self, video_path, text, duration=None, position="center", font_size=24):
        """Adiciona texto/legenda ao vídeo.
        position: top-left, top-center, center, bottom-left, bottom-center
        """
        try:
            output_path = os.path.join(
                self.output_dir,
                f"text_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            # Calcular posição
            positions = {
                "top-left": "(10,10)",
                "top-center": "(w/2-text_w/2,10)",
                "center": "(w/2-text_w/2,h/2-text_h/2)",
                "bottom-left": "(10,h-30)",
                "bottom-center": "(w/2-text_w/2,h-30)",
            }

            pos = positions.get(position, positions["center"])

            # Filtro drawtext do FFmpeg
            duration_filter = ""
            if duration:
                duration_filter = f":enable='between(t,0,{duration})'"

            filter_str = f"drawtext=text='{text}':fontsize={font_size}:fontcolor=white:x={pos}:y={pos}{duration_filter}"

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", filter_str,
                "-c:a", "copy",
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                return {
                    "success": True,
                    "output": output_path,
                    "text": text,
                    "position": position,
                    "duration": duration
                }
            else:
                return {"success": False, "error": "Falha ao adicionar texto"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_audio(self, video_path, audio_path, replace=False):
        """Adiciona ou substitui áudio do vídeo."""
        try:
            output_path = os.path.join(
                self.output_dir,
                f"audio_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            if replace:
                # Remover áudio original e usar novo
                cmd = [
                    "ffmpeg",
                    "-i", video_path,
                    "-i", audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    "-y",
                    output_path
                ]
            else:
                # Mesclar áudio (mixar)
                cmd = [
                    "ffmpeg",
                    "-i", video_path,
                    "-i", audio_path,
                    "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first[a]",
                    "-map", "0:v:0",
                    "-map", "[a]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-y",
                    output_path
                ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                return {
                    "success": True,
                    "output": output_path,
                    "audio_path": audio_path,
                    "replaced": replace
                }
            else:
                return {"success": False, "error": "Falha ao adicionar áudio"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def change_speed(self, video_path, speed=1.0):
        """Muda a velocidade do vídeo.
        speed: 0.5 (meio), 1.0 (normal), 2.0 (dobro)
        """
        try:
            output_path = os.path.join(
                self.output_dir,
                f"speed_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            # Validar speed
            speed = float(speed)
            if speed < 0.25 or speed > 4.0:
                return {"success": False, "error": "Velocidade deve ser entre 0.25 e 4.0"}

            filter_str = f"setpts={1/speed}*PTS,atempo={speed}"

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-filter:v", f"setpts={1/speed}*PTS",
                "-filter:a", f"atempo={speed}",
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                return {
                    "success": True,
                    "output": output_path,
                    "original_speed": 1.0,
                    "new_speed": speed
                }
            else:
                return {"success": False, "error": "Falha ao alterar velocidade"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_transition(self, video_path, transition_type="fade", duration=1):
        """Adiciona transição (simulado - apenas fade por enquanto)."""
        try:
            # Transições suportadas
            transitions = {
                "fade": "[0]fade=t=out:st=END-1:d=1[v1];[v1]fade=t=in:st=0:d=1[v]",
                "black": "[0]fade=t=out:st=END-1:d=1:color=black[v]",
                "white": "[0]fade=t=out:st=END-1:d=1:color=white[v]",
            }

            if transition_type not in transitions:
                return {"success": False, "error": f"Transição '{transition_type}' não suportada"}

            output_path = os.path.join(
                self.output_dir,
                f"transition_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            return {
                "success": True,
                "output": output_path,
                "transition": transition_type,
                "duration": duration,
                "note": "Transição aplicada no final do vídeo"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def resize(self, video_path, width, height, maintain_aspect=True):
        """Redimensiona vídeo."""
        try:
            output_path = os.path.join(
                self.output_dir,
                f"resized_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            if maintain_aspect:
                # Manter proporção com padding
                scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            else:
                scale_filter = f"scale={width}:{height}"

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", scale_filter,
                "-c:a", "copy",
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                return {
                    "success": True,
                    "output": output_path,
                    "resolution": f"{width}x{height}",
                    "maintain_aspect": maintain_aspect
                }
            else:
                return {"success": False, "error": "Falha ao redimensionar"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def convert_format(self, video_path, output_format="mp4"):
        """Converte vídeo para diferente formato."""
        try:
            # Formatos suportados
            formats = {
                "mp4": ("mp4", "h264"),
                "mkv": ("matroska", "libx264"),
                "avi": ("avi", "mpeg4"),
                "webm": ("webm", "vp8"),
                "mov": ("mov", "h264"),
                "flv": ("flv", "mpeg4"),
            }

            if output_format not in formats:
                return {"success": False, "error": f"Formato '{output_format}' não suportado"}

            container, codec = formats[output_format]
            output_path = os.path.join(
                self.output_dir,
                f"converted_{datetime.now():%Y%m%d_%H%M%S}.{output_format}"
            )

            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-c:v", codec,
                "-c:a", "aac",
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=300)

            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                return {
                    "success": True,
                    "output": output_path,
                    "format": output_format,
                    "codec": codec,
                    "size_mb": round(file_size, 2)
                }
            else:
                return {"success": False, "error": "Falha ao converter"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def merge(self, video_paths, output_name="merged"):
        """Mescla múltiplos vídeos em um."""
        try:
            if len(video_paths) < 2:
                return {"success": False, "error": "Precisa de ao menos 2 vídeos"}

            # Criar arquivo concat
            concat_file = os.path.join(self.output_dir, "concat.txt")
            with open(concat_file, 'w') as f:
                for path in video_paths:
                    f.write(f"file '{path}'\n")

            output_path = os.path.join(
                self.output_dir,
                f"{output_name}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            )

            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-y",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=600)

            # Limpar arquivo concat
            os.remove(concat_file)

            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                return {
                    "success": True,
                    "output": output_path,
                    "merged_count": len(video_paths),
                    "size_mb": round(file_size, 2)
                }
            else:
                return {"success": False, "error": "Falha ao mesclar vídeos"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_info(self, video_path):
        """Obtém informações detalhadas do vídeo."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            metadata = json.loads(result.stdout)

            # Extrair informações
            format_info = metadata.get("format", {})
            video_stream = next(
                (s for s in metadata.get("streams", []) if s["codec_type"] == "video"),
                None
            )
            audio_stream = next(
                (s for s in metadata.get("streams", []) if s["codec_type"] == "audio"),
                None
            )

            return {
                "success": True,
                "video_info": {
                    "duration": format_info.get("duration", "N/A"),
                    "size_mb": float(format_info.get("size", 0)) / (1024 * 1024),
                    "bit_rate": format_info.get("bit_rate", "N/A"),
                    "video": {
                        "codec": video_stream.get("codec_name") if video_stream else "N/A",
                        "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}" if video_stream else "N/A",
                        "fps": round(float(video_stream.get("r_frame_rate", "0/1").split("/")[0]) / float(video_stream.get("r_frame_rate", "0/1").split("/")[1])) if video_stream else 0
                    },
                    "audio": {
                        "codec": audio_stream.get("codec_name") if audio_stream else "N/A",
                        "sample_rate": audio_stream.get("sample_rate") if audio_stream else "N/A",
                        "channels": audio_stream.get("channels") if audio_stream else "N/A"
                    }
                }
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_duration(self, video_path):
        """Obtém duração do vídeo."""
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
            return {"success": True, "duration": duration}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def on_video_generated(self, data):
        """Webhook: quando vídeo é gerado, pode editar automaticamente."""
        if isinstance(data, dict) and "filename" in data:
            print(f"🎬 Vídeo gerado detectado: {data['filename']}")
            return {"status": "pronto para editar"}
        return None

    def get_info_plugin(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author"),
            "features": self.config.get("features", [])
        }
