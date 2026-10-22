"""
ARMAGEDON — Módulo de análise emocional

Saída no formato combinado (JSON):
  emocao_principal, emocoes_secundarias, intensidade (0-100), sentimento, confianca (0-100),
  risco_emocional, indicadores, explicacao, resposta_recomendada

Duas camadas:
  • analyze(text)          — regras + léxico em português, instantâneo (roda em toda mensagem).
                             Considera palavras, negação, intensificadores, pontuação, CAIXA ALTA, letras
                             repetidas, emojis, sarcasmo, agressividade, pedidos de ajuda e sinais de crise.
  • analyze_deep(text, fn) — o mesmo pedido feito à IA (prompt EMOTION_PROMPT), validado e combinado com as regras.

Segurança: sinais de crise (ideação suicida, autolesão, desesperança) são detectados por regras fixas,
e a camada de IA nunca pode baixar um risco que as regras encontraram.
"""

import json
import re
import unicodedata

EMOTIONS = ["Alegria", "Tristeza", "Raiva", "Frustração", "Medo", "Ansiedade", "Vergonha", "Culpa", "Orgulho",
            "Surpresa", "Confusão", "Solidão", "Entusiasmo", "Gratidão", "Esperança", "Decepção", "Neutralidade"]
POSITIVE = {"Alegria", "Orgulho", "Entusiasmo", "Gratidão", "Esperança"}
NEGATIVE = {"Tristeza", "Raiva", "Frustração", "Medo", "Ansiedade", "Vergonha", "Culpa", "Solidão", "Decepção"}
RISK_ORDER = {"Baixo": 0, "Médio": 1, "Alto": 2}

