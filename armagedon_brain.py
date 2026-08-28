#!/usr/bin/env python3
"""ARMAGEDON - Cérebro: RAG (documentos) + Memória de longo prazo.

Serviço Flask na porta 5002. O hub (server.js) chama /augment antes de
mandar a pergunta pro Ollama, e injeta o bloco de contexto no prompt.

Endpoints:
  GET    /health
  GET    /status                       -> docs indexados, nº de trechos, nº de fatos
  POST   /ingest                        -> (re)indexa a pasta documentos/
  POST   /augment  {prompt, use_rag}    -> {system_block, sources}
  GET    /memory                        -> lista de fatos
  POST   /memory   {categoria, texto}   -> adiciona fato
  DELETE /memory/<id>                   -> remove fato
  POST   /memory/extract {text}         -> LLM extrai fatos duráveis do texto e salva

Embeddings: modelo `nomic-embed-text` rodando no próprio Ollama.
Vetores: ChromaDB (se instalado) ou fallback em numpy + arquivo .npz.
"""
import os, sys, json, sqlite3, time, glob, urllib.request
from datetime import datetime
from flask import Flask, request, jsonify

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "documentos")
DATA_DIR = os.path.join(HERE, "brain_data")
DB_PATH = os.path.join(DATA_DIR, "memoria.db")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
NPZ_PATH = os.path.join(DATA_DIR, "vetores.npz")
MANIFEST = os.path.join(DATA_DIR, "indexados.json")
FEEDBACK_PATH = os.path.join(DATA_DIR, "feedback.jsonl")   # Fase 6: dataset de correções

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "armagedon"
TOP_K = 4
MIN_SCORE = 0.35            # similaridade de cosseno mínima pra usar um trecho
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 200

# --- Busca na web (informação em tempo real) --------------------------------
WEB_RESULTS = 4            # quantos resultados de busca considerar
WEB_FETCH = 2             # quantas páginas abrir e extrair texto
WEB_PAGE_CHARS = 1500     # máx. de texto por página injetado
WEB_TIMEOUT = 6           # segundos por request

# --- Roteador de modelos -----------------------------------------------------
import re
MODEL_DEFAULT = "armagedon"          # conversa, factual, código do dia a dia
MODEL_RACIOCINIO = "deepseek-r1:7b"  # matemática, lógica, problema de várias etapas
MODEL_CRIATIVO = "armagedon-livre"   # história, poema, roteiro, sem censura (Hermes 3, sem filtro)

_RE_RACIOCINIO = re.compile(
    r"\b(calcul\w*|quant[oa]s?|porcentagem|percentual|probabilidad\w*|deriv\w*|integr\w*|"
    r"equa\w*|fatori\w*|prov[ae]\b|demonstr\w*|resolv\w*|otimiz\w*|algoritm\w*|complexidad\w*|"
    r"big-?o|racioc\w*|l[oó]gic\w*|passo a passo|quebra-?cabe\w*|sudoku|xadrez|"
    r"quantas? (vezes|maneiras|formas)|qual (o|a) (resultado|valor) de)\b", re.I)
_RE_MATE_SIMB = re.compile(r"[=×÷√∑∫≤≥≠%]|\d+\s*[-+*/^]\s*\d+|\bx\s*=\s*-?\d")
_RE_CRIATIVO = re.compile(
    r"\b(conto|poema|hist[oó]ria|narrativ\w*|fic[cç][aã]o|roteiro|letra de m[uú]sica|"
    r"escrev[ae] (um|uma) (conto|poema|hist[oó]ria|narrativa|texto|cr[oô]nica)|"
    r"crie (um|uma) (conto|poema|hist[oó]ria)|sombri[ao]|sem censura|nsfw)\b", re.I)


def route_model(prompt):
    """Escolhe o modelo pela pergunta. Só heurística (rápido, sem custo)."""
    p = (prompt or "").strip()
    if not p:
        return MODEL_DEFAULT, "vazio"
    if _RE_RACIOCINIO.search(p) or _RE_MATE_SIMB.search(p):
        return MODEL_RACIOCINIO, "lógica/matemática"
    if _RE_CRIATIVO.search(p):
        return MODEL_CRIATIVO, "escrita criativa"
    return MODEL_DEFAULT, "conversa/geral"


