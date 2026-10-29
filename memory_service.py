#!/usr/bin/env python3
"""
ARMAGEDON — Memória de longo prazo e auto-melhoria (porta 5004)

O que faz:
  • Guarda memórias sobre o usuário (perfil, preferências, projetos, estilo visual) e regras de comportamento
    aprendidas ("instruções"), num SQLite local com o vetor de sentido (embedding) de cada uma.
  • A cada pergunta, monta um bloco de contexto só com o que é RELEVANTE (busca semântica) + o que é sempre
    útil (fixadas, perfil, instruções) — o contexto não cresce sem limite.
  • Aprende sozinho: depois de cada conversa, em segundo plano, a IA decide adicionar / atualizar / apagar
    memórias (ex.: uma preferência nova substitui a antiga em vez de contradizê-la).
  • Auto-melhoria: 👍/👎 e correções viram (a) regras de comportamento, geradas por "reflexão" periódica,
    e (b) lembretes de correção quando o usuário faz uma pergunta parecida com uma já corrigida.

Tudo local. Endpoints em /context, /observe, /memories, /feedback, /reflect, /events, /settings, /export, /import.
"""

import json
import queue
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from flask import Flask, jsonify, request

import emotion_analyzer   # análise emocional de cada mensagem (regras instantâneas + IA opcional)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "memoria"
DB_PATH = DATA_DIR / "memoria.db"
DATA_DIR.mkdir(exist_ok=True)

PORT = 5004
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"   # multilíngue: em português acertou 6/7 contra 2/7 do nomic-embed-text
LLM_MODELS = ["qwen2.5:7b", "dolphin-llama3"]   # extração e reflexão (o primeiro instalado)

KINDS = {
    "perfil": "Perfil",            # quem é o usuário: nome, profissão, cidade, família
    "preferencia": "Preferência",  # como gosta das coisas
    "projeto": "Projeto",          # objetivos e trabalhos em andamento
    "estilo": "Estilo visual",     # preferências para imagens/vídeos
    "instrucao": "Instrução",      # regras de comportamento (aprendidas com o feedback ou escritas pelo usuário)
}

TOP_K = 6              # memórias relevantes por pergunta
MIN_SIM = 0.35         # similaridade mínima (escala do bge-m3: relevantes ~0,37–0,6; sem relação ~0,3)
DUP_SIM = 0.90         # acima disso é a mesma memória (só reforça)
CORRECTION_SIM = 0.80  # pergunta parecida com uma que o usuário corrigiu
RELATIVE_MARGIN = 0.04 # quanto uma memória precisa se destacar da média para entrar no contexto
MAX_INSTRUCTIONS = 12
MAX_BLOCK_CHARS = 1800

app = Flask(__name__)
app.json.sort_keys = False   # mantém a ordem dos campos (ex.: o formato combinado da análise emocional)
db_lock = threading.RLock()
tasks = queue.Queue()     # extração / reflexão: uma de cada vez (CPU)


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

# ============================ BANCO ============================


def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db_lock, db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL, text TEXT NOT NULL, embedding BLOB,
            source TEXT NOT NULL DEFAULT 'manual',     -- manual | auto | reflexao | importado
            confidence REAL NOT NULL DEFAULT 0.8, evidence INTEGER NOT NULL DEFAULT 1,
            pinned INTEGER NOT NULL DEFAULT 0, uses INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL, updated REAL NOT NULL, last_used REAL
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, channel TEXT,
            prompt TEXT NOT NULL, response TEXT, rating TEXT NOT NULL, correction TEXT,
            embedding BLOB, processed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            action TEXT NOT NULL, memory_id INTEGER, kind TEXT, text TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        for k, v in {"auto_learn": "1", "reflect_every": "5", "last_reflect": "0",
                     "emotion_enabled": "1", "emotion_deep": "0"}.items():
            con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))


def setting(key, default=None):
    with db_lock, db() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with db_lock, db() as con:
        con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)))


