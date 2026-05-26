from __future__ import annotations

import math
import os
import tempfile
from typing import Any


RASTER_EXTS = (".tif", ".tiff", ".img", ".bil", ".flt", ".sdat", ".rdc", ".asc")
VECTOR_EXTS = (".shp", ".gpkg", ".geojson", ".json", ".fgb", ".sqlite", ".gml", ".kml")
LIDAR_EXTS = (".las", ".laz", ".zlidar", ".copc", ".e57", ".ply")


def infer_kind(
    name: str,
    description: str = "",
    type_text: str = "",
    default: Any = None,
    return_type: str = "",
) -> str:
    n = str(name or "").lower()
    d = str(description or "").lower()
    t = str(type_text or "").lower()
    r = str(return_type or "").lower()
    family = ""
    if isinstance(return_type, dict):
        family = str(
            return_type.get("taxonomy_category") or return_type.get("category") or ""
        ).lower()

    if n in {"output", "out", "output_path", "destination"} or n.startswith(
        ("output_", "out_")
    ):
        if "vector" in family or any(
            tok in n + d + r
            for tok in ("vector", "shp", "feature", "polygon", "line", "point")
        ):
            return "vector_out"
        if "lidar" in family or any(
            tok in n + d + r for tok in ("lidar", "las", "laz")
        ):
            return "lidar_out"
        if family in {
            "raster",
            "terrain",
            "hydrology",
            "remote_sensing",
            "projection_georeferencing",
        } or any(tok in n + d + r for tok in ("raster", "dem", "grid", "tif")):
            return "raster_out"
        return "file_out"
    if n in {"epsg", "dst_epsg", "src_epsg", "cols", "rows"}:
        return "int"
    if isinstance(default, bool) or t in {"bool", "boolean"} or "bool" in t:
        return "bool"
    if "int" in t:
        return "int"
    if any(tok in t for tok in ("float", "double", "number")):
        return "double"
    if n == "input" and family in {
        "raster",
        "terrain",
        "hydrology",
        "remote_sensing",
        "projection_georeferencing",
    }:
        return "raster_in"
    if n == "input" and family == "vector":
        return "vector_in"
    if n == "input" and family == "lidar":
        return "lidar_in"
    if "raster" in t or any(tok in n for tok in ("dem", "raster", "grid")):
        return "raster_in"
    if "vector" in t or any(
        tok in n
        for tok in (
            "vector",
            "feature",
            "polygon",
            "polygons",
            "line",
            "lines",
            "point",
            "points",
            "network",
            "origins",
            "destinations",
        )
    ):
        return "vector_in"
    if "lidar" in t or any(tok in n for tok in ("lidar", "las", "laz")):
        return "lidar_in"
    if any(
        tok in n or tok in d
        for tok in ("file", "path", "csv", "json", "html", "txt", "xml")
    ):
        return "file_in"
    return "string"


def create_parameter(arcpy, spec: dict[str, Any], manifest: dict[str, Any]):
    name = str(spec.get("name", ""))
    description = str(spec.get("description") or name)
    kind = str(
        spec.get("kind")
        or infer_kind(
            name, description, spec.get("type", ""), spec.get("default"), manifest
        )
    )
    required = bool(spec.get("required", False))
    if kind.endswith("_out"):
        required = True
    direction = "Output" if kind.endswith("_out") else "Input"
    datatype = {
        "raster_in": "GPRasterLayer",
        "raster_out": "DEFile",
        "vector_in": "GPFeatureLayer",
        "vector_out": "DEFile",
        "lidar_in": "DEFile",
        "lidar_out": "DEFile",
        "file_in": "DEFile",
        "file_out": "DEFile",
        "bool": "GPBoolean",
        "int": "GPLong",
        "double": "GPDouble",
        "enum": "GPString",
        "string": "GPString",
    }.get(kind, "GPString")
    param = arcpy.Parameter(
        displayName=description,
        name=name,
        datatype=datatype,
        parameterType="Required" if required else "Optional",
        direction=direction,
    )
    options = spec.get("options") or []
    if options:
        param.filter.type = "ValueList"
        param.filter.list = [str(o) for o in options]
        if spec.get("default") is not None:
            param.value = str(spec.get("default"))
    elif kind == "raster_out":
        param.filter.list = ["tif", "tiff"]
    elif kind == "vector_out":
        param.filter.list = ["shp", "gpkg", "geojson"]
    elif kind in {"lidar_in", "lidar_out"}:
        param.filter.list = ["las", "laz", "zlidar", "copc", "e57", "ply"]
    elif spec.get("default") is not None and kind not in {
        "file_in",
        "raster_in",
        "vector_in",
        "lidar_in",
    }:
        param.value = spec.get("default")
    return param, kind


def _looks_like_geodatabase_path(path: str) -> bool:
    lower = str(path or "").lower()
    return (
        ".gdb" + os.sep.lower() in lower
        or ".gdb/" in lower
        or ".mdb" + os.sep.lower() in lower
        or ".mdb/" in lower
    )


def _describe_path(arcpy, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        desc = arcpy.Describe(text)
        return str(getattr(desc, "catalogPath", text) or text)
    except Exception:
        return text


def materialize_input(arcpy, value: Any, kind: str, temp_paths: list[str]) -> str:
    path = _describe_path(arcpy, value)
    if not path:
        return ""
    if "|" in path:
        candidate = path.split("|", 1)[0]
        if os.path.exists(candidate):
            path = candidate

    if kind == "raster_in" and _looks_like_geodatabase_path(path):
        fd, out_path = tempfile.mkstemp(prefix="wbw_arcgis_raster_", suffix=".tif")
        os.close(fd)
        try:
            os.remove(out_path)
        except OSError:
            pass
        arcpy.management.CopyRaster(path, out_path)
        temp_paths.append(out_path)
        return out_path

    if kind == "vector_in" and (
        _looks_like_geodatabase_path(path) or not path.lower().endswith(VECTOR_EXTS)
    ):
        out_dir = tempfile.mkdtemp(prefix="wbw_arcgis_vector_")
        out_name = "input.shp"
        arcpy.conversion.FeatureClassToFeatureClass(path, out_dir, out_name)
        out_path = os.path.join(out_dir, out_name)
        temp_paths.append(out_dir)
        return out_path

    return path


def parameter_value(
    tool,
    arcpy,
    parameters: list[Any],
    index: int,
    kind: str,
    required: bool,
    temp_paths: list[str],
):
    param = parameters[index]
    raw = getattr(param, "valueAsText", None)
    if raw in {None, ""}:
        if required:
            raise ValueError(
                f"Missing required parameter: {getattr(param, 'name', index)}"
            )
        return None
    if kind in {"raster_in", "vector_in", "lidar_in", "file_in"}:
        return materialize_input(arcpy, raw, kind, temp_paths)
    if kind == "bool":
        return str(raw).strip().lower() in {"true", "1", "yes", "y"}
    if kind == "int":
        return int(float(raw))
    if kind == "double":
        value = float(raw)
        if not math.isfinite(value):
            return None
        return value
    return str(raw)
