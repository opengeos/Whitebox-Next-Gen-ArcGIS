from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


class RuntimeBootstrapError(RuntimeError):
    pass


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    return env


def _candidate_pythons() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(path: str | None) -> None:
        if not path:
            return
        p = str(Path(path).expanduser())
        if p in seen:
            return
        if os.path.isfile(p) and os.access(p, os.X_OK):
            seen.add(p)
            out.append(p)

    add(os.environ.get("WBW_EXTERNAL_PYTHON"))
    add(os.environ.get("WBW_PYTHON"))
    add(sys.executable)
    add(shutil.which("python"))
    add(shutil.which("python3"))
    return out


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
            "import whitebox_workflows as wbw\n"
            "p=json.loads(sys.argv[1])\n"
            "include_pro=bool(p.get('include_pro', True))\n"
            "tier=str(p.get('tier','open'))\n"
            "m=p.get('method')\n"
            "if hasattr(wbw, 'RuntimeSession'):\n"
            "    s=wbw.RuntimeSession(include_pro=include_pro, tier=tier)\n"
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
            env=_clean_env(),
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
            "import whitebox_workflows as wbw\n"
            "p=json.loads(sys.argv[1])\n"
            "def emit(evt):\n"
            "    txt=evt if isinstance(evt,str) else json.dumps(evt)\n"
            "    sys.stdout.write('__WBW_EVENT__'+base64.b64encode(txt.encode()).decode()+'\\n'); sys.stdout.flush()\n"
            "include_pro=bool(p.get('include_pro', True)); tier=str(p.get('tier','open'))\n"
            "tool_id=str(p.get('tool_id','')); args_json=str(p.get('args_json','{}'))\n"
            "try:\n"
            "    if hasattr(wbw, 'RuntimeSession'):\n"
            "        s=wbw.RuntimeSession(include_pro=include_pro, tier=tier)\n"
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
            env=_clean_env(),
            bufsize=1,
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
            self._session = wbw.RuntimeSession(
                include_pro=self.include_pro, tier=self.tier
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
    failures: list[str] = []

    if mode in {"auto", "external", "local"}:
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

    try:
        session = InProcessRuntimeSession(include_pro=include_pro, tier=tier)
        session.get_runtime_capabilities_json()
        return session
    except Exception as exc:
        failures.append(str(exc))

    raise RuntimeBootstrapError(
        "Unable to initialize whitebox_workflows runtime. " + " | ".join(failures)
    )
