#!/usr/bin/env python3
"""Incorpora un lote de conversaciones y reescribe solo esa sección en index.html.

No llama a la API de X y no publica. La ventana se vuelve a medir en este
instante (o en --evaluated-at): created_at del post original, máximo 7200 s.
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
    parser = argparse.ArgumentParser(description="Actualiza Conversaciones Power Law / precio BTC")
    parser.add_argument("batch", nargs="?", help="JSON de oportunidades. Omitir solo con --revalidate.")
    parser.add_argument("--index", default=os.path.join(repo, "index.html"))
    parser.add_argument("--store-dir", default=here)
    parser.add_argument("--revalidate", action="store_true", help="Reaplica los 7200 s al almacén, sin lote nuevo.")
    parser.add_argument("--evaluated-at", help="ISO-8601 con zona. Por defecto, la hora de esta ejecución.")
    args = parser.parse_args(argv)
    if not args.batch and not args.revalidate:
        parser.error("indica un JSON de oportunidades o --revalidate")
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
    store, _page = pl.refresh(args.store_dir, evaluated, batch, args.index)
    chosen = pl.qualified_items(store, evaluated)
    print("evaluated_at", store.get("evaluated_at"))
    print("window_seconds", pl.WINDOW_SECONDS)
    print("qualified", len(chosen))
    for item in chosen:
        created = pl.parse_time(item["created_at"])
        age = (evaluated - created).total_seconds()
        print(f"{item['author']}\t{item['id']}\tage_s={age:.3f}\tfollowers={item.get('followers_count')}")
    print("discarded", len(store.get("discarded") or {}))
    print("history", len(store.get("history") or {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
