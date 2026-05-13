# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.services.holding_image_extractor import _parse_items, extract_holdings_from_image


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00"
    b"\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


class HoldingImageExtractorTestCase(unittest.TestCase):
    @patch("src.services.holding_image_extractor.OCRServiceClient")
    def test_extract_uses_asset_screenshot_parser_service(self, mock_client_cls) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.is_configured.return_value = True
        mock_client.parse_holdings_screenshot.return_value = {
            "request_id": "req-1",
            "ocr_provider": "umi_http",
            "screenshot_type": "ths_stock_positions_mobile_v1",
            "warnings": [],
            "snapshot_candidate": {
                "source_platform": "ths_stock",
                "screenshot_type": "ths_stock_positions_mobile_v1",
                "warnings": [],
                "positions": [
                    {
                        "display_name": "航天发展",
                        "symbol": "",
                        "asset_type": "stock",
                        "market": "cn",
                        "quantity": 300,
                        "market_value": 8376.0,
                        "cost_price": 39.017,
                        "profit_amount": -3338.19,
                        "profit_pct": -28.44,
                        "price": 27.92,
                        "confidence": "high",
                    }
                ],
            },
        }

        items, raw, warnings = extract_holdings_from_image(
            PNG_1X1,
            "image/png",
            source_platform="ths_stock",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["display_name"], "航天发展")
        self.assertEqual(items[0]["symbol"], "000547")
        self.assertEqual(items[0]["market_value"], 8376.0)
        self.assertEqual(items[0]["cost_basis_total"], 11705.1)
        self.assertIn("umi_http", raw)
        self.assertTrue(any("000547" in warning for warning in warnings))

    def test_parse_alipay_mobile_snapshot_derives_cost_basis(self) -> None:
        raw_payload = json.dumps(
            [
                {
                    "display_name": "工银瑞信新能源汽车主题混合A",
                    "symbol": "",
                    "asset_type": "fund",
                    "market": "fund",
                    "quantity": "",
                    "market_value": "31618.92",
                    "profit_amount": "8397.06",
                    "profit_pct": "36.16%",
                    "price": "",
                    "confidence": "high",
                },
                {
                    "display_name": "汇添富恒生指数(QDII-LOF)C",
                    "symbol": "",
                    "asset_type": "fund",
                    "market": "fund",
                    "quantity": "",
                    "market_value": "3635.16",
                    "profit_amount": "635.16",
                    "profit_pct": "21.17%",
                    "price": "",
                    "confidence": "high",
                },
            ],
            ensure_ascii=False,
        )

        items, warnings = _parse_items(raw_text=raw_payload, source_platform="alipay_fund")

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["display_name"], "工银瑞信新能源汽车主题混合A")
        self.assertAlmostEqual(items[0]["market_value"], 31618.92)
        self.assertAlmostEqual(items[0]["profit_amount"], 8397.06)
        self.assertAlmostEqual(items[0]["cost_basis_total"], 23221.86)
        self.assertAlmostEqual(items[1]["cost_basis_total"], 3000.0)
        self.assertEqual(warnings, [])

    def test_parse_tonghuashun_mobile_snapshot_uses_local_index_for_names(self) -> None:
        raw_payload = json.dumps(
            [
                {
                    "display_name": "恒指科技",
                    "symbol": "",
                    "asset_type": "etf",
                    "market": "cn",
                    "quantity": "10000",
                    "market_value": "6470.00",
                    "cost_price": "0.734",
                    "profit_amount": "-870.00",
                    "profit_pct": "-11.790%",
                    "price": "0.647",
                    "confidence": "medium",
                },
                {
                    "display_name": "航天发展",
                    "symbol": "",
                    "asset_type": "stock",
                    "market": "cn",
                    "quantity": "300",
                    "market_value": "8376.00",
                    "cost_price": "39.017",
                    "profit_amount": "-3338.19",
                    "profit_pct": "-28.440%",
                    "price": "27.920",
                    "confidence": "high",
                },
                {
                    "display_name": "万向钱潮",
                    "symbol": "",
                    "asset_type": "stock",
                    "market": "cn",
                    "quantity": "700",
                    "market_value": "12348.00",
                    "cost_price": "20.207",
                    "profit_amount": "-1808.18",
                    "profit_pct": "-12.699%",
                    "price": "17.640",
                    "confidence": "high",
                },
                {
                    "display_name": "嘉事堂",
                    "symbol": "",
                    "asset_type": "stock",
                    "market": "cn",
                    "quantity": "500",
                    "market_value": "6855.00",
                    "cost_price": "19.130",
                    "profit_amount": "-2718.43",
                    "profit_pct": "-28.330%",
                    "price": "13.710",
                    "confidence": "high",
                },
            ],
            ensure_ascii=False,
        )

        items, warnings = _parse_items(raw_text=raw_payload, source_platform="ths_stock")

        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]["display_name"], "恒指科技")
        self.assertIsNone(items[0]["symbol"])
        self.assertEqual(items[1]["symbol"], "000547")
        self.assertEqual(items[2]["symbol"], "000559")
        self.assertEqual(items[3]["symbol"], "002462")
        self.assertAlmostEqual(items[1]["cost_basis_total"], 11705.1)
        self.assertAlmostEqual(items[2]["cost_basis_total"], 14144.9)
        self.assertAlmostEqual(items[3]["cost_basis_total"], 9565.0)
        self.assertTrue(any("000547" in warning for warning in warnings))
        self.assertTrue(any("000559" in warning for warning in warnings))
        self.assertTrue(any("002462" in warning for warning in warnings))
        self.assertTrue(any("指数/ETF代码缺失" in warning for warning in warnings))
        self.assertFalse(any("603106" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
