import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building, stdcpp_library
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir, save, rm, replace_in_file
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    avx512: bool = False
    avx512_spr: bool = False
    avx512_zen4: bool = False
    with_tcmalloc: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libjxl"
    version = "0.12.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "libjxl/libjxl")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.arch not in ["X64"]:
            self.options.avx512 = False
            self.options.avx512_spr = False
            self.options.avx512_zen4 = False

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("brotli")
        self.requires("highway")
        self.requires("little-cms")
        if self.options.with_tcmalloc:
            self.requires("gperftools")

    def source(self):
        get(
            self,
            url=f"https://github.com/libjxl/libjxl/archive/v{self.version}.tar.gz",
            sha256="03e9be69a30be4011f559da75328b6d7cea8ad921fabfbd551ce10bf45cdc992",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        # libjxl's own find_package(HWY/Brotli/LCMS2) lives in third_party/CMakeLists.txt,
        # which _patch_sources() empties. The deps are instead resolved by the CMakeDeps
        # aggregator (recipe_deps.cmake), injected right after project() so the hwy::hwy /
        # Brotli / LCMS2 targets exist before lib/CMakeLists.txt references them.
        tc.variables["CMAKE_PROJECT_LIBJXL_INCLUDE"] = (self.folders.generators / "recipe_deps.cmake").as_posix()
        tc.variables["BUILD_TESTING"] = False
        tc.variables["JPEGXL_STATIC"] = False
        tc.variables["JPEGXL_BUNDLE_LIBPNG"] = False
        tc.variables["JPEGXL_ENABLE_BENCHMARK"] = False
        tc.variables["JPEGXL_ENABLE_DOXYGEN"] = False
        tc.variables["JPEGXL_ENABLE_EXAMPLES"] = False
        tc.variables["JPEGXL_ENABLE_JNI"] = False
        tc.variables["JPEGXL_ENABLE_MANPAGES"] = False
        tc.variables["JPEGXL_ENABLE_OPENEXR"] = False
        tc.variables["JPEGXL_ENABLE_PLUGINS"] = False
        tc.variables["JPEGXL_ENABLE_SJPEG"] = False
        tc.variables["JPEGXL_ENABLE_SKCMS"] = False
        tc.variables["JPEGXL_ENABLE_TCMALLOC"] = self.options.with_tcmalloc
        tc.variables["JPEGXL_ENABLE_VIEWERS"] = False
        tc.variables["JPEGXL_ENABLE_TOOLS"] = False
        tc.variables["JPEGXL_FORCE_SYSTEM_BROTLI"] = True
        tc.variables["JPEGXL_FORCE_SYSTEM_GTEST"] = True
        tc.variables["JPEGXL_FORCE_SYSTEM_HWY"] = True
        tc.variables["JPEGXL_FORCE_SYSTEM_LCMS2"] = True
        tc.variables["JPEGXL_WARNINGS_AS_ERRORS"] = False
        tc.variables["JPEGXL_FORCE_NEON"] = False
        tc.variables["JPEGXL_ENABLE_AVX512"] = self.options.avx512
        tc.variables["JPEGXL_ENABLE_AVX512_SPR"] = self.options.avx512_spr
        tc.variables["JPEGXL_ENABLE_AVX512_ZEN4"] = self.options.avx512_zen4
        if cross_building(self):
            tc.variables["CMAKE_SYSTEM_PROCESSOR"] = str(self.settings.arch)
        # Allow non-cache_variables to be used
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
        # Skip the buggy custom FindAtomic and force the use of atomic library directly for libstdc++
        tc.variables["ATOMICS_LIBRARIES"] = "atomic" if self._atomic_required else ""
        tc.variables["JPEGXL_ENABLE_JPEGLI"] = False
        tc.variables["JPEGXL_ENABLE_JPEGLI_LIBJPEG"] = False
        # TODO: can hopefully be removed in newer versions
        # https://github.com/libjxl/libjxl/issues/3159
        if self.settings.build_type == "Debug" and is_msvc(self):
            tc.preprocessor_definitions["JXL_DEBUG_V_LEVEL"] = 1
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("brotli", "cmake_file_name", "Brotli")
        deps.set_property("brotli::brotlicommon", "cmake_target_name", "brotlicommon")
        deps.set_property("brotli::brotlidec", "cmake_target_name", "brotlidec")
        deps.set_property("brotli::brotlienc", "cmake_target_name", "brotlienc")
        deps.set_property("highway", "cmake_file_name", "HWY")
        deps.set_property("highway::hwy", "cmake_target_name", "hwy::hwy")
        deps.set_property("highway::hwy_contrib", "cmake_target_name", "hwy_contrib::hwy_contrib")
        deps.set_property("little-cms", "cmake_file_name", "LCMS2")
        deps.set_property("little-cms", "cmake_target_name", "lcms2")
        deps.generate()

        # CMakeDeps does not generate the CMakeDeps `recipe_deps.cmake` find_package
        # aggregator that libjxl injects via CMAKE_PROJECT_LIBJXL_INCLUDE (its own
        # find_package(HWY/Brotli/LCMS2) lives in third_party/CMakeLists.txt which
        # _patch_sources empties).  Write an equivalent so those targets exist at project() time.
        save(self, self.folders.generators / "recipe_deps.cmake",
             "find_package(Brotli)\nfind_package(HWY)\nfind_package(LCMS2)\n")

        # For tcmalloc
        deps = PkgConfigDeps(self)
        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        if self.options.shared:
            rm(self, "*.a", self.folders.package / "lib")
            rm(self, "*-static.lib", self.folders.package / "lib")

    def package_info(self):
        libcxx = stdcpp_library(self)

        # jxl
        self.info.components["jxl"].set_property("pkg_config_name", "libjxl")
        self.info.components["jxl"].libs = ["jxl"]
        self.info.components["jxl"].requires = ["brotli::brotli", "highway::highway", "little-cms::little-cms"]
        if self.options.with_tcmalloc:
            self.info.components["jxl"].requires.append("gperftools::tcmalloc_minimal")
        if self._atomic_required:
            self.info.components["jxl"].system_libs.append("atomic")
        if not self.options.shared:
            self.info.components["jxl"].defines.append("JXL_STATIC_DEFINE")
            if libcxx:
                self.info.components["jxl"].system_libs.append(libcxx)

        # jxl_cms
        self.info.components["jxl_cms"].set_property("pkg_config_name", "libjxl_cms")
        self.info.components["jxl_cms"].libs = ["jxl_cms"]
        self.info.components["jxl_cms"].requires = ["little-cms::little-cms", "highway::highway"]
        if not self.options.shared:
            self.info.components["jxl"].defines.append("JXL_CMS_STATIC_DEFINE")
            if libcxx:
                self.info.components["jxl_cms"].system_libs.append(libcxx)
        self.info.components["jxl"].requires.append("jxl_cms")

        # jxl_threads
        self.info.components["jxl_threads"].set_property("pkg_config_name", "libjxl_threads")
        self.info.components["jxl_threads"].libs = ["jxl_threads"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["jxl_threads"].system_libs = ["pthread"]
        if not self.options.shared:
            self.info.components["jxl_threads"].defines.append("JXL_THREADS_STATIC_DEFINE")
            if libcxx:
                self.info.components["jxl_threads"].system_libs.append(libcxx)

    @property
    def _atomic_required(self):
        return self.settings.compiler_libcxx in ["libstdc++", "libstdc++11"]

    def _patch_sources(self):
        # Disable tools, extras and third_party
        save(self, self.folders.source / "tools" / "CMakeLists.txt", "")
        save(self, self.folders.source / "third_party" / "CMakeLists.txt", "")
        # FindAtomics.cmake values are set by CMakeToolchain instead
        save(self, self.folders.source / "cmake" / "FindAtomics.cmake", "")

        # Allow pic to be set by Recipe (top-level set() was removed in 0.11.2; individual targets handle it)
        for cmake_file in ["jxl.cmake", "jxl_threads.cmake", "jxl_cms.cmake", "jpegli.cmake"]:
            path = self.folders.source / "lib" / cmake_file
            if os.path.exists(path):
                pic = "ON" if self.options.pic else "OFF"
                replace_in_file(self, path, "POSITION_INDEPENDENT_CODE ON", f"POSITION_INDEPENDENT_CODE {pic}")
