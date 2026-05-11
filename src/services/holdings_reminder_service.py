# -*- coding: utf-8 -*-
"""Schedule-mode reminders for screenshot-based external holdings updates."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.config import Config, get_config
from src.notification_sender import EmailSender, FeishuSender

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SUPPORTED_CHANNELS = {"feishu", "email"}


class HoldingsReminderService:
    """Send daily reminders to upload holdings screenshots."""

    def __init__(self, config: Optional[Config] = None):
        self._config = config or get_config()
        self._last_sent_keys: Dict[str, str] = {}

    def set_config(self, config: Config) -> None:
        self._config = config

    def run_pending(self, *, now: Optional[datetime] = None) -> List[Dict[str, str]]:
        current = now or datetime.now()
        config = self._config
        if not getattr(config, "external_holdings_enabled", False):
            return []
        if not getattr(config, "holding_screenshot_reminder_enabled", False):
            return []

        reminders = [
            {
                "kind": "ths_stock",
                "time": getattr(config, "holding_screenshot_reminder_stock_time", "15:10"),
                "title": "请更新同花顺股票持仓截图",
                "body": (
                    "请在同花顺中打开股票 / ETF 持仓页并截图，然后上传到 Web 持仓页中的"
                    "“外部持仓截图快照”面板。系统会识别候选持仓，确认后可同步飞书文档。"
                ),
            },
            {
                "kind": "alipay_fund",
                "time": getattr(config, "holding_screenshot_reminder_fund_time", "21:00"),
                "title": "请更新支付宝基金持仓截图",
                "body": (
                    "请在支付宝中打开基金持仓页并截图，然后上传到 Web 持仓页中的"
                    "“外部持仓截图快照”面板。系统会识别候选持仓，确认后可同步飞书文档。"
                ),
            },
        ]

        triggered: List[Dict[str, str]] = []
        current_hm = current.strftime("%H:%M")
        current_day = current.strftime("%Y-%m-%d")

        for reminder in reminders:
            reminder_time = str(reminder["time"] or "").strip()
            if not _TIME_RE.fullmatch(reminder_time):
                logger.warning(
                    "外部持仓截图提醒时间无效，已跳过 %s: %r",
                    reminder["kind"],
                    reminder["time"],
                )
                continue
            if reminder_time != current_hm:
                continue

            send_key = f"{reminder['kind']}:{current_day}:{reminder_time}"
            if self._last_sent_keys.get(reminder["kind"]) == send_key:
                continue

            if self._dispatch_reminder(reminder["title"], reminder["body"]):
                self._last_sent_keys[reminder["kind"]] = send_key
                triggered.append(
                    {
                        "kind": reminder["kind"],
                        "time": reminder_time,
                        "date": current_day,
                    }
                )

        return triggered

    def _resolve_channels(self) -> List[str]:
        config = self._config
        configured = [
            item.strip().lower()
            for item in (getattr(config, "holding_screenshot_reminder_channels", []) or [])
            if str(item).strip()
        ]
        channels = [item for item in configured if item in _SUPPORTED_CHANNELS]
        if channels:
            return list(dict.fromkeys(channels))

        inferred: List[str] = []
        if getattr(config, "feishu_webhook_url", None):
            inferred.append("feishu")
        if getattr(config, "email_sender", None) and getattr(config, "email_password", None):
            inferred.append("email")
        return inferred

    def _dispatch_reminder(self, title: str, body: str) -> bool:
        config = self._config
        channels = self._resolve_channels()
        if not channels:
            logger.info("外部持仓截图提醒已启用，但未配置可用提醒渠道，跳过本轮发送")
            return False

        content = f"## {title}\n\n{body}\n\n- 来源：外部持仓截图快照\n- 上传入口：Web 持仓页 -> 外部持仓截图快照"
        delivered = False
        for channel in channels:
            try:
                if channel == "feishu":
                    delivered = FeishuSender(config).send_to_feishu(content) or delivered
                elif channel == "email":
                    delivered = EmailSender(config).send_to_email(content, subject=title) or delivered
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("发送外部持仓截图提醒失败 [%s]: %s", channel, exc)
        return delivered
