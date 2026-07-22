from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    bit_depth: Literal["all", 8, 16] = "all"
    with_tools: bool = True
    assembly: bool = True


class Recipe(RecipeBase[_Options]):
    name = "dav1d"
    version = "1.5.4"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "videolan/dav1d")
        return Version(repo.latest_release)

    def configure(self):
        if is_msvc(self) and self.settings.build_type == "Debug":
            # debug builds with assembly often causes linker hangs or LNK1000
            self.options.assembly = False

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("meson")
        if self.options.assembly and self.settings.arch in ("X64",):
            self.requires_tool("nasm")
        if is_msvc(self) and self.settings.arch == "ARM":
            self.requires_tool("gas-preprocessor")
            self.requires_tool("strawberryperl")

    def source(self):
        get(
            self,
            url=f"https://github.com/videolan/dav1d/archive/refs/tags/{self.version}.tar.gz",
            sha256="a1d5b63d2d38ec9bd03acf643caa51fa22edd1e89c5a109c4807717216bbec07",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(self, self.folders.source / "meson.build", "subdir('doc')", "")

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = MesonToolchain(self)
        tc.project_options["enable_tests"] = False
        tc.project_options["enable_asm"] = self.options.assembly
        tc.project_options["enable_tools"] = self.options.with_tools
        if self.options.bit_depth == "all":
            tc.project_options["bitdepths"] = "8,16"
        else:
            tc.project_options["bitdepths"] = str(self.options.bit_depth)
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rm(self, "*.pdb", self.folders.package / "bin")
        rm(self, "*.pdb", self.folders.package / "lib")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("pkg_config_name", "dav1d")
        self.info.libs = ["dav1d"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["dl", "pthread"])
