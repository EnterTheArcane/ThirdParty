
import os

from thirdparty._internal.subsystems import deduce_subsystem, subsystem_path
from thirdparty.recipe import RecipeBase


def unix_path(recipe: RecipeBase, path: str | os.PathLike[str], scope: str = "build") -> str | None:
    subsystem = deduce_subsystem(recipe, scope=scope)
    return subsystem_path(subsystem, path)
