"""
ARMAGEDON — Diretor de voz

Analisa um texto e gera a direção de voz no formato combinado (JSON):
  tipo, emocao_principal, emocao_secundaria, energia, formalidade, velocidade, entonacao, pausas, volume,
  estilo, usar_expressividade, usar_pausas_dinamicas, usar_variacao_tonal, personagens, roteiro_otimizado

…e transforma a direção em áudio de verdade: cada trecho é sintetizado com velocidade, altura (pitch) e volume
próprios, com pausas entre os trechos e uma voz diferente para cada personagem (modo DIALOGO).

Duas camadas (como a análise emocional):
  • direct(text)           — regras, instantâneo; usa emotion_analyzer para a emoção de cada trecho.
  • direct_deep(text, fn)  — o mesmo pedido à IA (VOICE_PROMPT), validado; o elenco de vozes continua sendo
                             definido aqui, porque a IA não conhece as vozes instaladas.

Regra de ouro: o áudio fala SEMPRE o texto original. O roteiro_otimizado é uma marcação para leitura
(pausas e ênfases), nunca uma reescrita do que será falado.

Também oferece adapt_for_listener(analise): como o assistente deve falar conforme a emoção de quem o ouve.
"""

import re

import numpy as np

import emotion_analyzer as ea

SR = 24000

# vozes disponíveis para o elenco (edge-tts). "faber" (Piper, offline) é o plano B.
VOICES = {
    "francisca": {"name": "Francisca", "gender": "f", "edge": "pt-BR-FranciscaNeural"},
    "thalita": {"name": "Thalita", "gender": "f", "edge": "pt-BR-ThalitaMultilingualNeural"},
    "antonio": {"name": "Antônio", "gender": "m", "edge": "pt-BR-AntonioNeural"},
    "faber": {"name": "Faber (offline)", "gender": "m", "piper": True},
}

# como RETRATAR a emoção de um trecho: (velocidade %, altura Hz, volume %) na intensidade máxima
PORTRAY = {
    "Alegria": (8, 6, 5), "Entusiasmo": (14, 10, 10), "Tristeza": (-14, -6, -15), "Raiva": (6, -2, 15),
    "Frustração": (3, -2, 6), "Medo": (8, 6, -6), "Ansiedade": (10, 4, -5), "Vergonha": (-6, -2, -15),
    "Culpa": (-10, -4, -10), "Orgulho": (3, 3, 10), "Surpresa": (6, 12, 8), "Confusão": (-4, 4, 0),
    "Solidão": (-14, -6, -15), "Gratidão": (-2, 2, 0), "Esperança": (0, 4, 5), "Decepção": (-10, -4, -10),
    "Neutralidade": (0, 0, 0),
}

# como RESPONDER a quem está ouvindo (tabela "ADAPTAÇÃO DE TOM")
LISTENER = {
    "Tristeza": {"rate": -12, "pitch": -3, "volume": -10, "pause": 520, "tom": "voz mais suave, ritmo lento, entonação acolhedora"},
    "Solidão": {"rate": -12, "pitch": -3, "volume": -10, "pause": 520, "tom": "voz mais suave, ritmo lento, entonação acolhedora"},
    "Decepção": {"rate": -8, "pitch": -2, "volume": -6, "pause": 450, "tom": "voz suave e compreensiva"},
    "Ansiedade": {"rate": -10, "pitch": -2, "volume": -5, "pause": 650, "tom": "voz calma, pausas maiores, ritmo controlado"},
    "Medo": {"rate": -10, "pitch": -2, "volume": -5, "pause": 600, "tom": "voz calma e segura, ritmo controlado"},
    "Raiva": {"rate": -4, "pitch": -3, "volume": 3, "pause": 380, "tom": "voz firme, sem agressividade, transmitindo controle"},
    "Frustração": {"rate": -3, "pitch": -2, "volume": 2, "pause": 380, "tom": "voz firme e objetiva"},
    "Alegria": {"rate": 6, "pitch": 4, "volume": 5, "pause": 280, "tom": "mais energia, tom positivo, ritmo levemente acelerado"},
    "Gratidão": {"rate": 3, "pitch": 3, "volume": 3, "pause": 300, "tom": "tom caloroso e positivo"},
    "Orgulho": {"rate": 5, "pitch": 4, "volume": 6, "pause": 300, "tom": "tom positivo e celebrativo"},
    "Entusiasmo": {"rate": 12, "pitch": 8, "volume": 8, "pause": 250, "tom": "alto dinamismo, mais expressividade"},
}

