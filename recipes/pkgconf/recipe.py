import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, rename, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    enable_lib: bool = False


class Recipe(RecipeBase[_Options]):
    name = "pkgconf"
    version = "3.0.4"
    license = "ISC"

    def latest_version(self):
        repo = GithubRepository(self, "pkgconf/pkgconf")
        return Version(repo.latest_release.removeprefix("pkgconf-"))

    def configure(self):
        if not self.options.enable_lib:
            self.options.shared = False

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("meson")

    def source(self):
        get(
            self,
            url=f"https://github.com/pkgconf/pkgconf/archive/refs/tags/pkgconf-{self.version}.tar.gz",
            sha256="61436e5fa19bdb2dc999fba22e855aad999e9de0f196894068dbaeeb72aef2c4",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = MesonToolchain(self)
        if not self.options.enable_lib:
            tc.project_options["default_library"] = "static"
        tc.generate()

    def build(self):
        self._patch_sources()
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")

        meson = Meson(self)
        meson.install()

        if is_msvc(self):
            rm(self, "*.pdb", self.folders.package / "bin")
            if self.options.enable_lib and not self.options.shared:
                rm(self, "pkgconf.lib", self.folders.package / "lib")
                rename(
                    self, self.folders.package / "lib" / "libpkgconf.a",
                    self.folders.package / "lib" / "pkgconf.lib", )

        if not self.options.enable_lib:
            rmdir(self, self.folders.package / "lib")
            rmdir(self, self.folders.package / "include")

        rmdir(self, self.folders.package / "share" / "man")
        copy(
            self, "*", src=self.folders.package / "share" / "aclocal",
            dst=self.folders.package / "bin" / "aclocal")
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        if self.options.enable_lib:
            self.info.set_property("pkg_config_name", "libpkgconf")
            self.info.includedirs.append(os.path.join("include", "pkgconf"))
            self.info.libs = ["pkgconf"]
            if not self.options.shared:
                self.info.defines = ["PKGCONFIG_IS_STATIC"]
        else:
            self.info.includedirs = []
            self.info.libdirs = []

        bindir = self.folders.package / "bin"

        exesuffix = ".exe" if self.settings.os == "Windows" else ""
        pkg_config = (bindir / ("pkgconf" + exesuffix)).as_posix()
        self.info.buildenv.define_path("PKG_CONFIG", pkg_config)

        pkgconf_aclocal = self.folders.package / "bin" / "aclocal"
        self.info.buildenv.prepend_path("ACLOCAL_PATH", pkgconf_aclocal)
        # TODO: evaluate if `ACLOCAL_PATH` is enough and we can stop using `AUTOMAKE_RECIPE_INCLUDES`
        self.info.buildenv.prepend_path("AUTOMAKE_RECIPE_INCLUDES", pkgconf_aclocal)

    def _patch_sources(self):
        apply_patches(self)
