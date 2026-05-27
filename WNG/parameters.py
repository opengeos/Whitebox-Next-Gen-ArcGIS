from __future__ import annotations

import math
import os
import re
import tempfile
from typing import Any

RASTER_EXTS = (".tif", ".tiff", ".img", ".bil", ".flt", ".sdat", ".rdc", ".asc")
VECTOR_EXTS = (".shp", ".gpkg", ".geojson", ".json", ".fgb", ".sqlite", ".gml", ".kml")
LIDAR_EXTS = (".las", ".laz", ".zlidar", ".copc", ".e57", ".ply")
OUTPUT_CONTROL_SUFFIXES = ("_format", "_mode", "_type", "_units")
FILTER_SUFFIX_PATTERN = re.compile(r";\*\.[A-Za-z0-9_]+(?:;\*\.[A-Za-z0-9_]+)*$")
GEODATABASE_PATTERN = re.compile(r"(?i)(?:^|[\\/])[^\\/]+[.](?:gdb|mdb)(?:[\\/]|$)")


def _return_type_text(manifest_or_return_type: Any) -> str:
    """Return searchable return-type text from a manifest or raw type value.

    Args:
        manifest_or_return_type: Tool manifest dictionary or raw return type.

    Returns:
        Lowercase text describing the declared tool return type.
    """
    if isinstance(manifest_or_return_type, dict):
        parts = [
            manifest_or_return_type.get("return_type", ""),
            manifest_or_return_type.get("taxonomy_category", ""),
            manifest_or_return_type.get("category", ""),
        ]
        return " ".join(str(part or "") for part in parts).lower()
    return str(manifest_or_return_type or "").lower()


def _is_output_path_parameter(name: str, type_text: str) -> bool:
    """Return whether a parameter represents an output dataset path.

    Args:
        name: Parameter name.
        type_text: Parameter type annotation text.

    Returns:
        True when the parameter should be represented as an output path.
    """
    n = str(name or "").lower()
    t = str(type_text or "").lower()
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


def _declared_output_kind(manifest: dict[str, Any], name: str, description: str) -> str:
    """Infer output path kind from the tool's declared return type.

    Args:
        manifest: Tool manifest.
        name: Parameter name.
        description: Parameter description.

    Returns:
        Output kind such as ``raster_out`` or an empty string when unknown.
    """
    text = _return_type_text(manifest)
    hint = f"{name} {description}".lower()
    if any(tok in hint for tok in ("html", "report", "csv", "json", "txt", "xml")):
        return "file_out"
    has_raster = "raster" in text
    has_vector = "vector" in text
    has_lidar = "lidar" in text
    if has_vector and not has_raster and not has_lidar:
        return "vector_out"
    if has_lidar and not has_raster and not has_vector:
        return "lidar_out"
    if has_raster:
        if has_vector and any(
            tok in hint for tok in ("vector", "polygon", "line", "point", "feature")
        ):
            return "vector_out"
        if has_lidar and any(tok in hint for tok in ("lidar", "las", "laz")):
            return "lidar_out"
        return "raster_out"
    return ""


