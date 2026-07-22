import os
from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building, stdcpp_library
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, replace_in_file, rename, rm, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    assembly: bool = True
    bit_depth: Literal[8, 10, 12] = 8
    HDR10: bool = False
    SVG_HEVC_encoder: bool = False
    with_numa: bool = False


class Recipe(RecipeBase[_Options]):
    name = "x265"
    version = "4.2"
    # https://bitbucket.org/multicoreware/x265/src/default/COPYING
    license = "GPL-2.0-only", "commercial"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://downloads.videolan.org/videolan/x265/")
        return Version(index.latest_release(r"x265_([\d.]+)\.tar\.gz"))

    def configure(self):
        if self.settings.os != "Linux":
            self.options.with_numa = False
        # FIXME: Disable assembly by default if host is arm and compiler apple-clang for the moment.
        # Indeed, apple-clang is not able to understand some asm instructions of libx265
        # FIXME: Disable assembly by default if host is Android for the moment. It fails to build
        if (self.settings.compiler == "apple-clang" and "arm" in self.settings.arch) or self.settings.os == "Android":
            self.options.assembly = False
        if is_msvc(self) and self.settings.arch == "ARM":
            # Build errors, possibly unsupported
            self.options.assembly = False

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_numa:
            self.requires("libnuma")
        if self.options.assembly:
            if self.settings.arch in ["X64"]:
                self.requires_tool("nasm")

    def source(self):
        get(
            self,
            url=f"https://downloads.videolan.org/videolan/x265/x265_{self.version}.tar.gz",
            sha256="40b1ea0453e0309f0eba934e0ddf533f8f6295966679e8894e8f1c1c8d5e1210",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = CMakeToolchain(self)
        tc.variables["ENABLE_PIC"] = self.options.pic
        tc.variables["ENABLE_SHARED"] = self.options.shared
        tc.variables["ENABLE_ASSEMBLY"] = self.options.assembly
        tc.variables["ENABLE_LIBNUMA"] = self.options.with_numa
        if self.settings.os == "Mac":
            tc.variables["CMAKE_SHARED_LINKER_FLAGS"] = "-Wl,-read_only_relocs,suppress"
        tc.variables["HIGH_BIT_DEPTH"] = self.options.bit_depth != 8
        tc.variables["MAIN12"] = self.options.bit_depth == 12
        tc.variables["ENABLE_HDR10_PLUS"] = self.options.HDR10
        tc.variables["ENABLE_SVT_HEVC"] = self.options.SVG_HEVC_encoder
        if is_msvc(self):
            tc.variables["STATIC_LINK_CRT"] = is_msvc_static_runtime(self)
            tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0091"] = "NEW"
        if self.settings.os == "Linux":
            tc.variables["PLATFORM_LIBS"] = "dl"
        if "arm" in self.settings.arch:
            tc.variables["CROSS_COMPILE_ARM"] = cross_building(self)
        if self.settings.os in ("Linux", "FreeBSD") and self.settings.arch == "ARM":
            # x265's aarch64 asm addresses internal data tables (e.g. x265_entropyStateBits, defined
            # in dct.cpp) with ADRP+ADD direct page-relative relocations - its `movrel` macro has no
            # GOT-indirect path on Linux. Those R_AARCH64_ADR_PREL_PG_HI21 relocations "may bind
            # externally" when this static lib is linked into a shared object (e.g. libheif's
            # plugins), which ld rejects. Building the C/C++ with hidden visibility makes those data
            # symbols bind locally so the direct relocations are valid.
            tc.extra_cflags.append("-fvisibility=hidden")
            tc.extra_cxxflags.append("-fvisibility=hidden")
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "source")
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

        if self.options.shared:
            if is_msvc(self):
                static_lib = "x265-static.lib"
            else:
                static_lib = "libx265.a"
            os.unlink(self.folders.package / "lib" / static_lib)

        if is_msvc(self):
            name = "libx265.lib" if self.options.shared else "x265-static.lib"
            rename(
                self, self.folders.package / "lib" / name,
                self.folders.package / "lib" / "x265.lib")

        if self.settings.os == "Windows" and self.options.shared:
            rm(self, "*[!.dll]", self.folders.package / "bin")
        else:
            rmdir(self, self.folders.package / "bin")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "x265")
        self.info.set_property("cmake_target_name", "x265::x265")
        self.info.set_property("pkg_config_name", "x265")
        self.info.libs = ["x265"]
        if self.settings.os == "Windows":
            if self.options.shared:
                self.info.defines.append("X265_API_IMPORTS")
            if not self.options.shared:
                self.info.system_libs.extend(["advapi32"])
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["dl", "pthread", "m", "rt"])
            if not self.options.shared:
                self.info.sharedlinkflags = ["-Wl,-Bsymbolic,-znoexecstack"]
        elif self.settings.os == "Android":
            self.info.system_libs.extend(["dl", "m"])
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                if self.settings.os == "Android" and self.settings.compiler_libcxx == "c++_static":
                    self.info.system_libs.append("c++abi")
                self.info.system_libs.append(libcxx)

    def _patch_sources(self):
        apply_patches(self)
        cmakelists = self.folders.source / "source" / "CMakeLists.txt"
        # Drop the project's add_definitions(/W4) so the quiet -w wins without cl's D9025 spam.
        replace_in_file(self, cmakelists, "add_definitions(/W4)", "# add_definitions(/W4)", strict=False)
        replace_in_file(
            self, cmakelists,
            "if((WIN32 AND ENABLE_CLI) OR (WIN32 AND ENABLE_SHARED))",
            "if(FALSE)")
        if self.settings.os == "Android":
            replace_in_file(self, cmakelists, "list(APPEND PLATFORM_LIBS pthread)", "")
            replace_in_file(self, cmakelists, "list(APPEND PLATFORM_LIBS rt)", "")
        # The finite-math-only optimization has no effect and can cause linking errors
        # when linked against glibc >= 2.31
        replace_in_file(
            self, cmakelists,
            "add_definitions(-ffast-math)",
            "add_definitions(-ffast-math -fno-finite-math-only)")