# estilos de conteúdo: palavras-pista, ajustes e descrição
STYLES = {
    "técnico": {"cues": r"\b(instal\w*|configur\w*|comando|codigo|funcao|variavel|servidor|arquivo|parametro|algoritmo|"
                        r"api|python|javascript|sistema operacional|banco de dados|clique|terminal|versao|\d+\s?(gb|mb|ms|hz))\b",
                "rate": -6, "pitch": 0, "volume": 0, "emo": 0.4, "pause": 450, "formal": 65,
                "entonacao": "neutra e precisa, com clareza máxima", "estilo": "Explicação técnica: clareza máxima, menos emoção, pronúncia precisa"},
    "história": {"cues": r"\b(era uma vez|certo dia|naquela (noite|manha|tarde)|de repente|entao (ele|ela)|ha muito tempo|"
                         r"conta a lenda|finalmente|no dia seguinte|enquanto isso|foi entao que)\b",
                 "rate": -4, "pitch": 0, "volume": 0, "emo": 1.3, "pause": 700, "formal": 40,
                 "entonacao": "dramatizada, com muitas variações vocais", "estilo": "História: expressiva e cinematográfica, com pausas dramáticas"},
    "notícia": {"cues": r"\b(segundo (o|a|os|as)|informou|de acordo com|nesta (segunda|terca|quarta|quinta|sexta)|governo|"
                        r"ministerio|anunciou|reportagem|levantamento|pesquisa divulgada|prefeitura|nesta manha)\b",
                "rate": 0, "pitch": 0, "volume": 0, "emo": 0.3, "pause": 400, "formal": 85,
                "entonacao": "formal, objetiva e estável", "estilo": "Notícia: formal, objetiva, pouca emoção"},
    "tutorial": {"cues": r"\b(passo \d|primeiro passo|em seguida|depois disso|agora (clique|abra|digite|vamos)|"
                         r"siga os passos|voce vai precisar|dica:|no final|vamos aprender)\b",
                 "rate": -4, "pitch": 2, "volume": 0, "emo": 0.6, "pause": 500, "formal": 45,
                 "entonacao": "didática, clara e amigável", "estilo": "Tutorial: didático, claro e amigável"},
    "motivacional": {"cues": r"\b(voce consegue|acredite|nunca desista|seu potencial|nao desista|voce e capaz|sonhos?|"
                             r"conquiste|supere|forca|determinacao|vencer|vitoria|comece agora)\b",
                     "rate": 2, "pitch": 3, "volume": 10, "emo": 1.1, "pause": 600, "formal": 35,
                     "entonacao": "inspiradora, forte e confiante", "estilo": "Motivacional: inspiradora, forte e confiante"},
    "conversa": {"cues": None, "rate": 0, "pitch": 0, "volume": 0, "emo": 1.0, "pause": 380, "formal": 30,
                 "entonacao": "natural e conversacional", "estilo": "Conversa: natural e espontânea"},
}

FEMALE_NAMES = {"raquel", "isabel", "beatriz", "ester", "rute", "carmen", "ingrid", "alice", "clarice", "lis", "jasmin",
                "nicole", "michele", "rachel", "ruth", "liz", "miriam", "iris", "luz", "mel", "sol", "babi", "dani", "vivi"}
MALE_ENDING_A = {"luca", "joshua", "nikita", "andrea", "garcia", "costa", "silva", "souza", "moura", "batista"}
NARRATOR = "Narrador"

_DIALOGUE = re.compile(r"^\s*(?:[-—–]\s*)?([A-ZÀ-Ý][\wÀ-ÿ'’.]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’.]*){0,2})\s*:\s*(.+)$")
_DASH_LINE = re.compile(r"^\s*[—–-]\s+(.+)$")
_HUMOR = re.compile(r"\b(k{3,}|(ha){2,}|rs(rs)+|piada|brincadeira|zoeira|engracad\w*)\b|[😂🤣😆😜]")
_EMPHASIS = re.compile(r"\b(muito|nunca|sempre|tudo|nada|jamais|todos|ninguem|demais|absolutamente|essencial|importante|atencao|cuidado)\b|"
                       r"\b\d+[\d.,%]*\b|\b[A-ZÀ-Ý]{3,}\b")
_SLANG = re.compile(r"\b(to|ta|tava|pra|pro|vc|voces|ne|tipo|mano|cara|beleza|blz|kkk+|valeu|massa|show)\b")
_FORMAL = re.compile(r"\b(senhor|senhora|prezad\w*|portanto|entretanto|todavia|conforme|mediante|outrossim|ademais|"
                     r"cordialmente|atenciosamente|solicit\w*|informamos)\b")


def _norm(text):
    return ea._normalize(text)[0]

# ============================ SEGMENTAÇÃO ============================


# "Nome:" no começo da linha OU no meio do texto (depois de pontuação/aspas): "…Lisboa." Dom Pedro I: "Chega!"
_NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'’]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’]*|I{1,3}|IV|VI{0,3}|IX|X|de|da|do|dos|das|e)){0,3}"
_TAG = re.compile(rf"(?:^|(?<=[\s\"“”'.!?…:;]))({_NAME})\s*:(?=\s|$)")
_NOT_NAMES = {"obs", "nota", "dica", "atencao", "importante", "http", "https", "exemplo", "resposta", "pergunta",
              "passo", "titulo", "resumo", "observacao", "aviso", "cena", "parte", "capitulo"}
