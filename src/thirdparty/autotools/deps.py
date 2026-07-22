from typing import Any

from thirdparty import Info
from thirdparty.env import Environment
from thirdparty.build.gnudeps_flags import GnuDepsFlags
from thirdparty.recipe import RecipeBase


class AutotoolsDeps:
    _recipe: RecipeBase
    _environment: Environment | None
    _ordered_deps: list[Any] | None

    def __init__(self, recipe: RecipeBase):
        self._recipe = recipe
        self._environment = None
        self._ordered_deps = None

    @property
    def ordered_deps(self) -> list[Any]:
        if self._ordered_deps is None:
            deps = self._recipe.dependencies.host.topological_sort
            self._ordered_deps = [dep for dep in reversed(deps.values())]
        return self._ordered_deps

    def _get_cpp_info(self) -> Info:
        ret = Info()
        for dep in self.ordered_deps:
            dep_cppinfo = dep.info.aggregated_components()
            # In case we have components, aggregate them, we do not support isolated
            # "targets" with autotools
            ret.merge(dep_cppinfo)
        return ret

    def _rpaths_flags(self) -> list[str]:
        flags: list[str] = []
        for dep in self.ordered_deps:
            if dep.options.get_safe("shared"):
                flags.extend(
                    [f"-Wl,-rpath -Wl,{libdir}" for libdir in dep.info.aggregated_components().libdirs])
        return flags

    @property
    def environment(self) -> Environment:
        """

        :return: An ``Environment`` object containing the computed variables. If you need
                 to modify some of the computed values you can access to the ``environment`` object.
        """
        if self._environment is None:
            flags = GnuDepsFlags(self._recipe, self._get_cpp_info())

            # cpp_flags
            cpp_flags: list[str] = []
            cpp_flags.extend(flags.include_paths)
            cpp_flags.extend(flags.defines)

            # Ldflags
            ldflags: list[str] = flags.sharedlinkflags
            ldflags.extend(flags.exelinkflags)
            ldflags.extend(flags.frameworks)
            ldflags.extend(flags.framework_paths)
            ldflags.extend(flags.lib_paths)

            # set the rpath in Macos so that the library are found in the configure step
            if self._recipe.settings.os == "Mac":
                ldflags.extend(self._rpaths_flags())

            # libs
            libs: list[str] = flags.libs
            libs.extend(flags.system_libs)

            # cflags
            cflags: list[str] = flags.cflags
            cxxflags: list[str] = flags.cxxflags

            env = Environment()
            env.append("CPPFLAGS", cpp_flags)
            env.append("LIBS", libs)
            env.append("LDFLAGS", ldflags)
            env.append("CXXFLAGS", cxxflags)
            env.append("CFLAGS", cflags)
            self._environment = env
        return self._environment

    def vars(self, scope: str = "build"):
        return self.environment.vars(self._recipe, scope=scope)

    def generate(self, scope: str = "build"):
        self.vars(scope).save_script("autotoolsdeps")
