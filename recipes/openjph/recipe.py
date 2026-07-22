from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openjph"
    version = "0.30.1"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "aous72/OpenJPH")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("libtiff")

    def source(self):
        get(
            self,
            url=f"https://github.com/aous72/OpenJPH/archive/{self.version}.tar.gz",
            sha256="fb3ccf71af838ed2a42c6ea669308a2adaba115ae9d5862dfb1e2865b43eb5b8",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["OJPH_BUILD_EXECUTABLES"] = True
        tc.cache_variables["OJPH_ENABLE_TIFF_SUPPORT"] = True
        tc.cache_variables["OJPH_BUILD_STREAM_EXPAND"] = False
        tc.cache_variables["OJPH_DISABLE_SIMD"] = False
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cm = CMake(self)
        cm.configure()
        cm.build()

    def package(self):
        cm = CMake(self)
        cm.install()

        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "openjph")
        self.info.set_property("cmake_target_name", "openjph::openjph")
        self.info.set_property("pkg_config_name", "openjph")

        version_suffix = "_d" if self.settings.build_type == "Debug" else ""
        if is_msvc(self):
            v = Version(self.version)
            version_suffix = f".{v.major}.{v.minor}"
            if self.settings.build_type == "Debug":
                version_suffix += "d"
        self.info.libs = ["openjph" + version_suffix]
