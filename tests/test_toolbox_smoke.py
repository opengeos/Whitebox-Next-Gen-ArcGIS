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
    assert toolbox.InstallRequiredPackages in tb.tools


def test_install_required_packages_defaults(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    params = toolbox.InstallRequiredPackages().getParameterInfo()
    assert [p.name for p in params] == [
        "python_executable",
        "package_spec",
        "upgrade",
        "user_site",
    ]
    assert params[1].value == "whitebox-workflows"
    assert params[2].value is False
    assert params[3].value is False


def test_runtime_python_candidates_skip_arcgispro_exe(monkeypatch, tmp_path):
    runtime = importlib.import_module("WNG.runtime")
    arcgispro = tmp_path / "ArcGISPro.exe"
    python = tmp_path / "python.exe"
    arcgispro.write_text("")
    python.write_text("")
    arcgispro.chmod(0o755)
    python.chmod(0o755)
    monkeypatch.setenv("WBW_EXTERNAL_PYTHON", str(arcgispro))
    monkeypatch.setenv("WBW_PYTHON", str(python))
    monkeypatch.setattr(runtime.sys, "executable", str(arcgispro))
    candidates = runtime.candidate_python_executables()
    assert str(arcgispro) not in candidates
    assert candidates[0] == str(python)


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
