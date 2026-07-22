from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, copy, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "boost"
    version = "1.91.0-1"
    license = "BSL-1.0"

    def latest_version(self):
        repo = GithubRepository(self, "boostorg/boost")
        return Version(repo.latest_release.removeprefix("boost-"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/boostorg/boost/releases/download/boost-{self.version}/boost-{self.version}-cmake.tar.gz",
            sha256="8a82bd11a720c70923806c36ee5c26dbd2d630c1eaa1d8fad9a7bd5529908a26",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["BUILD_TESTING"] = False
        tc.cache_variables["BOOST_INSTALL_LAYOUT"] = "system"
        tc.cache_variables["BOOST_ENABLE_MPI"] = False
        tc.cache_variables["BOOST_ENABLE_PYTHON"] = False
        runtime = self.settings.compiler_runtime or "shared"
        tc.cache_variables["BOOST_RUNTIME_LINK"] = "static" if runtime == "static" else "shared"
        tc.cache_variables["CMAKE_POSITION_INDEPENDENT_CODE"] = self.options.pic
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE_1_0.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Boost")
        self.info.set_property("cmake_find_mode", "none")
        self.info.builddirs = ["lib/cmake/Boost-1.91.0"]
