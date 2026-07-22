from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "highway"
    version = "1.4.0"
    license = "Apache-2.0", "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "google/highway")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/highway/archive/{self.version}.tar.gz",
            sha256="e72241ac9524bb653ae52ced768b508045d4438726a303f10181a38f764a453c",
            destination=self.folders.source,
            strip_root=True)
        self._patch_sources()

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.variables["HWY_ENABLE_EXAMPLES"] = False
        tc.variables["HWY_ENABLE_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        license_folder = self.folders.package / "licenses"
        copy(self, "LICENSE", src=self.folders.source, dst=license_folder)
        copy(self, "LICENSE-BSD3", src=self.folders.source, dst=license_folder)
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.components["hwy"].set_property("pkg_config_name", "libhwy")
        self.info.components["hwy"].libs = ["hwy"]
        self.info.components["hwy"].defines.append(
            "HWY_SHARED_DEFINE" if self.options.shared else "HWY_STATIC_DEFINE"
        )
        self.info.components["hwy_contrib"].set_property("pkg_config_name", "libhwy-contrib")
        self.info.components["hwy_contrib"].libs = ["hwy_contrib"]
        self.info.components["hwy_contrib"].requires = ["hwy"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["hwy_contrib"].system_libs.append("pthread")

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")

    def _patch_sources(self):
        # No hardcoded CMAKE_CXX_STANDARD
        replace_in_file(
            self, self.folders.source / "cmake" / "FindAtomics.cmake",
            "set(CMAKE_CXX_STANDARD 11)", "")
        replace_in_file(
            self, self.folders.source / "cmake" / "FindAtomics.cmake",
            "unset(CMAKE_CXX_STANDARD)", "")
        # Honor pic option
        cmakelists = self.folders.source / "CMakeLists.txt"
        replace_in_file(self, cmakelists, "set(CMAKE_POSITION_INDEPENDENT_CODE TRUE)", "")
        # highway disables RTTI/exceptions by appending /GR- /EHs-c- (via HWY_FLAGS) on top of
        # CMake's default /GR /EHsc, which cl reports as cosmetic "D9025: overriding '/GR' with
        # '/GR-'" / "'/EHs' with '/EHs-'". Strip the defaults from CMAKE_CXX_FLAGS so highway's
        # negations apply cleanly without the warning.
        replace_in_file(
            self, cmakelists,
            "if (MSVC)\n  set(HWY_FLAGS",
            'if (MSVC)\n'
            '  string(REGEX REPLACE " /GR( |$)" " " CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")\n'
            '  string(REPLACE " /EHsc" "" CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")\n'
            "  set(HWY_FLAGS",
            strict=False)
        replace_in_file(
            self, cmakelists,
            "set_property(TARGET hwy PROPERTY POSITION_INDEPENDENT_CODE ON)",
            "")