# Padrões sobre o texto normalizado (minúsculas, sem acentos). Peso ~1 = sinal claro; 0,5 = sinal fraco.
LEXICON = {
    "Alegria": [(r"\bfeliz(es)?\b", 1), (r"\bfelicidade\b", 1), (r"\balegr(e|es|ia)\b", 1), (r"\bcontent[ea]s?\b", 0.8),
                (r"\bmaravilh\w*", 0.9), (r"\b(o|ó)timo\b", 0.6), (r"\badorei\b", 0.9), (r"\bamei\b", 0.9),
                (r"\bque bom\b", 0.8), (r"\bincrivel\b", 0.7), (r"\bsensacional\b", 0.8), (r"\bshow de bola\b", 0.8),
                (r"\b(k{3,}|(ha){2,}|(he){2,}|rs(rs)+)\b", 0.6), ("[😀😁😂😃😄😊🥰😍❤️🤣😆]", 0.7)],
    "Tristeza": [(r"\btrist(e|es|eza)\b", 1), (r"\bchor(ar|ando|ei|o|ou)\b", 1), (r"\bdeprimid[oa]s?\b", 1.1),
                 (r"\bdepress(ao|ivo|iva)\b", 1), (r"\bdesanimad[oa]\b", 0.9), (r"\babatid[oa]\b", 0.7),
                 (r"\bmagoad[oa]\b", 0.9), (r"\bmagoou\b", 0.8), (r"\bsofr(endo|imento|o)\b", 0.9), (r"\bvazi[oa] por dentro\b", 1),
                 (r"\bmelancol\w*", 0.9), (r"\bdesanimo\b", 0.9), (r"\bcoracao partido\b", 1), (r"\bpra baixo\b", 0.7),
                 (r"\bestou mal\b|\bto mal\b|\btou mal\b", 0.8), ("[😢😭☹️🙁😞😔💔]", 0.8),
                 (r"\bperdi (o|a|meu|minha|meus|minhas)\b", 0.9), (r"\b(faleceu|morreu|falecimento)\b", 1), (r"\bluto\b", 1),
                 (r"\bsinto (muita )?falta\b", 0.8), (r"\bsaudade\b", 0.5), (r"\bvazio (enorme|imenso|grande)\b", 0.9)],
    "Raiva": [(r"\braiva\b", 1), (r"\bodi(o|eio|ar)\b", 1), (r"\birritad[oa]\b", 0.9), (r"\birrit(a|ante|ando)\b", 0.7),
              (r"\bput[oa] da vida\b|\bto put[oa]\b|\bestou put[oa]\b", 1.1), (r"\bfurios[oa]\b", 1.1), (r"\brevoltad[oa]\b", 0.9),
              (r"\bindignad[oa]\b", 0.9), (r"\bque merda\b", 0.8), (r"\b(porra|caralho)\b", 0.6), ("[😡🤬😠]", 0.9)],
    "Frustração": [(r"\bfrustr\w*", 1), (r"\bnada (funciona|da certo|deu certo)\b", 1), (r"\bnao funciona\b", 0.7),
                   (r"\bnao (da|deu) certo\b", 0.7), (r"\btudo (da|deu) errado\b", 1), (r"\bde novo (nao|isso)\b", 0.6),
                   (r"\bdesisto\b", 0.9), (r"\bcansei\b", 0.8), (r"\b(aff+|afff*s|pqp)\b", 0.7), (r"\bperda de tempo\b", 0.8),
                   (r"\bja tentei de tudo\b", 0.9), (r"\bsempre a mesma coisa\b", 0.7),
                   (r"\bque droga\b|\bdroga\b", 0.6), ("[😤😩😫]", 0.8)],
    "Medo": [(r"\bmedo\b", 1), (r"\bassustad[oa]\b", 1), (r"\bapavorad[oa]\b", 1.1), (r"\bpavor\b", 1), (r"\bterror\b", 0.8),
             (r"\breceio\b", 0.7), (r"\btemo que\b", 0.8), (r"\bpanico\b", 0.9), ("[😨😱😧]", 0.9),
             (r"\b(sumiu|desapareceu)!", 0.6), (r"\bsocorro\b", 1)],
    "Ansiedade": [(r"\bansios[oa]s?\b(?! (para|pra|por) )", 1), (r"\bansiedade\b", 1.1), (r"\bnervos[oa]\b", 0.8),
                  (r"\bpreocupad[oa]\b", 0.9), (r"\bpreocupa(cao|coes)\b", 0.8), (r"\bangusti\w*", 1), (r"\baflit[oa]\b", 0.9),
                  (r"\binquiet[oa]\b", 0.7), (r"\bnao consigo (dormir|parar de pensar|respirar)\b", 1), (r"\binsonia\b", 0.7),
                  (r"\bcoracao (acelerado|disparado)\b", 1), (r"\bcrise de (ansiedade|panico)\b", 1.2), ("[😰😥😬]", 0.8)],
    "Vergonha": [(r"\bvergonha\b", 1), (r"\benvergonhad[oa]\b", 1), (r"\bconstrangid[oa]\b", 0.9), (r"\bconstrangedor\b", 0.8),
                 (r"\bhumilhad[oa]\b", 1), (r"\bque mico\b", 0.9), ("[😳🫣]", 0.6)],
    "Culpa": [(r"\bculpad[oa]\b", 1), (r"\b(minha|e minha) culpa\b", 1), (r"\bme arrependo\b", 1), (r"\barrependid[oa]\b", 1),
              (r"\bnao devia ter\b", 0.8), (r"\beu errei\b", 0.8), (r"\bpor minha causa\b", 0.8)],
    "Orgulho": [(r"\borgulho\b", 1), (r"\borgulhos[oa]\b", 1), (r"\bconsegui\b", 0.7), (r"\bconquistei\b", 0.9),
                (r"\bpassei (na|no|em)\b", 0.8), (r"\bfui aprovad[oa]\b", 1), (r"\bme formei\b", 1), (r"\bfui promovid[oa]\b", 1)],
    "Surpresa": [(r"\bsurpres\w*", 1), (r"\buau+\b", 0.8), (r"\bcaramba\b", 0.6), (r"\bnao acredito\b", 0.7),
                 (r"\bserio\?+", 0.6), (r"\binacreditavel\b", 0.8), (r"\bnossa+\b", 0.4), ("[😮😲🤯]", 0.8)],
    "Confusão": [(r"\bconfus[oa]\b", 1), (r"\bnao (entendi|entendo|to entendendo|estou entendendo)\b", 1),
                 (r"\b(estou|to|tou|me sinto|fiquei|ando) (meio |muito |tao )?perdid[oa]\b", 0.8),   # não "será perdido"
                 (r"\bcomo assim\b", 0.8), (r"\bsem entender\b", 0.9), (r"\bnao faz sentido\b", 0.6), (r"\?{2,}", 0.5),
                 ("[🤔😕🤨]", 0.7)],
    "Solidão": [(r"\bsozinh[oa]s?\b", 1), (r"\bsolidao\b", 1.1), (r"\bsolitari[oa]\b", 1), (r"\bninguem (me )?(entende|liga|ama|gosta|quer)\b", 1.1),
                (r"\bnao tenho ninguem\b", 1.2), (r"\bisolad[oa]\b", 0.8), (r"\babandonad[oa]\b", 1), (r"\bsem amigos\b", 1),
                (r"\bsaudade\b", 0.5)],
    "Entusiasmo": [(r"\banimad[oa]\b", 0.9), (r"\bempolgad[oa]\b", 1), (r"\bansios[oa] (para|pra|por)\b", 0.9),
                   (r"\bmal posso esperar\b", 1), (r"\bbora+\b", 0.6), (r"\bvamos (nessa|la)\b", 0.7), (r"\bque demais\b", 0.8),
                   ("[🚀🔥🤩🎉🥳]", 0.8)],
    "Gratidão": [(r"\bobrigad[oa]\b", 0.9), (r"\bvaleu\b", 0.8), (r"\bagradec\w*", 1), (r"\bgrat[oa]\b", 1), (r"\bgratidao\b", 1.1),
                 (r"\bmuito obrigad[oa]\b", 1.1), ("[🙏]", 0.8)],
    "Esperança": [(r"\bespero que\b", 0.9), (r"\besperanca\b", 1), (r"\btomara\b", 0.9), (r"\bvai dar certo\b", 0.9),
                  (r"\bvai melhorar\b", 0.9), (r"\botimista\b", 1), (r"\bquem sabe\b", 0.4), (r"\btenho fe\b", 0.9),
                  (r"\b(voce e capaz|voce consegue|acredite (em voce|no seu))\b", 0.9), (r"\bnunca desista\b", 0.9),
                  (r"\bseus sonhos\b", 0.6), (r"\bseu potencial\b", 0.7)],
    "Decepção": [(r"\bdecepcion\w*", 1), (r"\bdecepcao\b", 1), (r"\bdesapont\w*", 1), (r"\besperava mais\b", 1),
                 (r"\bque pena\b", 0.7), (r"\bpoxa\b", 0.5), (r"\bnao era (o que|isso que) eu esperava\b", 1), (r"\bme decepcionou\b", 1.1)],
}

