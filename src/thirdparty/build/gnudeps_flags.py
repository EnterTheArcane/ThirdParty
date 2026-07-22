"""
    This is a helper class which offers a lot of useful methods and attributes
"""

from typing import Any

from thirdparty._internal.subsystems import subsystem_path, deduce_subsystem
from thirdparty.apple.utils import is_apple_os
from thirdparty.microsoft import is_msvc
from thirdparty.recipe import RecipeBase


class GnuDepsFlags:
    def __init__(self, recipe: RecipeBase, info: Any):
        self._recipe = recipe
        self._subsystem = deduce_subsystem(recipe, scope="build")

        # From cppinfo, calculated flags
        self.include_paths = self._format_include_paths(info.includedirs)
        self.lib_paths = self._format_library_paths(info.libdirs)
        self.defines = self._format_defines(info.defines)
        self.libs = self._format_libraries(info.libs)
        self.frameworks = self._format_frameworks(info.frameworks)
        self.framework_paths = self._format_frameworks(info.frameworkdirs, is_path=True)

        # Direct flags
        self.cxxflags: list[Any] = info.cxxflags or []
        self.cflags: list[Any] = info.cflags or []
        self.sharedlinkflags: list[Any] = info.sharedlinkflags or []
        self.exelinkflags: list[Any] = info.exelinkflags or []
        self.system_libs = self._format_libraries(info.system_libs)

        # Not used?  # self.bin_paths  # self.build_paths  # self.src_paths

    _GCC_LIKE = ["clang", "apple-clang", "gcc"]

    @staticmethod
    def _format_defines(defines: Any) -> list[str]:
        return ["-D%s" % define for define in defines] if defines else []

    def _format_frameworks(self, frameworks: Any, is_path: bool = False) -> list[str]:
        """
        returns an appropriate compiler flags to link with Apple Frameworks
        or an empty array, if Apple Frameworks aren't supported by the given compiler
        """
        if not frameworks or not is_apple_os(self._recipe):
            return []
        compiler = self._recipe.settings.compiler
        if str(compiler) not in self._GCC_LIKE:
            return []
        if is_path:
            return ["-F\"%s\"" % self._adjust_path(framework_path) for framework_path in frameworks]
        else:
            return ["-framework %s" % framework for framework in frameworks]

    def _format_include_paths(self, include_paths: Any) -> list[str]:
        if not include_paths:
            return []
        pattern = "/I%s" if is_msvc(self._recipe) else "-I%s"
        return [pattern % (self._adjust_path(include_path)) for include_path in include_paths if include_path]

    def _format_library_paths(self, library_paths: Any) -> list[str]:
        if not library_paths:
            return []
        pattern = "/LIBPATH:%s" if is_msvc(self._recipe) else "-L%s"
        return [pattern % self._adjust_path(library_path) for library_path in library_paths if library_path]

    def _format_libraries(self, libraries: Any) -> list[str]:
        if not libraries:
            return []

        result: list[str] = []

        is_visual = is_msvc(self._recipe)
        for library in libraries:
            if is_visual:
                if not library.endswith(".lib"):
                    library += ".lib"
                result.append(library)
            else:
                result.append("-l%s" % library)
        return result

    def _adjust_path(self, path: str):
        if is_msvc(self._recipe):
            path = path.replace("/", "\\")
        else:
            path = path.replace("\\", "/")

        path = subsystem_path(self._subsystem, path)
        return '"%s"' % path if " " in path else path
