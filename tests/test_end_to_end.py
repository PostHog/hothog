"""End-to-end: exercise the live import hook + entry resolution + full join on a synthetic app.

This is the part the pure-core tests can't reach. No Django, no real SDKs — a toy first-party
package (`sample_app`) and two fake external SDKs reproduce the exact patterns hothog detects:
  * heavy_sdk — imported at module scope by two sibling views, used only in functions
                -> deferrable, with a single dominator cut-point at sample_app.api
  * config_sdk — used at module scope -> BLOCKED:modscope
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _capture_importtime(log_path: Path) -> None:
    code = f"import sys; sys.path.insert(0, {str(FIXTURES)!r}); import sample_app.boot as b; b.run()"
    with log_path.open("w") as fh:
        subprocess.run([sys.executable, "-X", "importtime", "-c", code], stderr=fh, check=True)


def _fresh_import_state() -> None:
    for name in list(sys.modules):
        if name.split(".")[0] in ("sample_app", "heavy_sdk", "config_sdk"):
            del sys.modules[name]


def test_live_path_finds_deferrable_sdk_with_cut_point(tmp_path):
    from hothog import Config, Triage

    log = tmp_path / "it.log"
    _capture_importtime(log)

    sys.path.insert(0, str(FIXTURES))
    _fresh_import_state()
    try:
        cfg = Config(
            importtime_log=str(log),
            entry="sample_app.boot:run",
            first_party=("sample_app",),
            min_removable=0.0,
            use_grimp=False,
        )
        report = Triage(cfg).run()
    finally:
        sys.path.remove(str(FIXTURES))
        _fresh_import_state()

    by_label = {r.label: r for r in report.rows}

    # heavy_sdk: external, deferrable (function-only usage), with the single upstream cut-point.
    assert "heavy_sdk" in by_label, f"got rows: {sorted(by_label)}"
    hs = by_label["heavy_sdk"]
    assert hs.external is True
    assert hs.defer.startswith(("easy", "many")), hs.defer
    assert hs.blocked is False
    assert hs.cut == "1-cut@sample_app.api", hs.cut
    assert sorted(hs.importers) == ["sample_app.api.billing", "sample_app.api.reports"]

    # config_sdk: used at module scope -> blocked.
    assert "config_sdk" in by_label
    assert by_label["config_sdk"].defer == "BLOCKED:modscope"
    assert by_label["config_sdk"].blocked is True


def test_report_totals_are_populated(tmp_path):
    from hothog import Config, Triage

    log = tmp_path / "it.log"
    _capture_importtime(log)

    sys.path.insert(0, str(FIXTURES))
    _fresh_import_state()
    try:
        cfg = Config(
            importtime_log=str(log),
            entry="sample_app.boot:run",
            first_party=("sample_app",),
            min_removable=0.0,
            use_grimp=False,
        )
        report = Triage(cfg).run()
    finally:
        sys.path.remove(str(FIXTURES))
        _fresh_import_state()

    assert report.total_self_ms > 0  # importtime log parsed
    assert report.rows  # at least the two SDKs surfaced


def test_run_restores_env(tmp_path):
    from hothog import Config, Triage

    log = tmp_path / "it.log"
    _capture_importtime(log)

    marker = "HOTHOG_ENV_RESTORE_CHECK"
    assert marker not in os.environ
    sys.path.insert(0, str(FIXTURES))
    _fresh_import_state()
    try:
        cfg = Config(
            importtime_log=str(log),
            entry="sample_app.boot:run",
            first_party=("sample_app",),
            env={marker: "set-during-run"},
            use_grimp=False,
        )
        Triage(cfg).run()
    finally:
        sys.path.remove(str(FIXTURES))
        _fresh_import_state()

    assert marker not in os.environ  # restored, not leaked into the calling process