INTENSIFIERS = re.compile(r"\b(muito|demais|super|extremamente|totalmente|completamente|absurdamente|tao|nunca|sempre|"
                          r"nada|tudo|ninguem|mesmo|bastante|horrivel|terrivel|insuportavel)\b")
NEGATION = re.compile(r"\b(nao|nem|nunca|jamais|nada de)\b")

# ---- sinais especiais ----
CRISIS = [  # ideação suicida / autolesão: risco alto sempre
    r"\bquero morrer\b", r"\bvontade de morrer\b", r"\bqueria (estar )?morrer\b", r"\bme matar\b", r"\bvou me matar\b",
    r"\bsuicid\w*", r"\btirar (a )?minha (propria )?vida\b", r"\bacabar com (a )?minha vida\b", r"\bnao quero (mais )?viver\b",
    r"\bnao (vale|faz) (a pena|sentido) (viver|continuar)\b", r"\bqueria (sumir|desaparecer|nao existir|nao ter nascido)\b",
    r"\bme (cortar|machucar|ferir)\b", r"\bautomutila\w*", r"\bmelhor (sem mim|se eu nao existisse)\b",
    r"\bsou um peso\b", r"\bdesistir da vida\b", r"\bacabar com tudo\b",
]
HOPELESS = [  # desesperança / exaustão emocional
    r"\bnao aguento mais\b", r"\bnao vejo saida\b", r"\bnao tem (saida|jeito)\b", r"\bsem saida\b", r"\bnada (mais )?faz sentido\b",
    r"\btudo (da|deu) errado na minha vida\b", r"\bminha vida (e|esta) um (lixo|inferno|fracasso)\b", r"\bsou um fracasso\b",
    r"\bnao sirvo para nada\b|\bnao sirvo pra nada\b", r"\bnao tenho (mais )?forcas\b", r"\bnao sei mais o que fazer\b",
    r"\bcansad[oa] de (tudo|viver)\b", r"\bdesisti de tudo\b",
]
HELP = [r"\bpreciso de ajuda\b", r"\bme ajuda\b.*\b(por favor|pfv|pf)\b", r"\bnao sei o que fazer\b", r"\balguem me ajuda\b",
        r"\bpreciso (desabafar|conversar|falar com alguem)\b", r"\bposso desabafar\b", r"\bme sinto (perdid[oa]|sem rumo)\b"]
