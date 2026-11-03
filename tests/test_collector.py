import unittest
from unittest.mock import MagicMock, patch
from collector import Collector, CollectionError, CSRFParser, hackerone_pages, normalize


class CollectorTests(unittest.TestCase):
    def test_token_attribute_order(self):
        p = CSRFParser()
        p.feed('<meta content="abc&amp;def" name="csrf-token">')
        self.assertEqual(p.token, "abc&def")

    def test_bounty_normalization(self):
        self.assertTrue(normalize("bugcrowd", {"max_payout": 10})["offers_bounties"])
        self.assertIsNone(normalize("bugcrowd", {})["offers_bounties"])
        self.assertFalse(normalize("intigriti", {"max_bounty": {"value": 0}})["offers_bounties"])

    def test_filter_deduplicate_pagination_partial(self):
        c = Collector()
        rows = [normalize("hackerone", {"name": n, "handle": n, "offers_bounties": paid})
                for n, paid in [("Beta", True), ("Alpha", True), ("Unknown", None)]]
        with patch.object(c, "programs", side_effect=lambda p:
                          {"ok": True, "programs": rows + [rows[0]]} if p == "hackerone" else {"ok": False}):
            r = c.collect(["hackerone", "bugcrowd"], bounty_only=True, limit=1, include_details=False)
            self.assertTrue(r["partial"])
            self.assertEqual(r["total"], 2)
            self.assertEqual(r["next_offset"], 1)
            self.assertEqual(r["programs"][0]["name"], "Alpha")
            self.assertNotIn("targets", r["programs"][0])
            self.assertEqual(c.collect(["hackerone"], search="BETA", include_details=False)["total"], 1)

    def test_intigriti_handles_do_not_collide_across_companies(self):
        first = normalize("intigriti", {"company_handle": "one", "handle": "vdp", "id": "uuid-one"})
        second = normalize("intigriti", {"company_handle": "two", "handle": "vdp", "id": "uuid-two"})
        self.assertNotEqual(first["id"], second["id"])

    def test_empty_success_and_failure(self):
        c = Collector()
        with patch.object(c, "programs", return_value={"ok": True, "programs": []}):
            self.assertTrue(c.collect()["ok"])
        with patch.object(c, "programs", return_value={"ok": False}):
            self.assertFalse(c.collect()["ok"])

    def test_cache_copy_and_expiry(self):
        c = Collector()
        loader = MagicMock(return_value={"ok": True, "programs": [{"name": "original"}]})
        with patch("collector.time.monotonic", return_value=10):
            first = c._cached("test", loader)
            first["programs"][0]["name"] = "changed"
            second = c._cached("test", loader)
        self.assertEqual(second["programs"][0]["name"], "original")
        self.assertTrue(second["cached"])
        self.assertEqual(loader.call_count, 1)
        with patch("collector.time.monotonic", return_value=1000):
            self.assertFalse(c._cached("test", loader)["cached"])
        self.assertEqual(loader.call_count, 2)

    def test_explicit_fallback(self):
        c = Collector()
        with patch("collector.hackerone_pages", side_effect=CollectionError("blocked")), \
             patch.object(c, "dataset", return_value={"ok": True, "mode": "public_dataset", "programs": []}):
            r = c.programs("hackerone")
        self.assertEqual(r["mode"], "public_dataset")
        self.assertIn("warning", r)

    def test_scope_exclusions_preserved(self):
        c = Collector()
        nodes = [{"asset_identifier": "*.example.com", "eligible_for_submission": True},
                 {"asset_identifier": "excluded.example.com", "eligible_for_submission": False}]
        with patch("details.live_details", return_value={"ok": True, "targets": {
            "in_scope": nodes[:1], "out_of_scope": nodes[1:]}}):
            r = c.scope("hackerone", "example")
        self.assertEqual(r["targets"]["out_of_scope"][0]["asset_identifier"], "excluded.example.com")

    def test_validation(self):
        c = Collector()
        for args in [([],), (["invalid"],), (["hackerone"], "", False, 1001),
                     (["hackerone"], "", False, 1, -1)]:
            with self.assertRaises(ValueError):
                c.collect(*args)
        with self.assertRaises(ValueError):
            c.scope("hackerone", "https://internal.invalid")

    def test_graphql_pagination_and_cursor_guard(self):
        client = MagicMock()
        client.get.return_value.text = '<meta name="csrf-token" content="public">'
        response = client.post.return_value
        response.json.side_effect = [
            {"data": {"teams": {"nodes": [{"handle": "a"}], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}},
            {"data": {"teams": {"nodes": [{"handle": "b"}], "pageInfo": {"hasNextPage": False}}}},
        ]
        with patch("collector.session") as factory, patch("collector.time.sleep"):
            factory.return_value.__enter__.return_value = client
            self.assertEqual(len(hackerone_pages("query", "teams")), 2)
            self.assertEqual(client.post.call_args.kwargs["json"]["variables"]["after"], "next")
            response.json.side_effect = None
            response.json.return_value = {"data": {"teams": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "same"}}}}
            with self.assertRaises(CollectionError):
                hackerone_pages("query", "teams")


if __name__ == "__main__":
    unittest.main()
