import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "fontconfig"
    version = "2.18.2"
    license = "MIT"

    def latest_version(self):
        repo = GitlabRepository(self, "fontconfig/fontconfig", host="gitlab.freedesktop.org")
        return Version(repo.latest_formal_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires("freetype")
        self.requires("libexpat")
        self.requires_tool("gperf")
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://gitlab.freedesktop.org/api/v4/projects/890/packages/generic/fontconfig/{self.version}/fontconfig-{self.version}.tar.xz",
            sha256="cf8e6576ef0484c15079bdaf77cd9c51c464df5365814ada4d3ee7331ea31eb5",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        deps = PkgConfigDeps(self)
        deps.generate()

        tc = MesonToolchain(self)
        tc.project_options.update(
            {
                "doc": "disabled",
                "nls": "disabled",
                "tests": "disabled",
                "tools": "disabled",
                "sysconfdir": os.path.join("res", "etc"),
                "datadir": os.path.join("res", "share"),
            })
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", self.folders.source, self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rm(self, "*.pdb", self.folders.package, recursive=True)
        rm(self, "*.conf", self.folders.package / "res" / "etc" / "fonts" / "conf.d")
        rm(self, "*.def", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "Fontconfig")
        self.info.set_property("cmake_target_name", "Fontconfig::Fontconfig")
        self.info.set_property("pkg_config_name", "fontconfig")
        self.info.libs = ["fontconfig"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs.extend(["m", "pthread"])

        fontconfig_path = self.folders.package / "res" / "etc" / "fonts"
        self.info.runenv.append_path("FONTCONFIG_PATH", fontconfig_path)
