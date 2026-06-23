#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "WNG" / "data" / "catalog_snapshot.json"


def _resolve_next_gen(arg: str | None) -> Path:
    """Locate the whitebox_next_gen checkout from CLI arg, env, or sibling dir.

    Resolution order:
        1. ``--next-gen`` CLI argument
        2. ``WBW_NEXT_GEN`` environment variable
        3. ``../whitebox_next_gen`` next to this repository

    Args:
        arg: Optional path provided on the command line.

    Returns:
        Absolute :class:`Path` to the Next Gen checkout.

    Raises:
        SystemExit: If no candidate path exists on disk.
    """

    candidates: list[Path] = []
    if arg:
        candidates.append(Path(arg).expanduser())
    env = os.environ.get("WBW_NEXT_GEN")
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(ROOT.parent / "whitebox_next_gen")

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    tried = "\n  ".join(str(c) for c in candidates)
    raise SystemExit(
        "Could not locate the whitebox_next_gen checkout. Tried:\n  "
        + tried
        + "\nPass --next-gen <path> or set WBW_NEXT_GEN."
    )


CATEGORY_DISPLAY = {
    "remote_sensing": "Remote Sensing",
    "terrain": "Terrain",
    "hydrology": "Hydrology",
    "streams": "Hydrology - Streams",
    "lidar": "LiDAR",
    "vector": "Vector",
    "raster": "Raster",
    "conversion": "Conversion",
    "projection_georeferencing": "Projection and Georeferencing",
}

SUBCATEGORY_DISPLAY = {
    "obia": "OBIA",
    "classification": "Classification",
    "change_detection": "Change Detection",
    "radiometric_correction": "Radiometric Correction",
    "thermal_emissivity": "Thermal & Emissivity",
    "edge_feature_detection": "Edge & Feature Detection",
    "enhancement_contrast": "Enhancement & Contrast",
    "filters": "Filters",
    "sar": "SAR",
    "spectral": "Spectral",
    "spectral_analytics": "Spectral Analytics",
    "workflow_products": "Workflow Products",
    "derivatives": "Derivatives",
    "landform_indices": "Landform Indices",
    "roughness_texture": "Roughness & Texture",
    "visibility": "Visibility",
    "local_neighborhood": "Local Neighborhood",
    "flow_routing": "Flow Routing",
    "depressions_storage": "Depressions & Storage",
    "watersheds_basins": "Watersheds & Basins",
    "hydrologic_indices": "Hydrologic Indices",
    "network_extraction": "Network Extraction",
    "ordering_metrics": "Ordering Metrics",
    "longitudinal_analysis": "Longitudinal Analysis",
    "analysis_metrics": "Analysis Metrics",
    "filtering_classification": "Filtering & Classification",
    "sampling_gridding": "Sampling & Gridding",
    "interpolation_gridding": "Interpolation & Gridding",
    "geometry_processing": "Geometry Processing",
    "geometry_topology": "Geometry & Topology",
    "attribute_analysis": "Attribute Analysis",
    "overlay_analysis": "Overlay Analysis",
    "distance_cost": "Distance & Cost",
    "shape_metrics": "Shape Metrics",
    "network_analysis": "Network Analysis",
    "linear_referencing": "Linear Referencing",
    "vector_table_io": "Vector & Table I/O",
    "overlay_math": "Overlay Math",
    "reclass_mask": "Reclassify & Mask",
    "raster_vector_conversion": "Raster/Vector Conversion",
    "io_management": "I/O & Management",
    "general": "General",
}


def humanize(text: str) -> str:
    return " ".join(part.capitalize() for part in re.sub(r"[_\-]+", " ", text).split())


def display_group(category: str, subcategory: str) -> str:
    cat = CATEGORY_DISPLAY.get(category, humanize(category))
    if not subcategory or subcategory == "general":
        return cat
    return f"{cat} - {SUBCATEGORY_DISPLAY.get(subcategory, humanize(subcategory))}"