_NARRATOR_NAMES = {"narrador", "narradora", "narracao", "narrativa", "voz em off"}

# rubricas entre parênteses: viram direção de atuação (não são faladas)
CUES = [
    (r"grit\w*|berr\w*|aos berros", "Raiva", {"volume": 18, "rate": 6}),
    (r"irritad\w*|furios\w*|bravo|com raiva|nervos\w*|indignad\w*", "Raiva", {}),
    (r"sussurr\w*|baixinho|em voz baixa|cochich\w*", None, {"volume": -22, "rate": -10}),
    (r"chor\w*|solu[cç]\w*|triste\w*|emocionad\w*|com a voz embargada", "Tristeza", {}),
    (r"rindo|gargalh\w*|sorrindo|feliz|alegre", "Alegria", {}),
    (r"assustad\w*|com medo|apavorad\w*|tremendo|em panico", "Medo", {}),
    (r"ansios\w*|aflit\w*|preocupad\w*|apressad\w*", "Ansiedade", {"rate": 6}),
    (r"animad\w*|empolgad\w*|euforic\w*|vibrando", "Entusiasmo", {}),
    (r"surpres\w*|espantad\w*|chocad\w*|incredul\w*", "Surpresa", {}),
    (r"calm\w*|seren\w*|tranquil\w*|suave\w*|pensativ\w*", "Neutralidade", {"rate": -8, "volume": -5}),
    (r"ironic\w*|sarcastic\w*|debochad\w*", "Frustração", {}),
    (r"decidid\w*|firme\w*|determinad\w*|solene\w*|erguendo|heroic\w*|imponente", "Orgulho", {"volume": 10, "rate": -3}),
    (r"perguntando|curios\w*|confus\w*|duvidando", "Confusão", {}),
]


def find_speaker_tags(text):
    """Posições de "Nome:" no texto (no começo da linha ou no meio, depois de pontuação). [(início, fim, nome)]"""
    tags = []
    for m in _TAG.finditer(text or ""):
        name = m.group(1).strip()
        if _norm(name) in _NOT_NAMES or len(name) > 40:
            continue
        tags.append((m.start(1), m.end(), name))
    return tags


def split_inline_speakers(text):
    """Põe cada fala na sua linha: '…Lisboa." Dom Pedro I: "Chega!"' → duas linhas."""
    text = text or ""
    out, last = [], 0
    for start, _, _ in find_speaker_tags(text):
        if start > last and text[last:start].strip():
            out.append(text[last:start].rstrip())
            last = start
    out.append(text[last:])
    return "\n".join(p.strip() for p in "\n".join(out).split("\n") if p.strip())


def _cue_of(text):
    """Tira as rubricas "(irritado)" da fala e devolve (fala_limpa, direção) — a direção ajusta emoção/volume/ritmo."""
    found = re.findall(r"\(([^)]{1,80})\)|\[([^\]]{1,80})\]", text)
    rubrics = [a or b for a, b in found]
    clean = re.sub(r"\s*(\([^)]{1,80}\)|\[[^\]]{1,80}\])\s*", " ", text)
    clean = re.sub(r"[\"“”]", "", clean)                     # aspas não se falam
    clean = re.sub(r"\s+", " ", clean).strip(" -–—:")
    cue = None
    if rubrics:
        joined = _norm(" ".join(rubrics))
        cue = {"rubrica": ", ".join(rubrics), "emocao": None, "rate": 0, "volume": 0}
        for pattern, emo, adj in CUES:
            if re.search(rf"\b({pattern})\b", joined):
                cue["emocao"] = cue["emocao"] or emo
                cue["rate"] += adj.get("rate", 0)
                cue["volume"] += adj.get("volume", 0)
    return clean, cue


def segment_full(text):
    """Texto → [(personagem, fala_limpa, direção)]. Entende "Nome: fala" no começo ou no meio da linha, "— fala",
    rubricas entre parênteses (viram direção e não são faladas) e descarta linhas que só têm rubrica
    (ex.: 'Narrador: (música épica aumentando)')."""
    segs, dash_turn = [], 0
    for raw in split_inline_speakers(text).split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _DIALOGUE.match(line)
        if m and _norm(m.group(1)) not in _NOT_NAMES:
            name = m.group(1).strip()
            who = NARRATOR if _norm(name) in _NARRATOR_NAMES else name
            speech = m.group(2)
        else:
            d = _DASH_LINE.match(line)
            if d:   # diálogo com travessão sem nome: alterna entre duas vozes
                who, speech = f"Voz {1 + dash_turn % 2}", d.group(1)
                dash_turn += 1
            else:
                who, speech = NARRATOR, line
        clean, cue = _cue_of(speech)
        if re.search(r"\w", clean):
            segs.append((who, clean, cue))
    return segs


def segment(text):
    """Texto → [(personagem, fala)] (sem as rubricas)."""
    return [(who, line) for who, line, _ in segment_full(text)]


