"""The Kitsu importer (docs/spec-importador-kitsu.md v1.3).

A contract-only consumer: it talks to `catalogue.contracts` and
`sources.contracts` and never to a concrete implementation, so it cannot
learn that a field is called `abbreviatedTitles` or how the source
enumerates its catalogue. `cli.py` is the only place those concretes are
wired in (KIT Seccion "Donde vive", enforced by tests/test_architecture.py).
"""
