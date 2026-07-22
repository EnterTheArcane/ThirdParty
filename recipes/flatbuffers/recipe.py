from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, copy, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "flatbuffers"
    version = "25.12.19"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "google/flatbuffers")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/flatbuffers/archive/v{self.version}.tar.gz",
            sha256="f81c3162b1046fe8b84b9a0dbdd383e24fdbcf88583b9cb6028f90d04d90696a",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["FLATBUFFERS_BUILD_TESTS"] = False
        tc.variables["FLATBUFFERS_INSTALL"] = True
        tc.variables["FLATBUFFERS_BUILD_FLATLIB"] = not self.options.shared
        tc.variables["FLATBUFFERS_BUILD_FLATC"] = True
        tc.variables["FLATBUFFERS_STATIC_FLATC"] = False
        tc.variables["FLATBUFFERS_BUILD_FLATHASH"] = False
        tc.variables["FLATBUFFERS_BUILD_SHAREDLIB"] = self.options.shared
        tc.variables["FLATBUFFERS_LIBCXX_WITH_CLANG"] = False
        tc.variables["FLATBUFFERS_STRICT_MODE"] = False
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "flatbuffers")
        # onnxruntime does find_package(Flatbuffers CONFIG); register both casings so both
        # flatbuffers_DIR and Flatbuffers_DIR are emitted.
        self.info.set_property("cmake_file_name_variants", ["flatbuffers", "Flatbuffers"])
        cmake_target = "flatbuffers_shared" if self.options.shared else "flatbuffers"
        self.info.set_property("cmake_target_name", f"flatbuffers::{cmake_target}")
        self.info.set_property("pkg_config_name", "flatbuffers")
        self.info.libs = ["flatbuffers"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m"]
