from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libsamplerate"
    version = "0.2.2"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "libsndfile/libsamplerate")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/libsndfile/libsamplerate/releases/download/{self.version}/libsamplerate-{self.version}.tar.xz",
            sha256="3258da280511d24b49d6b08615bbe824d0cacc9842b0e4caf11c52cf2b043893",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "cmake_policy(SET CMP0091 OLD)", "")

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = CMakeToolchain(self)
        tc.cache_variables["LIBSAMPLERATE_EXAMPLES"] = False
        tc.cache_variables["LIBSAMPLERATE_INSTALL"] = True
        tc.cache_variables["BUILD_TESTING"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "SampleRate")
        self.info.set_property("cmake_target_name", "SampleRate::samplerate")
        self.info.set_property("pkg_config_name", "samplerate")
        self.info.components["samplerate"].libs = ["samplerate"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["samplerate"].system_libs.append("m")
        self.info.components["samplerate"].set_property("cmake_target_name", "SampleRate::samplerate")
