from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "tracy"
    version = "0.13.1"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "wolfpld/tracy")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/wolfpld/tracy/archive/refs/tags/v{self.version}.tar.gz",
            sha256="d4efc50ebcb0bfcfdbba148995aeb75044c0d80f5d91223aebfaa8fa9e563d2b",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_POSITION_INDEPENDENT_CODE"] = self.options.pic
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["TRACY_DELAYED_INIT"] = True
        tc.cache_variables["TRACY_MANUAL_LIFETIME"] = True
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
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.libs = ["TracyClient"]
        self.info.set_property("cmake_file_name", "Tracy")
        self.info.set_property("cmake_target_name", "Tracy::TracyClient")
        self.info.includedirs = ["include/tracy"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["pthread", "dl"])
