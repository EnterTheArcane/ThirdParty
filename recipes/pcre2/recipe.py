from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_pcre2_8: bool = True
    build_pcre2_16: bool = True
    build_pcre2_32: bool = True
    build_pcre2grep: bool = True
    with_zlib: bool = True
    with_bzip2: bool = True
    support_jit: bool = False
    grep_support_callout_fork: bool = True
    link_size: Literal[2, 3, 4] = 2


class Recipe(RecipeBase[_Options]):
    name = "pcre2"
    version = "10.47"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "PCRE2Project/pcre2")
        return Version(repo.latest_release.removeprefix("pcre2-"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None
        if not self.options.build_pcre2grep:
            self.options.with_zlib = False
            self.options.with_bzip2 = False
            self.options.grep_support_callout_fork = False

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_zlib:
            self.requires("zlib")
        if self.options.with_bzip2:
            self.requires("bzip2")

    def source(self):
        get(
            self,
            url=f"https://github.com/PCRE2Project/pcre2/releases/download/pcre2-{self.version}/pcre2-{self.version}.tar.bz2",
            sha256="47fe8c99461250d42f89e6e8fdaeba9da057855d06eb7fc08d9ca03fd08d7bc7",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        # Mandatory because upstream CMakeLists overrides BUILD_SHARED_LIBS as a CACHE variable
        # (see upstream issue 11840)
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["BUILD_STATIC_LIBS"] = not self.options.shared
        tc.variables["PCRE2_BUILD_PCRE2GREP"] = self.options.build_pcre2grep
        tc.variables["PCRE2_SUPPORT_LIBZ"] = self.options.with_zlib
        tc.variables["PCRE2_SUPPORT_LIBBZ2"] = self.options.with_bzip2
        tc.variables["PCRE2_BUILD_TESTS"] = False
        if is_msvc(self):
            tc.variables["PCRE2_STATIC_RUNTIME"] = is_msvc_static_runtime(self)
        tc.variables["PCRE2_DEBUG"] = self.settings.build_type == "Debug"
        tc.variables["PCRE2_BUILD_PCRE2_8"] = self.options.build_pcre2_8
        tc.variables["PCRE2_BUILD_PCRE2_16"] = self.options.build_pcre2_16
        tc.variables["PCRE2_BUILD_PCRE2_32"] = self.options.build_pcre2_32
        tc.variables["PCRE2_SUPPORT_JIT"] = self.options.support_jit
        tc.variables["PCRE2_LINK_SIZE"] = self.options.link_size
        tc.variables["PCRE2GREP_SUPPORT_CALLOUT_FORK"] = self.options.grep_support_callout_fork
        # 10.47 accidentally dropped the list(APPEND CMAKE_MODULE_PATH cmake/) call;
        # inject it via the toolchain so cmake/ modules (PCRE2CheckVscript etc.) can be found
        tc.variables["CMAKE_MODULE_PATH"] = (self.folders.source / "cmake").as_posix()
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENCE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "man")
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "PCRE2")
        self.info.set_property("pkg_config_name", "libpcre2")
        if self.options.build_pcre2_8:
            # pcre2-8
            self.info.components["pcre2-8"].set_property("cmake_target_name", "PCRE2::8BIT")
            self.info.components["pcre2-8"].set_property("pkg_config_name", "libpcre2-8")
            self.info.components["pcre2-8"].libs = [self._lib_name("pcre2-8")]
            if not self.options.shared:
                self.info.components["pcre2-8"].defines.append("PCRE2_STATIC")
            # pcre2-posix
            self.info.components["pcre2-posix"].set_property("cmake_target_name", "PCRE2::POSIX")
            self.info.components["pcre2-posix"].set_property("pkg_config_name", "libpcre2-posix")
            self.info.components["pcre2-posix"].libs = [self._lib_name("pcre2-posix")]
            self.info.components["pcre2-posix"].requires = ["pcre2-8"]
            if is_msvc(self) and self.options.shared:
                self.info.components["pcre2-posix"].defines.append("PCRE2POSIX_SHARED=1")

        # pcre2-16
        if self.options.build_pcre2_16:
            self.info.components["pcre2-16"].set_property("cmake_target_name", "PCRE2::16BIT")
            self.info.components["pcre2-16"].set_property("pkg_config_name", "libpcre2-16")
            self.info.components["pcre2-16"].libs = [self._lib_name("pcre2-16")]
            if not self.options.shared:
                self.info.components["pcre2-16"].defines.append("PCRE2_STATIC")
        # pcre2-32
        if self.options.build_pcre2_32:
            self.info.components["pcre2-32"].set_property("cmake_target_name", "PCRE2::32BIT")
            self.info.components["pcre2-32"].set_property("pkg_config_name", "libpcre2-32")
            self.info.components["pcre2-32"].libs = [self._lib_name("pcre2-32")]
            if not self.options.shared:
                self.info.components["pcre2-32"].defines.append("PCRE2_STATIC")

        if self.options.build_pcre2grep:
            # FIXME: This is a workaround to avoid RecipeException. zlib and bzip2
            # are optional requirements of pcre2grep executable, not of any pcre2 lib.
            if self.options.with_zlib:
                self.info.components["pcre2-8"].requires.append("zlib::zlib")
            if self.options.with_bzip2:
                self.info.components["pcre2-8"].requires.append("bzip2::bzip2")

    def _patch_sources(self):
        apply_patches(self)
        cmakelists = self.folders.source / "CMakeLists.txt"
        # Avoid CMP0006 error (macos bundle)
        if self.settings.os == "Mac":
            replace_in_file(
                self, cmakelists,
                "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}",
                "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR} BUNDLE DESTINATION ${CMAKE_INSTALL_BINDIR}")
        # pcre2-config does not correctly include '-static' in static library names
        if is_msvc(self):
            postfix = "-static" if not self.options.shared else ""
            if self.settings.build_type == "Debug":
                postfix += "d"
            replace_in_file(self, cmakelists, "configure_file(pcre2-config.in", f'set(LIB_POSTFIX "{postfix}")\nconfigure_file(pcre2-config.in')

    def _lib_name(self, name: str) -> str:
        libname = name
        if is_msvc(self) and not self.options.shared:
            libname += "-static"
        if self.settings.os == "Windows":
            if self.settings.build_type == "Debug":
                libname += "d"
            if self.settings.compiler == "gcc" and self.options.shared:
                libname += ".dll"
        return libname
