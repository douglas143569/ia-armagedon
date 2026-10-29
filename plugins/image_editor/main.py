#!/usr/bin/env python3
"""
Image Editor Plugin - Edição de imagens com filtros e efeitos
"""

from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
import os
from datetime import datetime


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Image Editor")
        self.output_dir = "images_edited"
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ {self.name} inicializado")

    def resize(self, image_path, width, height, maintain_ratio=True):
        """Redimensiona imagem."""
        try:
            img = Image.open(image_path)
            original_size = img.size

            if maintain_ratio:
                # Manter proporção
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
            else:
                # Redimensionar forçado
                img = img.resize((width, height), Image.Resampling.LANCZOS)

            output_path = self._save_image(img, "resized")
            return {
                "success": True,
                "original_size": original_size,
                "new_size": img.size,
                "output": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def crop(self, image_path, left, top, right, bottom):
        """Corta imagem (box: (left, top, right, bottom))."""
        try:
            img = Image.open(image_path)
            box = (int(left), int(top), int(right), int(bottom))
            img_cropped = img.crop(box)

            output_path = self._save_image(img_cropped, "cropped")
            return {
                "success": True,
                "original_size": img.size,
                "crop_box": box,
                "new_size": img_cropped.size,
                "output": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def adjust(self, image_path, brightness=1.0, contrast=1.0, saturation=1.0):
        """Ajusta brilho, contraste e saturação."""
        try:
            img = Image.open(image_path)

            # Brilho
            if brightness != 1.0:
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(float(brightness))

            # Contraste
            if contrast != 1.0:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(float(contrast))

            # Saturação
            if saturation != 1.0:
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(float(saturation))

            output_path = self._save_image(img, "adjusted")
            return {
                "success": True,
                "adjustments": {
                    "brightness": brightness,
                    "contrast": contrast,
                    "saturation": saturation
                },
                "output": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply_filter(self, image_path, filter_type="blur"):
        """Aplica filtro à imagem."""
        try:
            img = Image.open(image_path)

            filters = {
                "blur": lambda x: x.filter(ImageFilter.GaussianBlur(radius=2)),
                "sharpen": lambda x: x.filter(ImageFilter.SHARPEN),
                "smooth": lambda x: x.filter(ImageFilter.SMOOTH),
                "emboss": lambda x: x.filter(ImageFilter.EMBOSS),
                "edge": lambda x: x.filter(ImageFilter.FIND_EDGES),
                "detail": lambda x: x.filter(ImageFilter.DETAIL),
                "contour": lambda x: x.filter(ImageFilter.CONTOUR),
            }

            if filter_type not in filters:
                return {
                    "success": False,
                    "error": f"Filtro '{filter_type}' não suportado. Opções: {list(filters.keys())}"
                }

            img_filtered = filters[filter_type](img)
            output_path = self._save_image(img_filtered, f"filtered_{filter_type}")

            return {
                "success": True,
                "filter": filter_type,
                "output": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_watermark(self, image_path, text, position="bottom-right", opacity=0.7, font_size=30):
        """Adiciona marca d'água com texto."""
        try:
            img = Image.open(image_path).convert("RGBA")
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)

            # Posição
            positions = {
                "top-left": (10, 10),
                "top-center": (img.width // 2 - 50, 10),
                "top-right": (img.width - 100, 10),
                "center": (img.width // 2 - 50, img.height // 2),
                "bottom-left": (10, img.height - 40),
                "bottom-center": (img.width // 2 - 50, img.height - 40),
                "bottom-right": (img.width - 100, img.height - 40),
            }

            xy = positions.get(position, positions["bottom-right"])

            # Desenhar texto
            color = (255, 255, 255, int(255 * opacity))
            draw.text(xy, text, fill=color, font=None)

            # Mesclar
            img = Image.alpha_composite(img, txt_layer)
            img = img.convert("RGB")

            output_path = self._save_image(img, "watermarked")
            return {
                "success": True,
                "text": text,
                "position": position,
                "opacity": opacity,
                "output": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def convert_format(self, image_path, output_format="PNG"):
        """Converte formato de imagem."""
        try:
            img = Image.open(image_path)
            format_upper = output_format.upper()

            if format_upper not in ["PNG", "JPG", "JPEG", "GIF", "WEBP", "BMP"]:
                return {"success": False, "error": f"Formato '{format_upper}' não suportado"}

            # Converter se necessário
            if format_upper in ["JPG", "JPEG"]:
                if img.mode == "RGBA":
                    img = img.convert("RGB")

            filename = f"{self.output_dir}/converted_{datetime.now():%Y%m%d_%H%M%S}.{format_upper.lower()}"
            img.save(filename, format=format_upper)

            return {
                "success": True,
                "original_format": os.path.splitext(image_path)[1],
                "new_format": format_upper,
                "output": filename
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_image(self, img, suffix="edited"):
        """Salva imagem com timestamp."""
        filename = f"{self.output_dir}/image_{suffix}_{datetime.now():%Y%m%d_%H%M%S}.png"
        img.save(filename)
        return filename

    def on_image_generated(self, data):
        """Webhook: executado quando imagem é gerada."""
        if isinstance(data, dict) and "filename" in data:
            print(f"📸 Imagem gerada detectada: {data['filename']}")
            return {"status": "pronto para editar"}
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
