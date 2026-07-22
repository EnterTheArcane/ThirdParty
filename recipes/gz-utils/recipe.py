from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "gz-utils"
    version = "4.0.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "gazebosim/gz-utils")
        tag = repo.latest_release
        return Version(tag.split("_", 1)[-1])

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("gz-cmake")
        self.requires("gz-cmake")
        self.requires("spdlog")

    def source(self):
        version_major = Version(self.version).major
        get(
            self,
            url=f"https://github.com/gazebosim/gz-utils/archive/refs/tags/gz-utils{version_major}_{self.version}.tar.gz",
            sha256="b06a179ea4297be8b8d09ea7a5d3d45059a3e4030c1bd256afc62f997cc992ed",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.variables["SKIP_PYBIND11"] = True
        tc.variables["SKIP_SWIG"] = True
        # Use bundled CLI11 to avoid external dependency
        tc.variables["GZ_UTILS_VENDOR_CLI11"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("gz-cmake", "cmake_find_mode", "none")
        deps.set_property("spdlog", "cmake_file_name", "spdlog")
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
        # Keep gz-utils cmake config files; consumers use find_package(gz-utils) via CMAKE_PREFIX_PATH
        self.info.set_property("cmake_find_mode", "none")

        # gz-utils major version suffix in library name: gz-utils4
        version_major = self.version.split(".")[0]
        lib_suffix = version_major

        self.info.components["core"].libs = [f"gz-utils{lib_suffix}"]
        self.info.components["core"].builddirs = [""]
        self.info.components["core"].set_property("cmake_target_name", "gz-utils::gz-utils")
        self.info.components["core"].requires = ["spdlog::spdlog"]

        self.info.components["cli"].libs = [f"gz-utils{lib_suffix}-cli"]
        self.info.components["cli"].set_property("cmake_target_name", "gz-utils::gz-utils-cli")
        self.info.components["cli"].requires = ["core"]

        self.info.components["log"].libs = [f"gz-utils{lib_suffix}-log"]
        self.info.components["log"].set_property("cmake_target_name", "gz-utils::gz-utils-log")
        self.info.components["log"].requires = ["core", "spdlog::spdlog"]
