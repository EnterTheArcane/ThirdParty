from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import collect_libs, copy, get, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    char_type: Literal["char", "wchar_t", "ushort"] = "char"
    large_size: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libexpat"
    version = "2.8.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "libexpat/libexpat")
        return Version(repo.latest_release.removeprefix("R_").replace("_", "."))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        release_tag = self.version.replace(".", "_")
        get(
            self,
            url=f"https://github.com/libexpat/libexpat/releases/download/R_{release_tag}/expat-{self.version}.tar.xz",
            sha256="3ad89b8588e6644bd4e49981480d48b21289eebbcd4f0a1a4afb1c29f99b6ab4",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["EXPAT_BUILD_DOCS"] = False
        tc.variables["EXPAT_BUILD_EXAMPLES"] = False
        tc.variables["EXPAT_SHARED_LIBS"] = self.options.shared
        tc.variables["EXPAT_BUILD_TESTS"] = False
        tc.variables["EXPAT_BUILD_TOOLS"] = False
        tc.variables["EXPAT_CHAR_TYPE"] = self.options.char_type
        if is_msvc(self):
            tc.variables["EXPAT_MSVC_STATIC_CRT"] = is_msvc_static_runtime(self)
        tc.variables["EXPAT_BUILD_PKGCONFIG"] = False
        tc.variables["EXPAT_LARGE_SIZE"] = self.options.large_size
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "expat")
        self.info.set_property("cmake_target_name", "expat::expat")
        self.info.set_property("cmake_target_aliases", ["libexpat::libexpat"])
        self.info.set_property("pkg_config_name", "expat")

        self.info.libs = collect_libs(self)
        if not self.options.shared:
            self.info.defines = ["XML_STATIC"]
        if self.options.char_type in ("wchar_t", "ushort"):
            self.info.defines.append("XML_UNICODE")
            if self.options.char_type == "wchar_t":
                self.info.defines.append("XML_UNICODE_WCHAR_T")
        if self.options.large_size:
            self.info.defines.append("XML_LARGE_SIZE")

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
