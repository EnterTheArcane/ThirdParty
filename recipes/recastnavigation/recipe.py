from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import copy, get, rmdir, rm
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "recastnavigation"
    version = "1.6.0"
    license = "Zlib"

    def latest_version(self):
        repo = GithubRepository(self, "recastnavigation/recastnavigation")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/recastnavigation/recastnavigation/archive/refs/tags/v{self.version}.tar.gz",
            sha256="d48ca0121962fa0639502c0f56c4e3ae72f98e55d88727225444f500775c0074",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["RECASTNAVIGATION_DEMO"] = False
        tc.cache_variables["RECASTNAVIGATION_TESTS"] = False
        tc.cache_variables["RECASTNAVIGATION_EXAMPLES"] = False
        tc.cache_variables["RECASTNAVIGATION_STATIC"] = not self.options.shared
        tc.cache_variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = self.options.shared
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "License.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.pdb", self.folders.package, recursive=True)

    def package_info(self):
        self.info.set_property("cmake_file_name", "recastnavigation")
        self.info.set_property("pkg_config_name", "recastnavigation")

        suffix = ""
        if self.settings.build_type == "Debug":
            suffix = "-d"

        self.info.components["Recast"].set_property("cmake_target_name", "RecastNavigation::Recast")
        self.info.components["Recast"].libs = ["Recast" + suffix]

        self.info.components["Detour"].set_property("cmake_target_name", "RecastNavigation::Detour")
        self.info.components["Detour"].libs = ["Detour" + suffix]

        self.info.components["DetourCrowd"].set_property("cmake_target_name", "RecastNavigation::DetourCrowd")
        self.info.components["DetourCrowd"].libs = ["DetourCrowd" + suffix]
        self.info.components["DetourCrowd"].requires = ["Detour"]

        self.info.components["DetourTileCache"].set_property("cmake_target_name", "RecastNavigation::DetourTileCache")
        self.info.components["DetourTileCache"].libs = ["DetourTileCache" + suffix]
        self.info.components["DetourTileCache"].requires = ["Detour"]

        self.info.components["DebugUtils"].set_property("cmake_target_name", "RecastNavigation::DebugUtils")
        self.info.components["DebugUtils"].libs = ["DebugUtils" + suffix]
        self.info.components["DebugUtils"].requires = ["Recast", "Detour", "DetourTileCache"]
