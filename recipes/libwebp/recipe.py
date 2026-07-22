from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libwebp"
    version = "1.6.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "webmproject/libwebp")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/webmproject/libwebp/archive/refs/tags/v{self.version}.tar.gz",
            sha256="93a852c2b3efafee3723efd4636de855b46f9fe1efddd607e1f42f60fc8f2136",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["WEBP_ENABLE_SIMD"] = True
        tc.variables["WEBP_NEAR_LOSSLESS"] = True
        tc.variables["WEBP_ENABLE_SWAP_16BIT_CSP"] = False
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_GIF"] = True
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_PNG"] = True
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_TIFF"] = True
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_JPEG"] = True
        tc.variables["WEBP_BUILD_ANIM_UTILS"] = False
        tc.variables["WEBP_BUILD_CWEBP"] = False
        tc.variables["WEBP_BUILD_DWEBP"] = False
        tc.variables["WEBP_BUILD_IMG2WEBP"] = False
        tc.variables["WEBP_BUILD_GIF2WEBP"] = False
        tc.variables["WEBP_BUILD_VWEBP"] = False
        tc.variables["WEBP_BUILD_EXTRAS"] = False
        tc.variables["WEBP_BUILD_WEBPINFO"] = False
        tc.variables["WEBP_BUILD_WEBPMUX"] = False
        tc.variables["WEBP_BUILD_LIBWEBPMUX"] = True
        if self.options.shared and is_msvc(self):
            # Building a dll (see fix-dll-export patch)
            tc.preprocessor_definitions["WEBP_DLL"] = 1
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "WebP")
        self.info.set_property("pkg_config_name", "libwebp-all-do-not-use")
        self.info.set_property("cmake_additional_variables_prefixes", ["WEBP"])

        # webpdecoder
        self.info.components["webpdecoder"].set_property("cmake_target_name", "WebP::webpdecoder")
        self.info.components["webpdecoder"].set_property("pkg_config_name", "libwebpdecoder")
        self.info.components["webpdecoder"].libs = ["webpdecoder"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["webpdecoder"].system_libs = ["m", "pthread"]
        if self.settings.os == "Android":
            self.info.components["webpdecoder"].system_libs = ["m"]

        # webp
        self.info.components["webp"].set_property("cmake_target_name", "WebP::webp")
        self.info.components["webp"].set_property("pkg_config_name", "libwebp")
        self.info.components["webp"].libs = ["webp"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["webp"].system_libs = ["m", "pthread"]
        if self.settings.os == "Android":
            self.info.components["webp"].system_libs = ["m"]

        self.info.components["webp"].requires = ["sharpyuv"]

        # sharpyuv
        self.info.components["sharpyuv"].set_property("cmake_target_name", "WebP::sharpyuv")
        self.info.components["sharpyuv"].set_property("pkg_config_name", "libsharpyuv")
        self.info.components["sharpyuv"].libs = ["sharpyuv"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["sharpyuv"].system_libs = ["m", "pthread"]
        if self.settings.os == "Android":
            self.info.components["sharpyuv"].system_libs = ["m"]

        # webpdemux
        self.info.components["webpdemux"].set_property("cmake_target_name", "WebP::webpdemux")
        self.info.components["webpdemux"].set_property("pkg_config_name", "libwebpdemux")
        self.info.components["webpdemux"].libs = ["webpdemux"]
        self.info.components["webpdemux"].requires = ["webp"]

        # webpmux
        self.info.components["webpmux"].set_property("cmake_target_name", "WebP::libwebpmux")
        self.info.components["webpmux"].set_property("pkg_config_name", "libwebpmux")
        self.info.components["webpmux"].libs = ["webpmux"]
        self.info.components["webpmux"].requires = ["webp"]
        if self.settings.os in ["Linux", "FreeBSD", "Android"]:
            self.info.components["webpmux"].system_libs = ["m"]