def split_args(args_text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    for ch in args_text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
            continue
        if ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_default(text: str) -> Any:
    raw = text.strip()
    if raw in {"None", "null"}:
        return None
    if raw in {"True", "False"}:
        return raw == "True"
    try:
        return ast.literal_eval(raw)
    except Exception:
        return None


def infer_kind(
    name: str,
    type_text: str,
    return_type: str,
    default: Any,
    options: list[str],
    tool_id: str,
) -> str:
    if options:
        return "enum"
    n = name.lower()
    t = type_text.lower()
    r = return_type.lower()
    tid = tool_id.lower()
    if is_output_path_parameter(n, t):
        text = n + " " + t + " " + r
        if any(tok in text for tok in ("html", "report", "csv", "json", "txt", "xml")):
            return "file_out"
        has_raster = "raster" in r
        has_vector = "vector" in r
        has_lidar = "lidar" in r
        if has_vector and not has_raster and not has_lidar:
            return "vector_out"
        if has_lidar and not has_raster and not has_vector:
            return "lidar_out"
        if has_raster:
            if has_vector and any(
                tok in text for tok in ("vector", "feature", "polygon", "line", "point")
            ):
                return "vector_out"
            if has_lidar and any(tok in text for tok in ("lidar", "las", "laz")):
                return "lidar_out"
            return "raster_out"
        if any(tok in text for tok in ("vector", "feature", "shp", "polygon")):
            return "vector_out"
        if any(tok in text for tok in ("lidar", "las", "laz")):
            return "lidar_out"
        if any(tok in text for tok in ("raster", "dem", "grid", "tif")):
            return "raster_out"
        return "file_out"
    if n in {"epsg", "dst_epsg", "src_epsg", "cols", "rows"}:
        return "int"
    if isinstance(default, bool) or "bool" in t:
        return "bool"
    if "int" in t:
        return "int"
    if any(tok in t for tok in ("float", "double", "number")):
        return "double"
    if n == "input" and "raster" in tid:
        return "raster_in"
    if n == "input" and "vector" in tid:
        return "vector_in"
    if n == "input" and "lidar" in tid:
        return "lidar_in"
    if "raster" in t or n in {"dem", "raster", "input_raster", "grid"}:
        return "raster_in"
    if "vector" in t or n in {
        "vector",
        "input_vector",
        "points",
        "polygons",
        "lines",
        "network",
        "origins",
        "destinations",
    }:
        return "vector_in"
    if "lidar" in t or "las" in n or "lidar" in n:
        return "lidar_in"
    if any(
        tok in n
        for tok in (
            "file",
            "path",
            "csv",
            "json",
            "html",
            "txt",
            "xml",
            "directory",
            "folder",
        )
    ):
        return "file_in"
    return "string"


def enum_options(name: str, default: Any) -> list[str]:
    if name == "units":
        return ["degrees", "radians", "percent"]
    if name == "resample":
        return [
            "nearest",
            "bilinear",
            "cubic",
            "lanczos",
            "average",
            "min",
            "max",
            "mode",
            "median",
        ]
    if isinstance(default, str) and default in {"degrees", "radians", "percent"}:
        return ["degrees", "radians", "percent"]
    return []


OUTPUT_CONTROL_SUFFIXES = ("_format", "_mode", "_type", "_units")


def is_output_path_parameter(name: str, type_text: str) -> bool:
    """Return whether a parameter represents an output dataset path.

    Args:
        name: Parameter name.
        type_text: Parameter type annotation text.

    Returns:
        True when the parameter should be tagged as an output path.
    """
    n = name.lower()
    t = type_text.lower()
    if n in {"output", "out", "output_path", "out_path"}:
        return True
    if n == "destination":
        return "str" in t or "path" in t
    if n.endswith(("_path", "_file", "_directory", "_dir")):
        return "str" in t or "path" in t
    if n.startswith(("output_", "out_")):
        if n.endswith(OUTPUT_CONTROL_SUFFIXES):
            return False
        if any(tok in t for tok in ("bool", "int", "float", "double", "literal")):
            return False
        return "str" in t or "path" in t
    return False


def _runtime_param_kind(io_role: str, data_kind: str, schema: dict[str, Any]) -> str:
    """Map a runtime catalog param (io_role/data_kind/schema) to the snapshot ``kind``."""
    dk = (data_kind or "").lower()
    io = (io_role or "").lower()
    skind = str(schema.get("kind", "")).lower()
    if dk in {"raster", "vector", "lidar"}:
        return f"{dk}_{'out' if io == 'output' else 'in'}"
    if skind == "scalar":
        scalar = str(schema.get("scalar", "")).lower()
        return "int" if scalar in {"integer", "int"} else "double"
    if skind == "bool" or dk == "bool":
        return "bool"
    if skind == "enum":
        return "enum"
    if io == "output":
        return "file_out"
    if dk in {"file", "json", "text", "table"}:
        return "file_in"
    return "string"


def _convert_runtime_param(p: dict[str, Any]) -> dict[str, Any]:
    """Convert one runtime catalog param to the snapshot param shape."""
    schema = p.get("schema") or {}
    options = [
        str(o.get("value"))
        for o in (schema.get("options") or [])
        if isinstance(o, dict) and o.get("value") is not None
    ]
    name = p.get("name", "")
    return {
        "name": "output" if name == "output_path" else name,
        "description": p.get("description") or humanize(name),
        "type": str(
            p.get("data_kind") or schema.get("scalar") or schema.get("kind") or "Any"
        ),
        "required": bool(p.get("required", False)),
        "default": schema.get("default"),
        "options": options,
        "kind": _runtime_param_kind(
            p.get("io_role", ""), p.get("data_kind", ""), schema
        ),
    }


def load_runtime_params() -> dict[str, list[dict[str, Any]]]:
    """Param schemas from the installed ``whitebox_workflows`` runtime catalog.

    The ``.pyi`` stub only carries ``*args, **kwargs`` for some tools, so their
    stub-derived params come out empty. The runtime catalog
    (``list_tool_catalog_json``) has the real schema, which we convert to the
    snapshot param shape and key by tool id. Returns an empty mapping if the
    package is unavailable, so the script still runs from the stub alone.

    Returns:
        Mapping of tool id to its converted parameter list.
    """

    try:
        import whitebox_workflows as wbw

        catalog = json.loads(wbw.list_tool_catalog_json())
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"  (runtime param backfill unavailable: {exc})")
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    for tool in catalog:
        tool_id = tool.get("id")
        if not tool_id:
            continue
        params = [
            _convert_runtime_param(p)
            for p in tool.get("params", [])
            if not str(p.get("name", "")).startswith("*")
        ]
        if params:
            out[str(tool_id)] = params
    return out


