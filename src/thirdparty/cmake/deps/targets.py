import textwrap

import jinja2

from typing import Any
from thirdparty.recipe import RecipeBase


class TargetsTemplate2:
    """
    FooTargets.cmake
    """

    def __init__(self, cmakedeps: Any, recipe: RecipeBase):
        self._cmakedeps = cmakedeps
        self._recipe = recipe

    def content(self) -> str:
        t = jinja2.Template(
            self._template, trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined)
        return t.render(self._context)

    @property
    def filename(self) -> str:
        f = self._cmakedeps.get_cmake_filename(self._recipe)
        return f"{f}Targets.cmake"

    @property
    def _context(self) -> dict[str, Any]:
        filename = self._cmakedeps.get_cmake_filename(self._recipe)
        ret = {
            "ref": self._recipe.name, "filename": filename,
        }
        return ret

    @property
    def _template(self) -> str:
        return textwrap.dedent(
            """
            include_guard()
            message(STATUS "Recipe: Configuring Targets for {{ ref }}")

            # Load information for each installed configuration.
            file(GLOB _target_files "${CMAKE_CURRENT_LIST_DIR}/{{filename}}-Targets-*.cmake")
            foreach(_target_file IN LISTS _target_files)
                include("${_target_file}")
            endforeach()

            file(GLOB _build_files "${CMAKE_CURRENT_LIST_DIR}/{{filename}}-TargetsBuild-*.cmake")
            foreach(_build_file IN LISTS _build_files)
                include("${_build_file}")
            endforeach()
            """)