def event(action, memory_id=None, kind=None, text=None):
    with db_lock, db() as con:
        con.execute("INSERT INTO events (ts, action, memory_id, kind, text) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), action, memory_id, kind, text))


def row_to_memory(r):
    return {"id": r["id"], "kind": r["kind"], "kind_name": KINDS.get(r["kind"], r["kind"]), "text": r["text"],
            "source": r["source"], "confidence": round(r["confidence"], 2), "evidence": r["evidence"],
            "pinned": bool(r["pinned"]), "uses": r["uses"],
            "created": r["created"], "updated": r["updated"], "last_used": r["last_used"]}

# ============================ OLLAMA ============================


def installed_models():
    try:
        return {m["name"].replace(":latest", "") for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()["models"]}
    except Exception:
        return set()


def embed(text, role="document"):
    """Vetor normalizado do texto, ou None se o modelo de embeddings não estiver disponível.
    role ("document" | "query") fica na assinatura para modelos que usam prefixos; o bge-m3 não precisa."""
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": text[:2000], "keep_alive": "30m"},
                          timeout=60)
        vec = np.array(r.json()["embeddings"][0], dtype=np.float32)
    except Exception:
        return None
    n = float(np.linalg.norm(vec))
    return vec / n if n else None


def to_blob(vec):
    return vec.astype(np.float32).tobytes() if vec is not None else None


def from_blob(blob):
    return np.frombuffer(blob, dtype=np.float32) if blob else None


def llm_json(system, user, num_predict=500):
    models = [m for m in LLM_MODELS if m in installed_models()]
    if not models:
        raise RuntimeError("Nenhum modelo de linguagem disponível no Ollama.")
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json={
        "model": models[0], "stream": False, "format": "json", "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_predict": num_predict},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })
    return json.loads(r.json()["message"]["content"])

# ============================ MEMÓRIAS ============================


def all_memories(kind=None):
    with db_lock, db() as con:
        sql = "SELECT * FROM memories" + (" WHERE kind = ?" if kind else "") + " ORDER BY pinned DESC, updated DESC"
        return con.execute(sql, (kind,) if kind else ()).fetchall()


_WORD = re.compile(r"\w{3,}", re.UNICODE)


def keyword_sim(a, b):
    """Plano B quando não há embeddings: sobreposição de palavras."""
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(wa & wb) / (len(wa | wb) or 1)


