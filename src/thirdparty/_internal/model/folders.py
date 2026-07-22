import os
from pathlib import Path

from thirdparty.errors import RecipeException


def _folder_path(base_folder: str | None) -> Path:
    if base_folder is None:
        raise RecipeException("Base folder is not set, cannot compute the final folder path")
    return Path(os.path.normpath(base_folder))


class Folders:
    _recipe: Path | None

    _base_source: str | None
    _base_build: str | None
    _base_package: str | None
    _base_generators: str | None

    def __init__(self):
        self._recipe: Path | None = None
        self._base_source: str | None = None
        self._base_build: str | None = None
        self._base_package: str | None = None
        self._base_generators: str | None = None

    @property
    def recipe(self) -> Path:
        if self._recipe is None:
            raise RecipeException("Recipe folder is not set, cannot compute the final folder path")
        return self._recipe

    def set_recipe(self, folder: str | Path) -> None:
        self._recipe = Path(folder)

    @property
    def source(self) -> Path:
        return _folder_path(self._base_source)

    def set_base_source(self, folder: str | None) -> None:
        self._base_source = folder

    @property
    def build(self) -> Path:
        return _folder_path(self._base_build)

    def set_base_build(self, folder: str | None) -> None:
        self._base_build = folder

    @property
    def base_package(self) -> str | None:
        return self._base_package

    def set_base_package(self, folder: str | None) -> None:
        self._base_package = folder

    @property
    def package(self) -> Path:
        return _folder_path(self._base_package)

    @property
    def generators(self) -> Path:
        return _folder_path(self._base_generators)

    def set_base_generators(self, folder: str | None) -> None:
        self._base_generators = folder
