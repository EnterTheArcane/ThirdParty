import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_prefix: bool = False
    default_reporter: str | None = None
    console_width: str = "80"
    no_posix_signals: bool = False


class Recipe(RecipeBase[_Options]):
    name = "catch2"
    version = "3.15.2"
    license = "BSL-1.0"

    def latest_version(self):
        repo = GithubRepository(self, "catchorg/Catch2")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/catchorg/Catch2/archive/v{self.version}.tar.gz",
            sha256="acfae120892c2b67a74142d36d060c0caa96f1c3aaa8aabd96e19961163d0420",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.cache_variables["CATCH_INSTALL_DOCS"] = False
        tc.cache_variables["CATCH_INSTALL_EXTRAS"] = True
        tc.cache_variables["CATCH_DEVELOPMENT_BUILD"] = False
        tc.variables["CATCH_CONFIG_PREFIX_ALL"] = self.options.with_prefix
        tc.variables["CATCH_CONFIG_CONSOLE_WIDTH"] = self.options.console_width
        if self.options.default_reporter:
            tc.variables["CATCH_CONFIG_DEFAULT_REPORTER"] = self._default_reporter_str
        tc.variables["CATCH_CONFIG_NO_POSIX_SIGNALS"] = self.options.no_posix_signals
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, pattern="LICENSE.txt", dst=self.folders.package / "licenses", src=self.folders.source)
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "share")
        for cmake_file in ["ParseAndAddCatchTests.cmake", "Catch.cmake", "CatchAddTests.cmake"]:
            copy(
                self,
                cmake_file,
                src=self.folders.source / "extras",
                dst=self.folders.package / "lib" / "cmake" / "Catch2",
                )

    def package_info(self):
        self.info.set_property("cmake_file_name", "Catch2")
        self.info.set_property("cmake_target_name", "Catch2::Catch2WithMain")
        self.info.set_property("pkg_config_name", "catch2-with-main")

        lib_suffix = "d" if self.settings.build_type == "Debug" else ""
        self.info.components["_catch2"].set_property("cmake_target_name", "Catch2::Catch2")
        self.info.components["_catch2"].set_property("pkg_config_name", "catch2")
        self.info.components["_catch2"].libs = ["Catch2" + lib_suffix]

        self.info.components["catch2_with_main"].builddirs.append(os.path.join("lib", "cmake", "Catch2"))
        self.info.components["catch2_with_main"].libs = ["Catch2Main" + lib_suffix]
        self.info.components["catch2_with_main"].requires = ["_catch2"]
        self.info.components["catch2_with_main"].system_libs = ["log"] if self.settings.os == "Android" else []
        self.info.components["catch2_with_main"].set_property("cmake_target_name", "Catch2::Catch2WithMain")
        self.info.components["catch2_with_main"].set_property("pkg_config_name", "catch2-with-main")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["catch2_with_main"].system_libs.append("m")

        defines: list[str] = []
        if self.options.with_prefix:
            defines.append("CATCH_CONFIG_PREFIX_ALL")
        if self.options.default_reporter:
            defines.append(f"CATCH_CONFIG_DEFAULT_REPORTER={self._default_reporter_str}")
        self.info.components["catch2_with_main"].defines = defines

    @property
    def _default_reporter_str(self):
        return str(self.options.default_reporter).strip('"')
