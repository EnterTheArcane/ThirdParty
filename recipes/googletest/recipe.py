from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.microsoft import msvc_runtime_flag
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    no_main: bool = False


class Recipe(RecipeBase[_Options]):
    name = "googletest"
    version = "1.17.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "google/googletest")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/googletest/archive/v{self.version}.tar.gz",
            sha256="65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c",
            destination=self.folders.source,
            strip_root=True)

        internal_utils = self.folders.source / "googletest" / "cmake" / "internal_utils.cmake"
        replace_in_file(self, internal_utils, "-WX", "")
        # Also drop the base /W4 (in cxx_base_flags) so the quiet -w wins without cl's D9025 spam.
        replace_in_file(self, internal_utils, 'set(cxx_base_flags "-GS -W4', 'set(cxx_base_flags "-GS', strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_GMOCK"] = True
        tc.variables["gtest_hide_internal_symbols"] = False

        if self.settings.compiler_runtime:
            tc.variables["gtest_force_shared_crt"] = "MD" in msvc_runtime_flag(self)
        tc.variables["gtest_disable_pthreads"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.pdb", self.folders.package / "lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "GTest")

        # gtest
        self.info.components["libgtest"].set_property("cmake_target_name", "GTest::gtest")
        self.info.components["libgtest"].set_property("cmake_target_aliases", ["GTest::GTest"])
        self.info.components["libgtest"].set_property("pkg_config_name", "gtest")
        self.info.components["libgtest"].libs = ["gtest"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["libgtest"].system_libs.append("m")
            self.info.components["libgtest"].system_libs.append("pthread")
        if self.settings.os == "Neutrino" and self.settings.os_version == "7.1":
            self.info.components["libgtest"].system_libs.append("regex")
        if self.options.shared:
            self.info.components["libgtest"].defines.append("GTEST_LINKED_AS_SHARED_LIBRARY=1")

        # gtest_main
        if not self.options.no_main:
            self.info.components["gtest_main"].set_property("cmake_target_name", "GTest::gtest_main")
            self.info.components["gtest_main"].set_property("cmake_target_aliases", ["GTest::Main"])
            self.info.components["gtest_main"].set_property("pkg_config_name", "gtest_main")
            self.info.components["gtest_main"].libs = ["gtest_main"]
            self.info.components["gtest_main"].requires = ["libgtest"]

        # gmock
        self.info.components["gmock"].set_property("cmake_target_name", "GTest::gmock")
        self.info.components["gmock"].set_property("pkg_config_name", "gmock")
        self.info.components["gmock"].libs = ["gmock"]
        self.info.components["gmock"].requires = ["libgtest"]

        # gmock_main
        if not self.options.no_main:
            self.info.components["gmock_main"].set_property("cmake_target_name", "GTest::gmock_main")
            self.info.components["gmock_main"].set_property("pkg_config_name", "gmock_main")
            self.info.components["gmock_main"].libs = ["gmock_main"]
            self.info.components["gmock_main"].requires = ["gmock"]