# --- Detecção de pergunta que pede informação atual -------------------------
_RE_TEMPO_REAL = re.compile(
    r"\b(hoje|agora|neste momento|atual\w*|recent\w*|[uú]ltim[ao]s?|not[ií]cia\w*|"
    r"cota[cç][aã]o|pre[cç]o d[eo]|d[oó]lar|euro|bitcoin|a[cç][aã]o d[aeo]|bolsa|"
    r"clima|previs[aã]o do tempo|temperatura em|quem (ganhou|venceu)|resultado d[oe]|"
    r"placar|lan[cç]amento|vers[aã]o (atual|mais recente)|quando (sai|lan[cç]a)|"
    r"20(2[6-9]|[3-9]\d))\b", re.I)


def precisa_web(prompt):
    return bool(_RE_TEMPO_REAL.search(prompt or ""))


def web_search(query, n=WEB_RESULTS):
    """Retorna [{title, url, snippet}] via DuckDuckGo (sem API key). Tenta 2x (throttle)."""
    from ddgs import DDGS
    for tentativa in range(2):
        try:
            with DDGS() as ddg:
                hits = list(ddg.text(query, region="br-pt", max_results=n))
            if hits:
                return [{"title": h.get("title", ""),
                         "url": h.get("href") or h.get("url", ""),
                         "snippet": h.get("body", "")} for h in hits]
        except Exception as e:
            print(f"web_search tentativa {tentativa+1} falhou: {e}")
            time.sleep(1.5)
    return []


def fetch_page(url):
    """Baixa a página e extrai o texto principal (trafilatura). '' se falhar."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ARMAGEDON"})
        with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="ignore")
        import trafilatura
        txt = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        return txt.strip()[:WEB_PAGE_CHARS]
    except Exception as e:
        print(f"fetch_page falhou ({url}): {e}")
        return ""


def web_context(query):
    """Bloco de texto com resultados da web pra injetar no prompt. ('', []) se nada."""
    hits = web_search(query)
    if not hits:
        return "", []
    linhas = [f"=== RESULTADOS DA WEB — {datetime.now():%d/%m/%Y %H:%M} (use isto como info atual) ==="]
    sources = []
    for i, h in enumerate(hits):
        linhas.append(f"[{i+1}] {h['title']}\n{h['url']}\n{h['snippet']}")
        sources.append({"source": h["title"] or h["url"], "url": h["url"], "web": True})
    for h in hits[:WEB_FETCH]:
        page = fetch_page(h["url"])
        if page:
            linhas.append(f"--- conteúdo de {h['url']} ---\n{page}")
    linhas.append("Baseie a resposta nesses resultados quando forem sobre o que foi perguntado, "
                  "e cite a fonte (URL). Se estiverem desatualizados ou irrelevantes, diga isso.")
    return "\n".join(linhas), sources


os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)


# ----------------------------------------------------------------------------
# Ollama helpers
# ----------------------------------------------------------------------------
def _post(path, payload, timeout=120):
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed(text):
    """Vetor de embedding para um texto (tenta /api/embed, cai pra /api/embeddings)."""
    try:
        out = _post("/api/embed", {"model": EMBED_MODEL, "input": text})
        return out["embeddings"][0]
    except Exception:
        out = _post("/api/embeddings", {"model": EMBED_MODEL, "prompt": text})
        return out["embedding"]


def llm(prompt, timeout=180):
    out = _post("/api/generate", {"model": CHAT_MODEL, "prompt": prompt, "stream": False}, timeout)
    return out.get("response", "").strip()


# ----------------------------------------------------------------------------
# Memória (SQLite)
# ----------------------------------------------------------------------------
def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS fatos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria TEXT NOT NULL DEFAULT 'fato',
        texto TEXT NOT NULL,
        criado_em TEXT NOT NULL
    )""")
    return con


def mem_list():
    con = db()
    rows = con.execute("SELECT id, categoria, texto, criado_em FROM fatos ORDER BY id").fetchall()
    con.close()
    return [{"id": r[0], "categoria": r[1], "texto": r[2], "criado_em": r[3]} for r in rows]