AGGRESSION = [r"\b(idiota|imbecil|burr[oa]|estupid[oa]|otari[oa]|inutil|lixo|retardad[oa]|babaca|merda de)\b",
              r"\b(vai se f\w*|vtnc|vsf|fdp|filh[oa] da puta|cala a boca|cala boca)\b", r"\bvoce e (um|uma) (inutil|lixo|idiota|merda)\b"]
SARCASM = [r"\bso que nao\b", r"\bobrigad[oa] por nada\b", r"\bclaro,? ne\b", r"\bparabens,? hein\b", r"\bque surpresa,? (ne|hein)\b",
           r"\bnossa,? que (otimo|maravilha|legal)\b", "[🙄😒😏]", r"\bque otimo,? (mais|de novo)\b", r"\bai que maravilha\b"]

RECOMMEND = {
    "Alegria": "Compartilhar a alegria com entusiasmo genuíno e manter um tom leve.",
    "Tristeza": "Responder com empatia, validar o sentimento e oferecer escuta, sem minimizar.",
    "Raiva": "Manter a calma, reconhecer a irritação sem confrontar e focar em resolver o problema.",
    "Frustração": "Reconhecer a frustração, ser objetivo e oferecer uma solução prática, passo a passo.",
    "Medo": "Acolher, transmitir segurança e dar informações claras que reduzam a incerteza.",
    "Ansiedade": "Responder com calma, em frases curtas e organizadas, ajudando a dividir o problema em passos.",
    "Vergonha": "Acolher sem julgamento e normalizar a situação.",
    "Culpa": "Acolher sem julgamento, separar o erro da pessoa e sugerir formas de reparar.",
    "Orgulho": "Parabenizar de forma sincera e específica pela conquista.",
    "Surpresa": "Acompanhar a surpresa e esclarecer o que for preciso.",
    "Confusão": "Explicar de forma mais simples, com exemplos, e confirmar se ficou claro.",
    "Solidão": "Demonstrar presença e acolhimento, validar o sentimento e incentivar o contato com pessoas próximas.",
    "Entusiasmo": "Compartilhar o entusiasmo e ajudar a transformar a empolgação em próximos passos.",
    "Gratidão": "Receber o agradecimento com cordialidade e se colocar à disposição.",
    "Esperança": "Apoiar a expectativa positiva de forma realista.",
    "Decepção": "Reconhecer a decepção, validar a expectativa que não se cumpriu e propor alternativas.",
    "Neutralidade": "Responder normalmente, de forma clara e objetiva.",
}
SUPPORT = ("Se a pessoa falar em se machucar ou não querer viver, pergunte com cuidado se ela está em segurança agora e "
           "indique o CVV (ligue 188, gratuito, 24 horas, ou cvv.org.br) e, em perigo imediato, o SAMU (192).")

# ============================ NORMALIZAÇÃO ============================


def _normalize(text):
    """minúsculas e sem acentos, mantendo emojis e o mesmo comprimento (as posições batem com o original)."""
    text = unicodedata.normalize("NFC", text)
    out = []
    for ch in text:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
        out.append((base or ch)[0].lower() if len(base) <= 1 else ch.lower())
    return "".join(out), text


def _find(patterns, norm, orig):
    hits = []
    for p in patterns:
        for m in re.finditer(p, norm):
            hits.append((m.start(), m.end(), orig[m.start():m.end()]))
    return hits


def _negated(norm, start):
    """Há um "não"/"nem" nas 2 palavras antes desta posição? ("não estou feliz" → sim).
    "nunca" fica de fora: em "nunca fui tão feliz" / "nunca me senti tão sozinho" ele intensifica, não nega."""
    before = norm[max(0, start - 25):start].split()[-2:]
    return any(w in ("nao", "nem") for w in before)

# ============================ ANÁLISE POR REGRAS ============================


