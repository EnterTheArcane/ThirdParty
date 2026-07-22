import sys
from functools import total_ordering
from typing import Any


def _ref_name(other: Any) -> str | None:
    """Best-effort recipe name for *other*, so a reference can be compared against a bare
    name string, another ``RecipeReference``, or a recipe object (anything exposing ``name``)
    directly. Returns ``None`` when *other* names no recipe."""
    if isinstance(other, str):
        return other
    # A RecipeReference, a recipe object, or anything else carrying a recipe name.
    return getattr(other, "name", None)


@total_ordering
class RecipeReference:
    """Reference to a recipe by name.

    This system has exactly one recipe per name, so the name alone is the identity. The name
    is interned so comparisons are cheap, and a reference compares equal to anything naming the
    same recipe -- a bare name string, another ``RecipeReference``, or a recipe object.
    """

    def __init__(self, name: str):
        self._name: str = sys.intern(name)

    @property
    def name(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return self._name

    def __str__(self) -> str:
        return self._name

    def __eq__(self, other: Any) -> bool:
        return self._name == _ref_name(other)

    def __lt__(self, other: Any) -> bool:
        name = _ref_name(other)
        if name is None:
            return NotImplemented
        return self._name < name

    def __hash__(self) -> int:
        return hash(self._name)
