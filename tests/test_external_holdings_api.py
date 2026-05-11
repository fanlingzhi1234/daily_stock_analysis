# -*- coding: utf-8 -*-
"""API tests for external holdings snapshot workflow."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00"
    b"\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class ExternalHoldingsApiTestCase(unittest.TestCase):
    """Integration tests for screenshot-driven holdings snapshots."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "external_holdings_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    "EXTERNAL_HOLDINGS_ENABLED=true",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("EXTERNAL_HOLDINGS_ENABLED", None)
        self.temp_dir.cleanup()

    @patch("src.services.external_holdings_doc_service.ExternalHoldingsDocService.sync_snapshot")
    @patch("src.services.external_holdings_service.extract_holdings_from_image")
    def test_extract_confirm_and_latest_flow(self, mock_extract, mock_sync_snapshot) -> None:
        mock_extract.return_value = (
            [
                {
                    "asset_type": "stock",
                    "source_platform": "ths_stock",
                    "symbol": "600519",
                    "display_name": "贵州茅台",
                    "market": "cn",
                    "quantity": 10.0,
                    "market_value": 18000.0,
                    "cost_basis_total": 16000.0,
                    "profit_amount": 2000.0,
                    "profit_pct": 12.5,
                    "position_weight": None,
                    "price": 1800.0,
                    "price_date": None,
                    "confidence": "high",
                    "is_manually_edited": False,
                    "raw_payload": "{}",
                }
            ],
            '[{"symbol":"600519"}]',
            ["row=1: sample warning"],
        )

        extract_resp = self.client.post(
            "/api/v1/external-holdings/extract-from-image",
            data={"source_platform": "ths_stock"},
            files={"file": ("ths.png", PNG_1X1, "image/png")},
        )
        self.assertEqual(extract_resp.status_code, 200)
        snapshot = extract_resp.json()["snapshot"]
        self.assertEqual(snapshot["status"], "draft")
        self.assertEqual(snapshot["positions"][0]["symbol"], "600519")
        snapshot_id = snapshot["id"]

        mock_sync_snapshot.return_value = {
            "snapshot": MagicMock(id=snapshot_id, doc_sync_error=None),
            "doc_url": "https://feishu.cn/docx/mock-doc",
            "doc_sync_status": "success",
        }
        confirm_resp = self.client.post(
            f"/api/v1/external-holdings/snapshots/{snapshot_id}/confirm",
            json={
                "items": [
                    {
                        "asset_type": "stock",
                        "source_platform": "ths_stock",
                        "symbol": "600519",
                        "display_name": "贵州茅台",
                        "market": "cn",
                        "quantity": 10,
                        "market_value": 18100,
                        "cost_basis_total": 16000,
                        "profit_amount": 2100,
                        "profit_pct": 13.125,
                        "price": 1810,
                        "confidence": "high",
                        "is_manually_edited": True,
                    }
                ],
                "review_notes": "confirmed by tester",
                "sync_doc": True,
            },
        )
        self.assertEqual(confirm_resp.status_code, 200)
        confirmed = confirm_resp.json()
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["doc_sync_status"], "success")
        self.assertEqual(confirmed["doc_url"], "https://feishu.cn/docx/mock-doc")

        latest_resp = self.client.get("/api/v1/external-holdings/latest", params={"source_platform": "ths_stock"})
        self.assertEqual(latest_resp.status_code, 200)
        latest = latest_resp.json()
        self.assertEqual(latest["id"], snapshot_id)
        self.assertEqual(latest["status"], "confirmed")

    @patch("src.services.external_holdings_doc_service.ExternalHoldingsDocService.sync_snapshot")
    @patch("src.services.external_holdings_service.extract_holdings_from_image")
    def test_manual_doc_sync_endpoint(self, mock_extract, mock_sync_snapshot) -> None:
        mock_extract.return_value = (
            [
                {
                    "asset_type": "fund",
                    "source_platform": "alipay_fund",
                    "symbol": "110011",
                    "display_name": "易方达中小盘",
                    "market": "fund",
                    "quantity": 100.0,
                    "market_value": 1234.5,
                    "cost_basis_total": 1200.0,
                    "profit_amount": 34.5,
                    "profit_pct": 2.875,
                    "position_weight": None,
                    "price": None,
                    "price_date": None,
                    "confidence": "medium",
                    "is_manually_edited": False,
                    "raw_payload": "{}",
                }
            ],
            '[{"symbol":"110011"}]',
            [],
        )
        extract_resp = self.client.post(
            "/api/v1/external-holdings/extract-from-image",
            data={"source_platform": "alipay_fund"},
            files={"file": ("alipay.png", PNG_1X1, "image/png")},
        )
        snapshot_id = extract_resp.json()["snapshot"]["id"]

        snapshot_mock = MagicMock(id=snapshot_id, doc_sync_error=None)
        mock_sync_snapshot.return_value = {
            "snapshot": snapshot_mock,
            "doc_url": "https://feishu.cn/docx/manual-sync",
            "doc_sync_status": "success",
        }
        sync_resp = self.client.post(f"/api/v1/external-holdings/snapshots/{snapshot_id}/doc-sync")
        self.assertEqual(sync_resp.status_code, 200)
        self.assertEqual(sync_resp.json()["doc_url"], "https://feishu.cn/docx/manual-sync")
        self.assertEqual(sync_resp.json()["doc_sync_status"], "success")

    def test_status_and_feature_gate(self) -> None:
        status_resp = self.client.get("/api/v1/external-holdings/status")
        self.assertEqual(status_resp.status_code, 200)
        self.assertTrue(status_resp.json()["enabled"])

        os.environ["EXTERNAL_HOLDINGS_ENABLED"] = "false"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    "EXTERNAL_HOLDINGS_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        Config.reset_instance()
        gated_resp = self.client.get("/api/v1/external-holdings/latest")
        self.assertEqual(gated_resp.status_code, 404)
        self.assertEqual(gated_resp.json()["error"], "feature_disabled")
