from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


class RuntimeBootstrapError(RuntimeError):
    pass


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _subprocess_startup_kwargs() -> dict[str, Any]:
    """Return subprocess options that keep external runtime windows hidden.

    Returns:
        Platform-specific keyword arguments for ``subprocess.run`` and
        ``subprocess.Popen``.
    """
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value not in {None, ""}:
            return str(value)
    return ""


def _runtime_session_factory_script() -> str:
    return (
        "import os\n"
        "def _env_first(*names):\n"
        "    for name in names:\n"
        "        value=os.environ.get(name)\n"
        "        if value not in (None, ''):\n"
        "            return str(value)\n"
        "    return ''\n"
        "def _make_session(wbw, include_pro, tier):\n"
        "    mode=_env_first('WBW_ARCGIS_LICENSE_MODE').strip().lower()\n"
        "    floating_id=_env_first('WBW_ARCGIS_FLOATING_LICENSE_ID', 'WBW_FLOATING_LICENSE_ID')\n"
        "    entitlement_file=_env_first('WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE', 'WBW_SIGNED_ENTITLEMENT_FILE')\n"
        "    entitlement_json=_env_first('WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON', 'WBW_SIGNED_ENTITLEMENT_JSON')\n"
        "    fallback=_env_first('WBW_ARCGIS_FALLBACK_TIER', 'WBW_FALLBACK_TIER') or 'open'\n"
        "    if mode in ('floating', 'floating_license') or floating_id:\n"
        "        if not floating_id:\n"
        "            raise RuntimeError('WBW_ARCGIS_LICENSE_MODE selects a floating license but no license ID was provided. Set WBW_ARCGIS_FLOATING_LICENSE_ID (or WBW_FLOATING_LICENSE_ID).')\n"
        "        factory=getattr(wbw.RuntimeSession, 'from_floating_license_id', None)\n"
        "        if not callable(factory):\n"
        "            raise RuntimeError('whitebox_workflows RuntimeSession does not support floating licenses')\n"
        "        return factory(\n"
        "            floating_id,\n"
        "            include_pro=True,\n"
        "            fallback_tier=fallback,\n"
        "            provider_url=_env_first('WBW_ARCGIS_LICENSE_PROVIDER_URL', 'WBW_LICENSE_PROVIDER_URL') or None,\n"
        "            machine_id=_env_first('WBW_ARCGIS_MACHINE_ID', 'WBW_MACHINE_ID') or None,\n"
        "            customer_id=_env_first('WBW_ARCGIS_CUSTOMER_ID', 'WBW_CUSTOMER_ID') or None,\n"
        "        )\n"
        "    if mode in ('signed_file', 'signed_entitlement_file') or entitlement_file:\n"
        "        if not entitlement_file:\n"
        "            raise RuntimeError('WBW_ARCGIS_LICENSE_MODE selects a signed entitlement file but no file path was provided. Set WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE (or WBW_SIGNED_ENTITLEMENT_FILE).')\n"
        "        if not os.path.isfile(entitlement_file):\n"
        "            raise RuntimeError('Signed entitlement file does not exist: ' + entitlement_file)\n"
        "        factory=getattr(wbw.RuntimeSession, 'from_signed_entitlement_file', None)\n"
        "        if callable(factory):\n"
        "            return factory(\n"
        "                entitlement_file,\n"
        "                public_key_kid=_env_first('WBW_ARCGIS_PUBLIC_KEY_KID', 'WBW_PUBLIC_KEY_KID'),\n"
        "                public_key_b64url=_env_first('WBW_ARCGIS_PUBLIC_KEY_B64URL', 'WBW_PUBLIC_KEY_B64URL'),\n"
        "                include_pro=True,\n"
        "                fallback_tier=fallback,\n"
        "            )\n"
        "        with open(entitlement_file, 'r', encoding='utf-8') as f:\n"
        "            entitlement_json=f.read()\n"
        "    if mode in ('signed_json', 'signed_entitlement_json') or entitlement_json:\n"
        "        if not entitlement_json:\n"
        "            raise RuntimeError('WBW_ARCGIS_LICENSE_MODE selects a signed entitlement JSON but no JSON was provided. Set WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON (or WBW_SIGNED_ENTITLEMENT_JSON).')\n"
        "        factory=getattr(wbw.RuntimeSession, 'from_signed_entitlement_json', None)\n"
        "        if not callable(factory):\n"
        "            raise RuntimeError('whitebox_workflows RuntimeSession does not support signed entitlements')\n"
        "        return factory(\n"
        "            entitlement_json,\n"
        "            public_key_kid=_env_first('WBW_ARCGIS_PUBLIC_KEY_KID', 'WBW_PUBLIC_KEY_KID'),\n"
        "            public_key_b64url=_env_first('WBW_ARCGIS_PUBLIC_KEY_B64URL', 'WBW_PUBLIC_KEY_B64URL'),\n"
        "            include_pro=True,\n"
        "            fallback_tier=fallback,\n"
        "        )\n"
        "    return wbw.RuntimeSession(include_pro=include_pro, tier=tier)\n"
    )


