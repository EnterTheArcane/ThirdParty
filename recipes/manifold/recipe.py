from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "manifold"
    version = "3.5.2"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "elalish/manifold")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("clipper2")
        self.requires("onetbb")

    def source(self):
        get(
            self,
            url=f"https://github.com/elalish/manifold/archive/refs/tags/v{self.version}.tar.gz",
            sha256="35cb5e0d78882f461ec39b17d8f09c2aceca761356f3ce948e3f3908289b8f2e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["MANIFOLD_DOWNLOADS"] = False
        tc.cache_variables["MANIFOLD_TEST"] = False
        tc.cache_variables["MANIFOLD_CBIND"] = False
        tc.cache_variables["MANIFOLD_PYBIND"] = False
        tc.cache_variables["MANIFOLD_STRICT"] = False  # no -Werror
        tc.cache_variables["MANIFOLD_PAR"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("clipper2", "cmake_file_name", "Clipper2")
        deps.set_property("clipper2::clipper2", "cmake_target_name", "Clipper2")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.libs = ["manifold"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
