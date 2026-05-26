from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import webbrowser
from typing import Any

try:
    import arcpy
except Exception:  # pragma: no cover - allows local smoke tests without ArcGIS
    arcpy = None

from . import __version__
from .catalog import default_catalog, humanize_tool_id
from .parameters import create_parameter, parameter_value
from .runtime import RuntimeBootstrapError, create_runtime_session


def _tool_class_name(tool_id: str) -> str:
    parts = [p for p in str(tool_id).replace("-", "_").split("_") if p]
    name = "".join(p[:1].upper() + p[1:] for p in parts) or "WhiteboxTool"
    if name[:1].isdigit():
        name = "Tool" + name
    return name


def _cleanup_temp_paths(paths: list[str]) -> None:
    for path in paths:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _messages_add(messages, text: str) -> None:
    if messages is not None and hasattr(messages, "addMessage"):
        messages.addMessage(text)
    elif arcpy is not None:
        arcpy.AddMessage(text)


class _StreamToArcGIS:
    def __init__(self, messages):
        self.messages = messages

    def __call__(self, event: Any) -> None:
        try:
            payload = json.loads(event) if isinstance(event, str) else event
        except Exception:
            if str(event).strip():
                _messages_add(self.messages, str(event).strip())
            return
        if not isinstance(payload, dict):
            return
        if str(payload.get("type", "")).lower() == "progress":
            pct = payload.get("percent", payload.get("value", None))
            try:
                pct_f = float(pct)
                if 0.0 <= pct_f <= 1.0:
                    pct_f *= 100.0
                if arcpy is not None:
                    arcpy.SetProgressorPosition(int(max(0, min(100, pct_f))))
            except Exception:
                pass
        msg = payload.get("message") or payload.get("text") or payload.get("label")
        if msg:
            _messages_add(self.messages, str(msg))


class Toolbox(object):
    def __init__(self):
        self.label = "Whitebox Next Gen Toolbox"
        self.alias = "WNG"
        self.tools = _build_tools()


class RuntimeDiagnostics(object):
    label = "Runtime Diagnostics"
    description = "Reports Whitebox Next Gen runtime availability and catalog status."
    category = "Whitebox Next Gen"

    def getParameterInfo(self):
        return []

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        include_pro = os.environ.get(
            "WBW_ARCGIS_INCLUDE_PRO", "true"
        ).strip().lower() not in {"0", "false", "no"}
        tier = os.environ.get("WBW_ARCGIS_TIER", "open").strip() or "open"
        _messages_add(messages, f"Whitebox Next Gen ArcGIS support: {__version__}")
        _messages_add(messages, f"Python: {sys.executable}")
        try:
            session = create_runtime_session(include_pro=include_pro, tier=tier)
            caps = json.loads(session.get_runtime_capabilities_json())
            _messages_add(messages, "Runtime: available")
            _messages_add(messages, json.dumps(caps, indent=2, sort_keys=True))
            catalog = json.loads(session.list_tool_catalog_json())
            _messages_add(messages, f"Runtime catalog tools: {len(catalog)}")
        except Exception as exc:
            _messages_add(messages, f"Runtime: unavailable ({exc})")
            _messages_add(messages, f"Snapshot catalog tools: {len(default_catalog())}")