def _create_runtime_session_from_env(wbw, include_pro: bool, tier: str):
    """Create a Whitebox RuntimeSession using ArcGIS licensing environment vars.

    Args:
        wbw: Imported ``whitebox_workflows`` module.
        include_pro: Whether Pro tools should be visible.
        tier: Requested runtime tier.

    Returns:
        A ``whitebox_workflows.RuntimeSession`` instance.
    """
    mode = _env_first("WBW_ARCGIS_LICENSE_MODE").strip().lower()
    floating_id = _env_first(
        "WBW_ARCGIS_FLOATING_LICENSE_ID", "WBW_FLOATING_LICENSE_ID"
    )
    entitlement_file = _env_first(
        "WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE", "WBW_SIGNED_ENTITLEMENT_FILE"
    )
    entitlement_json = _env_first(
        "WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON", "WBW_SIGNED_ENTITLEMENT_JSON"
    )
    fallback = _env_first("WBW_ARCGIS_FALLBACK_TIER", "WBW_FALLBACK_TIER") or "open"

    if mode in {"floating", "floating_license"} or floating_id:
        if not floating_id:
            raise RuntimeBootstrapError(
                "WBW_ARCGIS_LICENSE_MODE selects a floating license but no license "
                "ID was provided. Set WBW_ARCGIS_FLOATING_LICENSE_ID "
                "(or WBW_FLOATING_LICENSE_ID)."
            )
        factory = getattr(wbw.RuntimeSession, "from_floating_license_id", None)
        if not callable(factory):
            raise RuntimeBootstrapError(
                "whitebox_workflows RuntimeSession does not support floating licenses"
            )
        return factory(
            floating_id,
            include_pro=True,
            fallback_tier=fallback,
            provider_url=_env_first(
                "WBW_ARCGIS_LICENSE_PROVIDER_URL", "WBW_LICENSE_PROVIDER_URL"
            )
            or None,
            machine_id=_env_first("WBW_ARCGIS_MACHINE_ID", "WBW_MACHINE_ID") or None,
            customer_id=_env_first("WBW_ARCGIS_CUSTOMER_ID", "WBW_CUSTOMER_ID")
            or None,
        )

    if mode in {"signed_file", "signed_entitlement_file"} or entitlement_file:
        if not entitlement_file:
            raise RuntimeBootstrapError(
                "WBW_ARCGIS_LICENSE_MODE selects a signed entitlement file but no "
                "file path was provided. Set WBW_ARCGIS_SIGNED_ENTITLEMENT_FILE "
                "(or WBW_SIGNED_ENTITLEMENT_FILE)."
            )
        if not os.path.isfile(entitlement_file):
            raise RuntimeBootstrapError(
                f"Signed entitlement file does not exist: {entitlement_file}"
            )
        factory = getattr(wbw.RuntimeSession, "from_signed_entitlement_file", None)
        if callable(factory):
            return factory(
                entitlement_file,
                public_key_kid=_env_first(
                    "WBW_ARCGIS_PUBLIC_KEY_KID", "WBW_PUBLIC_KEY_KID"
                ),
                public_key_b64url=_env_first(
                    "WBW_ARCGIS_PUBLIC_KEY_B64URL", "WBW_PUBLIC_KEY_B64URL"
                ),
                include_pro=True,
                fallback_tier=fallback,
            )
        with open(entitlement_file, "r", encoding="utf-8") as f:
            entitlement_json = f.read()

    if mode in {"signed_json", "signed_entitlement_json"} or entitlement_json:
        if not entitlement_json:
            raise RuntimeBootstrapError(
                "WBW_ARCGIS_LICENSE_MODE selects a signed entitlement JSON but no "
                "JSON was provided. Set WBW_ARCGIS_SIGNED_ENTITLEMENT_JSON "
                "(or WBW_SIGNED_ENTITLEMENT_JSON)."
            )
        factory = getattr(wbw.RuntimeSession, "from_signed_entitlement_json", None)
        if not callable(factory):
            raise RuntimeBootstrapError(
                "whitebox_workflows RuntimeSession does not support signed entitlements"
            )
        return factory(
            entitlement_json,
            public_key_kid=_env_first("WBW_ARCGIS_PUBLIC_KEY_KID", "WBW_PUBLIC_KEY_KID"),
            public_key_b64url=_env_first(
                "WBW_ARCGIS_PUBLIC_KEY_B64URL", "WBW_PUBLIC_KEY_B64URL"
            ),
            include_pro=True,
            fallback_tier=fallback,
        )

    return wbw.RuntimeSession(include_pro=include_pro, tier=tier)


