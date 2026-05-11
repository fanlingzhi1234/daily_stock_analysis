# -*- coding: utf-8 -*-
"""Business logic for screenshot-based external holdings snapshots."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.config import get_config
from src.repositories.external_holdings_repo import ExternalHoldingsRepository
from src.services.external_holdings_doc_service import ExternalHoldingsDocService
from src.services.holding_image_extractor import (
    SUPPORTED_SOURCE_PLATFORMS,
    extract_holdings_from_image,
)

logger = logging.getLogger(__name__)


class ExternalHoldingsService:
    """Create, confirm, and sync external holdings snapshots."""

    def __init__(
        self,
        *,
        repo: Optional[ExternalHoldingsRepository] = None,
        doc_service: Optional[ExternalHoldingsDocService] = None,
    ):
        self.repo = repo or ExternalHoldingsRepository()
        self.doc_service = doc_service or ExternalHoldingsDocService(repo=self.repo)

    @staticmethod
    def _ensure_enabled() -> None:
        if getattr(get_config(), "external_holdings_enabled", False):
            return
        raise ValueError("External holdings screenshot snapshots are not enabled")

    def create_draft_from_image(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source_platform: str,
        snapshot_date: Optional[date] = None,
        captured_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        platform = (source_platform or "").strip().lower()
        if platform not in SUPPORTED_SOURCE_PLATFORMS:
            raise ValueError(f"unsupported source_platform: {source_platform}")

        items, raw_text, warnings = extract_holdings_from_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            source_platform=platform,
        )
        normalized_positions = self._normalize_positions(items)
        totals = self._compute_totals(normalized_positions)
        raw_image_path = self._persist_image(image_bytes=image_bytes, mime_type=mime_type, source_platform=platform)
        snapshot = self.repo.create_snapshot(
            source_platform=platform,
            snapshot_date=snapshot_date or date.today(),
            captured_at=captured_at,
            uploaded_at=datetime.now(),
            status="draft",
            total_market_value=totals["total_market_value"],
            total_profit=totals["total_profit"],
            currency=totals["currency"],
            raw_image_path=raw_image_path,
            ocr_raw_text=raw_text,
            warnings_json=json.dumps(warnings, ensure_ascii=False),
            review_notes=None,
            positions=normalized_positions,
        )
        return self.get_snapshot(int(snapshot.id))

    def get_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        self._ensure_enabled()
        snapshot = self.repo.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        positions = self.repo.list_positions(snapshot_id)
        return self._serialize_snapshot(snapshot=snapshot, positions=positions)

    def confirm_snapshot(
        self,
        *,
        snapshot_id: int,
        items: List[Dict[str, Any]],
        review_notes: Optional[str] = None,
        sync_doc: bool = True,
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        if not items:
            raise ValueError("items must not be empty")
        normalized_positions = self._normalize_positions(items, mark_manual=True)
        totals = self._compute_totals(normalized_positions)
        updated = self.repo.replace_snapshot(
            snapshot_id=snapshot_id,
            status="confirmed",
            total_market_value=totals["total_market_value"],
            total_profit=totals["total_profit"],
            currency=totals["currency"],
            warnings_json=json.dumps([], ensure_ascii=False),
            review_notes=(review_notes or "").strip() or None,
            positions=normalized_positions,
        )
        if updated is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        payload = self.get_snapshot(snapshot_id)
        should_sync_doc = bool(sync_doc and getattr(get_config(), "holding_screenshot_doc_sync_enabled", True))
        if should_sync_doc:
            doc_result = self.doc_service.sync_snapshot(payload)
            payload["doc_sync_status"] = doc_result["doc_sync_status"]
            payload["doc_url"] = doc_result.get("doc_url")
        return payload

    def sync_snapshot_doc(self, snapshot_id: int) -> Dict[str, Any]:
        self._ensure_enabled()
        payload = self.get_snapshot(snapshot_id)
        return self.doc_service.sync_snapshot(payload)

    def get_latest_snapshot(
        self,
        *,
        source_platform: Optional[str] = None,
        status: str = "confirmed",
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        snapshot = self.repo.get_latest_snapshot(source_platform=source_platform, status=status)
        if snapshot is None:
            raise ValueError("latest snapshot not found")
        return self.get_snapshot(int(snapshot.id))

    def _persist_image(self, *, image_bytes: bytes, mime_type: str, source_platform: str) -> str:
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get((mime_type or "").split(";")[0].strip().lower(), ".img")
        db_parent = Path(get_config().database_path).resolve().parent
        target_dir = db_parent / "external_holdings" / source_platform
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}{suffix}"
        path.write_bytes(image_bytes)
        return str(path)

    @staticmethod
    def _normalize_positions(
        items: List[Dict[str, Any]],
        *,
        mark_manual: bool = False,
    ) -> List[Dict[str, Any]]:
        positions: List[Dict[str, Any]] = []
        for item in items:
            payload = dict(item)
            payload["asset_type"] = (payload.get("asset_type") or "stock").strip().lower()
            payload["source_platform"] = (payload.get("source_platform") or "").strip().lower()
            payload["symbol"] = (payload.get("symbol") or "").strip().upper() or None
            payload["display_name"] = (payload.get("display_name") or "").strip() or payload.get("symbol")
            payload["market"] = (payload.get("market") or "cn").strip().lower()
            payload["confidence"] = (payload.get("confidence") or "medium").strip().lower()
            payload["is_manually_edited"] = bool(payload.get("is_manually_edited", False) or mark_manual)
            payload["raw_payload"] = payload.get("raw_payload") or json.dumps(item, ensure_ascii=False)
            positions.append(payload)
        return positions

    @staticmethod
    def _compute_totals(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_market_value = 0.0
        total_profit = 0.0
        has_market_value = False
        has_profit = False
        for item in positions:
            market_value = item.get("market_value")
            if isinstance(market_value, (int, float)):
                total_market_value += float(market_value)
                has_market_value = True
            profit_amount = item.get("profit_amount")
            if isinstance(profit_amount, (int, float)):
                total_profit += float(profit_amount)
                has_profit = True
        if has_market_value and total_market_value > 0:
            for item in positions:
                market_value = item.get("market_value")
                if isinstance(market_value, (int, float)):
                    item["position_weight"] = round(float(market_value) / total_market_value * 100.0, 4)
        return {
            "total_market_value": round(total_market_value, 4) if has_market_value else None,
            "total_profit": round(total_profit, 4) if has_profit else None,
            "currency": "CNY",
        }

    @staticmethod
    def _serialize_snapshot(*, snapshot: Any, positions: List[Any]) -> Dict[str, Any]:
        warnings: List[str] = []
        if getattr(snapshot, "warnings_json", None):
            try:
                warnings = json.loads(snapshot.warnings_json)
            except Exception:
                warnings = [str(snapshot.warnings_json)]

        position_items: List[Dict[str, Any]] = []
        for item in positions:
            position_items.append(
                {
                    "id": int(item.id),
                    "asset_type": item.asset_type,
                    "source_platform": item.source_platform,
                    "symbol": item.symbol,
                    "display_name": item.display_name,
                    "market": item.market,
                    "quantity": item.quantity,
                    "market_value": item.market_value,
                    "cost_basis_total": item.cost_basis_total,
                    "profit_amount": item.profit_amount,
                    "profit_pct": item.profit_pct,
                    "position_weight": item.position_weight,
                    "price": item.price,
                    "price_date": item.price_date.isoformat() if item.price_date else None,
                    "confidence": item.confidence,
                    "is_manually_edited": bool(item.is_manually_edited),
                    "raw_payload": item.raw_payload,
                }
            )

        return {
            "id": int(snapshot.id),
            "source_platform": snapshot.source_platform,
            "snapshot_date": snapshot.snapshot_date.isoformat() if snapshot.snapshot_date else None,
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
            "uploaded_at": snapshot.uploaded_at.isoformat() if snapshot.uploaded_at else None,
            "status": snapshot.status,
            "total_market_value": snapshot.total_market_value,
            "total_profit": snapshot.total_profit,
            "currency": snapshot.currency,
            "raw_image_path": snapshot.raw_image_path,
            "ocr_raw_text": snapshot.ocr_raw_text,
            "warnings": warnings,
            "review_notes": snapshot.review_notes,
            "doc_url": snapshot.doc_url,
            "doc_title": snapshot.doc_title,
            "doc_sync_status": snapshot.doc_sync_status,
            "doc_sync_error": snapshot.doc_sync_error,
            "doc_exported_at": snapshot.doc_exported_at.isoformat() if snapshot.doc_exported_at else None,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
            "positions": position_items,
        }
