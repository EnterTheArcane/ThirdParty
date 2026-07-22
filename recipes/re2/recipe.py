from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "re2"
    version = "20251105"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "google/re2")
        return Version(repo.latest_release.replace("-", ""))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("abseil")
        self.requires("icu")

    def source(self):
        release_date = f"{self.version[:4]}-{self.version[4:6]}-{self.version[6:]}"
        get(
            self,
            url=f"https://github.com/google/re2/releases/download/{release_date}/re2-{release_date}.tar.gz",
            sha256="87f6029d2f6de8aa023654240a03ada90e876ce9a4676e258dd01ea4c26ffd67",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["RE2_BUILD_TESTING"] = False
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "re2")
        self.info.set_property("cmake_target_name", "re2::re2")
        self.info.set_property("pkg_config_name", "re2")
        self.info.libs = ["re2"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m", "pthread"]
