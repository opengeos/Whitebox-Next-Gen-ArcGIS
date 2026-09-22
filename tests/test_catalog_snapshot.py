"""Checks on the committed catalog snapshot and the script that writes it."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "WNG" / "data" / "catalog_snapshot.json"

# Five tools live in the taxonomy but not in the runtime catalog, so they have
# no summary to copy. Pinning the number rather than the names keeps the test
# from failing every time the tool list moves, while still failing loudly if
# summaries start disappearing in bulk.
MAX_TOOLS_WITHOUT_SUMMARY = 5


def _generator() -> Any:
    """Import ``scripts/generate_catalog_snapshot.py`` as a module."""

    path = ROOT / "scripts" / "generate_catalog_snapshot.py"
    spec = importlib.util.spec_from_file_location("generate_catalog_snapshot", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    """The committed snapshot."""

    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_tools_carry_summaries(snapshot):
    """Nearly every tool describes itself.

    The snapshot shipped with all 775 summaries empty for as long as it existed,
    because the generator hard-coded the field. Nothing caught it: every summary
    being blank is indistinguishable from the field being unused, right up until
    ArcGIS Pro shows a tool with no description, or a consumer tries to search
    the catalog by what its tools do.
    """

    tools = snapshot["tools"]
    blank = [t["id"] for t in tools if not str(t.get("summary", "")).strip()]
    assert len(blank) <= MAX_TOOLS_WITHOUT_SUMMARY, (
        f"{len(blank)} of {len(tools)} tools have no summary: {blank[:10]}"
    )


def test_snapshot_summaries_are_prose_not_placeholders(snapshot):
    """A summary says something beyond the tool's own name.

    Guards the obvious wrong fix — filling the field by humanizing the id, which
    would look populated and carry no information at all.
    """

    for tool in snapshot["tools"]:
        summary = str(tool.get("summary", "")).strip()
        if not summary:
            continue
        assert summary.lower() != tool["display_name"].lower(), tool["id"]
        assert len(summary) > len(tool["display_name"]), tool["id"]


def test_snapshot_header_records_a_bare_source(snapshot):
    """The recorded source never leaks the generating machine's paths."""

    source = snapshot["source"]
    assert source
    assert "/" not in source and "\\" not in source
    assert snapshot["tool_count"] == len(snapshot["tools"])


def test_resolve_sources_falls_back_to_the_installed_package(tmp_path, monkeypatch):
    """With no checkout, the published wheel supplies the stub and taxonomy."""

    pytest.importorskip("whitebox_workflows")
    module = _generator()
    # Both checkout candidates have to be absent or this exercises the wrong
    # branch — and it would do so precisely on a Next Gen maintainer's machine,
    # where `../whitebox_next_gen` is the normal state of the world.
    monkeypatch.delenv("WBW_NEXT_GEN", raising=False)
    monkeypatch.setattr(module, "ROOT", tmp_path / "repo")

    stub, taxonomy, source = module.resolve_sources(None)
    assert stub.is_file() and taxonomy.is_file()
    assert source == "whitebox_workflows"


def test_resolve_sources_rejects_a_bad_explicit_path(monkeypatch):
    """A ``--next-gen`` path that does not exist is an error, not a fallback."""

    module = _generator()
    # Set the fallbacks up to succeed, so the test fails if the explicit path
    # is merely tried first rather than being authoritative.
    monkeypatch.setenv("WBW_NEXT_GEN", str(ROOT))
    with pytest.raises(SystemExit):
        module.resolve_sources("/nonexistent/whitebox_next_gen")


def test_resolve_sources_rejects_an_incomplete_explicit_checkout(tmp_path):
    """A named checkout missing the two files stops rather than falling back."""

    module = _generator()
    empty = tmp_path / "whitebox_next_gen"
    empty.mkdir()
    with pytest.raises(SystemExit):
        module.resolve_sources(str(empty))


def test_runtime_catalog_supplies_the_summaries():
    """The runtime catalog is where summaries come from."""

    pytest.importorskip("whitebox_workflows")
    module = _generator()
    runtime = module.load_runtime_catalog()
    assert runtime, "runtime catalog was empty"
    described = [t for t in runtime.values() if t["summary"]]
    assert len(described) > 0.9 * len(runtime)
