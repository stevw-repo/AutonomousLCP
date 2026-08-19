"""Every name in `__all__` must actually be importable from the package root.

A name listed but never imported passes every test that imports from a submodule,
and then fails at runtime inside a built image. That happened on 2026-08-19: the
gazette client was added to `__all__` without its import, the suite stayed green
because the tests import the submodule directly, and the acquisition worker
crashed on start with an ImportError.
"""

from __future__ import annotations

import asklegal_source_connectors


def test_every_exported_name_is_importable() -> None:
    """`__all__` is a promise about the package root, not a wish list."""
    missing = [
        name for name in asklegal_source_connectors.__all__
        if not hasattr(asklegal_source_connectors, name)
    ]

    assert missing == []


def test_nothing_public_is_left_out_of_all() -> None:
    """A public name absent from `__all__` is invisible to `from … import *`."""
    exported = set(asklegal_source_connectors.__all__)
    module_type = type(asklegal_source_connectors)
    public = {
        name
        for name in vars(asklegal_source_connectors)
        if not name.startswith("_")
        and not isinstance(getattr(asklegal_source_connectors, name), module_type)
    }

    assert public - exported == set()