def distribute_dialogue(chunks):
    """Roteiro de diálogo que foi repartido entre quadros (às vezes no meio de uma fala) → o roteiro de cada quadro
    com o personagem certo em cada pedaço. Ex.: quadro 3 termina em 'Dom Pedro I:' e o 4 começa com a fala dele."""
    joined, spans, pos = "", [], 0
    for c in chunks:
        c = c or ""
        spans.append((pos, pos + len(c)))
        joined += c + "\n"
        pos += len(c) + 1
    tags = find_speaker_tags(joined)
    if len(tags) < 2:
        return None   # não é diálogo: cada quadro segue como está
    # falas: (personagem, início, fim) — antes da primeira marcação é narração
    utter, cursor, who = [], 0, NARRATOR
    for start, end, name in tags:
        if start > cursor:
            utter.append((who, cursor, start))
        who = NARRATOR if _norm(name) in _NARRATOR_NAMES else name
        cursor = end
    utter.append((who, cursor, len(joined)))
    scripts = []
    for a, b in spans:
        lines = []
        for who, s, e in utter:
            piece = joined[max(a, s):min(b, e)].strip()
            if piece and re.search(r"\w", re.sub(r"\([^)]*\)", "", piece)):
                lines.append(f"{who}: {re.sub(chr(10), ' ', piece)}")
        scripts.append("\n".join(lines))
    return scripts


# como o personagem fala de si (concordância do português) — pista mais forte que o nome
_FEM_SELF = re.compile(r"\b(obrigada|cansada|pronta|animada|preocupada|sozinha|assustada|cansadas|prontas|animadas|"
                       r"(eu )?(estou|to|tou|fiquei|sou|me sinto) (tao |muito )?\w+ada\b|somos as|nos as|uma garota|uma mulher)\b")
_MASC_SELF = re.compile(r"\b(obrigado|cansado|pronto|animado|preocupado|sozinho|assustado|cansados|prontos|animados|"
                        r"(eu )?(estou|to|tou|fiquei|sou|me sinto) (tao |muito )?\w+ado\b|somos os|nos os|um garoto|um homem)\b")
# descrição (ficha) em inglês ou português
_FEM_DESC = re.compile(r"\b(woman|girl|female|she|her|lady|queen|princess|mother|sister|daughter|wife|"
                       r"mulher|menina|garota|moca|senhora|rainha|princesa|mae|irma|filha|esposa)\b")
_MASC_DESC = re.compile(r"\b(man|boy|male|he|his|gentleman|king|prince|father|brother|son|husband|"
                        r"homem|menino|garoto|rapaz|senhor|rei|principe|pai|irmao|filho|marido)\b")


def _gender(name, lines=(), description=""):
    """Gênero provável da voz: ficha do personagem > como ele fala de si > nome."""
    n = _norm(name).split()[0] if name.strip() else ""
    desc = _norm(description or "")
    if desc and n:
        # trecho da ficha que fala deste personagem (do nome até a próxima vírgula/ponto/" and ")
        m = re.search(rf"\b{re.escape(n)}\b[^.;]*", desc)
        part = m.group(0) if m else (desc if len(desc) < 160 else "")
        f, ms = len(_FEM_DESC.findall(part)), len(_MASC_DESC.findall(part))
        if f != ms:
            return "f" if f > ms else "m"
    spoken = _norm(" ".join(lines))
    f, ms = len(_FEM_SELF.findall(spoken)), len(_MASC_SELF.findall(spoken))
    if f != ms:
        return "f" if f > ms else "m"
    if n in FEMALE_NAMES or (n.endswith("a") and n not in MALE_ENDING_A):
        return "f"
    return "m"


def cast_voices(names, narrator_voice="francisca", lines_by_name=None, description="", overrides=None):
    """Uma voz (e altura própria) para cada personagem, tentando não repetir a do narrador.
    lines_by_name: falas de cada um (para deduzir o gênero); overrides: {nome: voz} escolhida pelo usuário."""
    # só existe uma voz masculina online em português; a offline (Faber) dá um segundo timbre masculino
    pools = {"f": ["francisca", "thalita"], "m": ["antonio", "faber"]}
    usage, cast = {}, {}
    lines_by_name, overrides = lines_by_name or {}, overrides or {}
    if narrator_voice in VOICES:
        usage[narrator_voice] = 1
    for name in names:
        if name == NARRATOR or name in cast:
            continue
        if overrides.get(name) in VOICES:
            v = overrides[name]
            cast[name] = {"voice": v, "pitch": 0, "gender": VOICES[v]["gender"]}
            usage[v] = usage.get(v, 0) + 1
            continue
        g = _gender(name, lines_by_name.get(name, ()), description) if not name.startswith("Voz ") \
            else ("m" if name.endswith("1") else "f")
        pool = pools[g]
        # a voz offline não muda de altura: dois personagens nela soariam idênticos, então ela vale para um só
        candidates = [v for v in pool if not (VOICES[v].get("piper") and usage.get(v, 0) >= 1)] or pool[:1]
        voice = min(candidates, key=lambda v: usage.get(v, 0))
        n_same = usage.get(voice, 0)
        usage[voice] = n_same + 1
        # quem divide a mesma voz ganha altura bem diferente, para soar como outra pessoa
        pitch = [0, -12, 10, -20, 18][n_same % 5]
        cast[name] = {"voice": voice, "pitch": pitch, "gender": g}
    cast[NARRATOR] = {"voice": narrator_voice if narrator_voice in VOICES else "francisca", "pitch": 0,
                      "gender": VOICES.get(narrator_voice, VOICES["francisca"])["gender"]}
    return cast

