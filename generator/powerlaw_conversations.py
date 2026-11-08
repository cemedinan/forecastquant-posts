#!/usr/bin/env python3
"""Sección «Conversaciones Power Law / precio BTC».

En cada actualización califican solo posts originales con created_at
de como máximo 7200 segundos y autor con followers_count verificado
estrictamente mayor que 20000. No se usa la hora de una cita, ni
searched_at, ni una marca de verificación. Un conteo ausente o no
verificado queda fuera. La ventana no se amplía para completar cupos.

No publica nada en X: solo arma enlaces https://x.com/intent/post.
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
SECTION_TITLE = "Conversaciones Power Law / precio BTC"
START = "<!-- powerlaw-conversations:start -->"
END = "<!-- powerlaw-conversations:end -->"
STORE_NAME = "powerlaw_store.json"
CHILE = ZoneInfo("America/Santiago")

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
)


def empty_store():
    return {
        "window_seconds": WINDOW_SECONDS,
        "min_followers_exclusive": MIN_FOLLOWERS_EXCLUSIVE,
        "evaluated_at": None,
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


def merge_batch(store, batch, evaluated_at):
    """Incorpora un lote. Dedup por id. No guarda texto de lo que no califica."""
    if not isinstance(batch, dict):
        raise ValueError("el lote debe ser un objeto JSON")
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
    reclassify(store, evaluated_at)
    store["evaluated_at"] = evaluated_at.astimezone(timezone.utc).isoformat()
    store["window_seconds"] = WINDOW_SECONDS
    store["min_followers_exclusive"] = MIN_FOLLOWERS_EXCLUSIVE
    store["last_batch_searched_at"] = batch.get("searched_at")
    return store


def reclassify(store, evaluated_at):
    items = store.setdefault("items", {})
    history = store.setdefault("history", {})
    discarded = store.setdefault("discarded", {})
    for status_id, item in list(items.items()):
        if status_id in discarded:
            history[status_id] = _archive_stub(item, "discarded", evaluated_at)
            del items[status_id]
            continue
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


def render_section(items, evaluated_at):
    evaluated_at = evaluated_at.astimezone(timezone.utc)
    parts = [
        START,
        "<style>textarea.pl-text{width:100%;min-height:8em;white-space:pre-wrap;font:inherit;margin:6px 0;background:#0B0D26;color:#fff;padding:10px;border-radius:8px;border:1px solid #2a2f5a;resize:vertical}</style>",
        f'<h2 class="sec">{_esc(SECTION_TITLE)}</h2>',
        (
            '<div class="warn">Nada se publica solo. Un modelo no es una garantía. '
            "Cada actualización incluye solo posts originales con como máximo 7200 segundos "
            "de antigüedad, contados desde la creación del post (no desde una cita ni desde "
            "la búsqueda), y un conteo de seguidores verificado estrictamente mayor que 20.000. "
            "Si el conteo falta, no entra. Una marca de verificación no sustituye el número. "
            "La ventana no se amplía para completar cupos. "
            f"Evaluado: {_esc(chile_stamp(evaluated_at))}.</div>"
        ),
    ]
    empty = (
        '<div class="pend" id="pl-empty"%s>Sin posts originales dentro de los últimos '
        "7200 segundos con un conteo de seguidores verificado mayor que 20.000. "
        "No se completa la sección con autores en o bajo 20.000 ni con un conteo desconocido.</div>"
    )
    if not items:
        parts.append(empty % "")
    else:
        parts.append(empty % " hidden")
    for item in items:
        status_id = str(item["id"])
        created = parse_time(item["created_at"])
        checked = parse_time(item.get("followers_checked_at"))
        count = item.get("followers_count")
        if checked is None or isinstance(count, bool) or not isinstance(count, int) or count <= MIN_FOLLOWERS_EXCLUSIVE:
            continue
        text = item["suggested_text"]
        suggestion = suggestion_intent(status_id, text)
        blank = blank_intent(status_id)
        expires = created + timedelta(seconds=WINDOW_SECONDS)
        length_note = ""
        if len(text) > 280:
            length_note = f'<div class="l280">más de 280 caracteres ({len(text)})</div>'
        parts.append(
            f'<article class="card pl-card" id="pl{status_id}" data-id="pl-{status_id}" '
            f'data-reply-id="{status_id}" data-created-at="{_esc(created.strftime("%Y-%m-%dT%H:%M:%SZ"))}" '
            f'data-followers-count="{count}" data-followers-checked-at="{_esc(item.get("followers_checked_at") or "")}" '
            f'data-g="0" data-n="1"><div class="ch"><div><b>{_esc(item["author"].strip())}</b> '
            f'<span class="pill new">Nuevo</span><div class="sm">{_esc(chile_stamp(created))} · vence {_esc(chile_stamp(expires))}</div>'
            f'<div class="sm">Seguidores: {_esc(format_followers(count))} · revisado {_esc(chile_stamp(checked))}</div></div>'
            f'<a class="ref" href="{_esc(item["url"])}" target="_blank" rel="noopener">Ver post original ↗</a></div>'
            f'<div class="why"><b>Contexto:</b> {_esc(item["context"].strip())}</div>'
            f'<div class="blk"><div class="bh"><span>Respuesta sugerida</span><div class="bb">'
            f'<button type="button" onclick="plCopy(this)">Copiar texto</button>'
            f'<a class="xb pl-sug" data-k="reply" href="{_esc(suggestion)}" target="_blank" rel="noopener">Responder con sugerencia</a>'
            f'<a class="xb pl-blank" data-k="reply" href="{_esc(blank)}" target="_blank" rel="noopener">Responder en blanco</a>'
            f'</div></div>{length_note}'
            f'<textarea class="pl-text" lang="en" spellcheck="true" oninput="plSync(this)">{_esc(text)}</textarea>'
            f'<div class="note">Nada se publica solo. Un modelo no es una garantía. '
            f'Puedes editar el texto: el enlace con sugerencia usa lo que queda en el recuadro. '
            f'El enlace en blanco abre la respuesta sin texto.</div></div>'
            f'<div class="dz"><button type="button" class="dx" onclick="dis(this.closest(\'.card\'))">✕ Descartar</button></div></article>'
        )
    parts.append(
        "<script>"
        "function plQuote(s){return encodeURIComponent(s).replace(/[!'()*]/g,function(c){return '%'+c.charCodeAt(0).toString(16).toUpperCase()})}"
        "function plSync(el){var card=el.closest('article.card');if(!card)return;var a=card.querySelector('a.pl-sug');if(!a)return;var id=card.getAttribute('data-reply-id');a.setAttribute('href','https://x.com/intent/post?in_reply_to='+id+'&text='+plQuote(el.value))}"
        "function plCopy(b){var ta=b.closest('.blk').querySelector('textarea');var t=ta.value;function ok(){b.textContent='Copiado';setTimeout(function(){b.textContent='Copiar texto'},2000)}function fb(){var e=document.createElement('textarea');e.value=t;e.style.position='fixed';e.style.left='-9999px';document.body.appendChild(e);e.select();try{document.execCommand('copy')}catch(x){}document.body.removeChild(e);ok()}if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,fb)}else fb()}"
        "(function(){var MAX=7200*1000,SKEW=120*1000,MIN=20000;function followersOk(c){var raw=c.getAttribute('data-followers-count')||'';if(!/^[0-9]+$/.test(raw))return false;var n=Number(raw);var checked=Date.parse(c.getAttribute('data-followers-checked-at')||'');return n>MIN&&isFinite(checked)}function sweep(){var now=Date.now(),left=0;document.querySelectorAll('article.pl-card').forEach(function(c){var t=Date.parse(c.getAttribute('data-created-at')||'');if(!isFinite(t)||(now-t)>MAX||(t-now)>SKEW||!followersOk(c)){c.remove()}else left++});var empty=document.getElementById('pl-empty');if(empty)empty.hidden=left>0}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',sweep);sweep()})();"
        "</script>"
        + END
    )
    return "".join(parts)


def strip_section(page):
    if START not in page:
        return page
    pre, rest = page.split(START, 1)
    _old, post = rest.split(END, 1)
    return pre + post


def inject_into_page(page, store_dir, evaluated_at=None, persist=True):
    evaluated_at = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    store = load_store(store_dir)
    if persist:
        reclassify(store, evaluated_at)
        save_store(store_dir, store)
    items = qualified_items(store, evaluated_at)
    section = render_section(items, evaluated_at)
    base = strip_section(page)
    marker = "<main>"
    if marker not in base:
        raise RuntimeError("index.html no tiene <main>")
    updated = base.replace(marker, marker + section, 1)
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


def refresh(store_dir, evaluated_at=None, batch=None, index_path=None):
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
    return store, page
