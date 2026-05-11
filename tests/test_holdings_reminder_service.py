# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from src.services.holdings_reminder_service import HoldingsReminderService


class HoldingsReminderServiceTestCase(unittest.TestCase):
    def _build_config(self, **overrides):
        defaults = {
            "external_holdings_enabled": True,
            "holding_screenshot_reminder_enabled": True,
            "holding_screenshot_reminder_stock_time": "15:10",
            "holding_screenshot_reminder_fund_time": "21:00",
            "holding_screenshot_reminder_channels": [],
            "feishu_webhook_url": "https://example.com/webhook",
            "email_sender": None,
            "email_sender_name": "DSA Bot",
            "email_password": None,
            "email_receivers": [],
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("src.services.holdings_reminder_service.FeishuSender.send_to_feishu", return_value=True)
    def test_run_pending_sends_once_per_time_slot(self, mock_send):
        service = HoldingsReminderService(self._build_config())

        first = service.run_pending(now=datetime(2026, 5, 11, 15, 10))
        second = service.run_pending(now=datetime(2026, 5, 11, 15, 10, 20))

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["kind"], "ths_stock")
        self.assertEqual(second, [])
        self.assertEqual(mock_send.call_count, 1)

    @patch("src.services.holdings_reminder_service.EmailSender.send_to_email", return_value=True)
    def test_run_pending_uses_explicit_channels(self, mock_send):
        service = HoldingsReminderService(
            self._build_config(
                holding_screenshot_reminder_channels=["email"],
                feishu_webhook_url=None,
                email_sender="bot@example.com",
                email_password="secret",
            )
        )

        triggered = service.run_pending(now=datetime(2026, 5, 11, 21, 0))

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["kind"], "alipay_fund")
        mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
