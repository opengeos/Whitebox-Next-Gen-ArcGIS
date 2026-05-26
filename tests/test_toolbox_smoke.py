from __future__ import annotations

import importlib


class _Filter:
    def __init__(self):
        self.type = ""
        self.list = []


class _Parameter:
    def __init__(self, displayName, name, datatype, parameterType, direction):
        self.displayName = displayName
        self.name = name
        self.datatype = datatype
        self.parameterType = parameterType
        self.direction = direction
        self.filter = _Filter()
        self.value = None
        self.valueAsText = None


class _Arcpy:
    Parameter = _Parameter


def test_toolbox_loads_with_arcpy_stub(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    assert tb.alias == "WNG"
    assert len(tb.tools) > 10


def test_representative_tool_has_parameters(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    slope_cls = next(
        cls for cls in tb.tools if getattr(cls, "_manifest", {}).get("id") == "slope"
    )
    params = slope_cls().getParameterInfo()
    names = [p.name for p in params]
    assert "input" in names
    assert "output" in names
