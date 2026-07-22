import os
from typing import Any

from thirdparty.env import Environment
from thirdparty.recipe import RecipeBase


def runenv_from_cpp_info(dep: Any, os_name: str | None):
    """ return an Environment deducing the runtime information from a info
    """
    dyn_runenv = Environment()
    info = dep.info.aggregated_components()

    def _prepend_path(envvar: str, paths: Any):
        existing = [p for p in paths if os.path.exists(p)] if paths else None
        if existing:
            dyn_runenv.prepend_path(envvar, existing)

    _prepend_path("PATH", info.bindirs)
    # For tool requirements this will be the build OS, otherwise it will be the host OS.
    if os_name and not os_name.startswith("Windows"):
        _prepend_path("LD_LIBRARY_PATH", info.libdirs)
        _prepend_path("DYLD_LIBRARY_PATH", info.libdirs)
        _prepend_path("DYLD_FRAMEWORK_PATH", info.frameworkdirs)
    return dyn_runenv


class VirtualRunEnv:
    """ Calculates the environment variables of the runtime context and produces a runenv
        .bat or .sh script
    """

    def __init__(self, recipe: RecipeBase):
        """

        :param recipe:  The current recipe object. Always use ``self``.
        """
        self._runenv = None
        self._recipe = recipe
        self.basename = "runenv"
        self.configuration = recipe.settings.build_type
        if self.configuration:
            self.configuration = self.configuration.lower()
        self.arch = recipe.settings.arch
        if self.arch:
            self.arch = self.arch.lower()

    @property
    def _filename(self):
        f = self.basename
        if self.configuration:
            f += "-" + self.configuration.replace(".", "_")
        if self.arch:
            f += "-" + self.arch.replace(".", "_").replace("|", "_")
        return f

    def environment(self):
        """
        Returns an ``Environment`` object containing the environment variables of the run context.

        :return: an ``Environment`` object instance containing the obtained variables.
        """

        if self._runenv is None:
            self._runenv = Environment()
        else:
            return self._runenv

        host_req = self._recipe.dependencies.host
        for require, dep in host_req.items():
            if dep.info.runenv:
                self._runenv.compose_env(dep.info.runenv)
            if require.run:  # Only if the require is run (shared or application to be run)
                _os = self._recipe.settings.os
                self._runenv.compose_env(runenv_from_cpp_info(dep, _os))

        return self._runenv

    def vars(self, scope: str = "run"):
        """
        :param scope: Scope to be used.
        :return: An ``EnvVars`` instance containing the computed environment variables.
        """
        return self.environment().vars(self._recipe, scope=scope)

    def generate(self, scope: str = "run"):
        """
        Produces the launcher scripts activating the variables for the run context.

        :param scope: Scope to be used.
        """
        run_env = self.environment()
        run_env.vars(self._recipe, scope=scope).save_script(self._filename)
