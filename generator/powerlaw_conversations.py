#!/usr/bin/env python3
"""Página «Conversaciones de interés» (conversaciones/index.html).

En cada actualización califican solo posts originales con created_at
de como máximo 7200 segundos y autor con followers_count verificado
estrictamente mayor que 20000. No se usa la hora de una cita, ni
searched_at, ni una marca de verificación. Un conteo ausente o no
verificado queda fuera. La ventana no se amplía para completar cupos.

Los temas viven en conversation_topics.json. Cada tarjeta lleva un tema
(el campo topic del lote, si es un id conocido; si no, la primera
palabra clave que aparezca en el contexto o en la respuesta; si no, el
tema marcado default).

No publica nada en X: solo arma enlaces https://x.com/intent/post.
La página principal solo recibe el enlace a conversaciones/.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WINDOW_SECONDS = 7200
MIN_FOLLOWERS_EXCLUSIVE = 20000
FUTURE_SKEW_SECONDS = 120
SNOWFLAKE_TOLERANCE_SECONDS = 2
SNOWFLAKE_EPOCH_MS = 1288834974657
SECTION_TITLE = "Conversaciones de interés"
START = "<!-- powerlaw-conversations:start -->"
END = "<!-- powerlaw-conversations:end -->"
STORE_NAME = "powerlaw_store.json"
TOPICS_NAME = "conversation_topics.json"
CONVERSATIONS_DIR = "conversaciones"
PAGE_NAME = "index.html"
MAIN_LINK_HREF = "conversaciones/"
HOME_HREF = "../index.html"
CHILE = ZoneInfo("America/Santiago")
_TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
EMPTY_TEXT = (
    "Sin posts originales dentro de los últimos 7200 segundos con un conteo de seguidores "
    "verificado mayor que 20.000. No se completa la sección con autores en o bajo 20.000 "
    "ni con un conteo desconocido."
)

_ITEM_FIELDS = (
    "id",
    "author",
    "url",
    "created_at",
    "created_at_verified",
    "timestamp_source",
    "created_at_chile",
    "context",
    "suggested_text",
    "language",
    "cta",
    "source_post_id",
    "reply_with_suggestion",
    "reply_blank",
    "followers_count",
    "followers_count_verified",
    "followers_source",
    "followers_checked_at",
    "topic",
)


def topics_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TOPICS_NAME)


def load_topics(path=None):
    """Lista ordenada de temas. Un solo default. Ids estables y en minúsculas."""
    path = path or topics_path()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not data:
        raise ValueError("la lista de temas debe tener al menos un tema")
    cleaned = []
    seen = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("cada tema debe ser un objeto")
        topic_id = entry.get("id")
        label = entry.get("label")
        if not isinstance(topic_id, str) or not _TOPIC_ID.fullmatch(topic_id):
            raise ValueError("id de tema inválido")
        if topic_id in seen:
            raise ValueError("id de tema repetido: " + topic_id)
        seen.add(topic_id)
        if not isinstance(label, str) or not label.strip():
            raise ValueError("cada tema necesita label")
        keywords = entry.get("keywords") or []
        if not isinstance(keywords, list) or not all(isinstance(word, str) and word.strip() for word in keywords):
            raise ValueError("keywords debe ser una lista de textos")
        cleaned.append({
            "id": topic_id,
            "label": label.strip(),
            "keywords": [word.strip() for word in keywords],
            "default": entry.get("default") is True,
        })
    if sum(1 for topic in cleaned if topic["default"]) != 1:
        raise ValueError('marca un solo tema con "default": true')
    return cleaned


def resolve_topic(item, topics=None):
    """Id de tema para una tarjeta. Un topic conocido gana; si no, palabras clave; si no, el default."""
    topics = load_topics() if topics is None else topics
    known = {topic["id"] for topic in topics}
    raw = item.get("topic")
    if isinstance(raw, str) and raw.strip() in known:
        return raw.strip()
    blob = "\n".join(
        value if isinstance(value, str) else ""
        for value in (item.get("context"), item.get("suggested_text"))
    ).casefold()
    for topic in topics:
        for keyword in topic["keywords"]:
            if keyword.casefold() in blob:
                return topic["id"]
    for topic in topics:
        if topic["default"]:
            return topic["id"]
    return topics[-1]["id"]


def conversations_path_for(index_path):
    return os.path.join(os.path.dirname(os.path.abspath(index_path)), CONVERSATIONS_DIR, PAGE_NAME)


def empty_store():
    return {
        "window_seconds": WINDOW_SECONDS,
        "min_followers_exclusive": MIN_FOLLOWERS_EXCLUSIVE,
        "evaluated_at": None,
        "last_batch_searched_at": None,
        "items": {},
        "discarded": {},
        "history": {},
    }


def store_path(store_dir):
    return os.path.join(store_dir, STORE_NAME)


def load_store(store_dir):
    path = store_path(store_dir)
    if not os.path.exists(path):
        return empty_store()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    base = empty_store()
    if isinstance(data, dict):
        for key in base:
            if key in data and isinstance(data[key], type(base[key])):
                base[key] = data[key]
        if data.get("evaluated_at"):
            base["evaluated_at"] = data["evaluated_at"]
        searched = data.get("last_batch_searched_at")
        if isinstance(searched, str):
            base["last_batch_searched_at"] = searched
    base["window_seconds"] = WINDOW_SECONDS
    base["min_followers_exclusive"] = MIN_FOLLOWERS_EXCLUSIVE
    return base


def save_store(store_dir, store):
    store["window_seconds"] = WINDOW_SECONDS
    store["min_followers_exclusive"] = MIN_FOLLOWERS_EXCLUSIVE
    path = store_path(store_dir)
    os.makedirs(store_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def parse_chile_label(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\s+America/Santiago)?",
        value.strip(),
    )
    if not match:
        return None
    try:
        naive = datetime.fromisoformat(match.group(1) + "T" + match.group(2))
    except ValueError:
        return None
    return naive.replace(tzinfo=CHILE).astimezone(timezone.utc)


def snowflake_datetime(status_id):
    try:
        number = int(str(status_id))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    millis = (number >> 22) + SNOWFLAKE_EPOCH_MS
    return datetime.fromtimestamp(millis / 1000, timezone.utc)


def status_id_from_url(url):
    match = re.search(r"/status/(\d+)", url or "")
    return match.group(1) if match else None


def suggestion_intent(status_id, text):
    return (
        "https://x.com/intent/post?in_reply_to="
        + str(status_id)
        + "&text="
        + urllib.parse.quote(text, safe="")
    )


def blank_intent(status_id):
    return "https://x.com/intent/post?in_reply_to=" + str(status_id)


def chile_stamp(moment, seconds=True):
    local = moment.astimezone(CHILE)
    pattern = "%d-%m-%Y %H:%M:%S hora Chile" if seconds else "%d-%m-%Y %H:%M hora Chile"
    return local.strftime(pattern)


def format_followers(count):
    return f"{count:,}".replace(",", ".")


def follower_gate(item, evaluated_at):
    """Conteo público verificado y estrictamente mayor que 20000.

    Una marca de verificación no cuenta como tamaño. Sin número verificable
    el resultado es negativo.
    """
    if "followers_count" not in item or item.get("followers_count") is None:
        return False, "missing_followers_count"
    if item.get("followers_count_verified") is not True:
        return False, "unverifiable_followers_count"
    count = item.get("followers_count")
    if isinstance(count, bool) or not isinstance(count, int):
        return False, "unverifiable_followers_count"
    checked = parse_time(item.get("followers_checked_at"))
    if checked is None:
        return False, "unverifiable_followers_count"
    if checked > evaluated_at.astimezone(timezone.utc) + timedelta(seconds=FUTURE_SKEW_SECONDS):
        return False, "unverifiable_followers_count"
    if count <= MIN_FOLLOWERS_EXCLUSIVE:
        return False, "followers_not_above_20000"
    return True, ""


def qualification_record(item, evaluated_at, qualified, reason):
    created = parse_time(item.get("created_at")) if item.get("created_at") else None
    checked = parse_time(item.get("followers_checked_at")) if item.get("followers_checked_at") else None
    count = item.get("followers_count")
    if isinstance(count, bool) or not isinstance(count, int):
        count = None
    age = None
    if created is not None:
        age = round((evaluated_at.astimezone(timezone.utc) - created).total_seconds(), 3)
    return {
        "qualified": qualified,
        "exclude_reason": reason,
        "window_seconds": WINDOW_SECONDS,
        "min_followers_exclusive": MIN_FOLLOWERS_EXCLUSIVE,
        "age_seconds": age,
        "followers_count": count,
        "followers_count_verified": item.get("followers_count_verified") is True,
        "followers_checked_at": checked.isoformat() if checked else "",
    }


def _archive_stub(item, reason, evaluated_at):
    count = item.get("followers_count")
    if isinstance(count, bool) or not isinstance(count, int):
        count = None
    return {
        "id": str(item.get("id") or ""),
        "author": item.get("author") or "",
        "url": item.get("url") or "",
        "created_at": item.get("created_at") or "",
        "followers_count": count,
        "followers_checked_at": item.get("followers_checked_at") or "",
        "exclude_reason": reason,
        "qualification": qualification_record(item, evaluated_at, False, reason),
        "archived_at": evaluated_at.astimezone(timezone.utc).isoformat(),
    }


def classify(item, evaluated_at):
    """Devuelve (califica, motivo). La ventana es siempre WINDOW_SECONDS."""
    status_id = str(item.get("id") or "").strip()
    if not status_id or not status_id.isdigit():
        return False, "missing_id"
    if item.get("created_at") in (None, ""):
        return False, "missing_created_at"
    if item.get("created_at_verified") is not True:
        return False, "unverifiable_created_at"
    created = parse_time(item.get("created_at"))
    if created is None:
        return False, "unverifiable_created_at"
    embedded = snowflake_datetime(status_id)
    if embedded is None or abs((embedded - created).total_seconds()) > SNOWFLAKE_TOLERANCE_SECONDS:
        return False, "snowflake_mismatch"
    chile = item.get("created_at_chile")
    if chile:
        labeled = parse_chile_label(chile)
        if labeled is None or abs((labeled - created).total_seconds()) > SNOWFLAKE_TOLERANCE_SECONDS:
            return False, "chile_label_mismatch"
    if status_id_from_url(item.get("url")) != status_id:
        return False, "url_id_mismatch"
    text = item.get("suggested_text")
    if not isinstance(text, str) or not text.strip():
        return False, "missing_suggested_text"
    author = item.get("author")
    if not isinstance(author, str) or not author.strip():
        return False, "missing_author"
    context = item.get("context")
    if not isinstance(context, str) or not context.strip():
        return False, "missing_context"
    expected_suggestion = suggestion_intent(status_id, text)
    expected_blank = blank_intent(status_id)
    supplied_suggestion = item.get("reply_with_suggestion")
    supplied_blank = item.get("reply_blank")
    if supplied_suggestion not in (None, "") and supplied_suggestion != expected_suggestion:
        return False, "intent_mismatch"
    if supplied_blank not in (None, "") and supplied_blank != expected_blank:
        return False, "intent_mismatch"
    if "text=" in expected_blank:
        return False, "intent_mismatch"
    age = (evaluated_at.astimezone(timezone.utc) - created).total_seconds()
    if age < -FUTURE_SKEW_SECONDS:
        return False, "unverifiable_created_at"
    if age > WINDOW_SECONDS:
        return False, "older_than_7200s"
    followers_ok, followers_reason = follower_gate(item, evaluated_at)
    if not followers_ok:
        return False, followers_reason
    return True, ""


def _public_item(raw, previous, evaluated_at):
    item = {}
    for field in _ITEM_FIELDS:
        if field in raw:
            item[field] = raw[field]
    item["id"] = str(raw.get("id") or "").strip()
    if previous and previous.get("created_at"):
        item["created_at"] = previous["created_at"]
        if previous.get("created_at_verified") is True:
            item["created_at_verified"] = True
        if previous.get("created_at_chile"):
            item["created_at_chile"] = previous["created_at_chile"]
    stamp = evaluated_at.astimezone(timezone.utc).isoformat()
    item["first_seen_at"] = (previous or {}).get("first_seen_at") or stamp
    item["last_seen_at"] = stamp
    return item


def merge_batch(store, batch, evaluated_at, topics=None):
    """Incorpora un lote. Dedup por id. No guarda texto de lo que no califica."""
    if not isinstance(batch, dict):
        raise ValueError("el lote debe ser un objeto JSON")
    topics = load_topics() if topics is None else topics
    discarded = store.setdefault("discarded", {})
    items = store.setdefault("items", {})
    history = store.setdefault("history", {})
    for entry in batch.get("excluded_previous_candidates") or []:
        if not isinstance(entry, dict):
            continue
        status_id = str(entry.get("id") or "").strip()
        if not status_id:
            continue
        record = {
            "id": status_id,
            "author": entry.get("author") or "",
            "created_at": entry.get("created_at") or "",
            "reason": entry.get("reason") or "discarded",
            "source": "excluded_previous_candidates",
        }
        count = entry.get("followers_count")
        if isinstance(count, int) and not isinstance(count, bool):
            record["followers_count"] = count
        checked = entry.get("followers_checked_at") or entry.get("checked_at")
        if isinstance(checked, str):
            record["followers_checked_at"] = checked
        discarded[status_id] = record
        items.pop(status_id, None)
        history.pop(status_id, None)
    for raw in batch.get("items") or []:
        if not isinstance(raw, dict):
            continue
        status_id = str(raw.get("id") or "").strip()
        if not status_id or status_id in discarded:
            continue
        previous = items.get(status_id)
        item = _public_item(raw, previous, evaluated_at)
        item["topic"] = resolve_topic(item, topics)
        ok, reason = classify(item, evaluated_at)
        if not ok:
            history[status_id] = _archive_stub(item, reason, evaluated_at)
            items.pop(status_id, None)
            continue
        item["qualified"] = True
        item["exclude_reason"] = ""
        item["qualification"] = qualification_record(item, evaluated_at, True, "")
        item["reply_with_suggestion"] = suggestion_intent(status_id, item["suggested_text"])
        item["reply_blank"] = blank_intent(status_id)
        history.pop(status_id, None)
        items[status_id] = item
    reclassify(store, evaluated_at, topics)
    store["evaluated_at"] = evaluated_at.astimezone(timezone.utc).isoformat()
    store["window_seconds"] = WINDOW_SECONDS
    store["min_followers_exclusive"] = MIN_FOLLOWERS_EXCLUSIVE
    store["last_batch_searched_at"] = batch.get("searched_at")
    return store


def reclassify(store, evaluated_at, topics=None):
    topics = load_topics() if topics is None else topics
    items = store.setdefault("items", {})
    history = store.setdefault("history", {})
    discarded = store.setdefault("discarded", {})
    for status_id, item in list(items.items()):
        if status_id in discarded:
            history[status_id] = _archive_stub(item, "discarded", evaluated_at)
            del items[status_id]
            continue
        item["topic"] = resolve_topic(item, topics)
        ok, reason = classify(item, evaluated_at)
        if not ok:
            history[status_id] = _archive_stub(item, reason, evaluated_at)
            del items[status_id]
            continue
        item["qualified"] = True
        item["exclude_reason"] = ""
        item["qualification"] = qualification_record(item, evaluated_at, True, "")
        item["reply_with_suggestion"] = suggestion_intent(status_id, item.get("suggested_text") or "")
        item["reply_blank"] = blank_intent(status_id)
    store["evaluated_at"] = evaluated_at.astimezone(timezone.utc).isoformat()
    store["window_seconds"] = WINDOW_SECONDS
    store["min_followers_exclusive"] = MIN_FOLLOWERS_EXCLUSIVE
    return store


def qualified_items(store, evaluated_at):
    chosen = []
    discarded = store.get("discarded") or {}
    for item in (store.get("items") or {}).values():
        status_id = str(item.get("id") or "")
        if status_id in discarded:
            continue
        ok, _reason = classify(item, evaluated_at)
        if ok:
            chosen.append(item)
    chosen.sort(key=lambda item: (item.get("created_at") or "", str(item.get("id") or "")))
    return chosen


def _esc(value):
    return html.escape(value or "", quote=True)


def render_main_link():
    """Bloque corto para index.html. Las tarjetas viven en conversaciones/index.html."""
    return (
        START
        + '<div class="warn" id="pl-conversations-link"><b>Conversaciones de interés.</b> '
        + "Posts de X a los que quizá quieras responder: power law de Bitcoin y el debate del precio de BTC. "
        + "Nada se publica solo."
        + f'<div><a class="ref" href="{MAIN_LINK_HREF}" style="display:inline-block;margin-top:8px">Abrir conversaciones</a></div></div>'
        + END
    )


def _topics_by_id(topics):
    return {topic["id"]: topic for topic in topics}


def _topic_of(item, topics):
    known = _topics_by_id(topics)
    topic_id = item.get("topic")
    if topic_id not in known:
        topic_id = resolve_topic(item, topics)
    return known[topic_id]


def _reply_lang(item):
    lang = item.get("language")
    if isinstance(lang, str) and re.fullmatch(r"[a-z]{2}", lang):
        return lang
    return "en"


def render_card(item, topic):
    status_id = str(item["id"])
    created = parse_time(item["created_at"])
    checked = parse_time(item.get("followers_checked_at"))
    count = item.get("followers_count")
    if created is None or checked is None or isinstance(count, bool) or not isinstance(count, int):
        return ""
    if count <= MIN_FOLLOWERS_EXCLUSIVE:
        return ""
    text = item["suggested_text"]
    suggestion = suggestion_intent(status_id, text)
    blank = blank_intent(status_id)
    expires = created + timedelta(seconds=WINDOW_SECONDS)
    length_note = ""
    if len(text) > 280:
        length_note = f'<div class="l280">más de 280 caracteres ({len(text)})</div>'
    return (
        f'<article class="card pl-card" id="pl{status_id}" data-id="pl-{status_id}" '
        f'data-reply-id="{status_id}" data-topic="{_esc(topic["id"])}" '
        f'data-created-at="{_esc(created.strftime("%Y-%m-%dT%H:%M:%SZ"))}" '
        f'data-followers-count="{count}" data-followers-checked-at="{_esc(item.get("followers_checked_at") or "")}" '
        f'data-g="0" data-n="1"><div class="ch"><div><b>{_esc(item["author"].strip())}</b> '
        f'<span class="pill new">Nuevo</span><span class="pill">{_esc(topic["label"])}</span>'
        f'<div class="sm">{_esc(chile_stamp(created))} · vence {_esc(chile_stamp(expires))}</div>'
        f'<div class="sm">Seguidores: {_esc(format_followers(count))} · revisado {_esc(chile_stamp(checked))}</div></div>'
        f'<a class="ref" href="{_esc(item["url"])}" target="_blank" rel="noopener">Ver post original ↗</a></div>'
        f'<div class="why"><b>Contexto:</b> {_esc(item["context"].strip())}</div>'
        f'<div class="blk"><div class="bh"><span>Respuesta sugerida</span><div class="bb">'
        f'<button type="button" onclick="plCopy(this)">Copiar texto</button>'
        f'<a class="xb pl-sug" data-k="reply" href="{_esc(suggestion)}" target="_blank" rel="noopener">Responder con sugerencia</a>'
        f'<a class="xb pl-blank" data-k="reply" href="{_esc(blank)}" target="_blank" rel="noopener">Responder en blanco</a>'
        f'</div></div>{length_note}'
        f'<textarea class="pl-text" lang="{_reply_lang(item)}" spellcheck="true" oninput="plSync(this)">{_esc(text)}</textarea>'
        f'<div class="note">Nada se publica solo. Un modelo no es una garantía. '
        f'Puedes editar el texto: el enlace con sugerencia usa lo que queda en el recuadro. '
        f'El enlace en blanco abre la respuesta sin texto.</div></div>'
        f'<div class="dz"><button type="button" class="dx" onclick="dis(this.closest(\'.card\'))">✕ Descartar</button></div></article>'
    )


PAGE_CSS = """
*{box-sizing:border-box}body{margin:0;background:#0B0D26;color:#fff;font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:#C6E427}.top{position:sticky;top:0;z-index:10;background:#0B0D26;border-bottom:1px solid #2a2f5a}
.tb{max-width:900px;margin:auto;padding:8px 16px;display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.tb b{font-size:15px}.tb span{color:#B8BCCB;font-size:12px}
a.home{background:#C6E427;color:#0B0D26;border-radius:8px;padding:6px 12px;font-weight:700;text-decoration:none;font-size:14px;white-space:nowrap}
header{display:flex;gap:14px;align-items:center;padding:18px 16px;max-width:900px;margin:auto}
header img{width:56px;height:56px;border-radius:10px}h1{margin:0;font-size:24px}
header p{margin:4px 0;color:#B8BCCB;font-size:14px}
.chips{max-width:900px;margin:0 auto 6px;padding:0 16px;display:flex;gap:8px;flex-wrap:wrap}
.chips button{background:transparent;color:#C6E427;border:1px solid #C6E427;border-radius:20px;padding:6px 14px;font-size:14px;cursor:pointer}
.chips button.on{background:#C6E427;color:#0B0D26}
.hint{max-width:900px;margin:0 auto 4px;padding:0 16px;color:#B8BCCB;font-size:12px}
main{max-width:900px;margin:auto;padding:8px 12px 40px}
.sec{color:#C6E427;font-size:20px;margin:22px 4px 4px}
.warn{border:1px solid #C6E427;border-radius:10px;padding:10px;font-size:13px;color:#fff;margin:6px 0}
.card{background:#141838;border:1px solid #2a2f5a;border-radius:14px;padding:14px;margin:14px 0;position:relative}
.ch{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}
.sm{color:#B8BCCB;font-size:13px}
.ref{background:#C6E427;color:#0B0D26;font-weight:700;padding:8px 12px;border-radius:8px;text-decoration:none;white-space:nowrap}
.pill{background:#2a2f5a;color:#C6E427;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:4px}
.pill.new{background:#C6E427;color:#0B0D26}
.why{font-size:14px;margin:6px 0 10px}.why b{color:#C6E427}
.pend{border:1px dashed #C6E427;color:#C6E427;border-radius:10px;padding:14px;font-size:14px;margin:6px 0}
.blk{border-left:3px solid #C6E427;margin:12px 0 0;padding:0 0 0 10px}
.bh{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.bh span{font-weight:700;color:#C6E427}
.bh button{background:#C6E427;color:#0B0D26;border:0;border-radius:8px;padding:6px 12px;font-weight:700;cursor:pointer;min-height:40px}
.bb{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.xb{background:#0B0D26;color:#C6E427;border:1px solid #C6E427;border-radius:8px;padding:8px 12px;font-weight:700;text-decoration:none;font-size:14px;min-height:40px;display:inline-flex;align-items:center}
.l280{color:#B8BCCB;font-size:12px;text-align:right}.note{color:#B8BCCB;font-size:12px}
textarea.pl-text{width:100%;min-height:8em;white-space:pre-wrap;font:inherit;margin:6px 0;background:#0B0D26;color:#fff;padding:10px;border-radius:8px;border:1px solid #2a2f5a;resize:vertical}
.dz{text-align:right;margin-top:10px}
.dx{background:transparent;color:#B8BCCB;border:1px solid #444a7a;border-radius:8px;padding:4px 10px;font-size:13px;cursor:pointer}
.tb-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#pl-refresh{background:#C6E427;color:#0B0D26;border:0;border-radius:8px;padding:6px 12px;font-weight:700;cursor:pointer;font-size:14px;white-space:nowrap}
#pl-refresh:disabled{opacity:.75;cursor:wait}
"""

PAGE_SCRIPT = """
function xdeep(h){var u=new URL(h);var t=u.searchParams.get("text")||"";var d="twitter://post?message="+encodeURIComponent(t);var r=u.searchParams.get("in_reply_to");if(r)d+="&in_reply_to_status_id="+r;return d}
document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a.xb");if(!a)return;var ios=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform=="MacIntel"&&navigator.maxTouchPoints>1);if(!ios)return;e.preventDefault();var w=a.href,tm;function cl(){if(document.hidden){clearTimeout(tm);document.removeEventListener("visibilitychange",cl)}}document.addEventListener("visibilitychange",cl);tm=setTimeout(function(){document.removeEventListener("visibilitychange",cl);if(!document.hidden)location.href=w},1500);location.href=xdeep(w)});
function plQuote(s){return encodeURIComponent(s).replace(/[!'()*]/g,function(c){return '%'+c.charCodeAt(0).toString(16).toUpperCase()})}
function plSync(el){var card=el.closest('article.card');if(!card)return;var a=card.querySelector('a.pl-sug');if(!a)return;var id=card.getAttribute('data-reply-id');a.setAttribute('href','https://x.com/intent/post?in_reply_to='+id+'&text='+plQuote(el.value))}
function plCopy(b){var ta=b.closest('.blk').querySelector('textarea');var t=ta.value;function ok(){b.textContent='Copiado';setTimeout(function(){b.textContent='Copiar texto'},2000)}function fb(){var e=document.createElement('textarea');e.value=t;e.style.position='fixed';e.style.left='-9999px';document.body.appendChild(e);e.select();try{document.execCommand('copy')}catch(x){}document.body.removeChild(e);ok()}if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,fb)}else fb()}
var PL_DK="fq_conv_dismissed_v1";
function plDismissed(){try{return JSON.parse(localStorage.getItem(PL_DK)||"[]")}catch(e){return []}}
function dis(c){if(!c)return;var id=c.getAttribute("data-id")||"";try{var d=plDismissed();if(d.indexOf(id)<0){d.push(id);localStorage.setItem(PL_DK,JSON.stringify(d))}}catch(e){}c.remove();plSweep()}
function plFilter(topic,btn){if(btn){document.querySelectorAll("#pl-topics button").forEach(function(b){b.classList.remove("on")});btn.classList.add("on")}var active=topic||"all";var cards=document.querySelectorAll("article.pl-card");var left=0;cards.forEach(function(c){var show=active==="all"||c.getAttribute("data-topic")===active;c.style.display=show?"":"none";if(show)left++});document.querySelectorAll("[data-topic-heading]").forEach(function(h){var id=h.getAttribute("data-topic-heading");var any=false;cards.forEach(function(c){if(c.style.display!=="none"&&c.getAttribute("data-topic")===id)any=true});h.style.display=any?"":"none"});var empty=document.getElementById("pl-empty");var topicEmpty=document.getElementById("pl-topic-empty");if(empty)empty.hidden=left>0||active!=="all";if(topicEmpty)topicEmpty.hidden=left>0||active==="all"}
function plSweep(){var MAX=7200*1000,SKEW=120*1000,MIN=20000,now=Date.now();function followersOk(c){var raw=c.getAttribute("data-followers-count")||"";if(!/^[0-9]+$/.test(raw))return false;var n=Number(raw);var checked=Date.parse(c.getAttribute("data-followers-checked-at")||"");return n>MIN&&isFinite(checked)}var gone=plDismissed();document.querySelectorAll("article.pl-card").forEach(function(c){if(gone.indexOf(c.getAttribute("data-id"))>=0){c.remove();return}var t=Date.parse(c.getAttribute("data-created-at")||"");if(!isFinite(t)||(now-t)>MAX||(t-now)>SKEW||!followersOk(c))c.remove()});var cnt=document.getElementById("pl-cnt");if(cnt)cnt.textContent=String(document.querySelectorAll("article.pl-card").length);var on=document.querySelector("#pl-topics button.on");plFilter(on?on.getAttribute("data-topic"):"all",null)}
function plRefresh(b){if(b){b.disabled=true;b.textContent="Actualizando…"}var on=document.querySelector("#pl-topics button.on");var topic=on?(on.getAttribute("data-topic")||"all"):"all";var u=location.pathname+"?t="+Date.now();if(topic!=="all"&&/^[a-z0-9][a-z0-9-]{0,40}$/.test(topic))u+="&tema="+encodeURIComponent(topic);setTimeout(function(){location.replace(u)},300)}
plSweep();
(function(){var topic="";try{topic=new URLSearchParams(location.search).get("tema")||""}catch(e){return}if(!/^[a-z0-9][a-z0-9-]{0,40}$/.test(topic))return;var btn=document.querySelector('#pl-topics button[data-topic="'+topic+'"]');if(btn)plFilter(topic,btn)})();
"""


def _warn(evaluated_at):
    return (
        '<div class="warn">Nada se publica solo. Un modelo no es una garantía. '
        "Cada actualización incluye solo posts originales con como máximo 7200 segundos "
        "de antigüedad, contados desde la creación del post (no desde una cita ni desde "
        "la búsqueda), y un conteo de seguidores verificado estrictamente mayor que 20.000. "
        "Si el conteo falta, no entra. Una marca de verificación no sustituye el número. "
        "La ventana no se amplía para completar cupos. "
        f"Evaluado: {_esc(chile_stamp(evaluated_at))}.</div>"
    )


def render_conversations_page(items, evaluated_at, topics=None):
    """HTML completo de conversaciones/index.html, con filtro y secciones por tema."""
    topics = load_topics() if topics is None else topics
    evaluated_at = evaluated_at.astimezone(timezone.utc)
    grouped = {topic["id"]: [] for topic in topics}
    for item in items:
        topic = _topic_of(item, topics)
        card = render_card(item, topic)
        if card:
            grouped[topic["id"]].append(card)
    total = sum(len(cards) for cards in grouped.values())
    buttons = [
        '<button type="button" class="on" data-topic="all" onclick="plFilter(\'all\',this)">Todos</button>'
    ]
    for topic in topics:
        buttons.append(
            f'<button type="button" data-topic="{_esc(topic["id"])}" '
            f'onclick="plFilter(\'{topic["id"]}\',this)">{_esc(topic["label"])}</button>'
        )
    sections = []
    for topic in topics:
        cards = grouped[topic["id"]]
        if not cards:
            continue
        sections.append(
            f'<h2 class="sec" data-topic-heading="{_esc(topic["id"])}">{_esc(topic["label"])}</h2>'
        )
        sections.extend(cards)
    hidden = "" if total == 0 else " hidden"
    parts = [
        "<!DOCTYPE html>",
        '<html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">',
        '<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">',
        f"<title>{_esc(SECTION_TITLE)}</title><style>{PAGE_CSS}</style></head><body>",
        '<div class="top"><div class="tb">',
        f"<b>{_esc(SECTION_TITLE)}</b>",
        f"<span>Evaluado: {_esc(chile_stamp(evaluated_at))}</span>",
        '<div class="tb-actions">',
        '<button type="button" id="pl-refresh" onclick="plRefresh(this)">🔄 Actualizar</button>',
        f'<a class="home" href="{HOME_HREF}">← Recomendaciones</a>',
        "</div>",
        "</div></div>",
        '<header><img src="../images/logo.jpg" alt="logo"><div>',
        f"<h1>{_esc(SECTION_TITLE)}</h1>",
        f'<p><span id="pl-cnt">{total}</span> dentro de la ventana de 2 horas. Nada se publica solo.</p>',
        f'<p><a href="{HOME_HREF}">Volver a recomendaciones</a></p>',
        "</div></header>",
        f'<div class="chips" id="pl-topics">{"".join(buttons)}</div>',
        '<p class="hint">Filtra por tema. Cada tarjeta vence dos horas después del post original.</p>',
        "<main>",
        _warn(evaluated_at),
        f'<div class="pend" id="pl-empty"{hidden}>{EMPTY_TEXT}</div>',
        (
            '<div class="pend" id="pl-topic-empty" hidden>Sin posts de este tema dentro de los últimos '
            "7200 segundos con un conteo de seguidores verificado mayor que 20.000. "
            "No se completa la página con autores en o bajo 20.000 ni con un conteo desconocido.</div>"
        ),
        *sections,
        "</main>",
        f"<script>{PAGE_SCRIPT}</script></body></html>",
    ]
    return "\n".join(parts)


def write_conversations_page(path, store_dir, evaluated_at=None, persist=False):
    evaluated_at = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    store = load_store(store_dir)
    if persist:
        reclassify(store, evaluated_at)
        save_store(store_dir, store)
    items = qualified_items(store, evaluated_at)
    page = render_conversations_page(items, evaluated_at)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)
        if not page.endswith("\n"):
            handle.write("\n")
    return page


def strip_section(page):
    if START not in page:
        return page
    pre, rest = page.split(START, 1)
    _old, post = rest.split(END, 1)
    return pre + post

def inject_into_page(page, store_dir, evaluated_at=None, persist=True, repo_dir=None):
    """Deja en index.html solo el enlace. Con repo_dir reescribe conversaciones/index.html."""
    evaluated_at = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    store = load_store(store_dir)
    if persist:
        reclassify(store, evaluated_at)
        save_store(store_dir, store)
    if repo_dir:
        write_conversations_page(
            os.path.join(repo_dir, CONVERSATIONS_DIR, PAGE_NAME),
            store_dir,
            evaluated_at,
            persist=False,
        )
    base = strip_section(page)
    marker = "<main>"
    if marker not in base:
        raise RuntimeError("index.html no tiene <main>")
    updated = base.replace(marker, marker + render_main_link(), 1)
    total = len(re.findall(r"<article\b", updated))
    updated, count = re.subn(
        r"(<span id=\"cnt\">)\d+(</span> de )\d+( tarjetas visibles)",
        lambda match: f"{match.group(1)}{total}{match.group(2)}{total}{match.group(3)}",
        updated,
        count=1,
    )
    if count != 1:
        raise RuntimeError("no se encontró el contador de tarjetas")
    return updated


def refresh(store_dir, evaluated_at=None, batch=None, index_path=None, page_path=None):
    evaluated_at = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    store = load_store(store_dir)
    if batch is not None:
        merge_batch(store, batch, evaluated_at)
    else:
        reclassify(store, evaluated_at)
    save_store(store_dir, store)
    page = None
    if index_path:
        with open(index_path, encoding="utf-8") as handle:
            page = inject_into_page(handle.read(), store_dir, evaluated_at, persist=False)
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(page)
        if page_path is None:
            page_path = conversations_path_for(index_path)
    if page_path:
        write_conversations_page(page_path, store_dir, evaluated_at, persist=False)
    return store, page
