from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    mz_compatibility: bool = False
    with_zlib: bool = True
    with_bzip2: bool = True
    with_lzma: bool = True
    with_zstd: bool = True
    with_openssl: bool = True
    with_iconv: bool = True
    with_libbsd: bool = True
    with_libcomp: bool = True


class Recipe(RecipeBase[_Options]):
    name = "minizip-ng"
    version = "4.2.2"
    license = "Zlib"

    def latest_version(self):
        repo = GithubRepository(self, "zlib-ng/minizip-ng")
        return Version(repo.latest_release)

    def configure(self):
        if self.settings.os == "Windows":
            self.options.with_iconv = False
            self.options.with_libbsd = False
        if not is_apple_os(self):
            self.options.with_libcomp = False

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None
        if self.options.with_libcomp:
            self.options.with_zlib = False

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_zlib:
            self.requires("zlib")
        if self.options.with_bzip2:
            self.requires("bzip2")
        if self.options.with_lzma:
            self.requires("xz")
        if self.options.with_zstd:
            self.requires("zstd")
        if self.options.with_openssl:
            self.requires("openssl")
        if self.settings.os != "Windows":
            if self.options.with_iconv:
                self.requires("libiconv")

    def source(self):
        get(
            self,
            url=f"https://github.com/zlib-ng/minizip-ng/archive/{self.version}.tar.gz",
            sha256="71af7b9799856d8b03619df3949e9c1be9703f8de0795af71399ba283cb27aac",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["MZ_FETCH_LIBS"] = False
        tc.cache_variables["MZ_COMPAT"] = self.options.mz_compatibility
        tc.cache_variables["MZ_ZLIB"] = self.options.with_zlib
        tc.cache_variables["MZ_ZLIB_FLAVOR"] = "zlib"
        tc.cache_variables["MZ_BZIP2"] = self.options.with_bzip2
        tc.cache_variables["MZ_PPMD"] = False
        tc.cache_variables["MZ_LZMA"] = self.options.with_lzma
        tc.cache_variables["MZ_ZSTD"] = self.options.with_zstd
        tc.cache_variables["MZ_OPENSSL"] = self.options.with_openssl
        tc.cache_variables["MZ_LIBCOMP"] = self.options.with_libcomp
        if self.settings.os != "Windows":
            tc.cache_variables["MZ_ICONV"] = self.options.with_iconv
            tc.cache_variables["MZ_LIBBSD"] = self.options.with_libbsd
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True

        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_PkgConfig"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "minizip")
        self.info.set_property("cmake_target_name", "MINIZIP::minizip")
        self.info.set_property("pkg_config_name", "minizip")

        suffix = "" if self.options.mz_compatibility else "-ng"
        self.info.components["minizip"].libs = [f"minizip{suffix}"]
        if self.options.with_lzma:
            self.info.components["minizip"].defines.append("HAVE_LZMA")
        if is_apple_os(self) and self.options.with_libcomp:
            self.info.components["minizip"].defines.append("HAVE_LIBCOMP")
            self.info.components["minizip"].system_libs.append("compression")
        if self.options.with_bzip2:
            self.info.components["minizip"].defines.append("HAVE_BZIP2")

        minizip_dir = "minizip" if self.options.mz_compatibility else "minizip-ng"
        self.info.components["minizip"].includedirs.append(str(self.folders.package / "include" / minizip_dir))

        self.info.components["minizip"].set_property("cmake_target_name", "MINIZIP::minizip")
        self.info.components["minizip"].set_property("pkg_config_name", "minizip")
        if self.options.with_zlib:
            self.info.components["minizip"].requires.append("zlib::zlib")
        if self.options.with_bzip2:
            self.info.components["minizip"].requires.append("bzip2::bzip2")
        if self.options.with_lzma:
            self.info.components["minizip"].requires.append("xz::xz")
        if self.options.with_zstd:
            self.info.components["minizip"].requires.append("zstd::zstd")
        if self.options.with_openssl:
            self.info.components["minizip"].requires.append("openssl::openssl")
        elif is_apple_os(self):
            self.info.components["minizip"].frameworks.extend(["CoreFoundation", "Security"])
        elif self.settings.os == "Windows":
            self.info.components["minizip"].system_libs.append("crypt32")
        if self.settings.os != "Windows" and self.options.with_iconv:
            self.info.components["minizip"].requires.append("libiconv::libiconv")
