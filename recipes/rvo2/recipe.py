from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import copy, get, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "rvo2"
    version = "2.0.2"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "snape/RVO2")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/snape/RVO2/archive/v{self.version}.tar.gz",
            sha256="20b59fcc4cf61783cb0d1baa40a0dff3c557a97246651f95d9d9fed91bf17724",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "add_subdirectory(examples)", "")
        replace_in_file(
            self,
            self.folders.source / "src" / "CMakeLists.txt",
            "DESTINATION include",
            "DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}")
        replace_in_file(
            self,
            self.folders.source / "src" / "CMakeLists.txt",
            "RVO DESTINATION lib",
            "RVO RUNTIME LIBRARY ARCHIVE")

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
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.libs = ["RVO"]
