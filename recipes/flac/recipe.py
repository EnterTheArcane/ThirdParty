from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "flac"
    version = "1.5.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "xiph/flac")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("ogg")

    def source(self):
        get(
            self,
            url=f"https://github.com/xiph/flac/releases/download/{self.version}/flac-{self.version}.tar.xz",
            sha256="f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
        tc.variables["BUILD_EXAMPLES"] = False
        tc.variables["BUILD_DOCS"] = False
        tc.variables["BUILD_PROGRAMS"] = not is_apple_os(self) or self.settings.os == "Mac"
        tc.variables["BUILD_TESTING"] = False
        tc.variables["BUILD_CXXLIBS"] = True
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        replace_in_file(
            self,
            self.folders.source / "src" / "share" / "getopt" / "CMakeLists.txt",
            "find_package(Intl)",
            "")
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(
            self, "COPYING.*", src=self.folders.source,
            dst=self.folders.package / "licenses", keep_path=False)
        copy(
            self, "*.h", src=self.folders.source / "include" / "share",
            dst=self.folders.package / "include" / "share", keep_path=False)
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "flac")

        self.info.components["libflac"].set_property("cmake_target_name", "FLAC::FLAC")
        self.info.components["libflac"].libs = ["FLAC"]
        self.info.components["libflac"].requires = ["ogg::ogg"]

        self.info.components["libflac++"].set_property("cmake_target_name", "FLAC::FLAC++")
        self.info.components["libflac++"].libs = ["FLAC++"]
        self.info.components["libflac++"].requires = ["libflac"]

        if not self.options.shared:
            self.info.components["libflac"].defines = ["FLAC__NO_DLL"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["libflac"].system_libs += ["m"]
