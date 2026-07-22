from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.build import stdcpp_library
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rmdir, rm
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openh264"
    version = "2.6.0"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "cisco/openh264")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")
        if self.settings.arch in ["X64"]:
            self.requires_tool("nasm")
        if is_msvc(self) and self.settings.arch == "ARM":
            self.requires_tool("strawberryperl")
            self.requires_tool("gas-preprocessor")

    def source(self):
        get(
            self,
            url=f"https://github.com/cisco/openh264/archive/refs/tags/v{self.version}.tar.gz",
            sha256="558544ad358283a7ab2930d69a9ceddf913f4a51ee9bf1bfb9e377322af81a69",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["tests"] = "disabled"
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        meson = Meson(self)
        meson.install()

        rmdir(self, self.folders.package / "lib" / "pkgconfig")

        if is_msvc(self) or self._is_clang_cl:
            rm(self, "*.pdb", self.folders.package / "bin")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.libs = [f"openh264"]
        if self.settings.os in ("FreeBSD", "Linux"):
            self.info.system_libs.extend(["m", "pthread"])
        if self.settings.os == "Android":
            self.info.system_libs.append("m")
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                if self.settings.os == "Android" and libcxx == "c++_static":
                    # INFO: When builing for Android, need to link against c++abi too. Otherwise will get linkage errors:
                    # ld.lld: error: undefined symbol: operator new(unsigned long)
                    # >>> referenced by welsEncoderExt.cpp
                    self.info.system_libs.append("c++abi")
                self.info.system_libs.append(libcxx)

    @property
    def _is_clang_cl(self):
        return self.settings.os == "Windows" and self.settings.compiler == "clang"
