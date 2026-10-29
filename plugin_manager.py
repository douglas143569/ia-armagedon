#!/usr/bin/env python3
"""ARMAGEDON - Plugin Manager
Sistema de plugins com suporte a webhooks e modelos customizados
"""

import os
import json
import importlib.util
import sys
from pathlib import Path
from datetime import datetime

class PluginManager:
    def __init__(self, plugins_dir="plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins = {}
        self.webhooks = {}
        self.plugins_dir.mkdir(exist_ok=True)

    def discover_plugins(self):
        """Descobre e carrega todos os plugins disponíveis."""
        print("\n" + "="*60)
        print("DESCOBRINDO PLUGINS")
        print("="*60)

        for plugin_path in self.plugins_dir.iterdir():
            if not plugin_path.is_dir():
                continue

            plugin_json = plugin_path / "plugin.json"
            if not plugin_json.exists():
                print(f"⚠️  Pulando {plugin_path.name} - sem plugin.json")
                continue

            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                plugin_name = config.get("name", plugin_path.name)
                print(f"\n✓ Plugin encontrado: {plugin_name}")
                print(f"  Versão: {config.get('version', '1.0.0')}")
                print(f"  Descrição: {config.get('description', 'N/A')}")
                print(f"  Autor: {config.get('author', 'Desconhecido')}")

                self.plugins[plugin_name] = {
                    "path": plugin_path,
                    "config": config,
                    "enabled": config.get("enabled", True),
                    "instance": None
                }

            except Exception as e:
                print(f"❌ Erro ao carregar {plugin_path.name}: {e}")

    def load_plugin(self, plugin_name):
        """Carrega um plugin específico."""
        if plugin_name not in self.plugins:
            print(f"❌ Plugin '{plugin_name}' não encontrado")
            return False

        plugin = self.plugins[plugin_name]
        if not plugin["enabled"]:
            print(f"⚠️  Plugin '{plugin_name}' está desativado")
            return False

        try:
            main_py = plugin["path"] / "main.py"
            if not main_py.exists():
                print(f"❌ {main_py} não encontrado")
                return False

            # Importar o módulo dinamicamente
            spec = importlib.util.spec_from_file_location(plugin_name, main_py)
            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_name] = module
            spec.loader.exec_module(module)

            # Criar instância da classe Plugin
            if hasattr(module, 'Plugin'):
                plugin["instance"] = module.Plugin(plugin["config"])
                print(f"✓ Plugin '{plugin_name}' carregado com sucesso")
                return True
            else:
                print(f"❌ Plugin '{plugin_name}' não tem classe 'Plugin'")
                return False

        except Exception as e:
            print(f"❌ Erro ao carregar plugin '{plugin_name}': {e}")
            return False

    def execute_plugin(self, plugin_name, method, *args, **kwargs):
        """Executa um método específico do plugin."""
        if plugin_name not in self.plugins or not self.plugins[plugin_name]["instance"]:
            return {"error": f"Plugin '{plugin_name}' não carregado"}

        plugin = self.plugins[plugin_name]["instance"]
        try:
            if hasattr(plugin, method):
                result = getattr(plugin, method)(*args, **kwargs)
                return {"success": True, "result": result}
            else:
                return {"error": f"Método '{method}' não encontrado"}
        except Exception as e:
            return {"error": str(e)}

    def register_webhook(self, event_name, plugin_name, method):
        """Registra um webhook para um evento específico."""
        if event_name not in self.webhooks:
            self.webhooks[event_name] = []

        self.webhooks[event_name].append({
            "plugin": plugin_name,
            "method": method,
            "registered_at": datetime.now().isoformat()
        })
        print(f"✓ Webhook registrado: {event_name} → {plugin_name}.{method}")

    def trigger_webhook(self, event_name, data=None):
        """Dispara webhooks registrados para um evento."""
        if event_name not in self.webhooks:
            return {"triggered": 0}

        results = []
        for webhook in self.webhooks[event_name]:
            result = self.execute_plugin(
                webhook["plugin"],
                webhook["method"],
                data
            )
            results.append(result)

        print(f"✓ Webhook '{event_name}' disparado para {len(results)} plugin(s)")
        return {"triggered": len(results), "results": results}

    def list_plugins(self):
        """Lista todos os plugins disponíveis."""
        output = []
        for name, plugin in self.plugins.items():
            output.append({
                "name": name,
                "enabled": plugin["enabled"],
                "version": plugin["config"].get("version", "1.0.0"),
                "loaded": plugin["instance"] is not None
            })
        return output

    def get_plugin_info(self, plugin_name):
        """Retorna informações detalhadas de um plugin."""
        if plugin_name not in self.plugins:
            return None
        return self.plugins[plugin_name]["config"]


# Instância global
plugin_manager = PluginManager()


if __name__ == "__main__":
    print("\n🔌 ARMAGEDON - Plugin Manager")
    print("=" * 60)

    manager = PluginManager()
    manager.discover_plugins()

    # Carregar todos os plugins habilitados
    for plugin_name, plugin in manager.plugins.items():
        if plugin["enabled"]:
            manager.load_plugin(plugin_name)

    print("\n" + "=" * 60)
    print("Plugins Carregados:")
    print("=" * 60)
    for plugin_info in manager.list_plugins():
        status = "✓" if plugin_info["loaded"] else "✗"
        print(f"{status} {plugin_info['name']} (v{plugin_info['version']})")
