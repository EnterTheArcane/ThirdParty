import types
from functools import cache
from typing import (
    Any, ClassVar, Literal, Union, get_args, get_origin, get_type_hints,
)

from thirdparty.errors import RecipeException


_ANY_OPTION_VALUE = "ANY"
_SCALAR_OPTION_TYPES = {str, int, float, Any}


class RecipeOptions:
    """Typing stub that recipe option classes inherit from.

    Provides the static signatures for the runtime ``Options`` API so type checkers accept
    ``self.options.get_safe(...)`` etc. At runtime ``self.options`` is an ``Options`` instance.
    """

    __defaults__: ClassVar[dict[str, Any]]
    __possible_values__: ClassVar[dict[str, list[Any]]]

    def get_safe(self, field: str, default: Any = None) -> Any:
        ...

    def items(self) -> list[Any]:
        ...

    def __contains__(self, option: object) -> bool:
        ...


def _is_none_type(annotation: Any) -> bool:
    return annotation is None or annotation is type(None)


def _append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def _derive_possible_values(name: str, annotation: Any) -> list[Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if _is_none_type(annotation):
        return [None]
    if annotation is bool:
        return [True, False]
    if origin is Literal:
        return list(args)
    if annotation in _SCALAR_OPTION_TYPES:
        return [_ANY_OPTION_VALUE]
    if origin in (types.UnionType, Union):
        result: list[Any] = []
        for arg in args:
            for value in _derive_possible_values(name, arg):
                _append_unique(result, value)
        if None in result:
            result.remove(None)
            result.insert(0, None)
        return result

    raise RecipeException(
        f"Unsupported typed option '{name}' annotation {annotation!r}. "
        "Supported annotations are bool, Literal, str, int, float, Any, "
        "and optional scalar forms like str | None")


def _typed_options_class(cls: type[Any]) -> type[Any] | None:
    from thirdparty._internal.model.recipe import RecipeBase
    for base in getattr(cls, "__orig_bases__", ()):
        if get_origin(base) is RecipeBase:
            args = get_args(base)
            if args and args[0] is not Any:
                return args[0]
    return None


@cache
def _derive_options(options_cls: type[Any]) -> tuple[dict[str, list[Any]], dict[str, Any]]:
    annotations = get_type_hints(options_cls, include_extras=True)
    explicit_defaults = getattr(options_cls, "__defaults__", {})
    explicit_possible_values = getattr(options_cls, "__possible_values__", {})
    options: dict[str, list[Any]] = {}
    defaults: dict[str, Any] = {}

    for name, annotation in annotations.items():
        if name.startswith("_"):
            continue
        options[name] = explicit_possible_values.get(name, _derive_possible_values(name, annotation))
        if name in options_cls.__dict__:
            defaults[name] = getattr(options_cls, name)
        elif name in explicit_defaults:
            defaults[name] = explicit_defaults[name]

    return options, defaults


class Options:
    """Runtime holder for a recipe's option values.

    Values are stored as their real Python types (``bool``/``int``/``str``/``None``/``Literal``
    members) derived from the recipe's typed options class. ``definition`` maps each option name
    to its list of allowed values (a bare ``["ANY"]`` marks an unconstrained scalar); when
    ``definition`` is ``None`` the options are unconstrained (any name/value allowed).
    """

    def __init__(self, definition: dict[str, list[Any]] | None = None,
                 values: dict[str, Any] | None = None):
        if definition is None:
            self._constrained = False
            self._possible: dict[str, list[Any]] = {}
        else:
            self._constrained = True
            self._possible = {str(name): list(possible) for name, possible in definition.items()}
        self._values: dict[str, Any] = {}
        if values:
            for name, value in values.items():
                if value is None:
                    continue  # a None value means "no value", same as not set
                self._set(str(name), value)

    @classmethod
    def from_recipe(cls, recipe_cls: type[Any]) -> "Options":
        typed = _typed_options_class(recipe_cls)
        if typed is None:
            return cls({}, {})
        definition, defaults = _derive_options(typed)
        return cls(definition, defaults)

    @staticmethod
    def validate_recipe_class(recipe_cls: type[Any]) -> None:
        """Eagerly derive (and thereby validate) a recipe's typed options at class definition."""
        typed = _typed_options_class(recipe_cls)
        if typed is not None:
            _derive_options(typed)

    def _check_valid_value(self, name: str, value: Any) -> None:
        possible = self._possible.get(name)
        if possible is None:  # unconstrained
            return
        if value in possible:
            return
        if value is not None and _ANY_OPTION_VALUE in possible:
            return
        raise RecipeException(
            "'%s' is not a valid 'options.%s' value.\nPossible values are %s"
            % (value, name, possible))

    def _ensure_exists(self, name: str) -> None:
        if self._constrained and name not in self._possible:
            raise RecipeException(
                "option '%s' doesn't exist\nPossible options are %s"
                % (name, list(self._possible.keys())))

    def _set(self, name: str, value: Any) -> None:
        self._ensure_exists(name)
        self._check_valid_value(name, value)
        self._values[name] = value

    def get_safe(self, field: str, default: Any = None) -> Any:
        return self._values.get(field, default)

    def items(self) -> list[Any]:
        return sorted(self._values.items())

    def dumps(self) -> str:
        """Multiline ``name=value`` representation, alphabetical, skipping unset values."""
        return "\n".join("%s=%s" % (name, value) for name, value in sorted(self._values.items()))

    def __repr__(self) -> str:
        return self.dumps()

    def __contains__(self, option: object) -> bool:
        return str(option) in self._values

    def __getattr__(self, name: str) -> Any:
        assert name[0] != "_", "ERROR %s" % name
        self._ensure_exists(name)
        return self._values.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name[0] == "_":
            return super().__setattr__(name, value)
        self._set(name, value)

    def __delattr__(self, name: str) -> None:
        self._ensure_exists(name)
        self._values.pop(name, None)
