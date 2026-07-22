from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "meshoptimizer"
    version = "1.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "zeux/meshoptimizer")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/zeux/meshoptimizer/archive/refs/tags/v{self.version}.tar.gz",
            sha256="e40f71b809cdf3361b9a4def85fd44534e8733ce29d4b943c145b76859e4c2b4",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["MESHOPT_BUILD_SHARED_LIBS"] = self.options.shared
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rm(self, "*.pdb", self.folders.package / "bin")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "meshoptimizer")
        self.info.set_property("cmake_target_name", "meshoptimizer::meshoptimizer")
        self.info.libs = ["meshoptimizer"]
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)
        if self.options.shared:
            self.info.defines = ["MESHOPTIMIZER_ALLOC_EXPORT"]
            if self.settings.os == "Windows":
                self.info.defines.append("MESHOPTIMIZER_API=__declspec(dllimport)")
