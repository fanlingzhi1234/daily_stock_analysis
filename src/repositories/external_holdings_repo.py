# -*- coding: utf-8 -*-
"""Repository helpers for external holdings screenshot snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, select

from src.storage import (
    DatabaseManager,
    ExternalHoldingPosition,
    ExternalHoldingSnapshot,
)


class ExternalHoldingsRepository:
    """Persistence layer for screenshot-based holdings snapshots."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def create_snapshot(
        self,
        *,
        source_platform: str,
        snapshot_date: date,
        captured_at: Optional[datetime],
        uploaded_at: Optional[datetime],
        status: str,
        total_market_value: Optional[float],
        total_profit: Optional[float],
        currency: str,
        raw_image_path: Optional[str],
        ocr_raw_text: Optional[str],
        warnings_json: Optional[str],
        review_notes: Optional[str],
        positions: List[Dict[str, Any]],
    ) -> ExternalHoldingSnapshot:
        with self.db.session_scope() as session:
            snapshot = ExternalHoldingSnapshot(
                source_platform=source_platform,
                snapshot_date=snapshot_date,
                captured_at=captured_at,
                uploaded_at=uploaded_at or datetime.now(),
                status=status,
                total_market_value=total_market_value,
                total_profit=total_profit,
                currency=currency,
                raw_image_path=raw_image_path,
                ocr_raw_text=ocr_raw_text,
                warnings_json=warnings_json,
                review_notes=review_notes,
            )
            session.add(snapshot)
            session.flush()
            self._add_positions(session=session, snapshot_id=int(snapshot.id), positions=positions)
            session.refresh(snapshot)
            session.expunge(snapshot)
            return snapshot

    def get_snapshot(self, snapshot_id: int) -> Optional[ExternalHoldingSnapshot]:
        with self.db.get_session() as session:
            row = session.execute(
                select(ExternalHoldingSnapshot)
                .where(ExternalHoldingSnapshot.id == snapshot_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    def list_positions(self, snapshot_id: int) -> List[ExternalHoldingPosition]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(ExternalHoldingPosition)
                .where(ExternalHoldingPosition.snapshot_id == snapshot_id)
                .order_by(ExternalHoldingPosition.id.asc())
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def replace_snapshot(
        self,
        *,
        snapshot_id: int,
        status: Optional[str] = None,
        total_market_value: Optional[float] = None,
        total_profit: Optional[float] = None,
        currency: Optional[str] = None,
        warnings_json: Optional[str] = None,
        review_notes: Optional[str] = None,
        positions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[ExternalHoldingSnapshot]:
        with self.db.session_scope() as session:
            row = session.execute(
                select(ExternalHoldingSnapshot)
                .where(ExternalHoldingSnapshot.id == snapshot_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            if status is not None:
                row.status = status
            row.total_market_value = total_market_value
            row.total_profit = total_profit
            if currency is not None:
                row.currency = currency
            if warnings_json is not None:
                row.warnings_json = warnings_json
            row.review_notes = review_notes
            row.updated_at = datetime.now()

            if positions is not None:
                session.execute(
                    delete(ExternalHoldingPosition)
                    .where(ExternalHoldingPosition.snapshot_id == snapshot_id)
                )
                self._add_positions(session=session, snapshot_id=snapshot_id, positions=positions)

            session.flush()
            session.refresh(row)
            session.expunge(row)
            return row

    def update_doc_sync(
        self,
        *,
        snapshot_id: int,
        doc_url: Optional[str],
        doc_title: Optional[str],
        doc_sync_status: str,
        doc_sync_error: Optional[str],
        doc_exported_at: Optional[datetime],
    ) -> Optional[ExternalHoldingSnapshot]:
        with self.db.session_scope() as session:
            row = session.execute(
                select(ExternalHoldingSnapshot)
                .where(ExternalHoldingSnapshot.id == snapshot_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            row.doc_url = doc_url
            row.doc_title = doc_title
            row.doc_sync_status = doc_sync_status
            row.doc_sync_error = doc_sync_error
            row.doc_exported_at = doc_exported_at
            row.updated_at = datetime.now()
            session.flush()
            session.refresh(row)
            session.expunge(row)
            return row

    def get_latest_snapshot(
        self,
        *,
        source_platform: Optional[str] = None,
        status: Optional[str] = "confirmed",
    ) -> Optional[ExternalHoldingSnapshot]:
        with self.db.get_session() as session:
            query = select(ExternalHoldingSnapshot)
            if source_platform:
                query = query.where(ExternalHoldingSnapshot.source_platform == source_platform)
            if status:
                query = query.where(ExternalHoldingSnapshot.status == status)
            row = session.execute(
                query.order_by(
                    desc(ExternalHoldingSnapshot.snapshot_date),
                    desc(ExternalHoldingSnapshot.uploaded_at),
                    desc(ExternalHoldingSnapshot.id),
                ).limit(1)
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    @staticmethod
    def _add_positions(
        *,
        session: Any,
        snapshot_id: int,
        positions: List[Dict[str, Any]],
    ) -> None:
        for item in positions:
            session.add(
                ExternalHoldingPosition(
                    snapshot_id=snapshot_id,
                    asset_type=item.get("asset_type") or "stock",
                    source_platform=item.get("source_platform") or "",
                    symbol=item.get("symbol"),
                    display_name=item.get("display_name"),
                    market=item.get("market") or "cn",
                    quantity=item.get("quantity"),
                    market_value=item.get("market_value"),
                    cost_basis_total=item.get("cost_basis_total"),
                    profit_amount=item.get("profit_amount"),
                    profit_pct=item.get("profit_pct"),
                    position_weight=item.get("position_weight"),
                    price=item.get("price"),
                    price_date=item.get("price_date"),
                    confidence=item.get("confidence") or "medium",
                    is_manually_edited=bool(item.get("is_manually_edited", False)),
                    raw_payload=item.get("raw_payload"),
                )
            )