def analyze(text):
    """Análise instantânea. Retorna (analise_no_formato_combinado, sinais)."""
    norm, orig = _normalize(text or "")
    words = re.findall(r"\w+", norm)
    scores, indicators = {}, []

    def add(emotion, weight, phrase):
        scores[emotion] = scores.get(emotion, 0) + weight
        if phrase.strip() and phrase.strip().lower() not in [i.lower() for i in indicators]:
            indicators.append(phrase.strip())

    for emotion, patterns in LEXICON.items():
        for pattern, weight in patterns:
            for m in re.finditer(pattern, norm):
                phrase = orig[m.start():m.end()]
                if emotion == "Solidão" and "sozinh" in norm[m.start():m.end()] and re.search(
                        r"\b(consegui|fiz|terminei|aprendi|resolvi|montei|criei|construi)\b(\W+\w+){0,5}\W*$", norm[:m.start()]):
                    continue   # "consegui sozinho" = por conta própria, não solidão
                if emotion in POSITIVE and _negated(norm, m.start()):
                    add("Decepção" if emotion != "Alegria" else "Tristeza", weight * 0.7, orig[max(0, m.start() - 12):m.end()])
                    continue
                if emotion in NEGATIVE and _negated(norm, m.start()) and not re.match(r"nao", norm[m.start():]):
                    scores[emotion] = scores.get(emotion, 0) - weight * 0.6   # "não estou triste"
                    continue
                add(emotion, weight, phrase)

    crisis = _find(CRISIS, norm, orig)
    hopeless = _find(HOPELESS, norm, orig)
    help_req = _find(HELP, norm, orig)
    aggression = _find(AGGRESSION, norm, orig)
    sarcasm = _find(SARCASM, norm, orig)

    for _, _, p in crisis:
        add("Tristeza", 1.5, p)
    for _, _, p in hopeless:   # desesperança pesa como tristeza (exaustão emocional), não só frustração
        add("Tristeza", 1.3, p)
        scores["Frustração"] = scores.get("Frustração", 0) + 0.3
    for _, _, p in aggression:
        add("Raiva", 1.0, p)
    for _, _, p in help_req:   # pedir ajuda/desabafo indica sofrimento mesmo sem a emoção nomeada
        add("Tristeza", 0.6, p)
        scores["Ansiedade"] = scores.get("Ansiedade", 0) + 0.45

    # sarcasmo: sinal explícito, ou elogio no meio de reclamação → as emoções positivas viram frustração/decepção
    pos_score = sum(v for k, v in scores.items() if k in POSITIVE)
    neg_score = sum(v for k, v in scores.items() if k in NEGATIVE)
    is_sarcasm = bool(sarcasm) or (pos_score > 0 and scores.get("Frustração", 0) >= 0.7 and re.search(r"\b(otimo|maravilh|parabens|adorei)\w*", norm))
    if is_sarcasm:
        for _, _, p in sarcasm:
            indicators.append(p) if p not in indicators else None
        moved = sum(scores.pop(k, 0) for k in list(scores) if k in POSITIVE)
        scores["Frustração"] = scores.get("Frustração", 0) + max(0.8, moved * 0.8)
        scores["Decepção"] = scores.get("Decepção", 0) + 0.4

    scores = {k: v for k, v in scores.items() if v > 0.15}

    # ---- intensidade ----
    n_int = len(INTENSIFIERS.findall(norm))
    exclam = min(text.count("!"), 4)
    letters = [c for c in text if c.isalpha()]
    caps = sum(c.isupper() for c in letters) / len(letters) if len(letters) >= 8 else 0
    stretched = bool(re.search(r"([a-z])\1{2,}", norm))
    if scores:
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        primary, top = ranked[0]
        intensity = 32 + 20 * min(top, 2.5) + 7 * min(n_int, 3) + 4 * exclam + (10 if caps > 0.6 else 0) + (6 if stretched else 0)
        intensity += 12 if crisis else 8 if hopeless else 0
        secondary = [k for k, v in ranked[1:] if v >= 0.4 * top][:3]
    else:
        primary, top, secondary = "Neutralidade", 0, []
        intensity = 8 + 4 * exclam
    intensity = int(max(3, min(100, intensity)))

    # ---- sentimento ----
    pos = sum(v for k, v in scores.items() if k in POSITIVE)
    neg = sum(v for k, v in scores.items() if k in NEGATIVE)
    sentiment = "Positivo" if pos > neg * 1.1 and pos > 0 else "Negativo" if neg > pos * 1.1 and neg > 0 else "Neutro"

    # ---- risco ----
    if crisis:
        risk = "Alto"
    elif hopeless and (intensity >= 70 or len(hopeless) >= 2):
        risk = "Alto"
    elif hopeless or (sentiment == "Negativo" and intensity >= 85) or (help_req and sentiment == "Negativo"):
        risk = "Médio"
    elif aggression:
        risk = "Médio"
    else:
        risk = "Baixo"

    # ---- confiança ----
    n_ind = len(indicators)
    if primary == "Neutralidade":
        confidence = 72 if len(words) >= 3 else 55
    else:
        second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
        margin = (top - second) / top if top else 0
        confidence = 50 + 11 * min(n_ind, 4) + 10 * margin - (15 if is_sarcasm else 0) - (10 if len(words) < 4 else 0)
        confidence += 6 if crisis else 0
    confidence = int(max(25, min(97, confidence)))

    # ---- explicação ----
    parts = []
    if primary == "Neutralidade":
        parts.append("Não há sinais claros de emoção; a mensagem é informativa ou neutra.")
    else:
        parts.append(f"Expressa {primary.lower()}" + (f", com {', '.join(s.lower() for s in secondary)}" if secondary else "") + ".")
    if crisis:
        parts.append("Há menção a se machucar ou a não querer viver: possível crise emocional.")
    elif hopeless:
        parts.append("Há sinais de desesperança e exaustão emocional.")
    if help_req:
        parts.append("A pessoa pede ajuda ou apoio emocional.")
    if is_sarcasm:
        parts.append("Há sinais de sarcasmo: o elogio não deve ser entendido ao pé da letra.")
    if aggression:
        parts.append("Há linguagem agressiva.")
    if n_int or exclam or caps > 0.6:
        parts.append("Intensificadores, pontuação ou caixa alta aumentam a intensidade.")
    explanation = " ".join(parts)

    # ---- resposta recomendada ----
    rec = RECOMMEND[primary]
    if is_sarcasm:
        rec = "Não interpretar o elogio ao pé da letra; reconhecer a insatisfação. " + RECOMMEND["Frustração"]
    if aggression:
        rec = "Não revidar a agressividade; responder com respeito e firmeza. " + rec
    if help_req and risk != "Alto":
        rec += " Oferecer escuta e apoio."
    if risk == "Alto":
        rec = "Responder com empatia e acolhimento, validar as emoções e incentivar a busca de apoio. " + SUPPORT

    analysis = {
        "emocao_principal": primary,
        "emocoes_secundarias": secondary,
        "intensidade": intensity,
        "sentimento": sentiment,
        "confianca": confidence,
        "risco_emocional": risk,
        # sem repetição: "tudo dá errado" some quando "tudo dá errado na minha vida" também foi encontrado
        "indicadores": [i for i in indicators if not any(i != o and i.lower() in o.lower() for o in indicators)][:8],
        "explicacao": explanation,
        "resposta_recomendada": rec,
    }
    signals = {"crise": bool(crisis), "desesperanca": bool(hopeless), "pedido_ajuda": bool(help_req),
               "agressividade": bool(aggression), "sarcasmo": bool(is_sarcasm)}
    return analysis, signals

