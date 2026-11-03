import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from api import create_api, normalize_asset


def program(handle, reward, currency="USD"):
    return {"id": "hackerone:" + handle, "platform": "hackerone", "handle": handle,
            "name": handle, "url": "https://hackerone.com/" + handle,
            "offers_bounties": True, "min_bounty": None, "max_bounty": reward, "currency": currency}


def detail(handle="security", ok=True):
    return {"ok": ok, "partial": False, "platform": "hackerone", "handle": handle,
            "targets": {"in_scope": [{"asset_identifier": "*.example.com", "asset_type": "WILDCARD"},
                                     {"asset_identifier": "https://example.com", "asset_type": "URL"}],
                        "out_of_scope": [{"asset_identifier": "excluded.example.com", "asset_type": "URL"}]},
            "rules": {"policy": "Keep this policy"}, "mode": "live"}


class RestTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_api())

    def test_public_health_openapi_and_browser_cors(self):
        r = self.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["authentication_required"])
        self.assertFalse(r.json()["upstream_checked"])
        self.assertEqual(r.headers["X-API-Version"], "1.0.0")
        spec = self.client.get("/api/openapi.json").json()
        self.assertFalse(spec.get("security"))
        self.assertFalse(spec["components"].get("securitySchemes"))
        self.assertIn("ProgramPage", spec["components"]["schemas"])
        r = self.client.options("/api/v1/programs/batch", headers={
            "Origin": "https://example.com", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], "*")

    def test_currency_reward_sort_and_pagination(self):
        rows = [program("a", 500), program("b", 9000), program("euro", 99999, "EUR"),
                program("unknown", None)]
        with patch("api.collector.collect", return_value={"ok": True, "partial": False,
                   "programs": rows, "sources": {}, "next_offset": None}):
            r = self.client.get("/api/v1/programs", params={"currency": "usd", "reward_at_least": 500,
                "sort_by": "max_bounty", "descending": True, "limit": 1, "offset": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)
        self.assertEqual(r.json()["programs"][0]["handle"], "a")
        self.assertIsNone(r.json()["next_offset"])

    def test_enrich_only_the_selected_page(self):
        rows = [program("a", 1), program("b", 2)]
        with patch("api.collector.collect", return_value={"ok": True, "partial": False,
                  "programs": rows, "sources": {}, "next_offset": None}), \
             patch("api.collector.details", return_value=detail("b")) as get_detail:
            r = self.client.get("/api/v1/programs?include_details=true&limit=1&offset=1")
        self.assertEqual(r.status_code, 200)
        get_detail.assert_called_once_with("hackerone", "b")
        self.assertIn("policy", r.json()["programs"][0]["rules"])

    def test_filter_and_parameter_errors(self):
        for query, status in [("reward_at_least=100", 400), ("sort_by=max_bounty", 400),
                              ("limit=0", 422), ("platforms=unknown", 400),
                              ("include_details=true&limit=101", 400)]:
            r = self.client.get("/api/v1/programs?" + query)
            self.assertEqual(r.status_code, status)
            self.assertFalse(r.json()["ok"])
            self.assertIn("message", r.json()["error"])

    def test_batch_preserves_order_and_partial_failures(self):
        with patch("api.collector.details", side_effect=lambda p, h: detail(h, h != "missing")):
            r = self.client.post("/api/v1/programs/batch", json={"programs": [
                {"platform": "hackerone", "handle": "security"},
                {"platform": "hackerone", "handle": "missing"}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["succeeded"], 1)
        self.assertTrue(r.json()["partial"])
        self.assertEqual([p["handle"] for p in r.json()["programs"]], ["security", "missing"])
        self.assertEqual(self.client.post("/api/v1/programs/batch", json={"programs": []}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/programs/batch", json={"programs": [
            {"platform": "hackerone", "handle": "security"}] * 21}).status_code, 422)

    def test_asset_filters_retain_exclusions_and_rules(self):
        with patch("api.collector.details", return_value=detail()):
            r = self.client.get("/api/v1/programs/hackerone/security/assets?asset_type=wildcard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)
        self.assertEqual(r.json()["in_scope"][0]["identifier"], "*.example.com")
        self.assertEqual(r.json()["out_of_scope"][0]["identifier"], "excluded.example.com")
        self.assertEqual(r.json()["rules"]["policy"], "Keep this policy")

    def test_normalization_of_each_platform(self):
        for raw, identifier, kind in [
            ({"asset_identifier": "*.example.com", "asset_type": "WILDCARD"}, "*.example.com", "wildcard"),
            ({"uri": "https://example.com/api", "category": "api"}, "https://example.com/api", "api"),
            ({"name": "10.0.0.0/24", "typeId": 4}, "10.0.0.0/24", "ip_range"),
            ({"scope": "https://example.com", "scope_type": "web-application"}, "https://example.com", "url"),
            ("No social engineering", "No social engineering", "other")]:
            normalized = normalize_asset(raw)
            self.assertEqual((normalized["identifier"], normalized["type"]), (identifier, kind))
            self.assertEqual(normalized["raw"], raw)

    def test_busy_and_unavailable_status(self):
        slots = MagicMock()
        slots.acquire.return_value = False
        with patch("api._work_slots", slots):
            r = self.client.get("/api/v1/programs/hackerone/security")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.headers["retry-after"], "5")
        with patch("api.collector.details", return_value={"ok": False}):
            r = self.client.get("/api/v1/programs/hackerone/missing")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
