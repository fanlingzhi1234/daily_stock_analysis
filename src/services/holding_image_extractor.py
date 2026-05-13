# -*- coding: utf-8 -*-
"""Extractor for screenshot holdings snapshots through the parser service."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.data.stock_index_loader import get_index_code_by_name
from src.services import image_stock_extractor as base_extractor
from src.services.name_to_code_resolver import resolve_name_to_code
from src.services.ocr_service_client import OCRServiceClient
from src.services.stock_code_utils import normalize_code

SUPPORTED_SOURCE_PLATFORMS = frozenset({"ths_stock", "alipay_fund"})
VALID_ASSET_TYPES = frozenset({"stock", "etf", "fund"})
VALID_MARKETS = frozenset({"cn", "hk", "us", "fund"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


def extract_holdings_from_image(
    image_bytes: bytes,
    mime_type: str,
    *,
    source_platform: str,
) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    """Extract structured holdings rows from one screenshot."""
    platform = (source_platform or "").strip().lower()
    if platform not in SUPPORTED_SOURCE_PLATFORMS:
        raise ValueError(f"unsupported source_platform: {source_platform}")

    mime_type = (mime_type or "image/jpeg").split(";")[0].strip().lower()
    if mime_type not in base_extractor.ALLOWED_MIME:
        raise ValueError(f"不支持的图片类型: {mime_type}")
    if not image_bytes:
        raise ValueError("图片内容为空")
    if len(image_bytes) > base_extractor.MAX_SIZE_BYTES:
        raise ValueError(
            f"Image too large (max {base_extractor.MAX_SIZE_BYTES // (1024 * 1024)}MB)"
        )

    base_extractor._verify_image_magic_bytes(image_bytes, mime_type)
    parser_client = OCRServiceClient()
    if not parser_client.is_configured():
        raise ValueError("未配置资产截图解析服务，请设置 ASSET_PARSER_BASE_URL")

    payload = parser_client.parse_holdings_screenshot(
        image_bytes=image_bytes,
        mime_type=mime_type,
        source_platform=platform,
    )
    candidate = payload.get("snapshot_candidate") or {}
    items = candidate.get("positions")
    if not isinstance(items, list):
        raise ValueError("资产截图解析服务响应缺少 positions")
    warnings: List[str] = []
    for source in (payload.get("warnings"), candidate.get("warnings")):
        if isinstance(source, list):
            warnings.extend(str(item) for item in source if item)
    raw = json.dumps(payload, ensure_ascii=False)
    return _normalize_items(items, source_platform=platform, extra_warnings=warnings), raw, warnings


def _parse_items(*, raw_text: str, source_platform: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    cleaned = raw_text.strip()
    for start in ("```json", "```"):
        if cleaned.startswith(start):
            cleaned = cleaned[len(start):].strip()
            break
    end_idx = cleaned.rfind("```")
    if end_idx >= 0:
        cleaned = cleaned[:end_idx].strip()

    parsed_data: Any = None
    try:
        parsed_data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json

            parsed_data = repair_json(cleaned, return_objects=True)
        except Exception as exc:
            raise ValueError(f"持仓截图结果不是有效 JSON: {exc}") from exc

    if not isinstance(parsed_data, list):
        raise ValueError("持仓截图识别结果必须为 JSON 数组")

    return _normalize_items(parsed_data, source_platform=source_platform, extra_warnings=warnings), warnings


def _normalize_items(
    parsed_items: List[Any],
    *,
    source_platform: str,
    extra_warnings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    warnings = extra_warnings if extra_warnings is not None else []
    items: List[Dict[str, Any]] = []
    for idx, raw_item in enumerate(parsed_items):
        if not isinstance(raw_item, dict):
            warnings.append(f"row={idx + 1}: 非对象条目已跳过")
            continue
        item = _normalize_item(
            raw_item=raw_item,
            source_platform=source_platform,
            warnings=warnings,
            row_index=idx + 1,
        )
        if item is not None:
            items.append(item)
    return items


def _normalize_item(
    *,
    raw_item: Dict[str, Any],
    source_platform: str,
    warnings: List[str],
    row_index: int,
) -> Optional[Dict[str, Any]]:
    display_name = _clean_text(raw_item.get("display_name") or raw_item.get("name"))
    symbol_raw = _clean_text(raw_item.get("symbol") or raw_item.get("code"))
    symbol = normalize_code(symbol_raw) if symbol_raw else None

    asset_type = _clean_text(raw_item.get("asset_type")) or _infer_asset_type(
        display_name=display_name,
        source_platform=source_platform,
    )
    asset_type = asset_type.lower()
    if asset_type not in VALID_ASSET_TYPES:
        asset_type = _infer_asset_type(
            display_name=display_name,
            source_platform=source_platform,
        )

    if not symbol and display_name:
        symbol = _resolve_symbol_for_holding(
            display_name=display_name,
            asset_type=asset_type,
            warnings=warnings,
            row_index=row_index,
        )

    market = _clean_text(raw_item.get("market")) or ("fund" if asset_type == "fund" else _infer_market(symbol))
    market = market.lower()
    if market not in VALID_MARKETS:
        market = "fund" if asset_type == "fund" else _infer_market(symbol)

    quantity = _parse_number(raw_item.get("quantity"))
    market_value = _parse_number(raw_item.get("market_value"))
    cost_basis_total = _parse_number(raw_item.get("cost_basis_total"))
    cost_price = _parse_number(raw_item.get("cost_price"))
    profit_amount = _parse_number(raw_item.get("profit_amount"))
    profit_pct = _parse_number(raw_item.get("profit_pct"), percent=True)
    price = _parse_number(raw_item.get("price"))
    confidence = (_clean_text(raw_item.get("confidence")) or "medium").lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = "medium"

    if cost_basis_total is None and quantity is not None and cost_price is not None:
        cost_basis_total = round(quantity * cost_price, 4)
    if cost_basis_total is None and market_value is not None and profit_amount is not None:
        cost_basis_total = round(market_value - profit_amount, 4)

    if not display_name and not symbol:
        warnings.append(f"row={row_index}: 名称和代码都缺失，已跳过")
        return None

    return {
        "asset_type": asset_type,
        "source_platform": source_platform,
        "symbol": symbol or symbol_raw or None,
        "display_name": display_name or symbol or symbol_raw,
        "market": market,
        "quantity": quantity,
        "market_value": market_value,
        "cost_basis_total": cost_basis_total,
        "profit_amount": profit_amount,
        "profit_pct": profit_pct,
        "position_weight": None,
        "price": price,
        "price_date": None,
        "confidence": confidence,
        "is_manually_edited": False,
        "raw_payload": json.dumps(raw_item, ensure_ascii=False),
    }


def _infer_asset_type(*, display_name: Optional[str], source_platform: str) -> str:
    if source_platform == "alipay_fund":
        return "fund"
    if _looks_like_etf_or_index_name(display_name):
        return "etf"
    return "stock"


def _resolve_symbol_for_holding(
    *,
    display_name: str,
    asset_type: str,
    warnings: List[str],
    row_index: int,
) -> Optional[str]:
    if asset_type == "fund":
        return None

    if asset_type == "etf":
        symbol = get_index_code_by_name(display_name)
        if symbol:
            warnings.append(f"row={row_index}: 代码缺失，已根据指数/ETF名称解析为 {symbol}")
            return symbol
        warnings.append(f"row={row_index}: 指数/ETF代码缺失，未执行普通股票模糊解析，请人工确认")
        return None

    symbol = get_index_code_by_name(display_name) or resolve_name_to_code(display_name)
    if symbol:
        warnings.append(f"row={row_index}: 代码缺失，已根据名称解析为 {symbol}")
    return symbol


def _looks_like_etf_or_index_name(name: Optional[str]) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    return any(keyword in text for keyword in ("ETF", "LOF", "指数", "恒指", "纳指"))


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_number(value: Any, *, percent: bool = False) -> Optional[float]:
    text = _clean_text(value)
    if text is None:
        return None
    normalized = text.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
    normalized = normalized.replace("元", "").replace("%", "").strip()
    if not normalized:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    number = float(match.group(0))
    return number if percent else number


def _infer_market(symbol: Optional[str]) -> str:
    if not symbol:
        return "cn"
    if symbol.isdigit():
        if len(symbol) == 5:
            return "hk"
        return "cn"
    return "us"
