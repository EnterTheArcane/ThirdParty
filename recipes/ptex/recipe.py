from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "ptex"
    version = "2.5.2"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "wdas/ptex")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("zlib")
        self.requires("libdeflate")

    def source(self):
        get(
            self,
            url=f"https://github.com/wdas/ptex/archive/refs/tags/v{self.version}.tar.gz",
            sha256="dd95fbea4b50e9e68fd042f540fb83157a0ff25053066c3439d4527de3621d34",
            destination=self.folders.source,
            strip_root=True)
        save(self, self.folders.source / "src" / "utils" / "CMakeLists.txt", "")
        save(self, self.folders.source / "src" / "tests" / "CMakeLists.txt", "")
        save(self, self.folders.source / "src" / "doc" / "CMakeLists.txt", "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["PTEX_BUILD_STATIC_LIBS"] = not self.options.shared
        tc.variables["PTEX_BUILD_SHARED_LIBS"] = self.options.shared
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
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        cmake_target = "Ptex_dynamic" if self.options.shared else "Ptex_static"
        self.info.set_property("cmake_file_name", "ptex")
        self.info.set_property("cmake_target_name", f"Ptex::{cmake_target}")
        self.info.components["_ptex"].libs = ["Ptex"]
        if not self.options.shared:
            self.info.components["_ptex"].defines.append("PTEX_STATIC")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["_ptex"].system_libs.append("pthread")
        self.info.components["_ptex"].requires = ["zlib::zlib", "libdeflate::_libdeflate"]

        self.info.components["_ptex"].set_property("cmake_target_name", f"Ptex::{cmake_target}")
