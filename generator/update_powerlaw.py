#!/usr/bin/env python3
"""Incorpora un lote y reescribe conversaciones/index.html.

index.html solo conserva el enlace a esa página. No llama a la API de X
y no publica. La ventana se vuelve a medir en este instante (o en
--evaluated-at): created_at del post original, máximo 7200 s.

Desde la raíz del repo:

    python3 generator/update_powerlaw.py --revalidate --index index.html
    python3 generator/update_powerlaw.py generator/inbox/opportunities_YYYYMMDD.json --index index.html

La página de conversaciones queda junto a --index, en conversaciones/index.html.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import powerlaw_conversations as pl


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    parser = argparse.ArgumentParser(description="Actualiza la página Conversaciones de interés")
    parser.add_argument("batch", nargs="?", help="JSON de oportunidades. Omitir solo con --revalidate.")
    parser.add_argument(
        "index_positional",
        nargs="?",
        help="Ruta de index.html si no usas --index (compatibilidad).",
    )
    parser.add_argument("--index", default=None, help="Página principal. Por defecto, index.html del repo.")
    parser.add_argument(
        "--page",
        default=None,
        help="HTML de conversaciones. Por defecto, conversaciones/index.html junto a --index.",
    )
    parser.add_argument("--store-dir", default=here)
    parser.add_argument("--revalidate", action="store_true", help="Reaplica los 7200 s al almacén, sin lote nuevo.")
    parser.add_argument("--evaluated-at", help="ISO-8601 con zona. Por defecto, la hora de esta ejecución.")
    args = parser.parse_args(argv)
    if not args.batch and not args.revalidate:
        parser.error("indica un JSON de oportunidades o --revalidate")
    index_path = args.index or args.index_positional or os.path.join(repo, "index.html")
    if args.evaluated_at:
        evaluated = pl.parse_time(args.evaluated_at)
        if evaluated is None:
            print("evaluated-at no verificable", file=sys.stderr)
            return 2
    else:
        evaluated = datetime.now(timezone.utc)
    batch = None
    if args.batch:
        with open(args.batch, encoding="utf-8") as handle:
            batch = json.load(handle)
    store, _page = pl.refresh(args.store_dir, evaluated, batch, index_path, args.page)
    page_path = args.page or pl.conversations_path_for(index_path)
    chosen = pl.qualified_items(store, evaluated)
    print("evaluated_at", store.get("evaluated_at"))
    print("window_seconds", pl.WINDOW_SECONDS)
    print("index", index_path)
    print("page", page_path)
    print("topics", ",".join(topic["id"] for topic in pl.load_topics()))
    print("qualified", len(chosen))
    for item in chosen:
        created = pl.parse_time(item["created_at"])
        age = (evaluated - created).total_seconds()
        print(
            f"{item['author']}\t{item['id']}\ttopic={item.get('topic')}\t"
            f"age_s={age:.3f}\tfollowers={item.get('followers_count')}"
        )
    print("discarded", len(store.get("discarded") or {}))
    print("history", len(store.get("history") or {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