# ============================ ANÁLISE PELA IA ============================

EMOTION_PROMPT = """Você é um módulo de análise emocional para uma IA conversacional.

Sua função é analisar a mensagem do usuário e identificar:

1. Emoção principal
2. Emoções secundárias (se existirem)
3. Intensidade emocional (0-100)
4. Sentimento geral (positivo, negativo ou neutro)
5. Nível de confiança da análise (0-100)
6. Indicadores encontrados no texto
7. Risco emocional (baixo, médio ou alto)
8. Resposta recomendada para a IA

Emoções possíveis:

- Alegria
- Tristeza
- Raiva
- Frustração
- Medo
- Ansiedade
- Vergonha
- Culpa
- Orgulho
- Surpresa
- Confusão
- Solidão
- Entusiasmo
- Gratidão
- Esperança
- Decepção
- Neutralidade

Regras:

- Considere contexto, palavras, tom e pontuação.
- Emoções podem coexistir.
- Não invente emoções sem evidências.
- Detecte sarcasmo quando houver sinais claros.
- Detecte linguagem agressiva.
- Detecte pedidos de ajuda emocional.
- Detecte possíveis crises emocionais.

Retorne APENAS JSON válido.

Formato:

{
  "emocao_principal": "",
  "emocoes_secundarias": [],
  "intensidade": 0,
  "sentimento": "",
  "confianca": 0,
  "risco_emocional": "",
  "indicadores": [],
  "explicacao": "",
  "resposta_recomendada": ""
}

Exemplo:

Entrada:
"Eu não aguento mais nada, tudo dá errado na minha vida."

Saída:
{
  "emocao_principal": "Tristeza",
  "emocoes_secundarias": ["Frustração"],
  "intensidade": 89,
  "sentimento": "Negativo",
  "confianca": 94,
  "risco_emocional": "Alto",
  "indicadores": [
    "não aguento mais",
    "tudo dá errado"
  ],
  "explicacao": "Expressa desesperança, exaustão emocional e sentimento persistente de fracasso.",
  "resposta_recomendada": "Responder com empatia, validar emoções e incentivar busca de apoio."
}"""

