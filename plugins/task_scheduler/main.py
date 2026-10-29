#!/usr/bin/env python3
"""
Task Scheduler Plugin - Agendador de tarefas automáticas
Suporta cron, intervalos e execução imediata
"""

import threading
import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class Plugin:
    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "Task Scheduler")
        self.tasks = {}
        self.task_history = []
        self.scheduler_thread = None
        self.running = False
        self.tasks_file = "scheduled_tasks.json"

        print(f"✓ {self.name} inicializado")

        # Carregar tarefas salvas
        self._load_tasks()

        # Iniciar scheduler
        if config.get("config", {}).get("enable_scheduler", True):
            self._start_scheduler()

    def create_task(self, task_name, task_type, action, schedule, enabled=True):
        """Cria uma nova tarefa agendada.

        task_type: 'cron', 'interval', 'at_time'
        action: 'generate_image', 'backup', 'cleanup', 'script'
        schedule:
            - cron: "0 0 * * *" (midnight diariamente)
            - interval: 3600 (segundos)
            - at_time: "14:30" (horário específico)
        """
        try:
            task_id = len(self.tasks) + 1

            task = {
                "id": task_id,
                "name": task_name,
                "type": task_type,
                "action": action,
                "schedule": schedule,
                "enabled": enabled,
                "created_at": datetime.now().isoformat(),
                "last_run": None,
                "next_run": self._calculate_next_run(task_type, schedule),
                "execution_count": 0,
                "last_result": None
            }

            self.tasks[task_id] = task
            self._save_tasks()

            return {
                "success": True,
                "task_id": task_id,
                "message": f"Tarefa '{task_name}' criada com sucesso"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_task(self, task_id):
        """Deleta uma tarefa agendada."""
        try:
            if task_id in self.tasks:
                task_name = self.tasks[task_id]["name"]
                del self.tasks[task_id]
                self._save_tasks()
                return {
                    "success": True,
                    "message": f"Tarefa '{task_name}' deletada"
                }
            else:
                return {"success": False, "error": "Tarefa não encontrada"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tasks(self):
        """Lista todas as tarefas agendadas."""
        try:
            tasks_list = []
            for task_id, task in self.tasks.items():
                tasks_list.append({
                    "id": task_id,
                    "name": task["name"],
                    "type": task["type"],
                    "schedule": task["schedule"],
                    "enabled": task["enabled"],
                    "next_run": task["next_run"],
                    "execution_count": task["execution_count"]
                })

            return {
                "success": True,
                "total": len(tasks_list),
                "tasks": tasks_list
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_task_now(self, task_id):
        """Executa uma tarefa imediatamente."""
        try:
            if task_id not in self.tasks:
                return {"success": False, "error": "Tarefa não encontrada"}

            task = self.tasks[task_id]
            result = self._execute_action(task)

            # Atualizar histórico
            self.task_history.append({
                "task_id": task_id,
                "task_name": task["name"],
                "executed_at": datetime.now().isoformat(),
                "result": result
            })

            # Atualizar tarefa
            task["last_run"] = datetime.now().isoformat()
            task["execution_count"] += 1
            task["last_result"] = result
            task["next_run"] = self._calculate_next_run(task["type"], task["schedule"])
            self._save_tasks()

            return {
                "success": True,
                "task_name": task["name"],
                "result": result,
                "execution_count": task["execution_count"]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pause_task(self, task_id, pause=True):
        """Pausa ou retoma uma tarefa."""
        try:
            if task_id not in self.tasks:
                return {"success": False, "error": "Tarefa não encontrada"}

            task = self.tasks[task_id]
            task["enabled"] = not pause

            self._save_tasks()

            status = "pausada" if pause else "retomada"
            return {
                "success": True,
                "message": f"Tarefa '{task['name']}' {status}",
                "enabled": task["enabled"]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_history(self, limit=100):
        """Retorna histórico de execuções."""
        try:
            return {
                "success": True,
                "total": len(self.task_history),
                "history": self.task_history[-limit:]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calculate_next_run(self, task_type, schedule):
        """Calcula próxima execução baseado no tipo de tarefa."""
        now = datetime.now()

        if task_type == "interval":
            # Adicionar segundos
            return (now + timedelta(seconds=int(schedule))).isoformat()

        elif task_type == "at_time":
            # Executar em horário específico
            hour, minute = map(int, schedule.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0)

            if next_run <= now:
                # Se já passou, agendar para amanhã
                next_run = next_run + timedelta(days=1)

            return next_run.isoformat()

        else:  # cron
            # Simulação simples: próxima meia-noite
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()

    def _execute_action(self, task):
        """Executa a ação da tarefa."""
        action = task["action"]

        actions = {
            "generate_image": self._action_generate_image,
            "backup": self._action_backup,
            "cleanup": self._action_cleanup,
            "script": self._action_script,
        }

        if action in actions:
            return actions[action](task)
        else:
            return f"Ação '{action}' não implementada"

    def _action_generate_image(self, task):
        """Gera uma imagem automaticamente."""
        # Simular geração de imagem
        return {
            "action": "generate_image",
            "status": "sucesso",
            "message": "Imagem gerada automaticamente",
            "filename": f"auto_image_{datetime.now():%Y%m%d_%H%M%S}.png"
        }

    def _action_backup(self, task):
        """Faz backup do banco de dados."""
        # Simular backup
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)

        return {
            "action": "backup",
            "status": "sucesso",
            "message": "Backup realizado com sucesso",
            "backup_dir": backup_dir
        }

    def _action_cleanup(self, task):
        """Limpa cache e arquivos antigos."""
        dirs_to_clean = ["images_edited", "video_summaries"]
        cleaned = 0

        for dir_name in dirs_to_clean:
            if os.path.exists(dir_name):
                for file in os.listdir(dir_name):
                    # Aqui poderia implementar lógica para deletar apenas arquivos antigos
                    cleaned += 1

        return {
            "action": "cleanup",
            "status": "sucesso",
            "message": f"Limpeza concluída",
            "files_processed": cleaned
        }

    def _action_script(self, task):
        """Executa um script customizado."""
        script = task.get("script", "")

        return {
            "action": "script",
            "status": "sucesso",
            "message": "Script executado com sucesso",
            "script_output": "Saída do script aqui"
        }

    def _start_scheduler(self):
        """Inicia a thread do scheduler."""
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        print("✓ Scheduler iniciado")

    def _scheduler_loop(self):
        """Loop principal do scheduler."""
        check_interval = self.config.get("config", {}).get("check_interval_seconds", 60)

        while self.running:
            try:
                now = datetime.now()

                for task_id, task in self.tasks.items():
                    if not task["enabled"]:
                        continue

                    next_run = datetime.fromisoformat(task["next_run"])

                    if now >= next_run:
                        # Executar tarefa
                        print(f"🔄 Executando tarefa: {task['name']}")
                        result = self._execute_action(task)

                        # Atualizar histórico
                        self.task_history.append({
                            "task_id": task_id,
                            "task_name": task["name"],
                            "executed_at": now.isoformat(),
                            "result": result
                        })

                        # Atualizar tarefa
                        task["last_run"] = now.isoformat()
                        task["execution_count"] += 1
                        task["last_result"] = result
                        task["next_run"] = self._calculate_next_run(task["type"], task["schedule"])

                # Salvar estado
                self._save_tasks()

                # Aguardar próxima verificação
                import time
                time.sleep(check_interval)

            except Exception as e:
                print(f"❌ Erro no scheduler: {e}")

    def _save_tasks(self):
        """Salva tarefas em arquivo JSON."""
        try:
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Erro ao salvar tarefas: {e}")

    def _load_tasks(self):
        """Carrega tarefas do arquivo JSON."""
        try:
            if os.path.exists(self.tasks_file):
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f)
                print(f"✓ {len(self.tasks)} tarefa(s) carregada(s)")
        except Exception as e:
            print(f"⚠️  Erro ao carregar tarefas: {e}")

    def get_info(self):
        """Retorna informações do plugin."""
        return {
            "name": self.name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description"),
            "author": self.config.get("author"),
            "total_tasks": len(self.tasks),
            "running_tasks": sum(1 for t in self.tasks.values() if t["enabled"]),
            "total_executions": sum(t["execution_count"] for t in self.tasks.values())
        }
