from thirdparty import RecipeBase
from thirdparty.files import apply_patches, copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "vulkan-memory-allocator"
    version = "3.4.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires("vulkan-headers")

    def source(self):
        get(
            self,
            url=f"https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator/archive/refs/tags/v{self.version}.tar.gz",
            sha256="822aa850c6ce77346ae96a8a1d351d52e77e85929f35363849a0a4e638e0a2a1",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        include_dir = self.folders.source / "include"
        copy(self, "vk_mem_alloc.h", src=include_dir, dst=self.folders.package / "include")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
        self.info.set_property("cmake_file_name", "VulkanMemoryAllocator")
        self.info.set_property("cmake_target_name", "GPUOpen::VulkanMemoryAllocator")
        self.info.set_property("cmake_target_aliases", ["VulkanMemoryAllocator", ])
