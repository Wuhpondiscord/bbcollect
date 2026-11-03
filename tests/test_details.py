import unittest
from unittest.mock import MagicMock, patch

from collector import Collector, CollectionError, normalize
from details import bugcrowd, intigriti, yeswehack, numeric_range


class DetailTests(unittest.TestCase):
    def test_unknown_ranges_are_not_zero(self):
        self.assertEqual(numeric_range([{"min": None, "max": 7500}]), (None, 7500))
        self.assertEqual(numeric_range([{"min": 0, "max": 0}]), (0, 0))

    def test_bugcrowd_minimum_across_severities_and_exclusions(self):
        client = MagicMock()
        client.get.return_value.text = '''<div data-react-class="ResearcherEngagementBrief"
          data-api-endpoints='{"engagementBriefApi":{"getBriefVersionDocument":"/engagements/demo/changelog/abc"}}'></div>'''
        client.get.return_value.json.return_value = {"data": {"brief": {"description": "rules"}, "scope": [
            {"name": "Main", "inScope": True, "targets": [{"uri": "https://example.com"}],
             "rewardRangeData": {"1": {"min": 3500, "max": 7500}, "4": {"min": 250, "max": 500}}},
            {"inScope": False, "targets": [{"uri": "https://excluded.example.com"}],
             "rewardRangeData": {"1": {"min": 1, "max": 99999}}}]}}
        with patch("details.session") as factory:
            factory.return_value.__enter__.return_value = client
            r = bugcrowd("demo")
        self.assertEqual((r["min_bounty"], r["max_bounty"]), (250, 7500))
        self.assertEqual(len(r["targets"]["out_of_scope"]), 1)
        self.assertEqual(r["rules"]["description"], "rules")

    def test_intigriti_latest_policy_and_group_context(self):
        client = MagicMock()
        client.get.return_value.json.return_value = {
            "confidentialityLevel": 4,
            "assetsCollection": [{"createdAt": 1, "content": {"assetsAndGroups": [
                {"name": "group", "description": "group rules", "assets": [
                    {"name": "*.example.com", "bountyTierId": 2},
                    {"name": "excluded.example.com", "bountyTierId": 5}]}]}}],
            "rulesOfEngagements": [{"createdAt": 2, "content": {"content": "new policy"}},
                                   {"createdAt": 1, "content": {"content": "old policy"}}]}
        with patch("details.session") as factory:
            factory.return_value.__enter__.return_value = client
            r = intigriti({"url": "https://www.intigriti.com/programs/company/slug/detail"})
        self.assertEqual(r["rules"]["rulesOfEngagements"]["content"], "new policy")
        self.assertEqual(r["targets"]["in_scope"][0]["groups"][0]["description"], "group rules")
        self.assertEqual(len(r["targets"]["out_of_scope"]), 1)

    def test_collect_includes_full_details_by_default(self):
        c = Collector()
        p = normalize("bugcrowd", {"name": "Demo", "url": "https://bugcrowd.com/engagements/demo"})
        d = {"ok": True, "partial": False, "min_bounty": 250, "max_bounty": 7500,
             "targets": {"in_scope": ["example.com"], "out_of_scope": []},
             "rules": {"policy": "testing requirements"}, "reward_table": ["severity table"]}
        with patch.object(c, "programs", return_value={"ok": True, "programs": [p]}), \
             patch.object(c, "details", return_value=d):
            r = c.collect(["bugcrowd"])
        self.assertEqual(r["programs"][0]["min_bounty"], 250)
        self.assertEqual(r["programs"][0]["rules"]["policy"], "testing requirements")
        self.assertIn("in_scope", r["programs"][0]["targets"])

    def test_detail_failure_keeps_scopes_but_does_not_invent_rules(self):
        c = Collector()
        p = normalize("bugcrowd", {"name": "Demo", "url": "https://bugcrowd.com/engagements/demo",
                                   "targets": {"in_scope": ["example.com"], "out_of_scope": []}, "max_payout": 7500})
        with patch("details.live_details", side_effect=CollectionError("blocked")), \
             patch.object(c, "dataset", return_value={"ok": True, "mode": "public_dataset", "programs": [p]}):
            r = c.details("bugcrowd", "demo")
        self.assertTrue(r["partial"])
        self.assertEqual(r["targets"]["in_scope"], ["example.com"])
        self.assertIsNone(r["rules"])
        self.assertIsNone(r["min_bounty"])
        self.assertEqual(r["field_status"]["rules"], "unavailable")


if __name__ == "__main__":
    unittest.main()
