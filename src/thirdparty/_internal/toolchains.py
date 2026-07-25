"""Toolchain provider selection.

Toolchains are ordinary recipes. A provider recipe overrides ``toolchain_settings()``
(which is also the discovery marker) to write its compiler fields into the target
settings, constrains itself via ``validate()``, and publishes a
``ToolchainInfo`` contract from ``package_info()``. ``--compiler <name>`` pins a
provider; without it the ``default_toolchain`` recipe is tried first, then the rest
alphabetically, taking the first whose ``validate()`` accepts the target.
"""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from thirdparty._internal import loader
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.profile import BuildProfile
from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty._internal.model.state import RecipeState
from thirdparty._internal.model.toolchain import find_toolchain  # noqa: F401  (re-export)
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration


def is_toolchain(recipe_cls: type[RecipeBase]) -> bool:
    return recipe_cls.toolchain_settings is not RecipeBase.toolchain_settings


@lru_cache(maxsize=None)
def _candidates(recipes_root: Path) -> tuple[tuple[str, type[RecipeBase]], ...]:
    found: list[tuple[str, type[RecipeBase]]] = []
    for path in sorted(recipes_root.iterdir()):
        if not (path / "recipe.py").is_file():
            continue
        cls = loader.try_load_recipe_class(recipes_root, path.name)
        if cls is not None and is_toolchain(cls):
            found.append((path.name, cls))
    found.sort(key=lambda item: (not item[1].default_toolchain, item[0]))
    return tuple(found)


def _probe(cls: type[RecipeBase], name: str, recipes_root: Path, profile: BuildProfile) -> RecipeBase:
    recipe = cls()
    recipe.version = loader.resolve_version(cls)
    recipe.folders.set_recipe(recipes_root / name)
    settings = profile.to_settings()
    # The probe stands in for this recipe acting as the selected provider, so validate()
    # can distinguish its provider role from its ingredient role (see the msvc recipe).
    settings.compiler_recipe = name
    recipe._state = RecipeState(
        dependencies=RecipeDependencies(OrderedDict()),
        build_context=False,
        settings=settings,
        settings_build=profile.build_machine().to_settings(),
        conf=Conf(),
        info=Info(set_defaults=True))
    return recipe


@lru_cache(maxsize=None)
def select_toolchain(profile: BuildProfile, recipes_root: Path) -> str:
    candidates = dict(_candidates(recipes_root))
    if profile.compiler is not None:
        cls = candidates.get(profile.compiler)
        if cls is None:
            known = ", ".join(candidates)
            raise RecipeException(
                f"--compiler {profile.compiler}: no such toolchain recipe "
                f"(known toolchains: {known})")
        try:
            _probe(cls, profile.compiler, recipes_root, profile).validate()
        except RecipeInvalidConfiguration as exc:
            raise RecipeException(
                f"--compiler {profile.compiler} does not support this target: {exc}")
        return profile.compiler

    rejections: list[str] = []
    for name, cls in candidates.items():
        try:
            _probe(cls, name, recipes_root, profile).validate()
        except RecipeInvalidConfiguration as exc:
            rejections.append(f"  {name}: {exc}")
            continue
        return name
    target = profile.to_settings()
    detail = "\n".join(rejections) or "  (no toolchain recipes found)"
    raise RecipeException(f"No toolchain supports target {target.os}-{target.arch}:\n{detail}")


def resolve_settings(profile: BuildProfile, recipes_root: Path) -> Settings:
    """Complete target settings for *profile*: base platform + the selected provider's
    ``toolchain_settings()``.

    Selection failure is tolerated (base settings without compiler fields): probes for
    package ids, listing, and archiving must work on recipe trees without toolchain
    recipes. The ``build`` command surfaces selection errors up-front instead.
    """
    settings = profile.to_settings()
    try:
        name = select_toolchain(profile, recipes_root)
    except RecipeException:
        return settings
    cls = dict(_candidates(recipes_root))[name]
    _probe(cls, name, recipes_root, profile).toolchain_settings(settings)
    settings.compiler_recipe = name
    settings.compiler_cxx_standard = settings.compiler_cxx_standard or "17"
    return settings


@lru_cache(maxsize=None)
def toolchain_layer(recipes_root: Path, provider: str, profile: BuildProfile) -> frozenset[str]:
    """The provider recipe plus its transitive declared requirements.

    Nothing in this set gets a toolchain injected into it - these recipes ARE the
    toolchain, and injecting into them would create dependency cycles. The walk uses
    the recipes' declared configure()/requirements() only (no injection).
    """
    names: set[str] = set(name for name, _ in _candidates(recipes_root))
    pending = [provider]
    while pending:
        name = pending.pop()
        if name in names and name != provider:
            continue
        names.add(name)
        cls = loader.try_load_recipe_class(recipes_root, name)
        if cls is None:
            continue
        recipe = _probe(cls, name, recipes_root, profile)
        try:
            recipe.configure()
            recipe.requirements()
        except Exception:
            continue
        pending.extend(str(r.name) for r in recipe._requires if str(r.name) not in names)
    return frozenset(names)


def injectable(recipe: RecipeBase) -> bool:
    """Whether *recipe* should get the selected toolchain provider injected."""
    provider = recipe.settings.compiler_recipe
    if not provider:
        return False
    if is_toolchain(type(recipe)):
        return False
    try:
        recipes_root = recipe.folders.recipe.parent
    except RecipeException:
        return False
    profile = BuildProfile(
        build_type=str(recipe.settings.build_type),
        target_os=str(recipe.settings.os),
        target_arch=str(recipe.settings.arch))
    return getattr(recipe, "name", None) not in toolchain_layer(recipes_root, provider, profile)