def mem_add(categoria, texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    con = db()
    # evita duplicado exato
    dup = con.execute("SELECT id FROM fatos WHERE texto = ?", (texto,)).fetchone()
    if dup:
        con.close()
        return dup[0]
    cur = con.execute(
        "INSERT INTO fatos (categoria, texto, criado_em) VALUES (?, ?, ?)",
        (categoria or "fato", texto, datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    fid = cur.lastrowid
    con.close()
    return fid


def mem_del(fid):
    con = db()
    con.execute("DELETE FROM fatos WHERE id = ?", (fid,))
    con.commit()
    con.close()


# ----------------------------------------------------------------------------
# Vetores: ChromaDB ou fallback numpy
# ----------------------------------------------------------------------------
class NumpyStore:
    """Fallback simples: guarda vetores num .npz e faz cosseno na mão."""
    def __init__(self):
        import numpy as np
        self.np = np
        self.ids, self.docs, self.metas, self.vecs = [], [], [], None
        if os.path.exists(NPZ_PATH):
            d = np.load(NPZ_PATH, allow_pickle=True)
            self.ids = list(d["ids"]); self.docs = list(d["docs"])
            self.metas = list(d["metas"]); self.vecs = d["vecs"]

    def reset(self):
        self.ids, self.docs, self.metas, self.vecs = [], [], [], None

    def add(self, ids, docs, metas, embs):
        np = self.np
        e = np.array(embs, dtype="float32")
        self.ids += ids; self.docs += docs; self.metas += metas
        self.vecs = e if self.vecs is None else np.vstack([self.vecs, e])

    def persist(self):
        np = self.np
        np.savez(NPZ_PATH, ids=np.array(self.ids, dtype=object),
                 docs=np.array(self.docs, dtype=object),
                 metas=np.array(self.metas, dtype=object),
                 vecs=self.vecs if self.vecs is not None else np.zeros((0, 1), "float32"))

    def query(self, emb, k):
        np = self.np
        if self.vecs is None or len(self.ids) == 0:
            return []
        q = np.array(emb, dtype="float32")
        q = q / (np.linalg.norm(q) + 1e-9)
        m = self.vecs / (np.linalg.norm(self.vecs, axis=1, keepdims=True) + 1e-9)
        sims = m @ q
        idx = np.argsort(-sims)[:k]
        return [(self.docs[i], self.metas[i], float(sims[i])) for i in idx]

    def count(self):
        return len(self.ids)


class ChromaStore:
    def __init__(self):
        import chromadb
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.col = self.client.get_or_create_collection(
            "documentos", metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def reset(self):
        try:
            self.client.delete_collection("documentos")
        except Exception:
            pass
        self.col = self.client.get_or_create_collection(
            "documentos", metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def add(self, ids, docs, metas, embs):
        self.col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)

    def persist(self):
        pass  # PersistentClient já grava em disco

    def query(self, emb, k):
        res = self.col.query(query_embeddings=[emb], n_results=k)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        # distância de cosseno -> similaridade
        return [(d, m, 1.0 - float(dist)) for d, m, dist in zip(docs, metas, dists)]

    def count(self):
        return self.col.count()


def make_store():
    try:
        s = ChromaStore()
        print("Vetores: ChromaDB")
        return s
    except Exception as e:
        print(f"ChromaDB indisponível ({e}); usando fallback numpy")
        return NumpyStore()


STORE = make_store()


# ----------------------------------------------------------------------------
# Ingestão de documentos
# ----------------------------------------------------------------------------
def read_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".markdown", ".text"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            print(f"  ! erro lendo {os.path.basename(path)}: {e}")
            return ""
    return ""


def chunk_text(text):
    text = " ".join(text.split())
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def ingest():
    files = []
    for ext in ("txt", "md", "markdown", "text", "pdf"):
        files += glob.glob(os.path.join(DOCS_DIR, "**", f"*.{ext}"), recursive=True)
    files = sorted(set(files))

    STORE.reset()
    manifest, total = [], 0
    for path in files:
        name = os.path.relpath(path, DOCS_DIR)
        raw = read_file(path)
        parts = chunk_text(raw)
        if not parts:
            manifest.append({"arquivo": name, "trechos": 0})
            continue
        ids, docs, metas, embs = [], [], [], []
        for idx, part in enumerate(parts):
            ids.append(f"{name}::{idx}")
            docs.append(part)
            metas.append({"source": name, "chunk": idx})
            embs.append(embed(part))
        STORE.add(ids, docs, metas, embs)
        total += len(parts)
        manifest.append({"arquivo": name, "trechos": len(parts)})
        print(f"  indexado {name}: {len(parts)} trechos")

    STORE.persist()
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"quando": datetime.now().isoformat(timespec="seconds"),
                   "docs": manifest, "total": total}, f, ensure_ascii=False, indent=2)
    return {"arquivos": len(files), "trechos": total, "docs": manifest}


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"docs": [], "total": 0, "quando": None}


# ----------------------------------------------------------------------------
# Montagem do bloco de contexto
# ----------------------------------------------------------------------------
def build_system_block(prompt, use_rag=True, use_web="auto"):
    linhas, sources = [], []

    fatos = mem_list()
    if fatos:
        linhas.append("=== O QUE VOCÊ JÁ SABE SOBRE DOUGLAS (memória de longo prazo) ===")
        for f in fatos:
            linhas.append(f"- [{f['categoria']}] {f['texto']}")
        linhas.append("")

    # Web: use_web True (sempre), False (nunca), "auto" (só se a pergunta pedir algo atual)
    quer_web = use_web is True or (use_web == "auto" and precisa_web(prompt))
    if quer_web and prompt.strip():
        wblock, wsrc = web_context(prompt)
        if wblock:
            linhas.append(wblock)
            linhas.append("")
            sources.extend(wsrc)

    if use_rag and STORE.count() > 0 and prompt.strip():
        try:
            hits = STORE.query(embed(prompt), TOP_K)
        except Exception as e:
            hits = []
            print(f"query RAG falhou: {e}")
        bons = [(d, m, s) for d, m, s in hits if s >= MIN_SCORE]
        if bons:
            linhas.append("=== TRECHOS RELEVANTES DOS DOCUMENTOS DE DOUGLAS ===")
            for d, m, s in bons:
                src = m.get("source", "?")
                linhas.append(f"[documento: {src}]\n{d}\n")
                sources.append({"source": src, "score": round(s, 3)})
            linhas.append("Se usar algum trecho acima, cite o nome do documento. "
                          "Se os documentos não responderem, diga isso e responda com seu conhecimento geral.")
            linhas.append("")

    return "\n".join(linhas).strip(), sources


# ----------------------------------------------------------------------------
# Rotas
# ----------------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "embed_model": EMBED_MODEL,
                    "chunks": STORE.count(), "memoria": len(mem_list())})


