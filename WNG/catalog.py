from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
CATALOG_SNAPSHOT = DATA_DIR / "catalog_snapshot.json"


def humanize_tool_id(tool_id: str) -> str:
    text = re.sub(r"[_\-]+", " ", str(tool_id or "").strip())
    return " ".join(part.capitalize() for part in text.split()) or "Tool"


@lru_cache(maxsize=1)
def load_catalog_snapshot() -> list[dict[str, Any]]:
    if not CATALOG_SNAPSHOT.exists():
        return []
    with CATALOG_SNAPSHOT.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    catalog = payload.get("tools", payload)
    if not isinstance(catalog, list):
        return []
    return [item for item in catalog if isinstance(item, dict)]


def _normalize_runtime_item(item: dict[str, Any]) -> dict[str, Any]:
    fixed = dict(item)
    tool_id = str(fixed.get("id", "")).strip()
    fixed.setdefault("display_name", humanize_tool_id(tool_id))
    fixed.setdefault("summary", "")
    fixed.setdefault("category", "General")
    tier = str(fixed.get("license_tier_name") or fixed.get("license_tier") or "open")
    fixed["license_tier"] = tier.lower()
    fixed["locked"] = bool(
        fixed.get("locked", False) or not fixed.get("available", True)
    )
    fixed.setdefault("params", [])
    fixed.setdefault("defaults", {})
    return fixed


def _merge_snapshot_hints(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot = {str(item.get("id", "")): item for item in load_catalog_snapshot()}
    out: list[dict[str, Any]] = []
    for item in catalog:
        tool_id = str(item.get("id", ""))
        snap = snapshot.get(tool_id)
        if not snap:
            out.append(item)
            continue

        fixed = dict(item)
        fixed.setdefault("taxonomy_category", snap.get("taxonomy_category"))
        fixed.setdefault("taxonomy_subcategory", snap.get("taxonomy_subcategory"))
        if not fixed.get("category"):
            fixed["category"] = snap.get("category", "General")

        snap_params = {
            str(p.get("name", "")): p
            for p in snap.get("params", [])
            if isinstance(p, dict)
        }
        merged_params = []
        for param in fixed.get("params", []):
            if not isinstance(param, dict):
                continue
            merged = dict(param)
            hint = snap_params.get(str(merged.get("name", "")))
            if hint:
                for key in ("kind", "type", "options", "default"):
                    if key not in merged or merged.get(key) in (None, "", []):
                        merged[key] = hint.get(key)
            merged_params.append(merged)
        if not merged_params:
            merged_params = list(snap.get("params", []))
        fixed["params"] = merged_params
        out.append(fixed)
    return out


def discover_catalog(
    include_pro: bool = True, tier: str = "open"
) -> list[dict[str, Any]]:
    """Return the live runtime catalog when available, otherwise the snapshot."""
    try:
        from .runtime import create_runtime_session

        session = create_runtime_session(include_pro=include_pro, tier=tier)
        raw = session.list_tool_catalog_json()
        catalog = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(catalog, list) and catalog:
            normalized = [
                _normalize_runtime_item(item)
                for item in catalog
                if isinstance(item, dict)
            ]
            return _merge_snapshot_hints(normalized)
    except Exception:
        pass

    return [_normalize_runtime_item(item) for item in load_catalog_snapshot()]


def default_catalog() -> list[dict[str, Any]]:
    include_pro = os.environ.get("WBW_ARCGIS_INCLUDE_PRO", "true").strip().lower()
    tier = os.environ.get("WBW_ARCGIS_TIER", "open").strip() or "open"
    return discover_catalog(
        include_pro=include_pro not in {"0", "false", "no"}, tier=tier
    )
