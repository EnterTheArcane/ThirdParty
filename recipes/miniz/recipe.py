import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "miniz"
    version = "3.1.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "richgel999/miniz")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/richgel999/miniz/archive/refs/tags/{self.version}.tar.gz",
            sha256="98468f8924934b723276680f85238b6c78bf1f8b49b4459cc9b7214a20e2e9fb",
            destination=self.folders.source,
            strip_root=True)
        # Strip the project's unconditional /W3 so the quiet -w wins without cl's D9025 spam
        # (set(CMAKE_C_FLAGS) can't be intercepted by the toolchain's compile_options override).
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "${CMAKE_C_FLAGS} /W3",
            "${CMAKE_C_FLAGS}",
            strict=False)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_EXAMPLES"] = False
        tc.variables["BUILD_FUZZERS"] = False
        tc.variables["AMALGAMATE_SOURCES"] = False
        tc.variables["BUILD_HEADER_ONLY"] = False
        tc.variables["INSTALL_PROJECT"] = True
        tc.cache_variables["BUILD_TESTS"] = False
        # Honor BUILD_SHARED_LIBS from recipe_toolchain (see upstream issue 11840)
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
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
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "miniz")
        self.info.set_property("cmake_target_name", "miniz::miniz")
        self.info.set_property("pkg_config_name", "miniz")
        self.info.libs = ["miniz"]
        self.info.includedirs.append(os.path.join("include", "miniz"))
