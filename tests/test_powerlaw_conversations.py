#!/usr/bin/env python3
"""Ventana de 7200 s, dedup e inyección sin tocar el resto de la página."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "generator"))
import powerlaw_conversations as pl  # noqa: E402

BATCH_PATH = os.path.join(ROOT, "generator", "inbox", "opportunities_20261108_2h_20k.json")
INDEX_PATH = os.path.join(ROOT, "index.html")
VALIDATION = datetime(2026, 11, 8, 22, 11, 54, tzinfo=timezone.utc)
DISCARDED_IDS = [
    "2119275500384206888",
    "2119448133621174613",
    "2119461857064833147",
    "2119415773479543260",
    "2119420052760109351",
    "2119547966536962235",
]
QUALIFIED_IDS = ["2119535615637324097"]


def load_batch():
    with open(BATCH_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def snowflake(moment):
    millis = int(moment.timestamp() * 1000)
    return str((millis - pl.SNOWFLAKE_EPOCH_MS) << 22)


def make_item(moment, text="A fixed curve is still a model, not a guarantee. What would change your mind?"):
    moment = moment.astimezone(timezone.utc).replace(microsecond=0)
    status_id = snowflake(moment)
    return {
        "id": status_id,
        "author": "example_author",
        "url": f"https://x.com/example_author/status/{status_id}",
        "created_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_at_verified": True,
        "timestamp_source": "test",
        "context": "Contexto de prueba, sin ampliar la ventana.",
        "suggested_text": text,
        "reply_with_suggestion": pl.suggestion_intent(status_id, text),
        "reply_blank": pl.blank_intent(status_id),
        "followers_count": 26377,
        "followers_count_verified": True,
        "followers_source": "test",
        "followers_checked_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def article_ids(page):
    return re.findall(r'<article[^>]*\sdata-id="([^"]+)"', page)


def hrefs(article_html):
    found = {}
    for kind, href in re.findall(r'class="xb pl-(sug|blank)"[^>]*href="([^"]+)"', article_html):
        found[kind] = href.replace("&amp;", "&")
    return found


def normalize_outside(page):
    page = pl.strip_section(page)
    return re.sub(
        r'(<span id="cnt">)\d+(</span> de )\d+',
        r"\1CNT\2CNT",
        page,
        count=1,
    )


class FreshnessTests(unittest.TestCase):
    def test_validation_instant_keeps_only_david(self):
        store = pl.empty_store()
        pl.merge_batch(store, load_batch(), VALIDATION)
        chosen = pl.qualified_items(store, VALIDATION)
        self.assertEqual([item["id"] for item in chosen], QUALIFIED_IDS)
        self.assertEqual(chosen[0]["followers_count"], 26377)
        self.assertEqual(chosen[0]["qualification"]["min_followers_exclusive"], 20000)
        self.assertTrue(chosen[0]["qualification"]["qualified"])
        self.assertEqual(store["window_seconds"], 7200)
        self.assertEqual(store["min_followers_exclusive"], 20000)
        alerts = store["discarded"]["2119547966536962235"]
        self.assertEqual(alerts["followers_count"], 9348)
        self.assertEqual(alerts["author"], "btcnewsalerts")
        for status_id in DISCARDED_IDS:
            self.assertIn(status_id, store["discarded"])
            self.assertNotIn(status_id, store["items"])
            self.assertNotIn("suggested_text", store["discarded"][status_id])
        expires = datetime(2026, 11, 8, 23, 0, 44, tzinfo=timezone.utc)
        self.assertEqual([item["id"] for item in pl.qualified_items(store, expires)], QUALIFIED_IDS)
        self.assertEqual(pl.qualified_items(store, expires + timedelta(seconds=1)), [])

    def test_supplied_intents_match_the_text_and_blank_has_no_text(self):
        batch = load_batch()
        for raw in batch["items"]:
            self.assertEqual(pl.suggestion_intent(raw["id"], raw["suggested_text"]), raw["reply_with_suggestion"])
            self.assertEqual(pl.blank_intent(raw["id"]), raw["reply_blank"])
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(raw["reply_blank"]).query)
            self.assertEqual(list(query), ["in_reply_to"])
            self.assertNotIn("text", query)
            suggestion = urllib.parse.parse_qs(urllib.parse.urlsplit(raw["reply_with_suggestion"]).query)
            self.assertEqual(suggestion["in_reply_to"], [raw["id"]])
            self.assertEqual(suggestion["text"], [raw["suggested_text"]])

    def test_own_post_link_stays_only_inside_the_supplied_reply(self):
        david = load_batch()["items"][0]
        self.assertEqual(david["id"], "2119535615637324097")
        self.assertNotIn("forecastquant", david["suggested_text"])
        self.assertEqual(david["source_post_id"], None)
        self.assertNotIn("2119547966536962235", json.dumps(load_batch()["items"]))

    def test_exact_boundary_and_no_widening(self):
        now = datetime(2026, 11, 8, 23, 0, 44, tzinfo=timezone.utc)
        edge = make_item(now - timedelta(seconds=7200))
        just_over = make_item(now - timedelta(seconds=7201))
        fresh = make_item(now - timedelta(seconds=10))
        store = pl.empty_store()
        pl.merge_batch(
            store,
            {"max_age_seconds": 86400, "searched_at": now.isoformat(), "items": [edge, just_over, fresh]},
            now,
        )
        chosen = [item["id"] for item in pl.qualified_items(store, now)]
        self.assertEqual(chosen, [edge["id"], fresh["id"]])
        self.assertNotIn(just_over["id"], chosen)
        self.assertEqual(store["window_seconds"], 7200)

    def test_missing_or_unverified_created_at_is_excluded(self):
        now = VALIDATION
        missing = make_item(now - timedelta(seconds=30))
        missing["created_at"] = None
        unverified = make_item(now - timedelta(seconds=40))
        unverified["created_at_verified"] = False
        garbage = make_item(now - timedelta(seconds=50))
        garbage["created_at"] = "yesterday"
        naive = make_item(now - timedelta(seconds=60))
        naive["created_at"] = "2026-11-08T18:00:44"
        store = pl.empty_store()
        pl.merge_batch(store, {"items": [missing, unverified, garbage, naive]}, now)
        self.assertEqual(pl.qualified_items(store, now), [])
        self.assertEqual(store["history"][missing["id"]]["exclude_reason"], "missing_created_at")
        self.assertEqual(store["history"][unverified["id"]]["exclude_reason"], "unverifiable_created_at")
        self.assertNotIn("suggested_text", json.dumps(store["history"]))

    def test_search_time_and_quote_time_do_not_qualify_an_old_original(self):
        now = VALIDATION
        old = make_item(now - timedelta(hours=5))
        old["parent_created_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        old["quoted_status_created_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        store = pl.empty_store()
        pl.merge_batch(store, {"searched_at": now.isoformat(), "window_end": now.isoformat(), "items": [old]}, now)
        self.assertEqual(pl.qualified_items(store, now), [])
        self.assertEqual(store["history"][old["id"]]["exclude_reason"], "older_than_7200s")

    def test_follower_count_must_be_verified_and_above_20000(self):
        now = VALIDATION
        exact = make_item(now - timedelta(seconds=30))
        exact["followers_count"] = 20000
        above = make_item(now - timedelta(seconds=45))
        above["followers_count"] = 20001
        missing = make_item(now - timedelta(seconds=55))
        missing.pop("followers_count")
        blue = make_item(now - timedelta(seconds=65))
        blue.pop("followers_count")
        blue["verified"] = True
        blue["is_blue_verified"] = True
        blue.pop("followers_count_verified")
        unverified = make_item(now - timedelta(seconds=75))
        unverified["followers_count_verified"] = False
        as_text = make_item(now - timedelta(seconds=85))
        as_text["followers_count"] = "26377"
        low_but_blue = make_item(now - timedelta(seconds=95))
        low_but_blue["followers_count"] = 9348
        low_but_blue["is_blue_verified"] = True
        widened = make_item(now - timedelta(seconds=20))
        widened["followers_count"] = 100
        store = pl.empty_store()
        pl.merge_batch(
            store,
            {"min_followers_exclusive": 0, "items": [exact, above, missing, blue, unverified, as_text, low_but_blue, widened]},
            now,
        )
        self.assertEqual([item["id"] for item in pl.qualified_items(store, now)], [above["id"]])
        self.assertEqual(store["history"][exact["id"]]["exclude_reason"], "followers_not_above_20000")
        self.assertEqual(store["history"][missing["id"]]["exclude_reason"], "missing_followers_count")
        self.assertEqual(store["history"][blue["id"]]["exclude_reason"], "missing_followers_count")
        self.assertEqual(store["history"][unverified["id"]]["exclude_reason"], "unverifiable_followers_count")
        self.assertEqual(store["history"][as_text["id"]]["exclude_reason"], "unverifiable_followers_count")
        self.assertEqual(store["history"][low_but_blue["id"]]["exclude_reason"], "followers_not_above_20000")
        self.assertEqual(store["min_followers_exclusive"], 20000)
        self.assertNotIn("suggested_text", json.dumps(store["history"]))

    def test_snowflake_mismatch_is_unverifiable_even_if_the_clock_looks_fresh(self):
        now = VALIDATION
        forged = make_item(now - timedelta(hours=6))
        forged["created_at"] = (now - timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        forged["created_at_verified"] = True
        forged.pop("created_at_chile", None)
        ok, reason = pl.classify(forged, now)
        self.assertFalse(ok)
        self.assertEqual(reason, "snowflake_mismatch")

    def test_discarded_ids_never_return_to_the_selection(self):
        now = VALIDATION
        fresh = make_item(now - timedelta(seconds=15))
        batch = {
            "excluded_previous_candidates": [
                {"id": fresh["id"], "created_at": fresh["created_at"], "reason": "Fuera de ventana estricta de 2 horas"}
            ],
            "items": [fresh],
        }
        store = pl.empty_store()
        pl.merge_batch(store, batch, now)
        self.assertEqual(pl.qualified_items(store, now), [])
        self.assertIn(fresh["id"], store["discarded"])
        self.assertNotIn("suggested_text", store["discarded"][fresh["id"]])

    def test_dedup_by_original_id(self):
        now = VALIDATION
        item = make_item(now - timedelta(seconds=40))
        again = dict(item)
        again["context"] = "Contexto actualizado, mismo post."
        store = pl.empty_store()
        pl.merge_batch(store, {"items": [item, again]}, now)
        pl.merge_batch(store, {"items": [again]}, now)
        self.assertEqual(list(store["items"]), [item["id"]])
        self.assertEqual(store["items"][item["id"]]["context"], again["context"])
        created = store["items"][item["id"]]["created_at"]
        moved = dict(again)
        moved["created_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        pl.merge_batch(store, {"items": [moved]}, now)
        self.assertEqual(store["items"][item["id"]]["created_at"], created)

    def test_aged_items_leave_the_selection_and_drop_the_reply_text(self):
        store = pl.empty_store()
        pl.merge_batch(store, load_batch(), VALIDATION)
        later = VALIDATION + timedelta(hours=3)
        pl.reclassify(store, later)
        self.assertEqual(pl.qualified_items(store, later), [])
        blob = json.dumps(store)
        for raw in load_batch()["items"]:
            self.assertNotIn(raw["suggested_text"], blob)
            self.assertIn(raw["id"], store["history"])
            self.assertNotIn("suggested_text", store["history"][raw["id"]])


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_dir = os.path.join(self.tmp.name, "store")
        os.makedirs(self.store_dir)
        self.index = os.path.join(self.tmp.name, "index.html")
        shutil.copy(INDEX_PATH, self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def _apply(self, evaluated):
        pl.refresh(self.store_dir, evaluated, load_batch(), self.index)
        with open(self.index, encoding="utf-8") as handle:
            return handle.read()

    def test_injection_preserves_prior_cards_order_scripts_and_dismissals(self):
        original = open(self.index, encoding="utf-8").read()
        updated = self._apply(VALIDATION)
        self.assertEqual(normalize_outside(original), normalize_outside(updated))
        self.assertEqual(updated[: updated.find("<body>")], original[: original.find("<body>")])
        self.assertEqual(updated.rfind("<script>"), updated.rfind("<script>"))
        self.assertIn("function xdeep", updated)
        self.assertEqual(
            updated[updated.rfind("<script>") :],
            original[original.rfind("<script>") :],
        )
        self.assertIn('localStorage.getItem("fq_dismissed_v1"', updated)
        base_ids = article_ids(pl.strip_section(original))
        out_ids = article_ids(updated)
        self.assertEqual([item for item in out_ids if not item.startswith("pl-")], base_ids)
        old_sections = re.findall(r'<h2 class="sec">([^<]*)</h2>', pl.strip_section(original))
        new_sections = re.findall(r'<h2 class="sec">([^<]*)</h2>', updated)
        self.assertEqual(new_sections[0], pl.SECTION_TITLE)
        self.assertEqual(new_sections[1:], old_sections)
        again = pl.inject_into_page(updated, self.store_dir, VALIDATION, persist=False)
        self.assertEqual(again, updated)

    def test_rendered_cards_use_both_validated_intents(self):
        page = self._apply(VALIDATION)
        batch = {item["id"]: item for item in load_batch()["items"]}
        cards = re.findall(r'<article class="card pl-card".*?</article>', page)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        raw = batch["2119535615637324097"]
        links = hrefs(card)
        self.assertEqual(links["sug"], raw["reply_with_suggestion"])
        self.assertEqual(links["blank"], raw["reply_blank"])
        self.assertNotIn("text=", links["blank"])
        self.assertIn(f">{raw['suggested_text']}</textarea>", card)
        self.assertIn("david_eng_mba", card)
        self.assertIn(raw["url"], card)
        self.assertIn(raw["context"], card)
        self.assertIn("Seguidores: 26.377", card)
        self.assertIn("revisado 08-11-2026 19:11:54 hora Chile", card)
        self.assertIn("vence 08-11-2026 20:00:44 hora Chile", card)
        self.assertIn('data-followers-count="26377"', card)
        self.assertIn("Responder con sugerencia", card)
        self.assertIn("Responder en blanco", card)
        self.assertNotIn("forecastquant", card)
        self.assertNotIn("btcnewsalerts", page)
        for status_id in DISCARDED_IDS:
            self.assertNotIn(status_id, page)
        self.assertIn("Un modelo no es una garantía.", page)
        self.assertIn("7200 segundos", page)
        self.assertIn("mayor que 20.000", page)
        self.assertIn('<span id="cnt">130</span> de 130 tarjetas visibles', page)

    def test_empty_state_when_nothing_is_inside_the_window(self):
        page = self._apply(VALIDATION + timedelta(hours=4))
        self.assertNotIn('class="card pl-card"', page)
        self.assertIn("Sin posts originales dentro de los últimos 7200 segundos con un conteo de seguidores verificado mayor que 20.000", page)
        self.assertNotIn("Responder con sugerencia", page)
        for raw in load_batch()["items"]:
            self.assertNotIn(raw["suggested_text"], page)
            self.assertNotIn(raw["id"], page)
        self.assertIn('<span id="cnt">129</span> de 129 tarjetas visibles', page)
        original = open(INDEX_PATH, encoding="utf-8").read()
        self.assertEqual(len(article_ids(page)), len(article_ids(pl.strip_section(original))))

    def test_cli_revalidates_at_the_given_update_time(self):
        script = os.path.join(ROOT, "generator", "update_powerlaw.py")
        subprocess.check_call(
            [
                sys.executable,
                script,
                BATCH_PATH,
                "--index",
                self.index,
                "--store-dir",
                self.store_dir,
                "--evaluated-at",
                "2026-11-08T22:11:54+00:00",
            ],
            cwd=ROOT,
        )
        page = open(self.index, encoding="utf-8").read()
        self.assertEqual(article_ids(page).count("pl-2119535615637324097"), 1)
        self.assertEqual(article_ids(page).count("pl-2119547966536962235"), 0)
        subprocess.check_call(
            [
                sys.executable,
                script,
                "--revalidate",
                "--index",
                self.index,
                "--store-dir",
                self.store_dir,
                "--evaluated-at",
                "2026-11-08T23:50:00+00:00",
            ],
            cwd=ROOT,
        )
        later = open(self.index, encoding="utf-8").read()
        self.assertNotIn('class="card pl-card"', later)
        store = json.load(open(os.path.join(self.store_dir, "powerlaw_store.json"), encoding="utf-8"))
        self.assertEqual(store["items"], {})
        self.assertEqual(store["window_seconds"], 7200)
        self.assertEqual(store["min_followers_exclusive"], 20000)
        self.assertEqual(store["discarded"]["2119547966536962235"]["followers_count"], 9348)
        self.assertNotIn("suggested_text", json.dumps(store))


class GeneratorContractTests(unittest.TestCase):
    def test_generator_hook_does_not_post(self):
        for name in ("powerlaw_conversations.py", "update_powerlaw.py", "build_site.py"):
            source = open(os.path.join(ROOT, "generator", name), encoding="utf-8").read()
            self.assertNotIn("create_posts", source)
            self.assertNotIn("api.x.com", source)
            self.assertNotIn("api.twitter.com", source)
        module = open(os.path.join(ROOT, "generator", "powerlaw_conversations.py"), encoding="utf-8").read()
        self.assertIn("WINDOW_SECONDS = 7200", module)
        self.assertIn("MIN_FOLLOWERS_EXCLUSIVE = 20000", module)
        self.assertIn("n>MIN", module)
        self.assertNotIn("timedelta(hours=24)", module)
        build = open(os.path.join(ROOT, "generator", "build_site.py"), encoding="utf-8").read()
        self.assertIn("powerlaw_conversations", build)
        self.assertIn("inject_into_page", build)


if __name__ == "__main__":
    unittest.main()
