from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    target_bits: Literal[64, 32, None] = None
    endianness: Literal["big", "little", "neutral", None] = None
    enable_portable: bool = False
    enable_rbit: bool = True
    enable_debug: bool = False
    enable_log: bool = False


class Recipe(RecipeBase[_Options]):
    name = "brotli"
    version = "1.2.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "google/brotli")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/brotli/archive/v{self.version}.tar.gz",
            sha256="816c96e8e8f193b40151dad7e8ff37b1221d019dbcb9c35cd3fadbfe6477dfec",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BROTLI_BUNDLED_MODE"] = False
        tc.variables["BROTLI_DISABLE_TESTS"] = True
        tc.variables["BROTLI_BUILD_TOOLS"] = False
        if self.options.target_bits == 32:
            tc.preprocessor_definitions["BROTLI_BUILD_32_BIT"] = 1
        elif self.options.target_bits == 64:
            tc.preprocessor_definitions["BROTLI_BUILD_64_BIT"] = 1
        if self.options.endianness == "big":
            tc.preprocessor_definitions["BROTLI_BUILD_BIG_ENDIAN"] = 1
        elif self.options.endianness == "neutral":
            tc.preprocessor_definitions["BROTLI_BUILD_ENDIAN_NEUTRAL"] = 1
        elif self.options.endianness == "little":
            tc.preprocessor_definitions["BROTLI_BUILD_LITTLE_ENDIAN"] = 1
        if self.options.enable_portable:
            tc.preprocessor_definitions["BROTLI_BUILD_PORTABLE"] = 1
        if not self.options.enable_rbit:
            tc.preprocessor_definitions["BROTLI_BUILD_NO_RBIT"] = 1
        if self.options.enable_debug:
            tc.preprocessor_definitions["BROTLI_DEBUG"] = 1
        if self.options.enable_log:
            tc.preprocessor_definitions["BROTLI_ENABLE_LOG"] = 1
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
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        # brotlicommon
        self.info.components["brotlicommon"].set_property("pkg_config_name", "libbrotlicommon")
        self.info.components["brotlicommon"].libs = [self._get_decorated_lib("brotlicommon")]
        if self.settings.os == "Windows" and self.options.shared:
            self.info.components["brotlicommon"].defines.append("BROTLI_SHARED_COMPILATION")
        # brotlidec
        self.info.components["brotlidec"].set_property("pkg_config_name", "libbrotlidec")
        self.info.components["brotlidec"].libs = [self._get_decorated_lib("brotlidec")]
        self.info.components["brotlidec"].requires = ["brotlicommon"]
        # brotlienc
        self.info.components["brotlienc"].set_property("pkg_config_name", "libbrotlienc")
        self.info.components["brotlienc"].libs = [self._get_decorated_lib("brotlienc")]
        self.info.components["brotlienc"].requires = ["brotlicommon"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["brotlienc"].system_libs = ["m"]

    def _get_decorated_lib(self, name: str) -> str:
        return name
