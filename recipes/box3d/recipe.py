from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    double_precision: bool = False
    simd: bool = True
    validate: bool = False
    profile: bool = False


class Recipe(RecipeBase[_Options]):
    name = "box3d"
    version = "0.1.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "erincatto/box3d")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.profile:
            self.requires("tracy")

    def source(self):
        get(
            self,
            url=f"https://github.com/erincatto/box3d/archive/refs/tags/v{self.version}.tar.gz",
            sha256="df232c7618c0d0d3927b798044559ee56eabadeb9d8ff9dc526d4b384d7b415d",
            destination=self.folders.source,
            strip_root=True)
        cmake_lists = self.folders.source / "src" / "CMakeLists.txt"
        replace_in_file(self, cmake_lists, "FetchContent_MakeAvailable(tracy)", "find_package(Tracy REQUIRED)")
        replace_in_file(self, cmake_lists, "box3d PUBLIC TracyClient", "box3d PUBLIC Tracy::TracyClient")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_POSITION_INDEPENDENT_CODE"] = self.options.pic
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["BOX3D_BENCHMARKS"] = False
        tc.cache_variables["BOX3D_BUILD_SHADERS"] = False
        tc.cache_variables["BOX3D_COMPILE_WARNING_AS_ERROR"] = False
        tc.cache_variables["BOX3D_DISABLE_SIMD"] = not self.options.simd
        tc.cache_variables["BOX3D_DOCS"] = False
        tc.cache_variables["BOX3D_DOUBLE_PRECISION"] = self.options.double_precision
        tc.cache_variables["BOX3D_PROFILE"] = self.options.profile
        tc.cache_variables["BOX3D_SAMPLES"] = False
        tc.cache_variables["BOX3D_SANITIZE"] = False
        tc.cache_variables["BOX3D_UNIT_TESTS"] = False
        tc.cache_variables["BOX3D_VALIDATE"] = self.options.validate
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

    def package_info(self):
        self.info.libs = ["box3d"]
        self.info.set_property("cmake_file_name", "box3d")
        self.info.set_property("cmake_target_name", "box3d::box3d")
        if self.options.double_precision:
            self.info.defines = ["BOX3D_DOUBLE_PRECISION"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
        if self.options.profile:
            self.info.requires = ["tracy::TracyClient"]
