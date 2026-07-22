import os

from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "vulkan-headers"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/Vulkan-Headers")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/Vulkan-Headers/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="6d1bb65e49520344cc0a48af3dc02e993781efff14c7ebdcb8ae9fa23ddf7e83",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["VULKAN_HEADERS_ENABLE_MODULE"] = False
        tc.cache_variables["VULKAN_HEADERS_ENABLE_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        copy(self, "*", src=self.folders.package / "share" / "vulkan" / "registry", dst=self.folders.package / "res" / "vulkan" / "registry")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "VulkanHeaders")
        self.info.components["vulkanheaders"].set_property("cmake_target_name", "Vulkan::Headers")
        self.info.components["vulkanheaders"].bindirs = []
        self.info.components["vulkanheaders"].libdirs = []

        self.info.components["vulkanregistry"].set_property("cmake_target_name", "Vulkan::Registry")
        self.info.components["vulkanregistry"].includedirs = [os.path.join("res", "vulkan", "registry")]
        self.info.components["vulkanregistry"].bindirs = []
        self.info.components["vulkanregistry"].libdirs = []
        self.info.components["vulkanregistry"].resdirs = ["res"]
