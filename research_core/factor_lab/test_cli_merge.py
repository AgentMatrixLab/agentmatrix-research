from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from research_core.factor_lab.libraries.factor_sets import ALPHA158_ALL_FACTORS


class FactorLabCliMergeTest(unittest.TestCase):
    def test_build_parser_keeps_all_expected_commands(self) -> None:
        from research_core.factor_lab.cli import build_parser

        parser = build_parser()

        self.assertEqual(
            parser.parse_args(["run-factor-set-real", "--factor-set", "gtja191"]).command,
            "run-factor-set-real",
        )
        self.assertEqual(
            parser.parse_args(["run-factor-research", "--factor-set", "alpha158"]).command,
            "run-factor-research",
        )
        self.assertEqual(
            parser.parse_args(["explore", "--factor-set", "alpha158"]).command,
            "explore",
        )
        self.assertEqual(
            parser.parse_args(["gate", "--input", "/tmp/factors.json"]).command,
            "gate",
        )

    def test_run_factor_research_defaults_to_alpha158_factors(self) -> None:
        import research_core.factor_lab.cli as cli

        captured: dict[str, object] = {}

        def fake_run_factor_set_research_job(payload: dict[str, object], config=None) -> dict[str, object]:
            captured.update(payload)
            return {"status": "ok", "factor_names": payload["factor_names"]}

        with patch.object(sys, "argv", ["factor-lab", "run-factor-research", "--factor-set", "alpha158"]):
            with patch.object(cli, "run_factor_set_research_job", side_effect=fake_run_factor_set_research_job):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    cli.main()

        response = json.loads(buffer.getvalue())
        self.assertEqual(response["status"], "ok")
        self.assertEqual(captured["factor_set"], "alpha158")
        self.assertEqual(captured["factor_names"], list(ALPHA158_ALL_FACTORS))


if __name__ == "__main__":
    unittest.main()
