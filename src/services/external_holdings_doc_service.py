# -*- coding: utf-8 -*-
"""Feishu doc export for external holdings snapshots."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.repositories.external_holdings_repo import ExternalHoldingsRepository

logger = logging.getLogger(__name__)


class ExternalHoldingsDocService:
    """Render one confirmed snapshot into a Feishu cloud document."""

    def __init__(self, repo: Optional[ExternalHoldingsRepository] = None):
        self.repo = repo or ExternalHoldingsRepository()

    def sync_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        snapshot_id = int(snapshot["id"])
        title = f"持仓总览 {snapshot.get('snapshot_date')}"
        content_md = self._render_markdown(snapshot)

        try:
            from src.feishu_doc import FeishuDocManager
        except Exception as exc:
            logger.warning("飞书云文档 SDK 不可用，跳过文档同步: %s", exc)
            updated = self.repo.update_doc_sync(
                snapshot_id=snapshot_id,
                doc_url=None,
                doc_title=title,
                doc_sync_status="unavailable",
                doc_sync_error=str(exc),
                doc_exported_at=None,
            )
            return {
                "snapshot": updated,
                "doc_url": None,
                "doc_sync_status": "unavailable",
            }

        manager = FeishuDocManager()
        if not manager.is_configured():
            updated = self.repo.update_doc_sync(
                snapshot_id=snapshot_id,
                doc_url=None,
                doc_title=title,
                doc_sync_status="skipped",
                doc_sync_error="Feishu cloud doc config missing",
                doc_exported_at=None,
            )
            return {
                "snapshot": updated,
                "doc_url": None,
                "doc_sync_status": "skipped",
            }

        doc_url = manager.create_daily_doc(title=title, content_md=content_md)
        status = "success" if doc_url else "failed"
        updated = self.repo.update_doc_sync(
            snapshot_id=snapshot_id,
            doc_url=doc_url,
            doc_title=title,
            doc_sync_status=status,
            doc_sync_error=None if doc_url else "Feishu doc create returned empty URL",
            doc_exported_at=datetime.now() if doc_url else None,
        )
        return {
            "snapshot": updated,
            "doc_url": doc_url,
            "doc_sync_status": status,
        }

    def _render_markdown(self, snapshot: Dict[str, Any]) -> str:
        parts: List[str] = [
            "# 持仓总览（自动更新）",
            "",
            f"- 快照日期：{snapshot.get('snapshot_date') or 'N/A'}",
            f"- 数据来源：{snapshot.get('source_platform') or 'N/A'}",
            f"- 状态：{snapshot.get('status') or 'N/A'}",
            f"- 总市值：{_fmt_num(snapshot.get('total_market_value'))}",
            f"- 总盈亏：{_fmt_num(snapshot.get('total_profit'))}",
            f"- 币种：{snapshot.get('currency') or 'CNY'}",
            f"- 更新时间：{snapshot.get('updated_at') or snapshot.get('uploaded_at') or 'N/A'}",
            "",
        ]

        positions = snapshot.get("positions") or []
        stock_like = [p for p in positions if p.get("asset_type") in {"stock", "etf"}]
        funds = [p for p in positions if p.get("asset_type") == "fund"]

        if stock_like:
            parts.extend(["## 股票 / ETF 持仓", ""])
            for item in stock_like:
                parts.append(
                    "- "
                    f"{item.get('display_name') or item.get('symbol') or '未知标的'} "
                    f"({item.get('symbol') or 'N/A'}) "
                    f"| 数量 {_fmt_num(item.get('quantity'))} "
                    f"| 市值 {_fmt_num(item.get('market_value'))} "
                    f"| 盈亏 {_fmt_num(item.get('profit_amount'))} "
                    f"| 收益率 {_fmt_pct(item.get('profit_pct'))}"
                )
            parts.append("")

        if funds:
            parts.extend(["## 基金持仓", ""])
            for item in funds:
                parts.append(
                    "- "
                    f"{item.get('display_name') or item.get('symbol') or '未知基金'} "
                    f"({item.get('symbol') or 'N/A'}) "
                    f"| 份额 {_fmt_num(item.get('quantity'))} "
                    f"| 市值 {_fmt_num(item.get('market_value'))} "
                    f"| 累计收益 {_fmt_num(item.get('profit_amount'))} "
                    f"| 收益率 {_fmt_pct(item.get('profit_pct'))}"
                )
            parts.append("")

        warnings = snapshot.get("warnings") or []
        if warnings:
            parts.extend(["## 识别提示", ""])
            for warning in warnings:
                parts.append(f"- {warning}")
            parts.append("")

        parts.extend(
            [
                "---",
                "",
                "说明：本页基于截图识别生成，为“外部持仓快照”，不等同于交易账本。",
            ]
        )
        return "\n".join(parts)


def _fmt_num(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)
