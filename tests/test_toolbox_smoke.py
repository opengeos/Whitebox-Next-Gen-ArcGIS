from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
from pathlib import Path


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


class _Messages:
    def __init__(self):
        self.text = []

    def addMessage(self, text):
        self.text.append(text)


def _load_python_toolbox():
    """Load the Python toolbox file through an explicit source loader.

    Returns:
        The loaded Python module for ``WhiteboxNextGen.pyt``.
    """
    toolbox_path = Path(__file__).resolve().parents[1] / "WhiteboxNextGen.pyt"
    loader = importlib.machinery.SourceFileLoader(
        "WhiteboxNextGen_test", str(toolbox_path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_toolbox_loads_with_arcpy_stub(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    assert tb.alias == "WNG"
    assert len(tb.tools) > 10
    assert toolbox.InstallRequiredPackages in tb.tools


def test_toolbox_load_does_not_touch_runtime(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")

    def fail_live_catalog(*args, **kwargs):
        raise AssertionError("toolbox discovery must not use the live catalog")

    monkeypatch.setattr(toolbox, "default_catalog", fail_live_catalog)
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    assert len(tb.tools) > 10


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
    assert (
        params[0].value
        == r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
    )
    assert params[1].value == "whitebox-workflows"
    assert params[2].value is False
    assert params[3].value is False


def test_catalog_categories_include_subcategories(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    tool_cls = next(
        cls
        for cls in tb.tools
        if getattr(cls, "_manifest", {}).get("id") == "fd8_pointer"
    )
    assert tool_cls().category == "Hydrology\\Flow Routing"


def test_equivalent_categories_prefer_ampersand_snapshot_label():
    catalog = importlib.import_module("WNG.catalog")
    merged = catalog._merge_snapshot_hints(
        [
            {
                "id": "breach_depressions_least_cost",
                "category": "Hydrology - Depressions Storage",
                "params": [],
            }
        ]
    )
    assert merged[0]["category"] == "Hydrology - Depressions & Storage"
    assert catalog.toolbox_category(merged[0]) == "Hydrology\\Depressions & Storage"


def test_locked_tools_include_unlock_instructions(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    assert toolbox.LicenseInstructions in tb.tools
    locked_cls = next(
        cls for cls in tb.tools if getattr(cls, "_manifest", {}).get("locked")
    )
    tool = locked_cls()
    assert tool.label.startswith("[Locked] ")
    assert "WBW_ARCGIS_TIER=pro" in tool.description
    try:
        tool.execute([], _Messages())
    except RuntimeError as exc:
        assert "License Instructions" in str(exc)
    else:
        raise AssertionError("locked tool should raise RuntimeError")


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


def test_external_runtime_invocation_uses_utf8(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")
    captured = {}

    class _Completed:
        returncode = 0
        stdout = "ok -> ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return _Completed()

    monkeypatch.setenv("PYTHONHOME", "bad")
    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    session = runtime.ExternalRuntimeSession(
        "python.exe", include_pro=True, tier="open"
    )
    assert session.get_runtime_capabilities_json() == "ok -> ok"
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["env"]["PYTHONUTF8"] == "1"
    assert "PYTHONHOME" not in captured["env"]


def test_runtime_session_uses_floating_license_env(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")
    calls = {}

    class _RuntimeSession:
        @staticmethod
        def from_floating_license_id(floating_license_id, **kwargs):
            calls["floating_license_id"] = floating_license_id
            calls.update(kwargs)
            return "floating-session"

    class _Wbw:
        RuntimeSession = _RuntimeSession

    monkeypatch.setenv("WBW_ARCGIS_FLOATING_LICENSE_ID", "fl_12345")
    monkeypatch.setenv("WBW_LICENSE_PROVIDER_URL", "https://license.example.com")
    monkeypatch.setenv("WBW_ARCGIS_MACHINE_ID", "machine-01")
    monkeypatch.setenv("WBW_ARCGIS_CUSTOMER_ID", "customer-abc")
    session = runtime._create_runtime_session_from_env(
        _Wbw, include_pro=False, tier="open"
    )
    assert session == "floating-session"
    assert calls == {
        "floating_license_id": "fl_12345",
        "include_pro": True,
        "fallback_tier": "open",
        "provider_url": "https://license.example.com",
        "machine_id": "machine-01",
        "customer_id": "customer-abc",
    }


def test_runtime_session_uses_signed_entitlement_file_env(monkeypatch, tmp_path):
    runtime = importlib.import_module("WNG.runtime")
    entitlement = tmp_path / "signed_entitlement.json"
    entitlement.write_text('{"license":"signed"}')
    calls = {}

    class _RuntimeSession:
        @staticmethod
        def from_signed_entitlement_json(signed_entitlement_json, **kwargs):
            calls["signed_entitlement_json"] = signed_entitlement_json
            calls.update(kwargs)
            return "signed-session"

    class _Wbw:
        RuntimeSession = _RuntimeSession

    monkeypatch.setenv("WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE", str(entitlement))
    monkeypatch.setenv("WBW_ARCGIS_PUBLIC_KEY_KID", "k1")
    monkeypatch.setenv("WBW_ARCGIS_PUBLIC_KEY_B64URL", "public-key")
    monkeypatch.setenv("WBW_ARCGIS_FALLBACK_TIER", "open")
    session = runtime._create_runtime_session_from_env(
        _Wbw, include_pro=False, tier="open"
    )
    assert session == "signed-session"
    assert calls == {
        "signed_entitlement_json": '{"license":"signed"}',
        "public_key_kid": "k1",
        "public_key_b64url": "public-key",
        "include_pro": True,
        "fallback_tier": "open",
    }


def test_floating_license_mode_without_id_raises(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")

    class _Wbw:
        class RuntimeSession:
            pass

    monkeypatch.setenv("WBW_ARCGIS_LICENSE_MODE", "floating")
    monkeypatch.delenv("WBW_ARCGIS_FLOATING_LICENSE_ID", raising=False)
    monkeypatch.delenv("WBW_FLOATING_LICENSE_ID", raising=False)
    try:
        runtime._create_runtime_session_from_env(_Wbw, include_pro=True, tier="pro")
    except runtime.RuntimeBootstrapError as exc:
        assert "WBW_ARCGIS_FLOATING_LICENSE_ID" in str(exc)
    else:
        raise AssertionError("floating mode without license ID should raise")


def test_signed_file_mode_without_path_raises(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")

    class _Wbw:
        class RuntimeSession:
            pass

    monkeypatch.setenv("WBW_ARCGIS_LICENSE_MODE", "signed_file")
    monkeypatch.delenv("WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE", raising=False)
    monkeypatch.delenv("WBW_SIGNED_ENTITLEMENT_FILE", raising=False)
    try:
        runtime._create_runtime_session_from_env(_Wbw, include_pro=True, tier="pro")
    except runtime.RuntimeBootstrapError as exc:
        assert "WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE" in str(exc)
    else:
        raise AssertionError("signed_file mode without path should raise")


def test_signed_file_mode_with_missing_file_raises(monkeypatch, tmp_path):
    runtime = importlib.import_module("WNG.runtime")

    class _Wbw:
        class RuntimeSession:
            pass

    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setenv("WBW_ARCGIS_LICENSE_MODE", "signed_file")
    monkeypatch.setenv("WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE", str(missing))
    try:
        runtime._create_runtime_session_from_env(_Wbw, include_pro=True, tier="pro")
    except runtime.RuntimeBootstrapError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("signed_file mode with missing file should raise")


def test_signed_json_mode_without_payload_raises(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")

    class _Wbw:
        class RuntimeSession:
            pass

    monkeypatch.setenv("WBW_ARCGIS_LICENSE_MODE", "signed_json")
    monkeypatch.delenv("WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON", raising=False)
    monkeypatch.delenv("WBW_SIGNED_ENTITLEMENT_JSON", raising=False)
    try:
        runtime._create_runtime_session_from_env(_Wbw, include_pro=True, tier="pro")
    except runtime.RuntimeBootstrapError as exc:
        assert "WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON" in str(exc)
    else:
        raise AssertionError("signed_json mode without JSON should raise")


def test_output_paths_are_set_for_arcgis_autoload(monkeypatch, tmp_path):
    toolbox = importlib.import_module("WNG.toolbox")
    set_parameters = {}

    class _ArcpyWithMap(_Arcpy):
        @staticmethod
        def SetParameterAsText(index, value):
            set_parameters[index] = value

    output = tmp_path / "result.tif"
    output.write_text("")
    monkeypatch.setattr(toolbox, "arcpy", _ArcpyWithMap())
    toolbox._set_output_parameter(2, str(output))
    assert set_parameters == {2: str(output)}


def test_update_parameters_moves_geodatabase_outputs_to_project_folder(
    monkeypatch, tmp_path
):
    toolbox = importlib.import_module("WNG.toolbox")

    class _Project:
        homeFolder = str(tmp_path)

    class _Mp:
        @staticmethod
        def ArcGISProject(value):
            assert value == "CURRENT"
            return _Project()

    class _ArcpyWithProject(_Arcpy):
        mp = _Mp()

    monkeypatch.setattr(toolbox, "arcpy", _ArcpyWithProject())
    tb = toolbox.Toolbox()
    tool_cls = next(
        cls for cls in tb.tools if getattr(cls, "_manifest", {}).get("id") == "slope"
    )
    tool = tool_cls()
    params = tool.getParameterInfo()
    output = next(param for param in params if param.name == "output")
    output.valueAsText = r"C:\project\MyProject.gdb\slope"
    tool.updateParameters(params)
    assert output.valueAsText == str(tmp_path / "slope.tif")


def test_execute_sets_output_without_manual_map_add(monkeypatch, tmp_path):
    toolbox = importlib.import_module("WNG.toolbox")
    set_parameters = {}

    class _Map:
        def addDataFromPath(self, path):
            raise AssertionError("execute should not manually add outputs to the map")

    class _Project:
        homeFolder = str(tmp_path)
        activeMap = _Map()

    class _Mp:
        @staticmethod
        def ArcGISProject(value):
            assert value == "CURRENT"
            return _Project()

    class _ArcpyForExecute(_Arcpy):
        mp = _Mp()

        @staticmethod
        def SetParameterAsText(index, value):
            set_parameters[index] = value

        @staticmethod
        def SetProgressor(*args):
            return None

        @staticmethod
        def SetProgressorPosition(*args):
            return None

        @staticmethod
        def ResetProgressor():
            return None

    class _Session:
        def run_tool_json_stream(self, tool_id, args_json, callback):
            return "{}"

    monkeypatch.setattr(toolbox, "arcpy", _ArcpyForExecute())
    monkeypatch.setattr(toolbox, "create_runtime_session", lambda **kwargs: _Session())
    tb = toolbox.Toolbox()
    tool_cls = next(
        cls for cls in tb.tools if getattr(cls, "_manifest", {}).get("id") == "slope"
    )
    tool = tool_cls()
    params = tool.getParameterInfo()
    for param in params:
        if param.name == "input":
            param.valueAsText = str(tmp_path / "input.tif")
        elif param.name == "output":
            param.valueAsText = str(tmp_path / "outputs.gdb" / "slope")
    tool.execute(params, _Messages())
    output_index = next(
        index for index, param in enumerate(params) if param.name == "output"
    )
    assert set_parameters == {output_index: str(tmp_path / "slope.tif")}


def test_windows_runtime_subprocesses_are_hidden(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")
    monkeypatch.setattr(runtime.os, "name", "nt")
    monkeypatch.setattr(
        runtime.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    kwargs = runtime._subprocess_startup_kwargs()
    assert kwargs == {"creationflags": 0x08000000}


def test_non_windows_runtime_subprocesses_do_not_set_creationflags(monkeypatch):
    runtime = importlib.import_module("WNG.runtime")
    monkeypatch.setattr(runtime.os, "name", "posix")
    assert runtime._subprocess_startup_kwargs() == {}


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


def test_fd8_pointer_output_is_raster(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    tool_cls = next(
        cls
        for cls in tb.tools
        if getattr(cls, "_manifest", {}).get("id") == "fd8_pointer"
    )
    params = tool_cls().getParameterInfo()
    output = next(param for param in params if param.name == "output")
    assert output.direction == "Output"
    assert output.datatype == "DERasterDataset"
    assert output.filter.list == []


def test_output_like_options_are_not_dataset_outputs(monkeypatch):
    toolbox = importlib.import_module("WNG.toolbox")
    monkeypatch.setattr(toolbox, "arcpy", _Arcpy())
    tb = toolbox.Toolbox()
    tool_cls = next(
        cls
        for cls in tb.tools
        if getattr(cls, "_manifest", {}).get("id") == "new_raster_from_base_vector"
    )
    params = tool_cls().getParameterInfo()
    out_val = next(param for param in params if param.name == "out_val")
    output = next(param for param in params if param.name == "output")
    assert out_val.direction == "Input"
    assert out_val.datatype == "GPDouble"
    assert output.direction == "Output"
    assert output.datatype == "DERasterDataset"
    assert output.filter.list == []


def test_output_parameter_value_removes_appended_file_filter():
    parameters = importlib.import_module("WNG.parameters")
    param = _Parameter("Output", "output", "DERasterDataset", "Required", "Output")
    param.valueAsText = r"C:\data\filled.tif;*.tiff"
    assert (
        parameters.parameter_value(None, None, [param], 0, "raster_out", True, [])
        == r"C:\data\filled.tif"
    )


def test_python_toolbox_exposes_module_local_tools(monkeypatch):
    module = _load_python_toolbox()
    monkeypatch.setattr(module._toolbox, "arcpy", _Arcpy())
    tb = module.Toolbox()
    assert tb.alias == "WNG"
    assert len(tb.tools) > 10
    assert module.InstallRequiredPackages in tb.tools
    assert all(getattr(module, cls.__name__) is cls for cls in tb.tools)
    assert all(cls.__module__ == module.__name__ for cls in tb.tools)
