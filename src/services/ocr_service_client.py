# -*- coding: utf-8 -*-
"""Asset screenshot parser service client used by screenshot-driven workflows."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_config

logger = logging.getLogger(__name__)
_OCR_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class OCRServiceClient:
    """Call the standalone asset screenshot parser service."""

    def __init__(self) -> None:
        cfg = get_config()
        self.enabled = bool(
            getattr(cfg, "asset_screenshot_parser_service_enabled", False)
            or getattr(cfg, "ocr_service_enabled", False)
        )
        self.base_url = (
            getattr(cfg, "asset_screenshot_parser_service_base_url", None)
            or getattr(cfg, "ocr_service_base_url", None)
            or ""
        ).rstrip("/")
        self.api_key = (
            getattr(cfg, "asset_screenshot_parser_service_api_key", None)
            or getattr(cfg, "ocr_service_api_key", None)
        )
        self.timeout_seconds = float(
            getattr(cfg, "asset_screenshot_parser_service_timeout_seconds", None)
            or getattr(cfg, "ocr_service_timeout_seconds", 20.0)
            or 20.0
        )

    def is_configured(self) -> bool:
        return self.enabled and bool(self.base_url)

    def parse_holdings_screenshot(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source_platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise ValueError("Asset screenshot parser service is disabled")
        if not self.base_url:
            raise ValueError("Asset screenshot parser service base URL is not configured")

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        files = {
            "file": ("upload", image_bytes, mime_type),
        }
        data = {
            "source_platform": source_platform or "",
        }
        url = f"{self.base_url}/api/v1/screenshots/parse"
        try:
            response = _post_with_retry(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise ValueError(f"Asset screenshot parser service timeout after {self.timeout_seconds:.1f}s") from exc
        except requests.exceptions.RequestException as exc:
            raise ValueError(f"Asset screenshot parser service request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(
                f"Asset screenshot parser service returned non-JSON response (status={response.status_code})"
            ) from exc

        if response.status_code >= 400:
            message = _extract_error_message(payload) or f"HTTP {response.status_code}"
            raise ValueError(f"Asset screenshot parser service error: {message}")

        snapshot_candidate = payload.get("snapshot_candidate")
        if not isinstance(snapshot_candidate, dict):
            raise ValueError("Asset screenshot parser service response missing snapshot_candidate")
        positions = snapshot_candidate.get("positions")
        if not isinstance(positions, list):
            raise ValueError("Asset screenshot parser service response missing snapshot_candidate.positions[]")

        return payload


def _extract_error_message(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                inner = _extract_error_message(value)
                if inner:
                    return inner
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type(_OCR_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _post_with_retry(
    url: str,
    *,
    headers: Dict[str, str],
    files: Dict[str, Any],
    data: Dict[str, Any],
    timeout: float,
) -> requests.Response:
    return requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        timeout=timeout,
    )
