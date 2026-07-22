from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rm, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    lzma: bool = True
    jpeg: bool = True
    zlib: bool = True
    libdeflate: bool = False
    zstd: bool = False
    jbig: bool = False
    webp: bool = False
    cxx: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libtiff"
    version = "4.7.2"
    license = "libtiff"

    def latest_version(self):
        repo = GitlabRepository(self, "libtiff/libtiff")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if not self.options.cxx:
            self.settings.compiler_cxx_standard = None
            self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.zlib:
            self.requires("zlib")
        if self.options.libdeflate:
            self.requires("libdeflate")
        if self.options.lzma:
            self.requires("xz")
        if self.options.jpeg:
            self.requires("libjpeg-turbo")
        if self.options.jbig:
            self.requires("jbig")
        if self.options.zstd:
            self.requires("zstd")
        if self.options.webp:
            self.requires("libwebp")

    def source(self):
        get(
            self,
            url=f"https://gitlab.com/libtiff/libtiff/-/archive/v{self.version}/libtiff-v{self.version}.tar.gz",
            sha256="62b15f44c10106065211efa22a2dc77937bd97ee1f6e3afd2c9659010de112eb",
            destination=self.folders.source,
            strip_root=True)
        # Drop the tested /W4 warning level so the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "cmake" / "CompilerChecks.cmake",
            "                /W4\n", "", strict=False)
        self._patch_sources()

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["lzma"] = self.options.lzma
        tc.variables["jpeg"] = self.options.jpeg
        tc.variables["jpeg12"] = False
        tc.variables["jbig"] = self.options.jbig
        tc.variables["zlib"] = self.options.zlib
        tc.variables["libdeflate"] = self.options.libdeflate
        tc.variables["zstd"] = self.options.zstd
        tc.variables["webp"] = self.options.webp
        tc.variables["lerc"] = False  # TODO: add lerc support for libtiff versions >= 4.3.0

        # Disable tools, test, contrib, man & html generation
        tc.variables["tiff-tools"] = False
        tc.variables["tiff-tests"] = False
        tc.variables["tiff-contrib"] = False
        tc.variables["tiff-docs"] = False
        cxx_option_name = "tiff-cxx"
        tc.variables[cxx_option_name] = self.options.cxx
        # BUILD_SHARED_LIBS must be set in command line because defined upstream before project()
        tc.cache_variables["BUILD_SHARED_LIBS"] = bool(self.options.shared)
        tc.cache_variables["CMAKE_FIND_PACKAGE_PREFER_CONFIG"] = True
        tc.cache_variables["HAVE_JPEGTURBO_DUAL_MODE_8_12"] = self.options.jpeg
        if cross_building(self):
            # libtiff's FindCMath does find_library(NAMES m). The cross gcc's sysroot is '/', and the
            # aarch64 libm lives in /usr/<triplet>/lib which CMake doesn't search by default -> the
            # check fails ("CMath_pow"). Add that dir to CMAKE_LIBRARY_PATH so find_library finds it.
            _triplet = {"ARM": "aarch64-linux-gnu", "X64": "x86_64-linux-gnu"}.get(str(self.settings.arch))
            if _triplet:
                tc.cache_variables["CMAKE_LIBRARY_PATH"] = f"/usr/{_triplet}/lib"
        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("jbig", "cmake_file_name", "JBIG")
        deps.set_property("jbig", "cmake_target_name", "JBIG::JBIG")
        deps.set_property("xz", "cmake_file_name", "liblzma")
        deps.set_property("xz", "cmake_target_name", "liblzma::liblzma")
        deps.set_property("libdeflate", "cmake_file_name", "Deflate")
        deps.set_property("libdeflate", "cmake_target_name", "Deflate::Deflate")
        deps.set_property("zstd", "cmake_file_name", "ZSTD")
        if self.options.jpeg:
            # libtiff strips its bundled FindJPEG.cmake and prefers config mode,
            # so present libjpeg-turbo as a JPEGConfig.cmake for find_package(JPEG)
            deps.set_property("libjpeg-turbo", "cmake_file_name", "JPEG")
            deps.set_property("libjpeg-turbo", "cmake_target_name", "JPEG::JPEG")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses", ignore_case=True, keep_path=False)
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "TIFF")
        self.info.set_property("cmake_target_name", "TIFF::TIFF")
        self.info.set_property("pkg_config_name", f"libtiff-{Version(self.version).major}")
        suffix = "d" if is_msvc(self) and self.settings.build_type == "Debug" else ""
        if self.options.cxx:
            self.info.libs.append(f"tiffxx{suffix}")
        self.info.libs.append(f"tiff{suffix}")
        if self.settings.os in ["Linux", "Android", "FreeBSD", "SunOS", "AIX"]:
            self.info.system_libs.append("m")

        requires: list[str] = []
        if self.options.zlib:
            requires.append("zlib::zlib")
        if self.options.libdeflate:
            requires.append("libdeflate::libdeflate")
        if self.options.lzma:
            requires.append("xz::xz")
        if self.options.jpeg:
            requires.append("libjpeg-turbo::jpeg")
        if self.options.jbig:
            requires.append("jbig::jbig")
        if self.options.zstd:
            requires.append("zstd::zstd")
        if self.options.webp:
            requires.append("libwebp::webp")
        self.info.requires = requires

    def _patch_sources(self):
        apply_patches(self)

        # remove FindXXXX for recipe dependencies
        for module in ["Deflate", "JBIG", "JPEG", "LERC", "WebP", "ZSTD", "liblzma", "LibLZMA"]:
            rm(self, f"Find{module}.cmake", self.folders.source / "cmake")

        # Export symbols of tiffxx for msvc shared
        replace_in_file(
            self,
            self.folders.source / "libtiff" / "CMakeLists.txt",
            "set_target_properties(tiffxx PROPERTIES SOVERSION ${SO_COMPATVERSION})",
            "set_target_properties(tiffxx PROPERTIES SOVERSION ${SO_COMPATVERSION} WINDOWS_EXPORT_ALL_SYMBOLS ON)")