def search(query, k=TOP_K, kinds=None, min_sim=MIN_SIM, qvec=None, relative=False):
    """Memórias mais parecidas com a consulta: [(row, sim)].
    relative=True: além do mínimo, exige que a memória se destaque da média das outras para essa consulta
    (os embeddings dão notas "espremidas": até o que não tem relação marca ~0,5)."""
    all_rows = all_memories()
    rows = [r for r in all_rows if not kinds or r["kind"] in kinds]
    if not rows:
        return []
    qvec = qvec if qvec is not None else embed(query, "query")

    def sim_of(r):
        vec = from_blob(r["embedding"])
        if qvec is not None and vec is not None and len(vec) == len(qvec):
            return float(np.dot(qvec, vec))
        return keyword_sim(query, r["text"]) * 1.6   # plano B: escala aproximada para o mesmo limiar

    scored = [(r, sim_of(r)) for r in rows]
    floor = min_sim
    if relative and len(all_rows) >= 4:
        baseline = float(np.median([sim_of(r) for r in all_rows]))
        floor = max(min_sim, baseline + RELATIVE_MARGIN)
    scored = [x for x in scored if x[1] >= floor]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def add_memory(kind, text, source="manual", confidence=0.8, pinned=False):
    """Adiciona, ou reforça uma memória quase idêntica. Retorna (id, 'novo'|'reforçado')."""
    kind = kind if kind in KINDS else "preferencia"
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:400]
    if len(text) < 4:
        raise ValueError("Memória vazia.")
    vec = embed(text)
    dup = search(text, k=1, kinds=[kind], min_sim=DUP_SIM, qvec=vec)
    now = time.time()
    with db_lock, db() as con:
        if dup:
            mid = dup[0][0]["id"]
            con.execute("UPDATE memories SET evidence = evidence + 1, confidence = MIN(1.0, MAX(confidence, ?) + 0.05), "
                        "updated = ?, pinned = MAX(pinned, ?) WHERE id = ?", (confidence, now, int(pinned), mid))
            return mid, "reforçado"
        cur = con.execute("INSERT INTO memories (kind, text, embedding, source, confidence, pinned, created, updated) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (kind, text, to_blob(vec), source, confidence, int(pinned), now, now))
        mid = cur.lastrowid
    event("novo", mid, kind, text)
    return mid, "novo"


def update_memory(mid, text=None, kind=None, pinned=None, source=None):
    with db_lock, db() as con:
        row = con.execute("SELECT * FROM memories WHERE id = ?", (mid,)).fetchone()
        if not row:
            raise ValueError("Memória não encontrada.")
        new_text = re.sub(r"\s+", " ", text).strip()[:400] if text else row["text"]
        vec = embed(new_text) if text and new_text != row["text"] else from_blob(row["embedding"])
        con.execute("UPDATE memories SET text = ?, kind = ?, pinned = ?, embedding = ?, source = ?, updated = ? WHERE id = ?",
                    (new_text, kind if kind in KINDS else row["kind"], row["pinned"] if pinned is None else int(pinned),
                     to_blob(vec), source or row["source"], time.time(), mid))
    if text and new_text != row["text"]:
        event("atualizado", mid, kind or row["kind"], new_text)
    return mid


def delete_memory(mid, log_event=True):
    with db_lock, db() as con:
        row = con.execute("SELECT kind, text FROM memories WHERE id = ?", (mid,)).fetchone()
        con.execute("DELETE FROM memories WHERE id = ?", (mid,))
    if row and log_event:
        event("esquecido", mid, row["kind"], row["text"])
    return bool(row)

# ============================ CONTEXTO PARA O MODELO ============================


def build_context(prompt, channel="chat"):
    """Bloco de texto para o system prompt + as memórias usadas (para a página mostrar)."""
    rows = all_memories()
    if not rows and channel != "chat":
        return "", []
    qvec = embed(prompt, "query") if prompt.strip() else None
    chosen, seen = [], set()

    def take(r):
        if r["id"] not in seen:
            seen.add(r["id"])
            chosen.append(r)

    if channel == "imagem":
        for r in rows:
            if r["kind"] == "estilo" and (r["pinned"] or len(chosen) < 6):
                take(r)
    else:
        for r in rows:                                        # sempre: fixadas, perfil e instruções
            if r["pinned"] or r["kind"] == "perfil":
                take(r)
        for r in sorted([r for r in rows if r["kind"] == "instrucao"], key=lambda r: -r["confidence"])[:MAX_INSTRUCTIONS]:
            take(r)
        for r, _ in search(prompt, TOP_K, ["preferencia", "projeto", "estilo"], qvec=qvec, relative=True):   # relevantes
            take(r)

    corrections = []
    if channel != "imagem" and qvec is not None:
        with db_lock, db() as con:
            fb = con.execute("SELECT prompt, correction, embedding FROM feedback WHERE correction <> '' "
                             "ORDER BY id DESC LIMIT 300").fetchall()
        for f in fb:
            vec = from_blob(f["embedding"])
            if vec is not None and len(vec) == len(qvec) and float(np.dot(qvec, vec)) >= CORRECTION_SIM:
                corrections.append(f)
            if len(corrections) >= 2:
                break

    sections = []
    about = [r for r in chosen if r["kind"] in ("perfil", "preferencia", "projeto", "estilo")]
    rules = [r for r in chosen if r["kind"] == "instrucao"]
    if about:
        sections.append("O QUE VOCÊ SABE SOBRE O USUÁRIO (memória de longo prazo; use quando for útil, sem repetir isso para ele):\n"
                        + "\n".join(f"- {r['text']}" for r in about))
    if rules:
        sections.append("COMO O USUÁRIO GOSTA QUE VOCÊ RESPONDA (aprendido com as avaliações dele; siga sempre):\n"
                        + "\n".join(f"- {r['text']}" for r in rules))
    for c in corrections:
        sections.append(f"O USUÁRIO JÁ CORRIGIU UMA PERGUNTA PARECIDA:\nPergunta: {c['prompt'][:300]}\n"
                        f"O que ele disse que estava certo: {c['correction'][:500]}")
    if channel == "imagem" and about:
        sections = ["Preferências visuais do usuário (aplique quando não conflitarem com o pedido):\n"
                    + "\n".join(f"- {r['text']}" for r in about)]
    block = "\n\n".join(sections)[:MAX_BLOCK_CHARS]

    if chosen:
        now = time.time()
        with db_lock, db() as con:
            con.executemany("UPDATE memories SET uses = uses + 1, last_used = ? WHERE id = ?", [(now, r["id"]) for r in chosen])
    used = [{"id": r["id"], "kind": r["kind"], "kind_name": KINDS[r["kind"]], "text": r["text"]} for r in chosen]
    return block, used + [{"id": None, "kind": "correcao", "kind_name": "Correção", "text": c["correction"][:120]}
                          for c in corrections]

# ============================ APRENDER COM A CONVERSA ============================

EXTRACT_SYSTEM = """You manage the long-term memory of a personal AI assistant. The user speaks Brazilian Portuguese.
You receive one exchange (user message + assistant answer) and the EXISTING memories that look related.
Decide what is worth remembering for FUTURE conversations: durable facts about the user, their preferences, ongoing
projects, visual style preferences for images/videos, and explicit instructions about how the assistant should behave.
Ignore small talk, one-off requests, anything temporary, and facts about the world that are not about the user.
Never store passwords, card numbers, documents or other secrets.
If the user says "lembre que", "anote que", "guarde que" → always store it. If the user says "esqueça" → delete the matching memory.
If new information contradicts or refines an existing memory → "update" that memory (the newest information wins).
Split different facts into separate operations (e.g. the user's profession → "perfil"; what they are working on now → "projeto").
Reply ONLY with JSON: {"ops": [{"op": "add"|"update"|"delete", "id": <existing id for update/delete>,
"kind": "perfil"|"preferencia"|"projeto"|"estilo"|"instrucao", "text": "<short sentence in Brazilian Portuguese,
third person, e.g. 'Prefere respostas curtas e diretas.'>"}]}
Use {"ops": []} when there is nothing worth remembering (this is the most common case)."""

_EXPLICIT = re.compile(r"\b(lembr[ae]|anote|guarde|memorize|esque[cç]a|prefiro|gosto|n[aã]o gosto|odeio|meu nome|me chame|"
                       r"sempre|nunca|eu sou|trabalho|moro|meu projeto|estou fazendo|minha|meu)\b", re.I)


# fala do próprio usuário (o "me" de "me explica..." fica de fora: é só um pedido)
_FIRST_PERSON = re.compile(r"\b(eu|meu|minha|meus|minhas|comigo|n[oó]s|nosso|nossa|sou|estou|tenho|moro|trabalho|"
                           r"fa[cç]o|estudo|prefiro|gosto|quero que|preciso que)\b", re.I)


def worth_learning(user):
    """Só gasta a IA com frases que falam do usuário (perguntas gerais como "qual a capital da Austrália?" não)."""
    return bool(_EXPLICIT.search(user) or _FIRST_PERSON.search(user))


def learn_from_exchange(user, assistant, channel):
    related = search(f"{user}\n{assistant[:400]}", k=8, min_sim=0.45)
    existing = "\n".join(f"[id {r['id']}] ({r['kind']}) {r['text']}" for r, _ in related) or "(nenhuma)"
    data = llm_json(EXTRACT_SYSTEM, f"EXISTING MEMORIES:\n{existing}\n\nUSER ({channel}): {user[:1500]}\n\n"
                                    f"ASSISTANT: {assistant[:1200]}", 400)
    valid_ids = {r["id"] for r, _ in related}
    done = []
    for op in (data.get("ops") or [])[:5]:
        if not isinstance(op, dict):
            continue
        kind, text, mid = op.get("kind"), str(op.get("text") or "").strip(), op.get("id")
        try:
            mid = int(mid) if mid is not None else None
        except (TypeError, ValueError):
            mid = None
        if op.get("op") == "delete" and mid in valid_ids:
            delete_memory(mid)
            done.append(f"esqueceu #{mid}")
        elif op.get("op") == "update" and mid in valid_ids and text:
            update_memory(mid, text=text, kind=kind, source="auto")
            done.append(f"atualizou #{mid}: {text}")
        elif op.get("op") == "add" and text:
            nid, how = add_memory(kind, text, source="auto", confidence=0.75)
            done.append(f"{how} #{nid}: {text}")
    if done:
        log("🧠 " + " | ".join(done))


_REMEMBER = re.compile(r"^\s*(?:por favor,?\s*)?(?:lembr[ae](?:-se)?(?:\s+de)?\s+que|anote(?:\s+que)?|guarde(?:\s+que)?|"
                       r"memorize(?:\s+que)?)\s+(.{4,})$", re.I | re.S)
_FORGET = re.compile(r"^\s*(?:por favor,?\s*)?esque[cç]a(?:\s+que|\s+de|\s+o que|\s+a\s+mem[oó]ria)?\s+(.{3,})$", re.I | re.S)


def explicit_command(user):
    """"lembre que X" / "esqueça X": efeito imediato, sem esperar a IA. Retorna uma frase ou None."""
    m = _REMEMBER.match(user)
    if m:
        text = m.group(1).strip().rstrip(".!")
        # "meu/minha" ficaria ambíguo para o modelo (pareceria ser dele); deixa claro que é do usuário
        text = f"O usuário pediu para lembrar: {text}."
        mid, how = add_memory("preferencia", text, source="manual", confidence=1.0, pinned=False)
        return f"{'eu já sabia disso' if how == 'reforçado' else 'vou lembrar'}: {m.group(1).strip().rstrip('.!')}"
    m = _FORGET.match(user)
    if m:
        hits = search(m.group(1), k=1, min_sim=0.55)
        if hits:
            delete_memory(hits[0][0]["id"])
            return f"esqueci: {hits[0][0]['text'].replace('O usuário pediu para lembrar: ', '')}"
    return None

# ============================ AUTO-MELHORIA (REFLEXÃO) ============================

REFLECT_SYSTEM = """You improve a personal AI assistant from its user's feedback. The user speaks Brazilian Portuguese.
You receive recent rated exchanges (👍 liked / 👎 disliked, sometimes with the user's correction) and the CURRENT
behavior rules. Find PATTERNS in what the user likes and dislikes (length, tone, format, language, level of detail,
examples, accuracy on certain topics...) and return the UPDATED full list of behavior rules.
Rules must be general (not about one specific question), short, actionable, in Brazilian Portuguese, imperative form
(e.g. "Responda de forma curta e direta, sem introduções."). Keep good existing rules, merge duplicates, remove rules
the new feedback contradicts. At most 12 rules. Only create a rule when the evidence supports it.
Reply ONLY with JSON: {"rules": [{"text": "...", "evidence": <how many feedback items support it>}]}"""


def reflect():
    """Gera/atualiza as regras de comportamento a partir do feedback. Retorna as regras novas."""
    with db_lock, db() as con:
        fb = con.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 40").fetchall()
    if not fb:
        return []
    current = [r for r in all_memories("instrucao") if r["source"] == "reflexao"]
    lines = []
    for f in fb:
        line = f"{'👍' if f['rating'] == 'up' else '👎'} PERGUNTA: {f['prompt'][:300]}\nRESPOSTA: {(f['response'] or '')[:400]}"
        if f["correction"]:
            line += f"\nCORREÇÃO DO USUÁRIO: {f['correction'][:400]}"
        lines.append(line)
    rules_txt = "\n".join(f"- {r['text']}" for r in current) or "(nenhuma ainda)"
    data = llm_json(REFLECT_SYSTEM, f"CURRENT RULES:\n{rules_txt}\n\nFEEDBACK:\n\n" + "\n\n".join(lines), 600)
    rules = [r for r in (data.get("rules") or []) if isinstance(r, dict) and str(r.get("text", "")).strip()][:MAX_INSTRUCTIONS]
    old_texts = {r["text"] for r in current}
    for r in current:   # as regras escritas pela reflexão são substituídas; as do usuário ficam
        if not r["pinned"]:
            delete_memory(r["id"], log_event=False)
    new = []
    for rule in rules:
        text = str(rule["text"]).strip()
        evidence = int(rule.get("evidence") or 1) if str(rule.get("evidence") or "1").isdigit() else 1
        mid, how = add_memory("instrucao", text, source="reflexao", confidence=min(1.0, 0.6 + 0.08 * evidence))
        if text not in old_texts:
            new.append(text)
        else:   # mesma regra de antes: não anuncia de novo como "aprendi"
            with db_lock, db() as con:
                con.execute("DELETE FROM events WHERE memory_id = ? AND action = 'novo'", (mid,))
    with db_lock, db() as con:
        con.execute("UPDATE feedback SET processed = 1")
    set_setting("last_reflect", time.time())
    log(f"🔁 Reflexão: {len(rules)} regras ({len(new)} novas)")
    return new

# ============================ FILA DE TAREFAS ============================


def worker():
    while True:
        kind, payload = tasks.get()
        try:
            if kind == "learn":
                learn_from_exchange(*payload)
            elif kind == "reflect":
                reflect()
        except Exception as e:
            log(f"⚠️  Tarefa {kind} falhou: {e}")

# ============================ API ============================


def body():
    return request.get_json(silent=True) or {}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "embeddings": embed("teste") is not None, "memories": len(all_memories())})


