# -*- coding: utf-8 -*-
"""Endpoints for screenshot-based external holdings snapshots."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.external_holdings import (
    ExternalHoldingConfirmRequest,
    ExternalHoldingDocSyncResponse,
    ExternalHoldingExtractResponse,
    ExternalHoldingSnapshotItem,
    ExternalHoldingStatusResponse,
)
from src.config import get_config
from src.services.external_holdings_service import ExternalHoldingsService
from src.services.image_stock_extractor import ALLOWED_MIME, MAX_SIZE_BYTES

logger = logging.getLogger(__name__)

router = APIRouter()


def _is_external_holdings_enabled() -> bool:
    return bool(getattr(get_config(), "external_holdings_enabled", False))


def _ensure_external_holdings_enabled() -> None:
    if _is_external_holdings_enabled():
        return
    raise HTTPException(
        status_code=404,
        detail={
            "error": "feature_disabled",
            "message": "External holdings screenshot snapshots are not enabled",
        },
    )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": "validation_error", "message": str(exc)},
    )


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error("%s: %s", message, exc, exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": f"{message}: {str(exc)}"},
    )


@router.get(
    "/status",
    response_model=ExternalHoldingStatusResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get external holdings screenshot feature status",
)
def get_external_holdings_status() -> ExternalHoldingStatusResponse:
    config = get_config()
    return ExternalHoldingStatusResponse(
        enabled=_is_external_holdings_enabled(),
        reminder_enabled=bool(getattr(config, "holding_screenshot_reminder_enabled", False)),
        doc_sync_enabled=bool(getattr(config, "holding_screenshot_doc_sync_enabled", True)),
        reminder_channels=list(getattr(config, "holding_screenshot_reminder_channels", []) or []),
        supported_source_platforms=["ths_stock", "alipay_fund"],
        mobile_upload_hint="Recommended for mobile screenshots from Tonghuashun holdings and Alipay fund holdings.",
    )


@router.post(
    "/extract-from-image",
    response_model=ExternalHoldingExtractResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Extract holdings snapshot from one screenshot",
)
def extract_external_holdings_from_image(
    file: Optional[UploadFile] = File(None, description="Screenshot file"),
    source_platform: str = Form(..., description="ths_stock or alipay_fund"),
) -> ExternalHoldingExtractResponse:
    _ensure_external_holdings_enabled()
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file 上传截图"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"不支持的类型: {content_type}",
            },
        )

    try:
        data = file.file.read(MAX_SIZE_BYTES)
        if file.file.read(1):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"图片超过 {MAX_SIZE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
        payload = ExternalHoldingsService().create_draft_from_image(
            image_bytes=data,
            mime_type=content_type,
            source_platform=source_platform,
        )
        return ExternalHoldingExtractResponse(snapshot=ExternalHoldingSnapshotItem(**payload))
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Extract external holdings failed", exc)


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=ExternalHoldingSnapshotItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get one external holdings snapshot",
)
def get_external_holdings_snapshot(snapshot_id: int) -> ExternalHoldingSnapshotItem:
    try:
        _ensure_external_holdings_enabled()
        payload = ExternalHoldingsService().get_snapshot(snapshot_id)
        return ExternalHoldingSnapshotItem(**payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get external holdings snapshot failed", exc)


@router.post(
    "/snapshots/{snapshot_id}/confirm",
    response_model=ExternalHoldingSnapshotItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Confirm one extracted holdings snapshot",
)
def confirm_external_holdings_snapshot(
    snapshot_id: int,
    request: ExternalHoldingConfirmRequest,
) -> ExternalHoldingSnapshotItem:
    try:
        _ensure_external_holdings_enabled()
        payload = ExternalHoldingsService().confirm_snapshot(
            snapshot_id=snapshot_id,
            items=[item.model_dump() for item in request.items],
            review_notes=request.review_notes,
            sync_doc=request.sync_doc,
        )
        return ExternalHoldingSnapshotItem(**payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Confirm external holdings snapshot failed", exc)


@router.post(
    "/snapshots/{snapshot_id}/doc-sync",
    response_model=ExternalHoldingDocSyncResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Sync one snapshot to Feishu cloud doc",
)
def sync_external_holdings_doc(snapshot_id: int) -> ExternalHoldingDocSyncResponse:
    try:
        _ensure_external_holdings_enabled()
        result = ExternalHoldingsService().sync_snapshot_doc(snapshot_id)
        snapshot = result.get("snapshot")
        snapshot_id_value = int(snapshot.id) if snapshot is not None else snapshot_id
        return ExternalHoldingDocSyncResponse(
            snapshot_id=snapshot_id_value,
            doc_url=result.get("doc_url"),
            doc_sync_status=result.get("doc_sync_status") or "unknown",
            doc_sync_error=getattr(snapshot, "doc_sync_error", None) if snapshot is not None else None,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Sync external holdings doc failed", exc)


@router.get(
    "/latest",
    response_model=ExternalHoldingSnapshotItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get latest confirmed external holdings snapshot",
)
def get_latest_external_holdings_snapshot(
    source_platform: Optional[str] = Query(None, description="ths_stock or alipay_fund"),
) -> ExternalHoldingSnapshotItem:
    try:
        _ensure_external_holdings_enabled()
        payload = ExternalHoldingsService().get_latest_snapshot(source_platform=source_platform)
        return ExternalHoldingSnapshotItem(**payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get latest external holdings snapshot failed", exc)
