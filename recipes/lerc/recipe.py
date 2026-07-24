from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "lerc"
    version = "4.2.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "Esri/lerc")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/Esri/lerc/archive/refs/tags/v{self.version}.tar.gz",
            sha256="a1fb593ed1fcb5b38800caf3c4454f872745202e961d00d745e53d81447e17c9",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.libs = ["Lerc"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
        if not self.options.shared:
            self.info.defines = ["LERC_STATIC"]
            lib = stdcpp_library(self)
            if lib:
                self.info.system_libs.append(lib)
