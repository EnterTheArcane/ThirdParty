from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "gz-math"
    version = "9.2.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "gazebosim/gz-math")
        tag = repo.latest_release
        return Version(tag.split("_", 1)[-1])

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("gz-cmake")
        self.requires("eigen")
        self.requires("gz-cmake")
        self.requires("gz-utils")

    def source(self):
        version_major = Version(self.version).major
        get(
            self,
            url=f"https://github.com/gazebosim/gz-math/archive/refs/tags/gz-math{version_major}_{self.version}.tar.gz",
            sha256="fed32da2ac16b96c45e87ceb03b0fae6cbc8a860c8341bd9a2549dffee1c1f59",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.variables["SKIP_PYBIND11"] = True
        tc.variables["SKIP_SWIG"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("gz-cmake", "cmake_find_mode", "none")
        deps.set_property("gz-utils", "cmake_find_mode", "none")
        deps.set_property("eigen", "cmake_file_name", "Eigen3")
        deps.set_property("eigen", "cmake_target_name", "Eigen3::Eigen")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_find_mode", "none")

        version_major = self.version.split(".")[0]
        lib_suffix = version_major

        self.info.components["core"].libs = [f"gz-math{lib_suffix}"]
        self.info.components["core"].builddirs = [""]
        self.info.components["core"].set_property("cmake_target_name", "gz-math::gz-math")
        self.info.components["core"].requires = ["gz-utils::core"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.components["core"].system_libs = ["m"]

        self.info.components["eigen3"].libs = []
        self.info.components["eigen3"].set_property("cmake_target_name", "gz-math::gz-math-eigen3")
        self.info.components["eigen3"].requires = ["core", "eigen::eigen3"]
