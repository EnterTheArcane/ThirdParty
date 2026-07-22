from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False


class Recipe(RecipeBase[_Options]):
    name = "d3d12-memory-allocator"
    version = "3.2.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "GPUOpen-LibrariesAndSDKs/D3D12MemoryAllocator")
        return Version(repo.latest_release.removeprefix("v"))

    def validate(self):
        if self.settings.os != "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Windows")

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/GPUOpen-LibrariesAndSDKs/D3D12MemoryAllocator/archive/refs/tags/v{self.version}.tar.gz",
            sha256="71d740ecb2d6cdf93b273ae571eb80097a530443993b0a5cb2bdb3cacc1548db",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_DOCUMENTATION"] = False
        tc.variables["D3D12MA_BUILD_SAMPLE"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "*LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "D3D12MemoryAllocator")
        self.info.set_property("cmake_target_name", "GPUOpen::D3D12MemoryAllocator")
        postfix = {"Release": "", "Debug": "d", "RelWithDebInfo": "rd", "MinSizeRel": "s"}[str(self.settings.build_type)]
        self.info.libs = [f"D3D12MA{postfix}"]
