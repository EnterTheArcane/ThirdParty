from abc import ABC
from collections import OrderedDict
from typing import Any, Generic, TypeVar, cast

from thirdparty._internal.graph import CONTEXT_BUILD, CONTEXT_HOST
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.folders import Folders
from thirdparty._internal.model.options import Options
from thirdparty._internal.model.refs import RecipeReference
from thirdparty._internal.model.requires import Requirement, ToolRequirement
from thirdparty._internal.model.settings import Settings
from thirdparty._internal.model.state import RecipeState
from thirdparty._internal.model.version import Version
from thirdparty._internal.output import Output
from thirdparty._internal.util.detect import detect_settings
from thirdparty.errors import RecipeException


TOptions = TypeVar("TOptions", default=Any)

__all__ = ["RecipeBase", "RecipeState"]


class RecipeBase(ABC, Generic[TOptions]):
    name: str
    version: str
    license: str | tuple[str, ...]

    options: TOptions

    win_bash: bool | None = None

    folders: Folders

    _requires: list[Requirement]
    _state: RecipeState

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)

        Options.validate_recipe_class(cls)

        license = cls.__dict__.get("license")
        if isinstance(license, str):
            cls.license = (license,)
        elif license is not None:
            cls.license = tuple(license)

    def __init__(self):
        self.folders = Folders()

        self._requires: list[Requirement] = []

        cast(Any, self).options = Options.from_recipe(type(self))
        settings = detect_settings()
        self._state = RecipeState(
            dependencies=RecipeDependencies(OrderedDict()),
            build_context=False,
            settings=settings,
            settings_build=settings,
            conf=Conf(),
            info=Info(set_defaults=True))
        self.env_scripts: dict[str, list[str]] = {}  # Accumulate the env scripts generated in order

    def requires(self, ref: str):
        req = Requirement(RecipeReference(ref), headers=True, libs=True, run=False)
        if any(r == req for r in self._requires):  # equality == (name, build)
            raise RecipeException(f"Duplicated requirement: {req.name}")
        self._requires.append(req)

    def requires_tool(self, ref: str):
        req = ToolRequirement(RecipeReference(ref), run=True)
        if any(r == req for r in self._requires):  # equality == (name, build)
            raise RecipeException(f"Duplicated requirement: {req.name}")
        self._requires.append(req)

    @property
    def output(self) -> Output:
        # an output stream (writeln, info, warn error)
        scope = self.name or ""
        return Output(scope=scope)

    @property
    def settings(self) -> Settings:
        return self._state.settings

    @property
    def settings_build(self) -> Settings:
        return self._state.settings_build

    @property
    def conf(self) -> Conf:
        return self._state.conf

    @property
    def info(self) -> Info:
        return self._state.info

    @property
    def context(self) -> str:
        return CONTEXT_BUILD if self._state.build_context else CONTEXT_HOST

    @property
    def is_build_context(self) -> bool:
        return self._state.build_context

    @property
    def dependencies(self) -> RecipeDependencies:
        return self._state.dependencies

    def latest_version(self) -> Version | None: ...
    def configure(self): ...
    def validate(self): ...
    def requirements(self): ...
    def package_id(self) -> str | None: ...
    def source(self): ...
    def generate(self): ...
    def build(self): ...
    def package(self): ...
    def package_info(self): ...

    def __repr__(self):
        return self.name or ""
