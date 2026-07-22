from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import copy, get, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    pic: bool = True
    shared: bool = False


class Recipe(RecipeBase[_Options]):
    name = "hidapi"
    version = "0.15.0"
    license = "BSD-3-Clause", "GPL-3.0-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "libusb/hidapi")
        return Version(repo.latest_release.removeprefix("hidapi-"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.requires("libusb")
        if self.settings.os == "Linux":
            self.requires("libudev")
        if self.settings.os != "Windows":
            self.requires_tool("libtool")
            if self.settings.os in ["Linux", "FreeBSD"] and not self.conf.tools.gnu.pkg_config:
                self.requires_tool("pkgconf")
            if self.settings_build.os == "Windows":
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://github.com/libusb/hidapi/archive/hidapi-{self.version}.tar.gz",
            sha256="5d84dec684c27b97b921d2f3b73218cb773cf4ea915caee317ac8fc73cef8136",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.generate()
        deps = PkgConfigDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["libusb"].set_property("pkg_config_name", "hidapi-libusb")
            self.info.components["libusb"].libs = ["hidapi-libusb"]
            self.info.components["libusb"].requires = ["libusb::libusb"]
            self.info.components["libusb"].system_libs = ["pthread", "dl", "rt"]

            self.info.components["hidraw"].set_property("pkg_config_name", "hidapi-hidraw")
            self.info.components["hidraw"].libs = ["hidapi-hidraw"]
            if self.settings.os == "Linux":
                self.info.components["hidraw"].requires = ["libudev::libudev"]
            self.info.components["hidraw"].system_libs = ["pthread", "dl"]
        else:
            self.info.libs = ["hidapi"]
            if is_apple_os(self):
                self.info.frameworks.extend(["IOKit", "CoreFoundation", "AppKit"])

    @property
    def _msbuild_configuration(self):
        return "Debug" if self.settings.build_type == "Debug" else "Release"
