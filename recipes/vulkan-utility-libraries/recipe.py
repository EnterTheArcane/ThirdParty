from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import copy, get, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vulkan-utility-libraries"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/Vulkan-Utility-Libraries")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("vulkan-headers")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/Vulkan-Utility-Libraries/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="e8eca1be31a658c9d0ca30951f2fc7912e4bb01502da64f8decdc71836241a6c",
            destination=self.folders.source,
            strip_root=True)
        for text in [
            "set(CMAKE_CXX_STANDARD 17)", "set(CMAKE_CXX_STANDARD_REQUIRED ON)",
            "set(CMAKE_POSITION_INDEPENDENT_CODE ON)",
        ]:
            replace_in_file(
                self, self.folders.source / "CMakeLists.txt",
                text, "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_TESTS"] = False
        tc.cache_variables["VUL_ENABLE_INSTALL"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "VulkanUtilityLibraries")

        self.info.components["UtilityHeaders"].libs = []
        self.info.components["UtilityHeaders"].includedirs = ["include"]
        self.info.components["UtilityHeaders"].set_property("cmake_target_name", "Vulkan::UtilityHeaders")
        self.info.components["UtilityHeaders"].requires = ["vulkan-headers::vulkan-headers"]

        self.info.components["SafeStruct"].libs = ["VulkanSafeStruct"]
        self.info.components["SafeStruct"].set_property("cmake_target_name", "Vulkan::SafeStruct")
        self.info.components["SafeStruct"].requires = ["UtilityHeaders", "vulkan-headers::vulkan-headers"]

        self.info.components["LayerSettings"].libs = ["VulkanLayerSettings"]
        self.info.components["LayerSettings"].set_property("cmake_target_name", "Vulkan::LayerSettings")
        self.info.components["LayerSettings"].requires = ["UtilityHeaders", "vulkan-headers::vulkan-headers"]
