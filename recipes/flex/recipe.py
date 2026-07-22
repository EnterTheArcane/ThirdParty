import os

from thirdparty import RecipeBase
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "flex"
    version = "2.6.4"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "westes/flex")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def validate(self):
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration("Windows is not supported")

    def requirements(self):
        # flex needs m4 at runtime to generate scanners
        self.requires("m4")
        self.requires_tool("m4")
        self.requires_tool("gnu-config")

    def source(self):
        get(
            self,
            url=f"https://github.com/westes/flex/releases/download/v{self.version}/flex-{self.version}.tar.gz",
            sha256="e87aae032bf07c26f85ac0ed3250998c37621d95f8bd748b31f15b33c45ee995",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend([
            "--disable-nls",
            "--disable-bootstrap",
            "HELP2MAN=/bin/true",
            "M4=m4",
            # https://github.com/westes/flex/issues/247
            "ac_cv_func_malloc_0_nonnull=yes",
            "ac_cv_func_realloc_0_nonnull=yes",
            # https://github.com/easybuilders/easybuild-easyconfigs/pull/5792
            "ac_cv_func_reallocarray=no",
        ])
        if is_apple_os(self):
            tc.extra_ldflags.append("-headerpad_max_install_names")
        tc.generate()

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source,
             dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rmdir(self, self.folders.package / "share")
        rm(self, "*.la", self.folders.package / "lib")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.libs = ["fl"]
        self.info.system_libs = ["m"]
        # Avoid CMakeDeps messing with Conan targets
        self.info.set_property("cmake_find_mode", "none")
        lex_path = (self.folders.package / "bin" / "flex").as_posix()
        self.info.buildenv.define("LEX", lex_path)

    def _patch_sources(self):
        # libtool's generated configure only enables -undefined dynamic_lookup for macOS 10.x.
        # On newer Darwin (11+) the version case falls through and leaves the allow-undefined flag empty, breaking the link.
        # Turn the "10.*" arm into a catch-all "*".
        replace_in_file(self, self.folders.source / "configure", "10.*)", "*)")
        # Refresh config.guess/config.sub so newer hosts (e.g. Apple Silicon) are recognised.
        for gnu_config in (
            self.conf.tools.gnu_config.config_guess,
            self.conf.tools.gnu_config.config_sub,
        ):
            if gnu_config:
                copy(self, os.path.basename(gnu_config),
                     src=os.path.dirname(gnu_config),
                     dst=self.folders.source / "build-aux")
