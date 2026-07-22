from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "ogg"
    version = "1.3.6"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "xiph/ogg")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/xiph/ogg/archive/refs/tags/v{self.version}.tar.gz",
            sha256="95b643da661155d79db9de2fca55daed3a8d491039829def246aacb3d9201c81",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        # Generate a relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        # Honor BUILD_SHARED_LIBS from recipe_toolchain (see upstream issue 11840)
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
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
        self.info.set_property("cmake_file_name", "Ogg")
        self.info.set_property("cmake_target_name", "Ogg::ogg")
        self.info.set_property("pkg_config_name", "ogg")
        self.info.components["ogglib"].libs = ["ogg"]
        self.info.components["ogglib"].set_property("cmake_target_name", "Ogg::ogg")
        self.info.components["ogglib"].set_property("pkg_config_name", "ogg")
