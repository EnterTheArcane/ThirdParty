from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir, rm
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "double-conversion"
    version = "3.4.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "google/double-conversion")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/double-conversion/archive/refs/tags/v{self.version}.tar.gz",
            sha256="42fd4d980ea86426e457b24bdfa835a6f5ad9517ddb01cdb42b99ab9c8dd5dc9",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.pdb", self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "double-conversion")
        self.info.set_property("cmake_target_name", "double-conversion::double-conversion")
        self.info.libs = ["double-conversion"]
