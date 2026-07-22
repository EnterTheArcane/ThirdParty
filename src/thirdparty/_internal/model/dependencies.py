from collections import OrderedDict
from typing import Any

from thirdparty.errors import RecipeException


class UserRequirementsDict:
    """ user facing dict to allow access of dependencies by name
    """

    def __init__(self, data: Any, require_filter: Any = None):
        self._data = data  # dict-like
        self._require_filter = require_filter  # dict {trait: value} for requirements

    def filter(self, require_filter: Any) -> UserRequirementsDict:
        def filter_fn(require: Any) -> bool:
            for k, v in require_filter.items():
                if getattr(require, k) != v:
                    return False
            return True

        data = OrderedDict((k, v) for k, v in self._data.items() if filter_fn(k))
        return UserRequirementsDict(data, require_filter)

    def __bool__(self) -> bool:
        return bool(self._data)

    def get(
        self,
        ref: str,
        build: Any = None,
        **kwargs: Any) -> Any:
        return self._get(ref, build, **kwargs)[1]

    def _get(
        self,
        ref: str,
        build: Any = None,
        **kwargs: Any) -> tuple[Any, Any]:
        if build is None:
            current_filters: dict[str, Any] = self._require_filter or {}
            if "build" not in current_filters:
                # By default we search in the "host" context
                kwargs["build"] = False
        else:
            kwargs["build"] = build
        data = self.filter(kwargs)
        ret: list[tuple[Any, Any]] = []
        for require, value in data.items():
            if require.ref == ref:  # RecipeReference == bare name string
                ret.append((require, value))
        if len(ret) > 1:
            filters_repr = data._require_filter or "{}"
            requires = "\n".join([f"- {require}" for require, _ in ret])
            raise RecipeException(
                "There are more than one requires matching the specified filters:"
                f" {filters_repr}\n{requires}")
        if not ret:
            raise KeyError(f"'{ref}' not found in the dependency set")

        key, value = ret[0]
        return key, value

    def __getitem__(self, name: str) -> Any:
        return self.get(name)

    def __delitem__(self, name: str):
        r, _ = self._get(name)
        del self._data[r]

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __contains__(self, item: str) -> bool:
        try:
            self.get(item)
            return True
        except KeyError:
            return False
        except RecipeException:
            # RecipeException is raised when there are more than one matching the filters
            # so it's definitely in the dict
            return True

    def of(
        self,
        ref: str,
        build: Any = None,
        **kwargs: Any) -> tuple[Any, Any]:
        # TODO: come up with a better name
        return self._get(ref, build, **kwargs)


class RecipeDependencies(UserRequirementsDict):
    def filter(self, require_filter: Any, remove_system: bool = True) -> RecipeDependencies:
        # FIXME: Copy of hte above, to return RecipeDependencies class object
        def filter_fn(require: Any) -> bool:
            for k, v in require_filter.items():
                if getattr(require, k) != v:
                    return False
            return True

        data = OrderedDict((k, v) for k, v in self._data.items() if filter_fn(k))
        return RecipeDependencies(data, require_filter)

    def transitive_requires(self, other: RecipeDependencies) -> RecipeDependencies:
        """
        :type other: RecipeDependencies
        """
        data: "OrderedDict[Any, Any]" = OrderedDict()
        for _k, v in self._data.items():
            for otherk, otherv in other._data.items():
                if v == otherv:
                    data[otherk] = v  # Use otherk to respect original replace_requires
        return RecipeDependencies(data)

    @property
    def topological_sort(self) -> RecipeDependencies:
        # Return first independent nodes, final ones are the more direct deps
        result: "OrderedDict[Any, Any]" = OrderedDict()
        opened: "OrderedDict[Any, Any]" = self._data.copy()

        while opened:
            opened_values: set[Any] = set(opened.values())
            new_opened: "OrderedDict[Any, Any]" = OrderedDict()
            for req, recipe in opened.items():
                deps_in_opened = any(d in opened_values for d in recipe.dependencies.values())
                if deps_in_opened:
                    new_opened[req] = recipe  # keep it for next iteration
                else:
                    result[req] = recipe  # No dependencies in open set!

            opened = new_opened
        return RecipeDependencies(result)

    @property
    def direct_host(self) -> RecipeDependencies:
        return self.filter({"build": False, "direct": True, "skip": False})

    @property
    def direct_build(self) -> RecipeDependencies:
        return self.filter({"build": True, "direct": True})

    @property
    def host(self) -> RecipeDependencies:
        return self.filter({"build": False, "skip": False})

    @property
    def build(self) -> RecipeDependencies:
        return self.filter({"build": True})


def get_transitive_requires(consumer: Any, dependency: Any) -> RecipeDependencies:
    """ the transitive requires that we need are the consumer ones, not the current dependencey
    ones, so we get the current ones, then look for them in the consumer, and return those
    """
    # The build dependencies cannot be transitive in generators like CMakeDeps,
    # even if users make them visible
    pkg_deps = dependency.dependencies.filter({"direct": True, "build": False})
    # First we filter the skipped dependencies
    result = consumer.dependencies.filter({"skip": False})
    # and we keep those that are really dependencies of the current package
    result = result.transitive_requires(pkg_deps)
    return result
