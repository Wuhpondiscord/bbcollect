"""Exercise Gradio preprocessing with the original five-value wire payload."""
import asyncio
import unittest
from unittest.mock import patch

from app import demo


class ApiCompatibilityTests(unittest.TestCase):
    def call(self, name, values):
        index = next(i for i, fn in demo.fns.items() if fn.api_name == name)
        return asyncio.run(demo.process_api(index, inputs=values))

    def test_collect_preserves_five_input_contract(self):
        expected = {"ok": True, "programs": [], "include_details": True}
        with patch("app.collector.collect", return_value=expected) as collect:
            result = self.call("collect", [["hackerone"], "", False, 100, 0])
        collect.assert_called_once_with(["hackerone"], "", False, 100, 0, True)
        self.assertEqual(result["data"][0].model_dump(), expected)

    def test_summary_toggle_has_separate_six_input_endpoint(self):
        with patch("app.collector.collect", return_value={"ok": True}) as collect:
            self.call("collect_options", [["hackerone"], "", False, 10, 0, False])
        collect.assert_called_once_with(["hackerone"], "", False, 10, 0, False)

    def test_generated_schema_input_counts(self):
        endpoints = demo.get_api_info()["named_endpoints"]
        self.assertEqual(len(endpoints["/collect"]["parameters"]), 5)
        self.assertEqual(len(endpoints["/collect_options"]["parameters"]), 6)


if __name__ == "__main__":
    unittest.main()
