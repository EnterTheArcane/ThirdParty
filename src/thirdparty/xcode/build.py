
from thirdparty.apple.utils import to_apple_arch, xcodebuild_deployment_target_key
from thirdparty.build import cmd_args_to_string
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run


class XcodeBuild:
    _recipe: RecipeBase
    _build_type: str | None
    _arch: str | None
    _sdk: str
    _sdk_version: str
    _os: str
    _os_version: str | None

    def __init__(self, recipe: RecipeBase):
        self._recipe = recipe
        self._build_type = recipe.settings.build_type
        self._arch = to_apple_arch(self._recipe)
        self._sdk = recipe.settings.os_sdk or ""
        self._sdk_version = recipe.settings.os_sdk_version or ""
        self._os = recipe.settings.os
        self._os_version = recipe.settings.os_version

    @property
    def _verbosity(self) -> str:
        verbose = self._recipe.conf.tools.build.verbose or self._recipe.conf.tools.compilation.verbose
        return "-verbose" if verbose else "-quiet"

    @property
    def _sdkroot(self) -> str:
        # User's sdk_path has priority, then if specified try to compose sdk argument
        # with sdk/sdk_version settings, leave blank otherwise and the sdk will be automatically
        # chosen by the build system
        sdk = self._recipe.conf.tools.apple.sdk_path
        if not sdk and self._sdk:
            sdk = f"{self._sdk}{self._sdk_version}"
        return f"SDKROOT={sdk}" if sdk else ""

    def build(
        self, xcodeproj: str, target: str | None = None, configuration: str | None = None, cli_args: list[str] | None = None):
        """
        Call to ``xcodebuild`` to build a Xcode project.

        :param xcodeproj: the *xcodeproj* file to build.
        :param target: the target to build, in case this argument is passed to the ``build()``
                       method it will add the ``-target`` argument to the build system call. If not passed, it
                       will build all the targets passing the ``-alltargets`` argument instead.
        :param configuration: Build configuration to use (e.g., ``Debug``, ``Release``).
                              Defaults to the recipe's ``settings.build_type``.
        :param cli_args: Extra options to pass directly to ``xcodebuild`` (list of strings).
                              Examples: ``["-xcconfig", "<path/to/file.xcconfig>"]`` or custom
                              Xcode build settings like ``["BUILD_LIBRARY_FOR_DISTRIBUTION=YES"]``.
        :return: the return code for the launched ``xcodebuild`` command.
        """
        target = f"-target '{target}'" if target else "-alltargets"
        build_config = configuration or self._build_type
        cmd = (f"xcodebuild -project '{xcodeproj}' -configuration {build_config} "
               f"-arch {self._arch} {self._sdkroot} {self._verbosity} {target}")
        deployment_target_key = xcodebuild_deployment_target_key(self._os)
        if deployment_target_key and self._os_version:
            cmd += f" {deployment_target_key}={self._os_version}"

        if cli_args:
            cmd += " " + cmd_args_to_string(cli_args)

        run(self._recipe, cmd)
