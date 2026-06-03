"""hothog — find the imports hogging your hot path, and the single best place to defer each one.

Public API:
    Config   — describe a triage run (entry, first-party packages, tuning).
    Triage   — run it; returns a Report.
    Report   — the ranked backlog of deferrals.
"""

from __future__ import annotations

from .analysis import Report, Row, Triage
from .config import Config

__all__ = ["Config", "Triage", "Report", "Row", "__version__"]

__version__ = "0.1.0"
