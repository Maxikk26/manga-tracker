"""Executable form of the source-client/discovery/storage/notifier/seed
import boundary (CLAUDE.md, design.md rule set). A violation MUST fail here,
not just in review."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "manga_tracker"

# top-level package -> other top-level packages it must never import
DIRECTIONAL_RULES = {
    "sources": {"storage", "discovery", "notifier", "seed"},
    "notifier": {"storage", "sources", "discovery", "seed"},
    "storage": {"sources", "discovery", "notifier", "seed"},
    "discovery": {"sources.manganato", "notifier.telegram"},
    "seed": {"sources.manganato", "notifier.telegram"},
}

# third-party module -> the only file (relative to manga_tracker/) allowed to import it
CONFINEMENT_RULES = {
    "curl_cffi": "sources/manganato/transport.py",
    "bs4": "sources/manganato/parsing.py",
    "apscheduler": "scheduler.py",
    "urllib.request": "notifier/telegram.py",
}
SQLITE_MODULE = "sqlite3"
SQLITE_PACKAGE = "storage"

# The composition root is the ONE place allowed to wire layers together: it
# builds the transport, the client, the connection and hands them to the
# layers. Naming it explicitly matters, because DIRECTIONAL_RULES is keyed on
# subpackage names, so any module sitting at the top level of the package is
# outside every rule by accident. Without this list, dropping a `detection.py`
# next to cli.py would silently escape the whole boundary.
COMPOSITION_ROOT = {"cli.py", "__main__.py"}

# Concrete implementations only the composition root may name.
CONCRETE_IMPLEMENTATIONS = {"sources.manganato", "notifier.telegram"}


def _imports(path: Path) -> set[str]:
    """Absolute module names imported by this file.

    Relative imports are resolved against the file's own package so that a rule
    cannot be evaded by writing `from ..sources.manganato import x` instead of
    the absolute form.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    here = [PKG.name, *path.relative_to(PKG).parent.parts]
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    modules.add(node.module)
            else:
                base = here[: len(here) - (node.level - 1)]
                parts = [*base, node.module] if node.module else base
                modules.add(".".join(parts))
    return modules


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _internal(module: str) -> str | None:
    """Package-relative form of an intra-package import, or None if external.

    Intra-package imports are written `manga_tracker.sources.manganato`, while
    the rule tables are keyed on the package-relative `sources.manganato`.
    Without stripping the prefix every directional rule matches nothing and the
    whole boundary check passes vacuously.
    """
    if module == PKG.name:
        return ""
    if module.startswith(PKG.name + "."):
        return module[len(PKG.name) + 1 :]
    return None


def test_directional_boundaries():
    violations = []
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(PKG).as_posix()
        forbidden = DIRECTIONAL_RULES.get(rel.split("/")[0])
        if not forbidden:
            continue
        for module in _imports(path):
            internal = _internal(module)
            if internal is None:
                continue
            if any(_matches(internal, prefix) for prefix in forbidden):
                violations.append(f"{rel} imports forbidden module {module!r}")
    assert not violations, "\n".join(violations)


def test_only_the_composition_root_wires_layers_together():
    """Top-level modules are outside DIRECTIONAL_RULES, so name the exception.

    `cli.py` legitimately imports the concrete client, storage and seed at
    once — that is what a composition root is for. But the rule table is keyed
    on subpackage names, so *every* top-level module inherits that freedom by
    accident. This pins the exemption to the composition root alone.
    """
    violations = []
    for path in PKG.glob("*.py"):
        rel = path.name
        if rel in COMPOSITION_ROOT or rel == "__init__.py":
            continue
        for module in _imports(path):
            internal = _internal(module)
            if internal is None:
                continue
            if any(_matches(internal, prefix) for prefix in CONCRETE_IMPLEMENTATIONS):
                violations.append(
                    f"{rel} imports concrete {module!r}; only {sorted(COMPOSITION_ROOT)} may"
                )
    assert not violations, "\n".join(violations)


def test_directional_rules_actually_fire():
    """Guards the guard: a rule table that matches nothing passes vacuously.

    This is not hypothetical — the first version of this file compared absolute
    import names against package-relative prefixes, so no directional rule
    could ever match and the boundary was unenforced while the suite was green.
    """
    for package, forbidden in DIRECTIONAL_RULES.items():
        for prefix in forbidden:
            offender = f"{PKG.name}.{prefix}"
            assert _matches(_internal(offender), prefix), (
                f"rule {package} -> {prefix} cannot match a real import of {offender}"
            )


def test_third_party_confinement():
    violations = []
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(PKG).as_posix()
        for module in _imports(path):
            if _matches(module, SQLITE_MODULE) and not rel.startswith(SQLITE_PACKAGE + "/"):
                violations.append(f"{rel} imports confined module {module!r}")
                continue
            for confined, allowed_file in CONFINEMENT_RULES.items():
                if _matches(module, confined) and rel != allowed_file:
                    violations.append(f"{rel} imports confined module {module!r}, only {allowed_file} may")
    assert not violations, "\n".join(violations)
