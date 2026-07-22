from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "alembic"
    version = "1.8.12"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "alembic/alembic")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("hdf5")
        self.requires("imath")

    def source(self):
        get(
            self,
            url=f"https://github.com/alembic/alembic/archive/refs/tags/{self.version}.tar.gz",
            sha256="b6d916c40446e8c502c84273092ab3d98f3f7f6094f8a2b8203d23e2f1d2a4a0",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["ALEMBIC_BUILD_LIBS"] = True
        tc.variables["ALEMBIC_DEBUG_WARNINGS_AS_ERRORS"] = False
        tc.variables["ALEMBIC_ILMBASE_FOUND"] = 1
        tc.variables["ALEMBIC_ILMBASE_LINK_STATIC"] = True  # for -DOPENEXR_DLL, handled by OpenEXR package
        tc.variables["ALEMBIC_SHARED_LIBS"] = self.options.shared
        tc.variables["ALEMBIC_USING_IMATH_3"] = False
        tc.variables["USE_ARNOLD"] = False
        tc.variables["USE_BINARIES"] = False
        tc.variables["USE_EXAMPLES"] = False
        tc.variables["USE_HDF5"] = True
        tc.variables["USE_MAYA"] = False
        tc.variables["USE_PRMAN"] = False
        tc.variables["USE_PYALEMBIC"] = False
        tc.variables["USE_TESTS"] = False
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Alembic")
        self.info.set_property("cmake_target_name", "Alembic::Alembic")
        self.info.libs = ["Alembic"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["m", "pthread"])