def _candidate_pythons() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(path: str | None) -> None:
        if not path:
            return
        p = str(Path(path).expanduser())
        if p in seen:
            return
        name = Path(p).name.lower()
        is_python = name.startswith("python") or name in {
            "propy",
            "propy.bat",
            "propy.exe",
        }
        if os.path.isfile(p) and os.access(p, os.X_OK) and is_python:
            seen.add(p)
            out.append(p)

    add(os.environ.get("WBW_EXTERNAL_PYTHON"))
    add(os.environ.get("WBW_PYTHON"))
    add(sys.executable)
    add(shutil.which("python"))
    add(shutil.which("python3"))
    return out


def candidate_python_executables() -> list[str]:
    return list(_candidate_pythons())


class ExternalRuntimeSession:
    def __init__(self, python_executable: str, include_pro: bool, tier: str):
        self.python_executable = python_executable
        self.include_pro = bool(include_pro)
        self.tier = str(tier or "open")

    def _invoke(self, method: str, **kwargs: Any) -> str:
        payload = {
            "method": method,
            "include_pro": self.include_pro,
            "tier": self.tier,
        }
        payload.update(kwargs)
        runner = (
            "import json, sys\n"
            "try:\n"
            "    sys.stdout.reconfigure(encoding='utf-8')\n"
            "except Exception:\n"
            "    pass\n"
        )
        runner += _runtime_session_factory_script()
        runner += (
            "import whitebox_workflows as wbw\n"
            "p=json.loads(sys.argv[1])\n"
            "include_pro=bool(p.get('include_pro', True))\n"
            "tier=str(p.get('tier','open'))\n"
            "m=p.get('method')\n"
            "if hasattr(wbw, 'RuntimeSession'):\n"
            "    s=_make_session(wbw, include_pro, tier)\n"
            "    if m=='capabilities': out=s.get_runtime_capabilities_json()\n"
            "    elif m=='catalog': out=s.list_tool_catalog_json()\n"
            "    elif m=='metadata': out=s.get_tool_metadata_json(str(p.get('tool_id','')))\n"
            "    elif m=='run': out=s.run_tool_json_with_progress(str(p.get('tool_id','')), str(p.get('args_json','{}')))\n"
            "    else: raise RuntimeError('unknown method')\n"
            "else:\n"
            "    if m=='capabilities': out=wbw.get_runtime_capabilities_json_with_options(include_pro, tier)\n"
            "    elif m=='catalog': out=wbw.list_tool_catalog_json_with_options(include_pro, tier)\n"
            "    elif m=='metadata': out=wbw.get_tool_metadata_json_with_options(str(p.get('tool_id','')), include_pro, tier)\n"
            "    elif m=='run': out=wbw.run_tool_json_with_progress_options(str(p.get('tool_id','')), str(p.get('args_json','{}')), include_pro, tier)\n"
            "    else: raise RuntimeError('unknown method')\n"
            "sys.stdout.write(out if isinstance(out, str) else json.dumps(out))\n"
        )
        completed = subprocess.run(
            [self.python_executable, "-c", runner, json.dumps(payload)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_clean_env(),
            **_subprocess_startup_kwargs(),
        )
        if completed.returncode != 0:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "unknown runtime error"
            )
            raise RuntimeBootstrapError(f"{self.python_executable}: {detail}")
        return completed.stdout

    def get_runtime_capabilities_json(self) -> str:
        return self._invoke("capabilities")

    def list_tool_catalog_json(self) -> str:
        return self._invoke("catalog")

    def get_tool_metadata_json(self, tool_id: str) -> str:
        return self._invoke("metadata", tool_id=tool_id)

    def run_tool_json_stream(
        self,
        tool_id: str,
        args_json: str,
        callback: Callable[[Any], None] | None = None,
    ) -> str:
        payload = {
            "include_pro": self.include_pro,
            "tier": self.tier,
            "tool_id": tool_id,
            "args_json": args_json,
        }
        runner = (
            "import base64, json, sys, traceback\n"
            "try:\n"
            "    sys.stdout.reconfigure(encoding='utf-8')\n"
            "except Exception:\n"
            "    pass\n"
        )
        runner += _runtime_session_factory_script()
        runner += (
            "import whitebox_workflows as wbw\n"
            "p=json.loads(sys.argv[1])\n"
            "def emit(evt):\n"
            "    txt=evt if isinstance(evt,str) else json.dumps(evt)\n"
            "    sys.stdout.write('__WBW_EVENT__'+base64.b64encode(txt.encode()).decode()+'\\n'); sys.stdout.flush()\n"
            "include_pro=bool(p.get('include_pro', True)); tier=str(p.get('tier','open'))\n"
            "tool_id=str(p.get('tool_id','')); args_json=str(p.get('args_json','{}'))\n"
            "try:\n"
            "    if hasattr(wbw, 'RuntimeSession'):\n"
            "        s=_make_session(wbw, include_pro, tier)\n"
            "        if hasattr(s, 'run_tool_json_stream'):\n"
            "            out=s.run_tool_json_stream(tool_id, args_json, emit)\n"
            "        else:\n"
            "            out=s.run_tool_json_with_progress(tool_id, args_json)\n"
            "    elif hasattr(wbw, 'run_tool_json_stream_options'):\n"
            "        out=wbw.run_tool_json_stream_options(tool_id, args_json, emit, include_pro, tier)\n"
            "    else:\n"
            "        out=wbw.run_tool_json_with_progress_options(tool_id, args_json, include_pro, tier)\n"
            "    txt=out if isinstance(out,str) else json.dumps(out)\n"
            "    sys.stdout.write('__WBW_RESULT__'+base64.b64encode(txt.encode()).decode()+'\\n')\n"
            "except Exception:\n"
            "    sys.stdout.write('__WBW_ERROR__'+base64.b64encode(traceback.format_exc().encode()).decode()+'\\n')\n"
        )
        completed_result = ""
        errors: list[str] = []
        process = subprocess.Popen(
            [self.python_executable, "-c", runner, json.dumps(payload)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_clean_env(),
            bufsize=1,
            **_subprocess_startup_kwargs(),
        )
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\r\n")
            if line.startswith("__WBW_EVENT__"):
                if callback:
                    callback(
                        base64.b64decode(line[len("__WBW_EVENT__") :]).decode(
                            "utf-8", "replace"
                        )
                    )
            elif line.startswith("__WBW_RESULT__"):
                completed_result = base64.b64decode(
                    line[len("__WBW_RESULT__") :]
                ).decode("utf-8", "replace")
            elif line.startswith("__WBW_ERROR__"):
                errors.append(
                    base64.b64decode(line[len("__WBW_ERROR__") :]).decode(
                        "utf-8", "replace"
                    )
                )
        stderr = process.stderr.read().strip() if process.stderr else ""
        rc = process.wait()
        if rc != 0 or errors:
            raise RuntimeBootstrapError(
                "\n".join(errors) or stderr or "runtime execution failed"
            )
        return completed_result or "{}"

    def run_tool_json_with_progress(self, tool_id: str, args_json: str) -> str:
        return self.run_tool_json_stream(tool_id, args_json, None)


class InProcessRuntimeSession:
    def __init__(self, include_pro: bool, tier: str):
        import whitebox_workflows as wbw

        self._wbw = wbw
        self.include_pro = bool(include_pro)
        self.tier = str(tier or "open")
        if hasattr(wbw, "RuntimeSession"):
            self._session = _create_runtime_session_from_env(
                wbw, include_pro=self.include_pro, tier=self.tier
            )
        else:
            self._session = None

    def get_runtime_capabilities_json(self) -> str:
        if self._session is not None:
            return self._session.get_runtime_capabilities_json()
        return self._wbw.get_runtime_capabilities_json_with_options(
            self.include_pro, self.tier
        )

    def list_tool_catalog_json(self) -> str:
        if self._session is not None:
            return self._session.list_tool_catalog_json()
        return self._wbw.list_tool_catalog_json_with_options(
            self.include_pro, self.tier
        )

    def get_tool_metadata_json(self, tool_id: str) -> str:
        if self._session is not None:
            return self._session.get_tool_metadata_json(tool_id)
        return self._wbw.get_tool_metadata_json_with_options(
            tool_id, self.include_pro, self.tier
        )

    def run_tool_json_stream(
        self,
        tool_id: str,
        args_json: str,
        callback: Callable[[Any], None] | None = None,
    ) -> str:
        if self._session is not None:
            method = getattr(self._session, "run_tool_json_stream", None)
            if callable(method):
                return method(tool_id, args_json, callback)
            return self._session.run_tool_json_with_progress(tool_id, args_json)
        method = getattr(self._wbw, "run_tool_json_stream_options", None)
        if callable(method):
            return method(tool_id, args_json, callback, self.include_pro, self.tier)
        return self._wbw.run_tool_json_with_progress_options(
            tool_id, args_json, self.include_pro, self.tier
        )


def create_runtime_session(include_pro: bool = True, tier: str = "open"):
    mode = os.environ.get("WBW_ARCGIS_RUNTIME_MODE", "auto").strip().lower()
    external_modes = {"auto", "external", "local"}
    inprocess_modes = {"auto", "arcgis", "inprocess", "in-process"}
    failures: list[str] = []

    if mode in external_modes:
        for python in _candidate_pythons():
            try:
                session = ExternalRuntimeSession(
                    python, include_pro=include_pro, tier=tier
                )
                session.get_runtime_capabilities_json()
                return session
            except Exception as exc:
                failures.append(str(exc))
        if mode in {"external", "local"}:
            raise RuntimeBootstrapError(
                "Unable to initialize external whitebox_workflows runtime. "
                + " | ".join(failures)
            )

    if mode in inprocess_modes:
        try:
            session = InProcessRuntimeSession(include_pro=include_pro, tier=tier)
            session.get_runtime_capabilities_json()
            return session
        except Exception as exc:
            failures.append(str(exc))

    raise RuntimeBootstrapError(
        f"Unable to initialize whitebox_workflows runtime (mode={mode!r}). "
        + " | ".join(failures)
    )
