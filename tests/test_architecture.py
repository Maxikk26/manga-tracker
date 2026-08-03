"""Executable form of the source-client/discovery/storage/notifier/seed
import boundary (CLAUDE.md, design.md rule set). A violation MUST fail here,
not just in review."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "manga_tracker"

# top-level package -> other top-level packages it must never import
DIRECTIONAL_RULES = {
    "sources": {"storage", "discovery", "notifier", "seed", "catalogue", "importer"},
    "notifier": {"storage", "sources", "discovery", "seed", "catalogue", "importer"},
    "storage": {"sources", "discovery", "notifier", "seed", "catalogue", "importer"},
    "discovery": {"sources.manganato", "notifier.telegram"},
    "seed": {"sources.manganato", "notifier.telegram"},
    # catalogue is not downstream of the source client, nor of storage,
    # discovery, notifier, seed or its own consumer (design D8, CAT-6).
    "catalogue": {"storage", "discovery", "notifier", "seed", "sources", "importer"},
    # The importer reads both contracts and writes through storage — that is
    # its job. What it must never do is name a concrete implementation: the
    # day it does, swapping Kitsu for AniList stops being a one-line change in
    # cli.py (design D8, IMP-13).
    "importer": {"catalogue.kitsu", "catalogue.transport", "sources.manganato"},
}

# third-party module -> the file(s) (relative to manga_tracker/) allowed to import it
CONFINEMENT_RULES = {
    "curl_cffi": frozenset({"sources/manganato/transport.py"}),
    "bs4": frozenset({"sources/manganato/parsing.py"}),
    "apscheduler": frozenset({"scheduler.py"}),
    # catalogue/transport.py joins notifier/telegram.py: both are documented
    # JSON HTTPS calls with no anti-bot need (design D1).
    "urllib.request": frozenset({"notifier/telegram.py", "catalogue/transport.py"}),
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
#
# `catalogue.kitsu` and `catalogue.transport` join the list with `import-kitsu`.
# KIT's promise is that replacing Kitsu costs "una linea en cli.py", and that is
# only true while the class is named in exactly one place - the day a top-level
# module constructs it, the line becomes two and nobody finds out until the
# catalogue closes. `catalogue.transport` is listed for the same reason and is
# one name beyond design D8's literal list: it is a concrete too, and the
# importer is already forbidden from naming either.
CONCRETE_IMPLEMENTATIONS = {
    "sources.manganato",
    "notifier.telegram",
    "catalogue.kitsu",
    "catalogue.transport",
}

# word (lowercased) -> the only directory allowed to say it.
#
# Source knowledge leaks as vocabulary long before it leaks as an import, and
# the AST check above structurally cannot see it: `"/sitemap.xml"` is a string,
# not an import. The sitemap is manganato's own mechanism for publishing its
# catalogue — a caller asks for known slugs and must no more learn that a
# sitemap exists than it learns how a chapter URL is assembled. The day another
# module names one, it has started depending on how this source works.
VOCABULARY_RULES = {
    "sitemap": "sources/manganato/",
    "shard": "sources/manganato/",
}


def _imports(path: Path, pkg_root: Path) -> set[str]:
    """Absolute module names imported by this file.

    Relative imports are resolved against the file's own package so that a rule
    cannot be evaded by writing `from ..sources.manganato import x` instead of
    the absolute form.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    here = [pkg_root.name, *path.relative_to(pkg_root).parent.parts]
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


def _internal(module: str, pkg_name: str) -> str | None:
    """Package-relative form of an intra-package import, or None if external.

    Intra-package imports are written `manga_tracker.sources.manganato`, while
    the rule tables are keyed on the package-relative `sources.manganato`.
    Without stripping the prefix every directional rule matches nothing and the
    whole boundary check passes vacuously.
    """
    if module == pkg_name:
        return ""
    if module.startswith(pkg_name + "."):
        return module[len(pkg_name) + 1 :]
    return None


# The three scanners below take the package root as an argument rather than
# closing over PKG, and that is the whole of design D8's mechanism. Run against
# `manga_tracker/` they are the boundary check; run against a throwaway tree of
# deliberate violations they prove the check can still see one. A rule table
# that has quietly stopped matching passes both a real package with no
# violations and a review, which is exactly how this repo once shipped an
# unenforced boundary with a green suite.


def _directional_violations(pkg_root: Path) -> list[str]:
    violations = []
    for path in sorted(pkg_root.rglob("*.py")):
        rel = path.relative_to(pkg_root).as_posix()
        forbidden = DIRECTIONAL_RULES.get(rel.split("/")[0])
        if not forbidden:
            continue
        for module in sorted(_imports(path, pkg_root)):
            internal = _internal(module, pkg_root.name)
            if internal is None:
                continue
            if any(_matches(internal, prefix) for prefix in forbidden):
                violations.append(f"{rel} imports forbidden module {module!r}")
    return violations


