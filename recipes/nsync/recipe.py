from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import get, copy, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "nsync"
    version = "1.30.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "google/nsync")
        return Version(repo.latest_release)

    def validate(self):
        # nsync is only consumed on non-Windows platforms; onnxruntime uses wil on Windows.
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration("nsync is not supported on Windows")

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/nsync/archive/{self.version}.tar.gz",
            sha256="883a0b3f8ffc1950670425df3453c127c1a3f6ed997719ca1bbe7f474235b6cc",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "set (CMAKE_POSITION_INDEPENDENT_CODE ON)",
            "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["NSYNC_ENABLE_TESTS"] = False
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        tc.cache_variables["CMAKE_POLICY_VERSION_MINIMUM"] = "3.5"
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

    def package_info(self):
        self.info.set_property("cmake_file_name", "nsync")
        self.info.components["nsync_c"].set_property("cmake_target_name", "nsync::nsync_c")
        self.info.components["nsync_c"].libs = ["nsync"]
        self.info.components["nsync_cpp"].set_property("cmake_target_name", "nsync::nsync_cpp")
        self.info.components["nsync_cpp"].libs = ["nsync_cpp"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["nsync_c"].system_libs.append("pthread")
            self.info.components["nsync_cpp"].system_libs.extend(["m", "pthread"])