def resolve_parameter_kind(spec: dict[str, Any], manifest: dict[str, Any]) -> str:
    """Resolve the ArcGIS parameter kind, correcting stale output metadata.

    Args:
        spec: Parameter specification from the runtime or snapshot catalog.
        manifest: Tool manifest containing return type and category hints.

    Returns:
        Normalized parameter kind.
    """
    name = str(spec.get("name", ""))
    description = str(spec.get("description") or name)
    type_text = str(spec.get("type", ""))
    raw_kind = str(spec.get("kind") or "")
    if _is_output_path_parameter(name, type_text):
        declared = _declared_output_kind(manifest, name, description)
        if declared:
            return declared
        if raw_kind.endswith("_out"):
            return raw_kind
    elif raw_kind.endswith("_out"):
        return infer_kind(name, description, type_text, spec.get("default"), manifest)

    return raw_kind or infer_kind(
        name, description, type_text, spec.get("default"), manifest
    )


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
    r = _return_type_text(return_type)
    family = ""
    if isinstance(return_type, dict):
        family = str(return_type.get("taxonomy_category") or "").lower()

    if _is_output_path_parameter(n, t):
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
    kind = resolve_parameter_kind(spec, manifest)
    required = bool(spec.get("required", False))
    if kind.endswith("_out"):
        required = True
    direction = "Output" if kind.endswith("_out") else "Input"
    datatype = {
        "raster_in": "GPRasterLayer",
        "raster_out": "DERasterDataset",
        "vector_in": "GPFeatureLayer",
        "vector_out": "DEFeatureClass",
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
    elif kind == "lidar_in":
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
    return bool(GEODATABASE_PATTERN.search(str(path or "")))


def _safe_output_stem(tool_id: str, parameter_name: str = "output") -> str:
    text = str(tool_id or "").strip() or "whitebox_output"
    param = str(parameter_name or "").strip().lower()
    if param not in {"output", "out", "output_path"}:
        text = f"{text}_{param}"
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    return text or "whitebox_output"


def _output_extension(kind: str) -> str:
    return {
        "raster_out": ".tif",
        "vector_out": ".shp",
        "lidar_out": ".las",
    }.get(kind, "")


def _path_basename_without_gdb(path: str) -> str:
    parts = re.split(r"[\\/]+", str(path or "").strip())
    if not parts:
        return ""
    name = parts[-1]
    if name.lower().endswith((".gdb", ".mdb")) and len(parts) > 1:
        name = parts[-2]
    stem, _ext = os.path.splitext(name)
    return stem or name


def _project_output_folder(arcpy) -> str:
    if arcpy is not None:
        try:
            project = arcpy.mp.ArcGISProject("CURRENT")
            folder = str(getattr(project, "homeFolder", "") or "").strip()
            if folder and not _looks_like_geodatabase_path(folder):
                return folder
        except Exception:
            pass
        try:
            folder = str(getattr(arcpy.env, "scratchFolder", "") or "").strip()
            if folder and not _looks_like_geodatabase_path(folder):
                return folder
        except Exception:
            pass
    return os.getcwd()


def default_output_path(
    arcpy,
    kind: str,
    tool_id: str,
    parameter_name: str = "output",
    source_path: str = "",
) -> str:
    """Return a Whitebox-compatible default output file path.

    Args:
        arcpy: ArcPy module or test stub.
        kind: Resolved output parameter kind.
        tool_id: Tool identifier used for generated filenames.
        parameter_name: Output parameter name.
        source_path: Existing path to preserve the requested output name from.

    Returns:
        Output file path in the project folder, never inside a geodatabase.
    """
    folder = _project_output_folder(arcpy)
    stem = _path_basename_without_gdb(source_path) or _safe_output_stem(
        tool_id, parameter_name
    )
    ext = _output_extension(kind)
    return os.path.join(folder, stem + ext)


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


def clean_output_path(path: str) -> str:
    """Remove ArcGIS file-filter suffixes accidentally appended to output paths.

    Args:
        path: Raw output path text from an ArcGIS parameter.

    Returns:
        Cleaned output path.
    """
    return FILTER_SUFFIX_PATTERN.sub("", str(path or "").strip())


def ensure_output_file_path(
    arcpy,
    path: str,
    kind: str,
    tool_id: str,
    parameter_name: str = "output",
) -> str:
    """Return an output path that Whitebox can write.

    Args:
        arcpy: ArcPy module or test stub.
        path: Raw output path from an ArcGIS parameter.
        kind: Resolved output parameter kind.
        tool_id: Tool identifier used for generated filenames.
        parameter_name: Output parameter name.

    Returns:
        File-system output path outside any geodatabase.
    """
    cleaned = clean_output_path(path)
    if not cleaned or _looks_like_geodatabase_path(cleaned):
        return default_output_path(arcpy, kind, tool_id, parameter_name, cleaned)
    ext = _output_extension(kind)
    if ext and not os.path.splitext(cleaned)[1]:
        return cleaned + ext
    return cleaned


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
    if kind.endswith("_out"):
        tool_id = str(getattr(tool, "_manifest", {}).get("id", "whitebox_output"))
        parameter_name = str(getattr(param, "name", f"output_{index}"))
        return ensure_output_file_path(arcpy, raw or "", kind, tool_id, parameter_name)
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
