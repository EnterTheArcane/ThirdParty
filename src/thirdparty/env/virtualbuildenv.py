from thirdparty.env import Environment
from thirdparty.env.virtualrunenv import runenv_from_cpp_info
from thirdparty.recipe import RecipeBase


class VirtualBuildEnv:
    """ Calculates the environment variables of the build time context and produces a buildenv
        .bat or .sh script
    """

    def __init__(self, recipe: RecipeBase):
        self._buildenv = None
        self._recipe = recipe
        self.basename = "buildenv"
        self.configuration = None
        self.arch = None

    @property
    def _filename(self):
        if not self.configuration:
            # TODO: Make this use the settings_build
            configuration = self._recipe.settings.build_type
            configuration = configuration.lower() if configuration else None
        else:
            configuration = self.configuration
        if not self.arch:
            arch = self._recipe.settings.arch
            arch = arch.lower() if arch else None
        else:
            arch = self.arch
        f = self.basename
        if configuration:
            f += "-" + configuration.replace(".", "_")
        if arch:
            f += "-" + arch.replace(".", "_").replace("|", "_")
        return f

    def environment(self):
        """
        Returns an ``Environment`` object containing the environment variables of the build context.

        :return: an ``Environment`` object instance containing the obtained variables.
        """

        if self._buildenv is None:
            self._buildenv = Environment()
        else:
            return self._buildenv

        build_deps = self._recipe.dependencies.build.topological_sort
        for require, build_dep in reversed(build_deps.items()):
            if require.direct:  # Only direct buildenv from tool deps is propagated
                # higher priority, explicit buildenv
                if build_dep.info.buildenv:
                    self._buildenv.compose_env(build_dep.info.buildenv)
            # Lower priority, the runenv of all transitive "requires" of the tool requirements
            if build_dep.info.runenv:
                self._buildenv.compose_env(build_dep.info.runenv)
            # Then the implicit
            if require.run:
                os_name = self._recipe.settings_build.os
                self._buildenv.compose_env(runenv_from_cpp_info(build_dep, os_name))

        # Requires in host context can also bring some direct buildenv
        host_requires = self._recipe.dependencies.host.topological_sort
        for dep in reversed(host_requires.values()):
            if dep.info.buildenv:
                self._buildenv.compose_env(dep.info.buildenv)

        return self._buildenv

    def vars(self, scope: str = "build"):
        """
        :param scope: Scope to be used.
        :return: An ``EnvVars`` instance containing the computed environment variables.
        """
        return self.environment().vars(self._recipe, scope=scope)

    def generate(self, scope: str = "build"):
        """
        Produces the launcher scripts activating the variables for the build context.

        :param scope: Scope to be used.
        """
        build_env = self.environment()
        build_env.vars(self._recipe, scope=scope).save_script(self._filename)
