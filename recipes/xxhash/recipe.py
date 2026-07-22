from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "xxhash"
    version = "0.8.3"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "Cyan4973/xxHash")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/Cyan4973/xxHash/archive/v{self.version}.tar.gz",
            sha256="aae608dfe8213dfd05d909a57718ef82f30722c392344583d3f39050c7f29a80",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["XXHASH_BUNDLED_MODE"] = False
        tc.variables["XXHASH_BUILD_XXHSUM"] = True
        # Fix CMake configuration if target is iOS/tvOS/watchOS
        tc.cache_variables["CMAKE_MACOSX_BUNDLE"] = False
        # Generate a relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "cmake_unofficial")
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "xxHash")
        self.info.set_property("cmake_target_name", "xxHash::xxhash")
        self.info.set_property("pkg_config_name", "libxxhash")
        self.info.components["libxxhash"].libs = ["xxhash"]
        self.info.components["libxxhash"].set_property("cmake_target_name", "xxHash::xxhash")
