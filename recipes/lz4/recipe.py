import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "lz4"
    version = "1.10.0"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "lz4/lz4")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/lz4/lz4/archive/v{self.version}.tar.gz",
            sha256="537512904744b35e232912055ccf8ec66d768639ff3abe5788d90d792ec5f48b",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        set_cmake_minimum_required(self, path=self._cmakelists_folder / "CMakeLists.txt")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["LZ4_BUILD_CLI"] = False
        tc.variables["LZ4_BUNDLED_MODE"] = False
        tc.variables["LZ4_POSITION_INDEPENDENT_LIB"] = self.options.pic
        # Generate a relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        # Honor BUILD_SHARED_LIBS (see upstream issue 11840)
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self._cmakelists_folder)
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source / "lib", dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "lz4")
        self.info.set_property("cmake_target_name", self._lz4_target)
        self.info.set_property("cmake_target_aliases", ["lz4::lz4"])  # old unofficial target in CCI for lz4, kept for the moment to not break consumers
        self.info.set_property("pkg_config_name", "liblz4")
        self.info.libs = ["lz4"]
        if is_msvc(self) and self.options.shared:
            self.info.defines.append("LZ4_DLL_IMPORT=1")

    @property
    def _cmakelists_folder(self):
        subfolder = os.path.join("build", "cmake")
        return self.folders.source / subfolder

    @property
    def _lz4_target(self):
        return f"LZ4::{"lz4_shared" if self.options.shared else "lz4_static"}"