@app.route("/context", methods=["POST"])
def context_route():
    d = body()
    block, used = build_context(str(d.get("prompt") or ""), d.get("channel") or "chat")
    return jsonify({"block": block, "used": used})


@app.route("/observe", methods=["POST"])
def observe_route():
    """Chamado depois de cada resposta. Comandos diretos agem na hora; o resto vai para a fila de aprendizado."""
    d = body()
    user, assistant = str(d.get("user") or "").strip(), str(d.get("assistant") or "").strip()
    if not user:
        return jsonify({"ok": False})
    direct = explicit_command(user)
    queued = False
    if not direct and setting("auto_learn", "1") == "1" and worth_learning(user):
        tasks.put(("learn", (user, assistant, d.get("channel") or "chat")))
        queued = True
    return jsonify({"ok": True, "direct": direct, "queued": queued})


@app.route("/memories")
def memories_list():
    return jsonify({"memories": [row_to_memory(r) for r in all_memories(request.args.get("kind"))],
                    "kinds": [{"id": k, "name": v} for k, v in KINDS.items()]})


@app.route("/memories", methods=["POST"])
def memories_add():
    d = body()
    try:
        mid, how = add_memory(d.get("kind"), d.get("text"), "manual", 1.0, bool(d.get("pinned")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": mid, "status": how})


@app.route("/memories/<int:mid>", methods=["PATCH"])
def memories_patch(mid):
    d = body()
    try:
        update_memory(mid, text=d.get("text"), kind=d.get("kind"), pinned=d.get("pinned"),
                      source="manual" if d.get("text") else None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"ok": True})


@app.route("/memories/<int:mid>", methods=["DELETE"])
def memories_delete(mid):
    return jsonify({"ok": delete_memory(mid)})


@app.route("/memories/forget-all", methods=["POST"])
def memories_forget_all():
    if body().get("confirm") != "ESQUECER":
        return jsonify({"error": "Confirmação ausente."}), 400
    with db_lock, db() as con:
        n = con.execute("DELETE FROM memories").rowcount
        con.execute("DELETE FROM feedback")
        con.execute("DELETE FROM events")
    log(f"🗑  Esqueceu tudo ({n} memórias)")
    return jsonify({"deleted": n})


@app.route("/feedback", methods=["POST"])
def feedback_route():
    d = body()
    prompt, rating = str(d.get("prompt") or "").strip(), d.get("rating")
    if not prompt or rating not in ("up", "down"):
        return jsonify({"error": "prompt e rating (up/down) são obrigatórios"}), 400
    correction = str(d.get("correction") or "").strip()
    with db_lock, db() as con:
        con.execute("INSERT INTO feedback (ts, channel, prompt, response, rating, correction, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (time.time(), d.get("channel") or "chat", prompt[:4000], str(d.get("response") or "")[:6000], rating,
                     correction[:3000], to_blob(embed(prompt, "query"))))   # comparada depois com outras perguntas
        pending = con.execute("SELECT COUNT(*) FROM feedback WHERE processed = 0").fetchone()[0]
    every = int(setting("reflect_every", "5"))
    reflecting = pending >= every
    if reflecting:
        tasks.put(("reflect", None))
    return jsonify({"ok": True, "pending": pending, "reflect_every": every, "reflecting": reflecting})


