from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "jansson"
    version = "2.15.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "akheron/jansson")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/akheron/jansson/releases/download/v{self.version}/jansson-{self.version}.tar.bz2",
            sha256="f9aa4b3ec8496fee69db94f06f3d76fd4a26b012ee9bf1e917078c2cd2841881",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["JANSSON_BUILD_DOCS"] = False
        tc.variables["JANSSON_BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["JANSSON_EXAMPLES"] = False
        tc.variables["JANSSON_WITHOUT_TESTS"] = True
        tc.variables["USE_URANDOM"] = True
        tc.variables["USE_WINDOWS_CRYPTOAPI"] = True
        if is_msvc(self):
            tc.variables["JANSSON_STATIC_CRT"] = is_msvc_static_runtime(self)
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "jansson")
        self.info.set_property("cmake_target_name", "jansson::jansson")
        self.info.set_property("pkg_config_name", "jansson")
        suffix = "_d" if self.settings.os == "Windows" and self.settings.build_type == "Debug" else ""
        self.info.libs = [f"jansson{suffix}"]