@app.route("/status")
def status():
    man = load_manifest()
    return jsonify({"docs": man["docs"], "total_trechos": STORE.count(),
                    "indexado_em": man.get("quando"),
                    "memoria": len(mem_list()),
                    "pasta_documentos": DOCS_DIR})


@app.route("/ingest", methods=["POST"])
def ingest_route():
    try:
        return jsonify(ingest())
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/augment", methods=["POST"])
def augment():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "")
    use_rag = data.get("use_rag", True)
    use_web = data.get("use_web", "auto")   # True | False | "auto"
    block, sources = build_system_block(prompt, use_rag, use_web)
    resp = {"system_block": block, "sources": sources,
            "web_usada": any(s.get("web") for s in sources)}
    if data.get("route"):
        model, reason = route_model(prompt)
        resp["model"] = model
        resp["route_reason"] = reason
    return jsonify(resp)


@app.route("/route", methods=["POST"])
def route_only():
    data = request.get_json(silent=True) or {}
    model, reason = route_model(data.get("prompt", ""))
    return jsonify({"model": model, "reason": reason})


@app.route("/websearch", methods=["POST"])
def websearch_only():
    data = request.get_json(silent=True) or {}
    q = (data.get("query") or data.get("prompt") or "").strip()
    if not q:
        return jsonify({"erro": "query vazia"}), 400
    return jsonify({"query": q, "auto_dispararia": precisa_web(q),
                    "resultados": web_search(q)})