class SearchTools(object):
    label = "Search Tools"
    description = "Searches the Whitebox Next Gen toolbox catalog."
    category = "Whitebox Next Gen"

    def getParameterInfo(self):
        q = arcpy.Parameter(
            displayName="Search text",
            name="query",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        return [q]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        query = (parameters[0].valueAsText or "").lower()
        matches = []
        for item in default_catalog():
            haystack = " ".join(
                str(item.get(k, ""))
                for k in ("id", "display_name", "summary", "category")
            ).lower()
            if query in haystack:
                matches.append(item)
        for item in matches[:100]:
            _messages_add(
                messages,
                f"{item.get('id')}: {item.get('display_name')} [{item.get('category')}]",
            )
        _messages_add(messages, f"{len(matches)} match(es)")


class RunToolJson(object):
    label = "Run Tool From JSON"
    description = "Runs a Whitebox Next Gen tool using a JSON argument payload."
    category = "Whitebox Next Gen"

    def getParameterInfo(self):
        tool_id = arcpy.Parameter(
            displayName="Tool ID",
            name="tool_id",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        args = arcpy.Parameter(
            displayName="Arguments JSON",
            name="args_json",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        return [tool_id, args]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        tool_id = parameters[0].valueAsText
        args_json = parameters[1].valueAsText or "{}"
        include_pro = os.environ.get(
            "WBW_ARCGIS_INCLUDE_PRO", "true"
        ).strip().lower() not in {"0", "false", "no"}
        tier = os.environ.get("WBW_ARCGIS_TIER", "open").strip() or "open"
        session = create_runtime_session(include_pro=include_pro, tier=tier)
        response = session.run_tool_json_stream(
            tool_id, args_json, _StreamToArcGIS(messages)
        )
        _messages_add(messages, response)


class ToolHelp(object):
    label = "Tool Help"
    description = "Opens local or generated help for a Whitebox Next Gen tool."
    category = "Whitebox Next Gen"

    def getParameterInfo(self):
        tool = arcpy.Parameter(
            displayName="Tool ID",
            name="tool_id",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        tool.filter.type = "ValueList"
        tool.filter.list = [item.get("id", "") for item in default_catalog()]
        return [tool]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        tool_id = parameters[0].valueAsText
        url = f"https://www.whiteboxgeo.com/manual/wbw-user-manual/"
        _messages_add(messages, f"Tool ID: {tool_id}")
        _messages_add(messages, f"Online manual: {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass


class _CatalogTool(object):
    _manifest: dict[str, Any] = {}

    def __init__(self):
        self._kinds: list[str] = []
        self.label = self._manifest.get("display_name") or humanize_tool_id(
            self._manifest.get("id", "")
        )
        if self._manifest.get("locked"):
            self.label = "[Locked] " + self.label
        self.description = self._manifest.get("summary", "")
        self.category = self._manifest.get("category", "General")

    def isLicensed(self):
        return True

    def getParameterInfo(self):
        params = []
        self._kinds = []
        for spec in self._manifest.get("params", []):
            param, kind = create_parameter(arcpy, spec, self._manifest)
            params.append(param)
            self._kinds.append(kind)
        return params

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        if self._manifest.get("locked"):
            raise RuntimeError(
                f"This tool is locked for the active runtime tier: {self._manifest.get('locked_reason', 'license_tier_insufficient')}"
            )

        if not self._kinds:
            self.getParameterInfo()

        temp_paths: list[str] = []
        try:
            args: dict[str, Any] = {}
            specs = list(self._manifest.get("params", []))
            for index, spec in enumerate(specs):
                kind = self._kinds[index]
                required = bool(spec.get("required", False)) or kind.endswith("_out")
                value = parameter_value(
                    self, arcpy, parameters, index, kind, required, temp_paths
                )
                if value is not None and value != "":
                    args[str(spec.get("name"))] = value

            tier = str(self._manifest.get("license_tier", "open")).lower()
            include_pro = tier in {"pro", "enterprise"}
            exec_tier = "pro" if include_pro else "open"
            tool_id = str(self._manifest.get("id"))
            _messages_add(messages, f"Running {tool_id} with {len(args)} argument(s).")
            if arcpy is not None:
                arcpy.SetProgressor("step", f"Running {tool_id}", 0, 100, 1)
            session = create_runtime_session(include_pro=include_pro, tier=exec_tier)
            response_raw = session.run_tool_json_stream(
                tool_id, json.dumps(args), _StreamToArcGIS(messages)
            )
            response = (
                json.loads(response_raw)
                if isinstance(response_raw, str) and response_raw.strip()
                else {}
            )
            outputs = (
                response.get("outputs", response) if isinstance(response, dict) else {}
            )
            if isinstance(outputs, dict):
                for key, value in outputs.items():
                    if isinstance(value, dict):
                        value = value.get("path")
                    if isinstance(value, str):
                        _messages_add(messages, f"{key}: {value}")
            if arcpy is not None:
                arcpy.SetProgressorPosition(100)
        except Exception as exc:
            if isinstance(exc, RuntimeBootstrapError):
                raise RuntimeError(str(exc))
            raise
        finally:
            _cleanup_temp_paths(temp_paths)
            if arcpy is not None:
                try:
                    arcpy.ResetProgressor()
                except Exception:
                    pass


def _build_tools():
    tools = [RuntimeDiagnostics, SearchTools, ToolHelp, RunToolJson]
    seen: set[str] = set()
    for manifest in default_catalog():
        tool_id = str(manifest.get("id", "")).strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        class_name = _tool_class_name(tool_id)
        cls = type(class_name, (_CatalogTool,), {"_manifest": manifest})
        globals()[class_name] = cls
        tools.append(cls)
    return tools
