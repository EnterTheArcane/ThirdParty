from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    md2html: bool
    encoding: Literal["utf-8", "utf-16", "ascii"] = "utf-8"


class Recipe(RecipeBase[_Options]):
    name = "md4c"
    version = "0.5.3"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "mity/md4c")
        return Version(repo.latest_release.removeprefix("release-"))

    def configure(self):
        # Set it to false for iOS, tvOS, watchOS, visionOS
        # to prevent cmake from creating a bundle for the md2html executable
        is_ios_variant = is_apple_os(self) and not self.settings.os == "Mac"
        self.options.md2html = not is_ios_variant

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/mity/md4c/archive/refs/tags/release-{self.version}.tar.gz",
            sha256="353c346f376b87c954a13f3415ede2d51264cc61dc5abcd38ff1d2aa0d059b9e",
            destination=self.folders.source,
            strip_root=True)
        # md4c hardcodes the static MSVC runtime (/MT, /MTd) into CMAKE_C_FLAGS_*, which overrides
        # the framework's CMAKE_MSVC_RUNTIME_LIBRARY (CMP0091) selection -> "D9025: overriding
        # '/MT' with '/MD'". Strip it so the framework controls the runtime like every other recipe.
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "${CMAKE_C_FLAGS_DEBUG} /MTd", "${CMAKE_C_FLAGS_DEBUG}", strict=False)
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "${CMAKE_C_FLAGS_RELEASE} /MT", "${CMAKE_C_FLAGS_RELEASE}", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_MD2HTML_EXECUTABLE"] = self.options.md2html
        if self.options.encoding == "utf-8":
            tc.preprocessor_definitions["MD4C_USE_UTF8"] = "1"
        elif self.options.encoding == "utf-16":
            tc.preprocessor_definitions["MD4C_USE_UTF16"] = "1"
        elif self.options.encoding == "ascii":
            tc.preprocessor_definitions["MD4C_USE_ASCII"] = "1"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, pattern="LICENSE.md", dst=self.folders.package / "licenses", src=self.folders.source)
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "md4c")

        self.info.components["_md4c"].set_property("cmake_target_name", "md4c::md4c")
        self.info.components["_md4c"].set_property("pkg_config_name", "md4c")
        self.info.components["_md4c"].libs = ["md4c"]
        if self.settings.os == "Windows" and self.options.encoding == "utf-16":
            self.info.components["_md4c"].defines.append("MD4C_USE_UTF16")

        self.info.components["md4c_html"].set_property("cmake_target_name", "md4c::md4c-html")
        self.info.components["md4c_html"].set_property("pkg_config_name", "md4c-html")
        self.info.components["md4c_html"].libs = ["md4c-html"]
        self.info.components["md4c_html"].requires = ["_md4c"]

        # workaround so that global target & pkgconfig file have all components while avoiding
        # to create unofficial target or pkgconfig file
        self.info.set_property("cmake_target_name", "md4c::md4c-html")
        self.info.set_property("pkg_config_name", "md4c-html")