# ============================ DIREÇÃO POR REGRAS ============================


def _style(norm):
    best, hits = "conversa", 0
    for key, st in STYLES.items():
        if st["cues"]:
            n = len(re.findall(st["cues"], norm))
            if n > hits:
                best, hits = key, n
    return best


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _emphasis_marks(text):
    """Marca ênfases (*palavra*) para o roteiro; não altera o que é falado.
    A busca é no texto normalizado, que tem o mesmo comprimento do original (as posições batem)."""
    norm, orig = ea._normalize(text)
    out, last = [], 0
    for m in _EMPHASIS.finditer(norm):
        out += [orig[last:m.start()], f"*{orig[m.start():m.end()]}*"]
        last = m.end()
    return "".join(out) + orig[last:]


def lines_by_speaker(segs):
    out = {}
    for item in segs:
        out.setdefault(item[0], []).append(item[1])
    return out


def direct(text, narrator_voice="francisca", base_rate=0, cast=None, overrides=None, description=""):
    """Direção de voz por regras. Retorna (direcao_no_formato_combinado, segmentos, deteccoes).
    segmentos: [{personagem, texto, voz, rate, pitch, volume, pausa_ms}] — pronto para render().
    overrides: {personagem: voz} escolhida pelo usuário; description: ficha dos personagens (ajuda no gênero)."""
    segs_full = segment_full(text)
    segs = [(w, l) for w, l, _ in segs_full]
    cues = [c for _, _, c in segs_full]
    norm_all = _norm(" ".join(l for _, l in segs))
    speakers = [s for s, _ in segs]
    named = [s for s in dict.fromkeys(speakers) if s != NARRATOR]
    is_dialogue = len(named) >= 2 or (len(named) == 1 and speakers.count(named[0]) >= 2 and NARRATOR in speakers)
    style_key = _style(norm_all) if not is_dialogue else ("história" if NARRATOR in speakers else "conversa")
    st = STYLES[style_key]
    by_name = lines_by_speaker(segs)
    cast = cast or cast_voices(named, narrator_voice, by_name, description, overrides)
    for name in named:   # personagem que não estava no elenco recebido
        if name not in cast:
            cast.update({k: v for k, v in cast_voices([name], narrator_voice, by_name, description, overrides).items() if k == name})

    overall, osig = ea.analyze(text or "")
    humor = bool(_HUMOR.search(norm_all))
    slang, formal = len(_SLANG.findall(norm_all)), len(_FORMAL.findall(norm_all))
    formality = int(_clip(st["formal"] + 12 * formal - 8 * slang, 0, 100))

    out_segs, per_char, script = [], {}, []
    for (who, line), cue in zip(segs, cues):
        a, _ = ea.analyze(line)
        emo, inten = a["emocao_principal"], a["intensidade"] / 100
        if cue and cue["emocao"]:   # a rubrica do roteiro manda: "(irritado)" → raiva, mesmo que a frase pareça neutra
            emo, inten = cue["emocao"], max(inten, 0.75)
        pr, pp, pv = PORTRAY.get(emo, (0, 0, 0))
        # no diálogo a emoção pesa mais: cada personagem precisa soar diferente (ex.: um a 90%, outro a 110%)
        k = st["emo"] * inten * (1.6 if is_dialogue else 1.2)
        voice = cast.get(who, cast[NARRATOR])
        rate = int(_clip(base_rate + st["rate"] + pr * k + (cue["rate"] if cue else 0), -40, 40))
        pitch = int(_clip(st["pitch"] + voice["pitch"] + pp * k, -30, 30))
        volume = int(_clip(st["volume"] + pv * k + (cue["volume"] if cue else 0), -40, 30))
        pause = int(st["pause"] + (250 if line.rstrip().endswith(("...", "…")) else 0) + (120 if emo in ("Tristeza", "Solidão") else 0))
        out_segs.append({"personagem": who, "texto": line, "voz": voice["voice"], "rate": rate, "pitch": pitch,
                         "volume": volume, "pausa_ms": pause, "emocao": emo, "rubrica": cue["rubrica"] if cue else ""})
        c = per_char.setdefault(who, {"emos": [], "rates": [], "pitches": [], "energy": []})
        c["emos"].append(emo)
        c["rates"].append(rate)
        c["pitches"].append(pitch)
        c["energy"].append(50 + volume + (rate / 2) + (20 * inten if emo in ("Entusiasmo", "Raiva", "Alegria", "Surpresa") else 0))
        label = f"{who} ({emo.lower()}{', ' + cue['rubrica'] if cue else ''}, {100 + rate}%)" if is_dialogue else ""
        pause_txt = f"{pause / 1000:.1f}".replace(".", ",")
        script.append(f"{label + ': ' if label else ''}{_emphasis_marks(line)} [pausa {pause_txt} s]")

    personagens = []
    if is_dialogue:
        for who in [s for s in dict.fromkeys(speakers)]:
            c = per_char[who]
            emo = max(set(c["emos"]), key=c["emos"].count)
            pitch = int(np.mean(c["pitches"]))
            energy = int(_clip(np.mean(c["energy"]), 0, 100))
            vel = int(100 + np.mean(c["rates"]))
            personality = {"Raiva": "firme e intensa", "Frustração": "impaciente", "Alegria": "alegre e expansiva",
                           "Entusiasmo": "vibrante e expressiva", "Tristeza": "suave e contida", "Medo": "hesitante",
                           "Ansiedade": "acelerada e tensa", "Surpresa": "expressiva", "Neutralidade": "calma e natural"}.get(emo, "natural")
            personagens.append({
                "nome": who, "emocao": emo, "energia": energy, "velocidade": f"{vel}%",
                "tom_de_voz": "grave" if pitch <= -5 else "agudo" if pitch >= 5 else "médio",
                "personalidade_vocal": personality, "voz": VOICES[cast[who]["voice"]]["name"],
            })

    energy = int(_clip(np.mean([s["volume"] for s in out_segs] or [0]) + 50 + overall["intensidade"] * 0.3 * st["emo"]
                       + (10 if osig.get("sarcasmo") or humor else 0), 0, 100))
    speed = round(1 + (np.mean([s["rate"] for s in out_segs] or [0])) / 100, 2)
    vol_avg = np.mean([s["volume"] for s in out_segs] or [0])
    direcao = {
        "tipo": "DIALOGO" if is_dialogue else "TEXTO",
        "emocao_principal": overall["emocao_principal"],
        "emocao_secundaria": overall["emocoes_secundarias"],
        "energia": energy,
        "formalidade": formality,
        "velocidade": speed,
        "entonacao": st["entonacao"] + (" — com ironia sutil (há sarcasmo)" if osig.get("sarcasmo") else "")
                     + (" — leve e bem-humorada" if humor else ""),
        "pausas": {"técnico": "curtas e regulares, entre ideias", "história": "cinematográficas, longas antes dos momentos importantes",
                   "notícia": "regulares, entre as frases", "tutorial": "médias, entre cada passo",
                   "motivacional": "dramáticas antes das frases de impacto", "conversa": "naturais, entre as falas"}[style_key],
        "volume": "forte" if vol_avg >= 6 else "suave" if vol_avg <= -6 else "normal",
        "estilo": st["estilo"] if not is_dialogue else f"Diálogo com {len(named)} personagens" + (" e narrador" if NARRATOR in speakers else ""),
        "usar_expressividade": st["emo"] >= 0.6,
        "usar_pausas_dinamicas": style_key in ("história", "motivacional", "tutorial") or is_dialogue,
        "usar_variacao_tonal": st["emo"] >= 0.6 or is_dialogue,
        "personagens": personagens,
        "roteiro_otimizado": "\n".join(script),
    }
    detections = {"sarcasmo": bool(osig.get("sarcasmo")), "humor": humor,
                  "tristeza": overall["emocao_principal"] in ("Tristeza", "Solidão", "Decepção"),
                  "ansiedade": overall["emocao_principal"] in ("Ansiedade", "Medo"),
                  "raiva": overall["emocao_principal"] in ("Raiva", "Frustração") or osig.get("agressividade", False),
                  "empolgacao": overall["emocao_principal"] in ("Entusiasmo", "Alegria", "Surpresa")}
    return direcao, out_segs, detections