@app.route("/memory", methods=["GET"])
def memory_get():
    return jsonify({"fatos": mem_list()})


@app.route("/memory", methods=["POST"])
def memory_post():
    data = request.get_json(silent=True) or {}
    fid = mem_add(data.get("categoria", "fato"), data.get("texto", ""))
    if fid is None:
        return jsonify({"erro": "texto vazio"}), 400
    return jsonify({"id": fid, "fatos": mem_list()})


@app.route("/memory/<int:fid>", methods=["DELETE"])
def memory_del(fid):
    mem_del(fid)
    return jsonify({"ok": True, "fatos": mem_list()})


@app.route("/memory/extract", methods=["POST"])
def memory_extract():
    data = request.get_json(silent=True) or {}
    texto = (data.get("text") or "").strip()
    if not texto:
        return jsonify({"erro": "text vazio"}), 400
    p = (
        "Extraia da conversa abaixo APENAS fatos duráveis e úteis sobre Douglas "
        "(preferências, decisões, dados pessoais, contexto de projetos). "
        "Ignore o que for efêmero. Responda só com um JSON array de objetos "
        '{"categoria": "preferencia|fato|projeto", "texto": "..."} — no máximo 5. '
        "Se não houver nada relevante, responda [].\n\nCONVERSA:\n" + texto
    )
    try:
        raw = llm(p)
        ini, fim = raw.find("["), raw.rfind("]")
        novos = json.loads(raw[ini:fim + 1]) if ini >= 0 and fim > ini else []
    except Exception as e:
        return jsonify({"erro": f"falha ao extrair: {e}"}), 500
    salvos = []
    for item in novos[:5]:
        if isinstance(item, dict) and item.get("texto"):
            fid = mem_add(item.get("categoria", "fato"), item["texto"])
            if fid:
                salvos.append({"id": fid, **item})
    return jsonify({"salvos": salvos, "fatos": mem_list()})


# ----------------------------------------------------------------------------
# Fase 6 — feedback (👍/👎) que vira dataset de fine-tuning
# ----------------------------------------------------------------------------
def _feedback_all():
    if not os.path.exists(FEEDBACK_PATH):
        return []
    out = []
    with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


@app.route("/feedback", methods=["POST"])
def feedback_post():
    d = request.get_json(silent=True) or {}
    prompt = (d.get("prompt") or "").strip()
    resposta = (d.get("response") or "").strip()
    rating = d.get("rating")  # "up" | "down"
    if not prompt or rating not in ("up", "down"):
        return jsonify({"erro": "prompt e rating (up/down) obrigatórios"}), 400
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": d.get("model") or "",
        "prompt": prompt,
        "response": resposta,
        "rating": rating,
        "correction": (d.get("correction") or "").strip(),  # o que a resposta DEVERIA ter sido
    }
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})


@app.route("/feedback/stats", methods=["GET"])
def feedback_stats():
    fb = _feedback_all()
    up = sum(1 for r in fb if r.get("rating") == "up")
    down = sum(1 for r in fb if r.get("rating") == "down")
    corr = sum(1 for r in fb if r.get("correction"))
    # quantos exemplos de treino dá pra montar: 👍 com resposta + 👎 com correção
    treinaveis = sum(1 for r in fb
                     if (r.get("rating") == "up" and r.get("response"))
                     or (r.get("rating") == "down" and r.get("correction")))
    return jsonify({"total": len(fb), "up": up, "down": down,
                    "com_correcao": corr, "treinaveis": treinaveis,
                    "arquivo": FEEDBACK_PATH})


@app.route("/feedback/recent", methods=["GET"])
def feedback_recent():
    fb = _feedback_all()[-20:][::-1]
    return jsonify({"itens": fb})


if __name__ == "__main__":
    print("=" * 50)
    print("ARMAGEDON - Cérebro (RAG + Memória + Feedback)")
    print("=" * 50)
    print(f"documentos/  -> {DOCS_DIR}")
    print(f"trechos indexados: {STORE.count()} | fatos na memória: {len(mem_list())}")
    print("http://localhost:5002\n")
    sys.stdout.flush()
    app.run(host="localhost", port=5002, debug=False, threaded=True)
