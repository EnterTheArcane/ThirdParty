from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, get, rmdir, copy, rm
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "zlib"
    version = "1.3.2"
    license = "Zlib"

    def latest_version(self):
        repo = GithubRepository(self, "madler/zlib")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/madler/zlib/archive/refs/tags/v{self.version}.tar.gz",
            sha256="b99a0b86c0ba9360ec7e78c4f1e43b1cbdf1e6936c8fa0f6835c0cd694a495a1",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["ZLIB_BUILD_TESTING"] = False
        tc.cache_variables["ZLIB_BUILD_SHARED"] = self.options.shared
        tc.cache_variables["ZLIB_BUILD_STATIC"] = not self.options.shared
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rm(self, "*.pdb", self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "ZLIB")
        self.info.set_property("cmake_target_name", "ZLIB::ZLIB")
        self.info.set_property("pkg_config_name", "zlib")

        if self.settings.os == "Windows" and not self.settings.compiler_libcxx:
            # The recipe patches CMakeLists.txt to keep the MSVC-style filenames on Windows.
            # MinGW-style builds still use the upstream z/zdll names.
            libname = "zdll" if self.options.shared else "zlib"
        else:
            libname = "z"
        self.info.libs = [libname]