_CANON = {re.sub(r"[^a-z]", "", _normalize(e)[0]): e for e in EMOTIONS}


def _canon_emotion(name):
    return _CANON.get(re.sub(r"[^a-z]", "", _normalize(str(name or ""))[0]))


def _canon_choice(value, options):
    key = _normalize(str(value or ""))[0].strip()
    for opt in options:
        if _normalize(opt)[0] == key:
            return opt
    return None


def analyze_deep(text, llm_json):
    """Análise pela IA (prompt combinado), validada e combinada com as regras.
    llm_json(system, user) → dict. Retorna (analise, sinais, metodo)."""
    rules, signals = analyze(text)
    try:
        data = llm_json(EMOTION_PROMPT, f'Entrada:\n"{text}"\n\nSaída:')
    except Exception as e:
        return rules, signals, f"regras (IA indisponível: {e})"
    primary = _canon_emotion(data.get("emocao_principal")) or rules["emocao_principal"]
    secondary = [e for e in (_canon_emotion(x) for x in data.get("emocoes_secundarias") or []) if e and e != primary][:3]
    sentiment = _canon_choice(data.get("sentimento"), ["Positivo", "Negativo", "Neutro"]) or rules["sentimento"]
    risk = _canon_choice(data.get("risco_emocional"), ["Baixo", "Médio", "Alto"]) or rules["risco_emocional"]

    def num(key, fallback):
        try:
            return int(max(0, min(100, float(data.get(key)))))
        except (TypeError, ValueError):
            return fallback

    # segurança: a IA nunca baixa o risco que as regras encontraram
    if RISK_ORDER[rules["risco_emocional"]] > RISK_ORDER[risk]:
        risk = rules["risco_emocional"]
    rec = str(data.get("resposta_recomendada") or "").strip() or RECOMMEND.get(primary, RECOMMEND["Neutralidade"])
    if risk == "Alto" and "188" not in rec:
        rec = rec.rstrip(".") + ". " + SUPPORT
    indicators = [str(i).strip() for i in (data.get("indicadores") or []) if str(i).strip()][:8] or rules["indicadores"]
    analysis = {
        "emocao_principal": primary,
        "emocoes_secundarias": secondary,
        "intensidade": num("intensidade", rules["intensidade"]),
        "sentimento": sentiment,
        "confianca": num("confianca", rules["confianca"]),
        "risco_emocional": risk,
        "indicadores": indicators,
        "explicacao": str(data.get("explicacao") or rules["explicacao"]).strip(),
        "resposta_recomendada": rec,
    }
    return analysis, signals, "ia + regras de segurança"


def guidance(analysis, signals):
    """Trecho para o system prompt da IA conversacional ('' quando não há nada a ajustar)."""
    if analysis["emocao_principal"] == "Neutralidade" and analysis["risco_emocional"] == "Baixo" and not signals["agressividade"]:
        return ""
    sec = f" (também {', '.join(e.lower() for e in analysis['emocoes_secundarias'])})" if analysis["emocoes_secundarias"] else ""
    return ("ESTADO EMOCIONAL PERCEBIDO NA MENSAGEM DO USUÁRIO (não comente esta análise com ele, apenas ajuste o jeito de responder):\n"
            f"- Emoção: {analysis['emocao_principal']}{sec}; intensidade {analysis['intensidade']}/100; "
            f"sentimento {analysis['sentimento'].lower()}; risco {analysis['risco_emocional'].lower()}.\n"
            f"- Como responder: {analysis['resposta_recomendada']}")


if __name__ == "__main__":
    import sys
    msg = " ".join(sys.argv[1:]) or "Eu não aguento mais nada, tudo dá errado na minha vida."
    a, s = analyze(msg)
    print(json.dumps(a, ensure_ascii=False, indent=2))
    print(s)
