from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.verify_strategy_dashboard_deployment import verify


class _Response:
    def __init__(self, payload):
        self.status = 200
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        import json

        return json.dumps(self.payload).encode()


class StrategyDashboardDeploymentTest(unittest.TestCase):
    def test_accepts_consistent_review_deployment(self):
        responses = [
            _Response({"status": "ok", "strategies": 1}),
            _Response([{"id": "dividend-v6", "publication_status": "review"}]),
            _Response({"data": {"data_version": "2026-08-06"}}),
        ]
        with patch("scripts.verify_strategy_dashboard_deployment.urlopen", side_effect=responses):
            result = verify("http://127.0.0.1:8813/", require_strategy=True, expected_status="review")
        self.assertEqual(result["strategies"], 1)
        self.assertEqual(result["data_version"], "2026-08-06")

    def test_rejects_empty_required_library(self):
        responses = [_Response({"status": "ok", "strategies": 0}), _Response([]), _Response({"data": {}})]
        with patch("scripts.verify_strategy_dashboard_deployment.urlopen", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "empty"):
                verify("http://127.0.0.1:8813", require_strategy=True, expected_status="review")


if __name__ == "__main__":
    unittest.main()