# ============================ DIREÇÃO PELA IA ============================

VOICE_PROMPT = """Você é um Especialista em Direção de Voz para IA.

Sua função é analisar o texto e gerar instruções detalhadas para síntese de voz.

OBJETIVO:

Criar falas naturais, emocionais e humanas.

Você deve adaptar a voz de acordo com o contexto.

Existem 2 modos:

MODO 1 - DIALOGO
Quando houver interação entre personagens.

MODO 2 - TEXTO
Quando apenas uma pessoa estiver falando.

━━━━━━━━━━━━━━━━━━━━━━
ANÁLISE OBRIGATÓRIA
━━━━━━━━━━━━━━━━━━━━━━

Detecte:

- Emoção principal
- Emoções secundárias
- Intensidade emocional
- Energia da fala
- Nível de formalidade
- Velocidade ideal
- Entonação ideal
- Pausas naturais
- Ênfases importantes
- Possível sarcasmo
- Possível humor
- Possível tristeza
- Possível ansiedade
- Possível raiva
- Possível empolgação

━━━━━━━━━━━━━━━━━━━━━━
ADAPTAÇÃO DE TOM
━━━━━━━━━━━━━━━━━━━━━━

SE O USUÁRIO ESTIVER:

Triste:
- Voz mais suave
- Ritmo lento
- Entonação acolhedora

Ansioso:
- Voz calma
- Pausas maiores
- Ritmo controlado

Bravo:
- Voz firme
- Sem agressividade
- Transmitir controle

Feliz:
- Mais energia
- Tom positivo
- Ritmo levemente acelerado

Empolgado:
- Alto dinamismo
- Mais expressividade

Explicando algo técnico:
- Clareza máxima
- Menos emoção
- Pronúncia precisa

Contando história:
- Mais dramatização
- Mais variações vocais
- Pausas cinematográficas

━━━━━━━━━━━━━━━━━━━━━━
MODO DIALOGO
━━━━━━━━━━━━━━━━━━━━━━

Se houver dois ou mais personagens:

Defina para cada personagem:

- Nome
- Emoção
- Energia
- Velocidade
- Tom de voz
- Personalidade vocal

Exemplo:

Personagem A:
- Calmo
- Voz grave
- Velocidade 90%

Personagem B:
- Irritado
- Voz mais forte
- Velocidade 110%

As falas devem soar naturais.

Evite que todos os personagens falem da mesma forma.

━━━━━━━━━━━━━━━━━━━━━━
MODO TEXTO
━━━━━━━━━━━━━━━━━━━━━━

Caso seja apenas um narrador:

Defina:

- Estilo narrativo
- Energia da narração
- Intensidade emocional
- Velocidade
- Tom predominante

Exemplos:

Notícia:
- Formal
- Objetiva
- Pouca emoção

História:
- Expressiva
- Cinematográfica

Tutorial:
- Didática
- Clara
- Amigável

Motivacional:
- Inspiradora
- Forte
- Confiante

━━━━━━━━━━━━━━━━━━━━━━
RETORNO
━━━━━━━━━━━━━━━━━━━━━━

Retorne apenas JSON.

{
  "tipo": "",
  "emocao_principal": "",
  "emocao_secundaria": [],
  "energia": 0,
  "formalidade": 0,
  "velocidade": 1.0,
  "entonacao": "",
  "pausas": "",
  "volume": "",
  "estilo": "",
  "usar_expressividade": true,
  "usar_pausas_dinamicas": true,
  "usar_variacao_tonal": true,
  "personagens": [],
  "roteiro_otimizado": ""
}"""

