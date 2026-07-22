from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_libde265: bool = True
    with_x265: bool = True
    with_x264: bool = True
    with_libaomav1: bool = True
    with_dav1d: bool = True
    with_jpeg: bool = True
    with_openjpeg: bool = False
    with_openjph: bool = True
    with_openh264: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libheif"
    version = "1.23.1"
    license = "GPL-3.0-or-later", "LGPL-3.0-only", "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "strukturag/libheif")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_libde265:
            self.requires("libde265")
        if self.options.with_x265:
            self.requires("x265")
        if self.options.with_libaomav1:
            self.requires("aom")
        if self.options.with_dav1d:
            self.requires("dav1d")
        if self.options.with_jpeg:
            self.requires("libjpeg-turbo")
        if self.options.with_openjpeg:
            self.requires("openjpeg")
        if self.options.with_openjph:
            self.requires("openjph")
        if self.options.with_openh264:
            self.requires("openh264")
        if self.options.with_x264:
            self.requires("x264")

    def source(self):
        get(
            self,
            url=f"https://github.com/strukturag/libheif/releases/download/v{self.version}/libheif-{self.version}.tar.gz",
            sha256="0de0327f60fcd47de90d5654c6fe152232738d60d84fe084ec3e0f35e03b166a",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "set(CMAKE_POSITION_INDEPENDENT_CODE", "#set(CMAKE_POSITION_INDEPENDENT_CODE")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["WITH_LIBSHARPYUV"] = False
        tc.cache_variables["WITH_LIBDE265"] = self.options.with_libde265
        tc.cache_variables["WITH_X265"] = self.options.with_x265
        tc.cache_variables["WITH_AOM"] = self.options.with_libaomav1
        tc.cache_variables["WITH_AOM_DECODER"] = self.options.with_libaomav1
        tc.cache_variables["WITH_AOM_ENCODER"] = self.options.with_libaomav1
        if self.options.with_libaomav1:
            tc.cache_variables["AOM_ENCODER_FOUND"] = "YES"
            tc.cache_variables["AOM_DECODER_FOUND"] = "YES"
        tc.cache_variables["WITH_X264"] = self.options.with_x264
        tc.cache_variables["WITH_RAV1E"] = False
        tc.cache_variables["WITH_DAV1D"] = self.options.with_dav1d
        tc.cache_variables["WITH_EXAMPLES"] = False
        tc.cache_variables["WITH_GDK_PIXBUF"] = False
        tc.cache_variables["BUILD_TESTING"] = False
        tc.cache_variables["WITH_JPEG_DECODER"] = self.options.with_jpeg
        tc.cache_variables["WITH_JPEG_ENCODER"] = self.options.with_jpeg
        tc.cache_variables["WITH_OpenJPEG_DECODER"] = self.options.with_openjpeg
        tc.cache_variables["WITH_OpenJPEG_ENCODER"] = self.options.with_openjpeg
        tc.cache_variables["WITH_OPENJPH_ENCODER"] = self.options.with_openjph
        tc.cache_variables["WITH_OPENH264_DECODER"] = self.options.with_openh264

        # Disable finding possible Doxygen in system, so no docs are built
        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_Doxygen"] = True
        tc.cache_variables["CMAKE_COMPILE_WARNING_AS_ERROR"] = False
        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("dav1d", "cmake_additional_variables_prefixes", ["DAV1D"])
        deps.set_property("libde265", "cmake_file_name", "LIBDE265")
        deps.set_property("openjph", "cmake_file_name", "OPENJPH")
        deps.set_property("openh264", "cmake_file_name", "OpenH264")
        if self.options.with_jpeg:
            # Present libjpeg-turbo as libjpeg so upstream find_package(JPEG) resolves
            deps.set_property("libjpeg-turbo", "cmake_file_name", "JPEG")
            deps.set_property("libjpeg-turbo", "cmake_target_name", "JPEG::JPEG")
        deps.generate()
        PkgConfigDeps(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "libheif")
        self.info.set_property("cmake_target_name", "libheif::heif")
        self.info.set_property("pkg_config_name", "libheif")
        self.info.libs = ["heif"]

        if not self.options.shared:
            self.info.defines = ["LIBHEIF_STATIC_BUILD"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["m", "pthread"])
            self.info.system_libs.append("dl")
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)

        if self.options.with_libde265:
            self.info.requires.append("libde265::libde265")
        if self.options.with_x265:
            self.info.requires.append("x265::x265")
        if self.options.with_libaomav1:
            self.info.requires.append("aom::aom")
        if self.options.with_dav1d:
            self.info.requires.append("dav1d::dav1d")
        if self.options.with_jpeg:
            self.info.requires.append("libjpeg-turbo::jpeg")
        if self.options.with_openjpeg:
            self.info.requires.append("openjpeg::openjpeg")
        if self.options.with_openjph:
            self.info.requires.append("openjph::openjph")
        if self.options.with_openh264:
            self.info.requires.append("openh264::openh264")
        if self.options.with_x264:
            self.info.requires.append("x264::x264")
