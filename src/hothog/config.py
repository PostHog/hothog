"""Run configuration for a hothog triage.

Everything that used to be hard-wired to one codebase (the Django settings module, the
set of "first-party" packages, the test-only libraries) lives here so the tool can point
at any project's hot path, not just the one it was extracted from.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    """A single triage run.

    `entry` is an import string ``"module:callable"`` invoked under the import hook
    (default ``"django:setup"`` — the original use case). `first_party` is the set of
    top-level packages whose modules are scored individually (everything else is an
    external library, aggregated to its top-level package).
    """

    importtime_log: str
    entry: str = "django:setup"
    django_settings: str | None = None
    import_extra: list[str] = field(default_factory=list)
    root_override: list[str] = field(default_factory=list)
    first_party: tuple[str, ...] = ()
    test_only: frozenset[str] = frozenset()
    env: dict[str, str] = field(default_factory=dict)
    top: int = 35
    min_removable: float = 15.0
    use_grimp: bool = True
    compare: str | None = None

    @property
    def entry_module(self) -> str:
        """The module imported to reach the entry callable, e.g. ``"django"``."""
        return self.entry.split(":", 1)[0]

    def is_first_party(self, module: str) -> bool:
        return module.split(".")[0] in self.first_party
