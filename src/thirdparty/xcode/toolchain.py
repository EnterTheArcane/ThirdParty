import textwrap

from thirdparty._internal.util.files import save
from thirdparty.apple.utils import to_apple_arch, xcodebuild_deployment_target_key
from thirdparty.xcode.deps import GLOBAL_XCCONFIG_FILENAME, GLOBAL_XCCONFIG_TEMPLATE, _add_includes_to_file_or_create, _xcconfig_settings_filename, _xcconfig_conditional
from thirdparty.recipe import RecipeBase


class XcodeToolchain:
    filename = "recipe_toolchain"
    extension = ".xcconfig"

    _vars_xconfig = textwrap.dedent(
        """
        // Definition of toolchain variables
        {apple_deployment_target}
        {clang_cxx_library}
        {clang_cxx_language_standard}
        """)

    _flags_xconfig = textwrap.dedent(
        """
        // Global flags
        {defines}
        {cflags}
        {cppflags}
        {ldflags}
        """)

    _agreggated_xconfig = textwrap.dedent(
        """
        // Recipe XcodeToolchain generated file
        // Includes all installed configurations

        """)

    def __init__(self, recipe: RecipeBase):
        self._recipe = recipe
        arch = recipe.settings.arch
        self.architecture = to_apple_arch(self._recipe, default=arch)
        self.configuration = recipe.settings.build_type
        self.libcxx = recipe.settings.compiler_libcxx
        self.os_version = recipe.settings.os_version
        self._global_defines = self._recipe.conf.tools.build.defines
        self._global_cxxflags = self._recipe.conf.tools.build.cxxflags
        self._global_cflags = self._recipe.conf.tools.build.cflags
        sharedlinkflags = self._recipe.conf.tools.build.sharedlinkflags
        exelinkflags = self._recipe.conf.tools.build.exelinkflags
        self._global_ldflags = sharedlinkflags + exelinkflags

    def generate(self):
        save(self._agreggated_xconfig_filename, self._agreggated_xconfig_content)
        save(self._vars_xconfig_filename, self._vars_xconfig_content)
        if self._check_if_extra_flags:
            save(self._flags_xcconfig_filename, self._flags_xcconfig_content)
        save(GLOBAL_XCCONFIG_FILENAME, self._global_xconfig_content)

    @property
    def _cppstd(self):
        from thirdparty.build.flags import cppstd_flag
        cppstd = cppstd_flag(self._recipe)
        if cppstd.startswith("-std="):
            return cppstd[5:]
        return cppstd

    @property
    def _apple_deployment_target(self):
        deployment_target_key = xcodebuild_deployment_target_key(self._recipe.settings.os)
        return "{}{}={}".format(
            deployment_target_key, _xcconfig_conditional(self._recipe.settings, self.configuration), self.os_version) if deployment_target_key and self.os_version else ""

    @property
    def _clang_cxx_library(self):
        return "CLANG_CXX_LIBRARY{}={}".format(
            _xcconfig_conditional(
                self._recipe.settings, self.configuration), self.libcxx) if self.libcxx else ""

    @property
    def _clang_cxx_language_standard(self):
        return "CLANG_CXX_LANGUAGE_STANDARD{}={}".format(
            _xcconfig_conditional(self._recipe.settings, self.configuration), self._cppstd) if self._cppstd else ""

    @property
    def _vars_xconfig_filename(self) -> str:
        return "recipe_toolchain{}{}".format(
            _xcconfig_settings_filename(
                self._recipe.settings, self.configuration), self.extension)

    @property
    def _vars_xconfig_content(self):
        ret = self._vars_xconfig.format(
            apple_deployment_target=self._apple_deployment_target, clang_cxx_library=self._clang_cxx_library, clang_cxx_language_standard=self._clang_cxx_language_standard)
        return ret

    @property
    def _agreggated_xconfig_content(self):
        return _add_includes_to_file_or_create(
            self._agreggated_xconfig_filename, self._agreggated_xconfig, [self._vars_xconfig_filename])

    @property
    def _global_xconfig_content(self):
        files_to_include = [self._agreggated_xconfig_filename]
        if self._check_if_extra_flags:
            files_to_include.append(self._flags_xcconfig_filename)
        content = _add_includes_to_file_or_create(
            GLOBAL_XCCONFIG_FILENAME, GLOBAL_XCCONFIG_TEMPLATE, files_to_include)
        return content

    @property
    def _agreggated_xconfig_filename(self):
        return self.filename + self.extension

    @property
    def _check_if_extra_flags(self):
        return self._global_cflags or self._global_cxxflags or self._global_ldflags or self._global_defines

    @property
    def _flags_xcconfig_content(self):
        defines = f"GCC_PREPROCESSOR_DEFINITIONS = $(inherited) {" ".join(self._global_defines)}" if self._global_defines else ""
        cflags = f"OTHER_CFLAGS = $(inherited) {" ".join(self._global_cflags)}" if self._global_cflags else ""
        cppflags = f"OTHER_CPLUSPLUSFLAGS = $(inherited) {" ".join(self._global_cxxflags)}" if self._global_cxxflags else ""
        ldflags = f"OTHER_LDFLAGS = $(inherited) {" ".join(self._global_ldflags)}" if self._global_ldflags else ""
        ret = self._flags_xconfig.format(defines=defines, cflags=cflags, cppflags=cppflags, ldflags=ldflags)
        return ret

    @property
    def _flags_xcconfig_filename(self):
        return "recipe_global_flags" + self.extension