@app.route("/feedback/stats")
def feedback_stats():
    with db_lock, db() as con:
        row = con.execute("SELECT COUNT(*) total, SUM(rating = 'up') up, SUM(rating = 'down') down, "
                          "SUM(correction <> '') corr, SUM(processed = 0) pending FROM feedback").fetchone()
    return jsonify({"total": row["total"] or 0, "up": row["up"] or 0, "down": row["down"] or 0,
                    "corrections": row["corr"] or 0, "pending": row["pending"] or 0,
                    "reflect_every": int(setting("reflect_every", "5")), "last_reflect": float(setting("last_reflect", "0")),
                    "busy": not tasks.empty()})


@app.route("/reflect", methods=["POST"])
def reflect_route():
    tasks.put(("reflect", None))
    return jsonify({"started": True})


@app.route("/events")
def events_route():
    since = request.args.get("since", type=int)
    with db_lock, db() as con:
        last = con.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
        rows = [] if since is None else con.execute("SELECT * FROM events WHERE id > ? ORDER BY id", (since,)).fetchall()
    return jsonify({"last": last, "events": [dict(r) for r in rows]})


@app.route("/emotion", methods=["POST"])
def emotion_route():
    """Análise emocional de uma mensagem (formato combinado) + o trecho de orientação para o system prompt.
    Não é guardada: emoções são dados sensíveis e servem só para ajustar a resposta do momento."""
    d = body()
    text = str(d.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text é obrigatório"}), 400
    t0 = time.time()
    deep = d.get("deep") if d.get("deep") is not None else setting("emotion_deep", "0") == "1"
    if deep:
        analysis, signals, method = emotion_analyzer.analyze_deep(text, lambda s, u: llm_json(s, u, 400))
    else:
        analysis, signals = emotion_analyzer.analyze(text)
        method = "regras"
    return jsonify({"analise": analysis, "sinais": signals, "metodo": method,
                    "orientacao": emotion_analyzer.guidance(analysis, signals),
                    "ms": round((time.time() - t0) * 1000)})


@app.route("/settings", methods=["GET", "POST"])
def settings_route():
    if request.method == "POST":
        d = body()
        if "auto_learn" in d:
            set_setting("auto_learn", "1" if d["auto_learn"] else "0")
        if "reflect_every" in d:
            set_setting("reflect_every", max(1, min(50, int(d["reflect_every"]))))
        for key in ("emotion_enabled", "emotion_deep"):
            if key in d:
                set_setting(key, "1" if d[key] else "0")
    return jsonify({"auto_learn": setting("auto_learn") == "1", "reflect_every": int(setting("reflect_every", "5")),
                    "emotion_enabled": setting("emotion_enabled", "1") == "1", "emotion_deep": setting("emotion_deep", "0") == "1",
                    "embeddings": embed("teste") is not None})


@app.route("/export")
def export_route():
    data = {"version": 1, "exported": datetime.now().isoformat(timespec="seconds"),
            "memories": [{k: m[k] for k in ("kind", "text", "source", "confidence", "evidence", "pinned")}
                         for m in map(row_to_memory, all_memories())]}
    resp = app.response_class(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json")
    resp.headers["Content-Disposition"] = f"attachment; filename=memoria_armagedon_{datetime.now():%Y%m%d}.json"
    return resp


@app.route("/import", methods=["POST"])
def import_route():
    try:
        data = json.loads(request.files["file"].read().decode("utf-8")) if "file" in request.files else body()
        count = 0
        for m in data.get("memories", []):
            add_memory(m.get("kind"), m.get("text"), "importado", float(m.get("confidence", 0.8)), bool(m.get("pinned")))
            count += 1
    except Exception as e:
        return jsonify({"error": f"Arquivo inválido: {e}"}), 400
    return jsonify({"imported": count})


def reindex():
    """Recalcula vetores ausentes ou de outro modelo (ex.: depois de trocar o EMBED_MODEL)."""
    probe = embed("teste")
    if probe is None:
        return
    fixed = 0
    for r in all_memories():
        vec = from_blob(r["embedding"])
        if vec is None or len(vec) != len(probe):
            with db_lock, db() as con:
                con.execute("UPDATE memories SET embedding = ? WHERE id = ?", (to_blob(embed(r["text"])), r["id"]))
            fixed += 1
    with db_lock, db() as con:
        rows = con.execute("SELECT id, prompt, embedding FROM feedback").fetchall()
    for f in rows:
        vec = from_blob(f["embedding"])
        if vec is None or len(vec) != len(probe):
            with db_lock, db() as con:
                con.execute("UPDATE feedback SET embedding = ? WHERE id = ?", (to_blob(embed(f["prompt"], "query")), f["id"]))
            fixed += 1
    if fixed:
        log(f"🔄 Reindexou {fixed} item(ns) com {EMBED_MODEL}")


if __name__ == "__main__":
    init_db()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=reindex, daemon=True).start()
    log(f"🧠 ARMAGEDON — Memória de longo prazo em http://127.0.0.1:{PORT}")
    log(f"   banco: {DB_PATH} · {len(all_memories())} memórias · embeddings: {'ok' if embed('teste') is not None else 'indisponível (usando palavras-chave)'}")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
