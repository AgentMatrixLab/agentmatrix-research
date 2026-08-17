from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.factor_lab_api import app


class FactorDetailDatasourceDefaultTest(unittest.TestCase):
    """Guards the post-merge datasource-default regression:

    The default factor-detail GET must NOT trigger live Quant API research on
    cache miss. Live research requires explicit `?data_source=real` opt-in.
    """

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_default_cache_miss_does_not_invoke_real_path(self) -> None:
        with patch("backend.factor_lab_api._read_artifact_cache", return_value=None), \
             patch("backend.factor_lab_api._build_factor_detail_from_latest_job", return_value=None) as mock_artifact, \
             patch("backend.factor_lab_api._build_real_factor_detail") as mock_real, \
             patch("backend.factor_lab_api.QuantApiClient") as mock_client, \
             patch("backend.factor_lab_api.build_factor_library_view", return_value={}):
            resp = self.client.get("/api/agents/factor-lab/factor/Alpha101:alpha1")
            self.assertEqual(resp.status_code, 404)
            self.assertIn("no precomputed research artifact", resp.get_json()["error"])
            mock_artifact.assert_called_once()
            mock_real.assert_not_called()
            mock_client.assert_not_called()

    def test_explicit_real_opt_in_uses_real_path(self) -> None:
        payload = {"factor_id": "Alpha101:alpha1", "stratification": {}, "group_returns": {}}
        with patch("backend.factor_lab_api._read_artifact_cache", return_value=None), \
             patch("backend.factor_lab_api._build_factor_detail_from_latest_job") as mock_artifact, \
             patch("backend.factor_lab_api._build_real_factor_detail", return_value=payload) as mock_real, \
             patch("backend.factor_lab_api._ensure_stratification_from_group_returns", return_value=False), \
             patch("backend.factor_lab_api._write_artifact_cache", side_effect=lambda k, i, p: p), \
             patch("backend.factor_lab_api.build_factor_library_view", return_value={}):
            resp = self.client.get("/api/agents/factor-lab/factor/Alpha101:alpha1?data_source=real")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["factor_id"], "Alpha101:alpha1")
            mock_real.assert_called_once()
            mock_artifact.assert_not_called()


if __name__ == "__main__":
    unittest.main()
