from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, copy, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "cutlass"
    version = "4.6.1"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "NVIDIA/cutlass")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/NVIDIA/cutlass/archive/refs/tags/v{self.version}.tar.gz",
            sha256="455d9ba37d57cb214d67b5d1a6070441244b378bcacb2e916c3b86f2a9b02e1c",
            destination=self.folders.source,
            strip_root=True)
        # Don't look for CUDA, we're only installing the headers.
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "include(${CMAKE_CURRENT_SOURCE_DIR}/CUDA.cmake)",
            "if(NOT CUTLASS_ENABLE_HEADERS_ONLY)\n"
            "  include(${CMAKE_CURRENT_SOURCE_DIR}/CUDA.cmake)\n"
            "endif()")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_SUPPRESS_REGENERATION"] = True
        tc.cache_variables["CUTLASS_ENABLE_CUBLAS"] = False
        tc.cache_variables["CUTLASS_ENABLE_CUDNN"] = False
        tc.cache_variables["CUTLASS_ENABLE_GTEST_UNIT_TESTS"] = False
        tc.cache_variables["CUTLASS_ENABLE_HEADERS_ONLY"] = True
        tc.cache_variables["CUTLASS_ENABLE_LIBRARY"] = False
        tc.cache_variables["CUTLASS_ENABLE_PERFORMANCE"] = False
        tc.cache_variables["CUTLASS_ENABLE_PROFILER"] = False
        tc.cache_variables["CUTLASS_ENABLE_TESTS"] = False
        tc.cache_variables["CUTLASS_ENABLE_TOOLS"] = False
        tc.cache_variables["CUTLASS_ENABLE_SELF_CONTAINED_INCLUDES_CHECK"] = False
        tc.cache_variables["CUTLASS_INSTALL_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib")
        rmdir(self, self.folders.package / "test")

    def package_info(self):
        self.info.set_property("cmake_file_name", "NvidiaCutlass")
        self.info.set_property("cmake_target_name", "nvidia::cutlass::cutlass")
        self.info.bindirs = []
        self.info.libdirs = []
