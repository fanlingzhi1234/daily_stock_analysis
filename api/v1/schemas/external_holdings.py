# -*- coding: utf-8 -*-
"""Schemas for screenshot-based external holdings snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


SourcePlatform = Literal["ths_stock", "alipay_fund"]
AssetType = Literal["stock", "etf", "fund"]
HoldingMarket = Literal["cn", "hk", "us", "fund"]
HoldingConfidence = Literal["high", "medium", "low"]
SnapshotStatus = Literal["draft", "confirmed", "archived"]


class ExternalHoldingPositionInput(BaseModel):
    asset_type: AssetType = "stock"
    source_platform: SourcePlatform
    symbol: Optional[str] = Field(None, max_length=32)
    display_name: Optional[str] = Field(None, max_length=128)
    market: HoldingMarket = "cn"
    quantity: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis_total: Optional[float] = None
    profit_amount: Optional[float] = None
    profit_pct: Optional[float] = None
    position_weight: Optional[float] = None
    price: Optional[float] = None
    price_date: Optional[date] = None
    confidence: HoldingConfidence = "medium"
    is_manually_edited: bool = False
    raw_payload: Optional[str] = None


class ExternalHoldingPositionItem(ExternalHoldingPositionInput):
    id: int
    price_date: Optional[str] = None


class ExternalHoldingSnapshotItem(BaseModel):
    id: int
    source_platform: SourcePlatform
    snapshot_date: str
    captured_at: Optional[str] = None
    uploaded_at: Optional[str] = None
    status: SnapshotStatus
    total_market_value: Optional[float] = None
    total_profit: Optional[float] = None
    currency: str
    raw_image_path: Optional[str] = None
    ocr_raw_text: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    review_notes: Optional[str] = None
    doc_url: Optional[str] = None
    doc_title: Optional[str] = None
    doc_sync_status: Optional[str] = None
    doc_sync_error: Optional[str] = None
    doc_exported_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    positions: List[ExternalHoldingPositionItem] = Field(default_factory=list)


class ExternalHoldingExtractResponse(BaseModel):
    snapshot: ExternalHoldingSnapshotItem


class ExternalHoldingConfirmRequest(BaseModel):
    items: List[ExternalHoldingPositionInput] = Field(default_factory=list)
    review_notes: Optional[str] = None
    sync_doc: bool = True


class ExternalHoldingDocSyncResponse(BaseModel):
    snapshot_id: int
    doc_url: Optional[str] = None
    doc_sync_status: str
    doc_sync_error: Optional[str] = None


class ExternalHoldingStatusResponse(BaseModel):
    enabled: bool
    reminder_enabled: bool
    doc_sync_enabled: bool
    reminder_channels: List[str] = Field(default_factory=list)
    supported_source_platforms: List[SourcePlatform] = Field(default_factory=list)
    mobile_upload_hint: Optional[str] = None
