#!/usr/bin/env python3
"""
Plugin Executor - Executa métodos de plugins via plugin_manager
Chamado pelo server.js quando APIs de plugin são requisitadas
"""

import sys
import json
from plugin_manager import PluginManager

def execute_plugin(plugin_name, method_name, params):
    """Executa um método de um plugin."""
    try:
        manager = PluginManager()
        manager.discover_plugins()

        # Carregar plugin
        if not manager.load_plugin(plugin_name):
            return {
                "success": False,
                "error": f"Plugin '{plugin_name}' não carregado"
            }

        # Executar método
        result = manager.execute_plugin(plugin_name, method_name, **params)
        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "error": "Uso: plugin_executor.py <plugin_name> <method_name> [params_json]"
        }))
        sys.exit(1)

    plugin_name = sys.argv[1]
    method_name = sys.argv[2]
    params_json = sys.argv[3] if len(sys.argv) > 3 else '{}'

    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        params = {}

    result = execute_plugin(plugin_name, method_name, params)
    print(json.dumps(result))
    sys.exit(0 if result.get('success', False) else 1)