_TONE_PITCH = {"grave": -8, "baixo": -6, "medio": 0, "médio": 0, "agudo": 8, "alto": 6, "suave": -3, "forte": -2}


def _parse_pct(value, default=100):
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(value or ""))
    if not m:
        return default
    v = float(m.group(1).replace(",", "."))
    return v * 100 if v <= 3 else v   # aceita 1.1 e 110%


def direct_deep(text, llm_json, narrator_voice="francisca", base_rate=0, cast=None, overrides=None):
    """Direção pela IA (prompt combinado), validada; as falas continuam sendo o texto original."""
    rules, segs, det = direct(text, narrator_voice, base_rate, cast, overrides)
    try:
        data = llm_json(VOICE_PROMPT, f"TEXTO:\n{text}")
    except Exception as e:
        return rules, segs, det, f"regras (IA indisponível: {e})"

    def num(key, lo, hi, fallback):
        """Número da IA; 0 (o valor do modelo de exemplo) ou ausente → mantém o das regras; 0–1 vira 0–100."""
        try:
            v = float(data.get(key))
        except (TypeError, ValueError):
            return fallback
        if v == 0:
            return fallback
        if hi == 100 and 0 < v <= 1:
            v *= 100
        return type(fallback)(_clip(v, lo, hi))

    tipo = str(data.get("tipo") or rules["tipo"]).upper()
    tipo = "DIALOGO" if "DIAL" in tipo else "TEXTO"
    if tipo != rules["tipo"]:
        tipo = rules["tipo"]   # quem falou cada linha é estrutura do texto: vale a detecção pelas linhas
    emo = ea._canon_emotion(data.get("emocao_principal")) or rules["emocao_principal"]
    sec = [e for e in (ea._canon_emotion(x) for x in data.get("emocao_secundaria") or []) if e and e != emo][:3]
    speed = num("velocidade", 0.6, 1.6, float(rules["velocidade"]))

    # personagens da IA: só ajustam velocidade/tom de quem existe no texto; as vozes vêm do elenco
    ia_chars = {}
    for p in data.get("personagens") or []:
        if isinstance(p, dict):
            name = str(p.get("nome") or p.get("Nome") or "").strip()
            if name:
                ia_chars[_norm(name)] = p
    personagens = []
    for base in rules["personagens"]:
        p = ia_chars.get(_norm(base["nome"]), {})
        merged = dict(base)
        for key in ("emocao", "energia", "velocidade", "tom_de_voz", "personalidade_vocal"):
            val = p.get(key) or p.get(key.replace("_", " ").title()) or p.get(key.capitalize())
            if val in (None, "", 0):
                continue
            if key == "emocao":
                val = ea._canon_emotion(val) or val
            elif key == "energia":   # a IA às vezes usa 0–1
                try:
                    f = float(val)
                    val = int(_clip(f * 100 if f <= 1 else f, 0, 100))
                except (TypeError, ValueError):
                    continue
            elif key == "velocidade":
                val = f"{int(_clip(_parse_pct(val), 60, 160))}%"
            merged[key] = val
        personagens.append(merged)

    by_name = {p["nome"]: p for p in personagens}
    scale = speed / max(0.01, float(rules["velocidade"]))
    for s in segs:   # aplica a velocidade geral da IA e, no diálogo, a de cada personagem
        p = by_name.get(s["personagem"])
        if p:
            s["rate"] = int(_clip(_parse_pct(p.get("velocidade")) - 100, -40, 40))
            words = re.findall(r"[a-z]+", _norm(str(p.get("tom_de_voz", ""))))   # "Grave, firme" → grave, firme
            shift = next((v for w in words for k, v in _TONE_PITCH.items() if w.startswith(k[:4])), 0)   # "aguada" ~ agudo
            s["pitch"] = int(_clip(s["pitch"] + shift * 0.5, -30, 30))
        else:
            s["rate"] = int(_clip((100 + s["rate"]) * scale - 100, -40, 40))

    direcao = {
        "tipo": tipo, "emocao_principal": emo, "emocao_secundaria": sec,
        "energia": num("energia", 0, 100, rules["energia"]), "formalidade": num("formalidade", 0, 100, rules["formalidade"]),
        "velocidade": round(speed, 2),
        "entonacao": str(data.get("entonacao") or rules["entonacao"]), "pausas": str(data.get("pausas") or rules["pausas"]),
        "volume": str(data.get("volume") or rules["volume"]), "estilo": str(data.get("estilo") or rules["estilo"]),
        "usar_expressividade": bool(data.get("usar_expressividade", rules["usar_expressividade"])),
        "usar_pausas_dinamicas": bool(data.get("usar_pausas_dinamicas", rules["usar_pausas_dinamicas"])),
        "usar_variacao_tonal": bool(data.get("usar_variacao_tonal", rules["usar_variacao_tonal"])),
        "personagens": personagens,
        "roteiro_otimizado": str(data.get("roteiro_otimizado") or rules["roteiro_otimizado"]),
    }
    return direcao, segs, det, "ia + elenco e falas originais"

