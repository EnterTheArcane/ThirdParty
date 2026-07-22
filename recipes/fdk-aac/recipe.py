from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "fdk-aac"
    version = "2.0.3"
    license = "https://github.com/mstorsjo/fdk-aac/blob/master/NOTICE"

    def latest_version(self):
        repo = GithubRepository(self, "mstorsjo/fdk-aac")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/mstorsjo/fdk-aac/archive/refs/tags/v{self.version}.tar.gz",
            sha256="e25671cd96b10bad896aa42ab91a695a9e573395262baed4e4a2ff178d6a3a78",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_PROGRAMS"] = False
        tc.variables["FDK_AAC_INSTALL_CMAKE_CONFIG_MODULE"] = False
        tc.variables["FDK_AAC_INSTALL_PKGCONFIG_MODULE"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "NOTICE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "fdk-aac")
        self.info.set_property("cmake_target_name", "FDK-AAC::fdk-aac")
        self.info.set_property("pkg_config_name", "fdk-aac")

        self.info.components["fdk-aac"].libs = ["fdk-aac"]
        if self.settings.os in ["Linux", "FreeBSD", "Android"]:
            self.info.components["fdk-aac"].system_libs.append("m")

        self.info.components["fdk-aac"].set_property("cmake_target_name", "FDK-AAC::fdk-aac")