def _confinement_violations(pkg_root: Path) -> list[str]:
    violations = []
    for path in sorted(pkg_root.rglob("*.py")):
        rel = path.relative_to(pkg_root).as_posix()
        for module in sorted(_imports(path, pkg_root)):
            if _matches(module, SQLITE_MODULE) and not rel.startswith(SQLITE_PACKAGE + "/"):
                violations.append(f"{rel} imports confined module {module!r}")
                continue
            for confined, allowed_files in CONFINEMENT_RULES.items():
                if _matches(module, confined) and rel not in allowed_files:
                    violations.append(
                        f"{rel} imports confined module {module!r}, only {sorted(allowed_files)} may"
                    )
    return violations


def _composition_root_violations(pkg_root: Path) -> list[str]:
    violations = []
    for path in sorted(pkg_root.glob("*.py")):
        rel = path.name
        if rel in COMPOSITION_ROOT or rel == "__init__.py":
            continue
        for module in sorted(_imports(path, pkg_root)):
            internal = _internal(module, pkg_root.name)
            if internal is None:
                continue
            if any(_matches(internal, prefix) for prefix in CONCRETE_IMPLEMENTATIONS):
                violations.append(
                    f"{rel} imports concrete {module!r}; only {sorted(COMPOSITION_ROOT)} may"
                )
    return violations


def test_directional_boundaries():
    violations = _directional_violations(PKG)
    assert not violations, "\n".join(violations)


def test_only_the_composition_root_wires_layers_together():
    """Top-level modules are outside DIRECTIONAL_RULES, so name the exception.

    `cli.py` legitimately imports the concrete client, storage and seed at
    once — that is what a composition root is for, and `import-kitsu` added two
    more concretes to what it wires. But the rule table is keyed on subpackage
    names, so *every* top-level module inherits that freedom by accident. This
    pins the exemption to the composition root alone.
    """
    violations = _composition_root_violations(PKG)
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
            assert _matches(_internal(offender, PKG.name), prefix), (
                f"rule {package} -> {prefix} cannot match a real import of {offender}"
            )


def test_boundary_check_flags_an_injected_violation(tmp_path):
    """Design D8, and the permanent form of what every phase did by hand.

    `test_directional_rules_actually_fire` proves a prefix *string* can match a
    module name. It would not notice a walker that never reaches the new files,
    a rule keyed on a directory that does not exist, or a confinement set
    widened until it allows everyone. So the scanners run here against a
    package-shaped tree built entirely out of violations, and every rule this
    change added has to report its own.

    The tree is named `manga_tracker` because the checks strip that prefix to
    reach the package-relative names the rule tables use; a differently named
    root would make every import look external and the test would pass
    vacuously - the precise failure it exists to prevent.
    """
    root = tmp_path / PKG.name
    probes = {
        # Directional: the catalogue is not downstream of storage (CAT-6) ...
        "catalogue/probe.py": "from manga_tracker.storage import db\n",
        # ... and the importer may know the contracts, never the concrete
        # behind them (IMP-13).
        "importer/probe.py": "import manga_tracker.catalogue.kitsu\n",
        # Confinement: manganato's anti-bot transport stays in manganato ...
        "catalogue/probe2.py": "import curl_cffi\n",
        # ... and widening `urllib.request` to two homes must not open it to a
        # third (design D1).
        "sources/probe.py": "import urllib.request\n",
        # Composition root: only cli.py and __main__.py may name a concrete.
        "probe.py": "from manga_tracker.catalogue.kitsu import KitsuCatalogue\n",
        # The same import in the exempt file, which must NOT be reported -
        # an exemption that flagged its own holder would be a rule nobody
        # could satisfy, and one that exempted everyone would be no rule.
        "cli.py": "from manga_tracker.catalogue.kitsu import KitsuCatalogue\n",
    }
    for relative, source in probes.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    assert _directional_violations(root) == [
        "catalogue/probe.py imports forbidden module 'manga_tracker.storage'",
        "importer/probe.py imports forbidden module 'manga_tracker.catalogue.kitsu'",
    ]
    assert _confinement_violations(root) == [
        "catalogue/probe2.py imports confined module 'curl_cffi', "
        "only ['sources/manganato/transport.py'] may",
        "sources/probe.py imports confined module 'urllib.request', "
        "only ['catalogue/transport.py', 'notifier/telegram.py'] may",
    ]
    assert _composition_root_violations(root) == [
        "probe.py imports concrete 'manga_tracker.catalogue.kitsu'; "
        "only ['__main__.py', 'cli.py'] may"
    ]


def test_source_vocabulary_stays_inside_its_own_client():
    """The boundary as words, not just as imports.

    A module that never imports `sources.manganato` but prints "fetching shard
    3 of 10" has still learned how manganato works, and a change of source
    would leave that string lying. Progress is therefore reported as `(unit,
    total)` integers, and the naming stays where the knowledge is.
    """
    violations = []
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(PKG).as_posix()
        text = path.read_text(encoding="utf-8").lower()
        for word, home in VOCABULARY_RULES.items():
            if word in text and not rel.startswith(home):
                violations.append(f"{rel} says {word!r}; only {home} may — that is source knowledge")
    assert not violations, "\n".join(violations)


def test_third_party_confinement():
    violations = _confinement_violations(PKG)
    assert not violations, "\n".join(violations)