# ============================ ÁUDIO ============================


def synth(text, voice, rate=0, pitch=0, volume=0):
    """Um trecho → float32 mono em SR. Voz online com prosódia; se falhar, Piper (só velocidade e volume)."""
    import narrated_video as nv
    v = VOICES.get(voice, VOICES["francisca"])
    if v.get("edge"):
        try:
            return nv._edge(text, v["edge"], rate, pitch, volume), voice
        except Exception as e:
            print(f"⚠️  Voz online indisponível ({e}); usando a voz offline.")
    audio = nv._piper_tts(text, rate)
    return (audio * (10 ** (volume / 40))).astype(np.float32), "faber"


def render(segments, progress=None):
    """Segmentos dirigidos → um áudio só (float32, SR), com as pausas entre eles."""
    parts, used = [], set()
    for i, s in enumerate(segments):
        if progress:
            progress(i / max(1, len(segments)), f"Gravando {s['personagem']} ({i + 1}/{len(segments)})...")
        audio, v = synth(s["texto"], s["voz"], s["rate"], s["pitch"], s["volume"])
        used.add(v)
        parts.append(audio)
        parts.append(np.zeros(int(SR * s["pausa_ms"] / 1000), dtype=np.float32))
    if not parts:
        return np.zeros(0, dtype=np.float32), used
    track = np.concatenate(parts[:-1] if len(parts) > 1 else parts)
    peak = float(np.max(np.abs(track))) or 1.0
    return (track * min(1.0, 0.95 / peak)).astype(np.float32), used

# ============================ ADAPTAÇÃO AO OUVINTE ============================


def adapt_for_listener(analysis):
    """Como o assistente deve falar com alguém nesse estado emocional (tabela "ADAPTAÇÃO DE TOM").
    Retorna {rate, pitch, volume, pause, tom} — neutro quando não há o que ajustar."""
    emo = (analysis or {}).get("emocao_principal", "Neutralidade")
    inten = (analysis or {}).get("intensidade", 0) / 100
    base = LISTENER.get(emo)
    if not base or inten < 0.3:
        return {"rate": 0, "pitch": 0, "volume": 0, "pause": 320, "tom": "natural"}
    k = 0.5 + 0.5 * inten   # adapta mais quando a emoção é mais forte
    return {"rate": int(base["rate"] * k), "pitch": int(base["pitch"] * k), "volume": int(base["volume"] * k),
            "pause": base["pause"], "tom": base["tom"]}