def signatures(stub_text: str) -> dict[str, dict[str, Any]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for m in re.finditer(
        r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*->\s*([^:]+):",
        stub_text,
        flags=re.DOTALL,
    ):
        name, args_text, ret = m.group(1), m.group(2), m.group(3).strip()
        raw_parts = split_args(args_text)
        params = []
        for part in raw_parts:
            if part in {"self", "*", "/"}:
                continue
            default = None
            required = True
            if "=" in part:
                left, right = [x.strip() for x in part.split("=", 1)]
                default = parse_default(right)
                required = False
            else:
                left = part
            if ":" in left:
                pname, ptype = [x.strip() for x in left.split(":", 1)]
            else:
                pname, ptype = left.strip(), "Any"
            if (
                pname in {"self", "env", "callback", "kwargs", "args"}
                or pname.startswith("*")
                or not pname
            ):
                continue
            options = enum_options(pname, default)
            kind = infer_kind(pname, ptype, ret, default, options, name)
            if kind.endswith("_out"):
                required = True
            params.append(
                {
                    "name": "output" if pname == "output_path" else pname,
                    "description": humanize(
                        "output" if pname == "output_path" else pname
                    ),
                    "type": ptype,
                    "required": required,
                    "default": default,
                    "options": options,
                    "kind": kind,
                }
            )
        score = (
            sum(3 for p in params if p["kind"].endswith("_out"))
            + sum(1 for p in params if p["kind"].endswith("_in"))
            + len(params)
        )
        found.setdefault(name, []).append(
            {"params": params, "return_type": ret, "score": score}
        )
    return {
        name: sorted(candidates, key=lambda c: c["score"], reverse=True)[0]
        for name, candidates in found.items()
    }


def main() -> None:
    """Generate the catalog snapshot JSON from a local Next Gen checkout."""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "--next-gen",
        help="Path to the whitebox_next_gen checkout (overrides WBW_NEXT_GEN).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output JSON path (default: {DEFAULT_OUT}).",
    )
    args = parser.parse_args()

    next_gen = _resolve_next_gen(args.next_gen)
    wbw_python = next_gen / "crates" / "wbw_python"
    stub = wbw_python / "whitebox_workflows" / "whitebox_workflows.pyi"
    taxonomy_path = wbw_python / "tool_taxonomy.resolved.json"
    out_path = args.out

    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    sigs = signatures(stub.read_text(encoding="utf-8"))
    runtime_params = load_runtime_params()

    index: dict[str, tuple[str, str]] = {}
    ordered_tools: list[str] = []
    for entry in taxonomy.get("mapping", []):
        cat = str(entry.get("category", ""))
        sub = str(entry.get("subcategory", ""))
        for tool_id in entry.get("tools", []):
            tid = str(tool_id)
            if tid not in index:
                ordered_tools.append(tid)
            index[tid] = (cat, sub)

    tool_meta = taxonomy.get("tools", {})
    tools: list[dict[str, Any]] = []
    for tool_id in ordered_tools:
        cat, sub = index[tool_id]
        sig = sigs.get(tool_id, {"params": [], "return_type": "Any"})
        params = list(sig["params"])
        # The .pyi stub exposes only *args/**kwargs for some tools, leaving their
        # params empty. Backfill those from the runtime catalog, which carries the
        # real schema.
        if not params and tool_id in runtime_params:
            params = [dict(p) for p in runtime_params[tool_id]]
        ret = str(sig.get("return_type", "Any"))
        if not any(str(p.get("kind", "")).endswith("_out") for p in params):
            if "Raster" in ret:
                params.append(
                    {
                        "name": "output",
                        "description": "Output raster",
                        "type": "str",
                        "required": True,
                        "default": None,
                        "options": [],
                        "kind": "raster_out",
                    }
                )
            elif "Vector" in ret:
                params.append(
                    {
                        "name": "output",
                        "description": "Output vector",
                        "type": "str",
                        "required": True,
                        "default": None,
                        "options": [],
                        "kind": "vector_out",
                    }
                )
            elif "Lidar" in ret:
                params.append(
                    {
                        "name": "output",
                        "description": "Output LiDAR",
                        "type": "str",
                        "required": True,
                        "default": None,
                        "options": [],
                        "kind": "lidar_out",
                    }
                )
        tier = str(tool_meta.get(tool_id, {}).get("license_tier", "open")).lower()
        tools.append(
            {
                "id": tool_id,
                "display_name": humanize(tool_id),
                "summary": "",
                "category": display_group(cat, sub),
                "taxonomy_category": cat,
                "taxonomy_subcategory": sub,
                "license_tier": tier,
                "locked": tier not in {"open", "oss"},
                "locked_reason": (
                    "Pro license required" if tier not in {"open", "oss"} else None
                ),
                "params": params,
                "return_type": ret,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            # Record only the checkout's directory name, never the absolute path,
            # so the snapshot does not leak the generating machine's filesystem.
            {"source": next_gen.name, "tool_count": len(tools), "tools": tools},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out_path} with {len(tools)} tools")


if __name__ == "__main__":
    main()
