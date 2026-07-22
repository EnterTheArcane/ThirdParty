from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir, apply_patches
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    SIMD: bool = True
    arithmetic_encoder: bool = True
    arithmetic_decoder: bool = True
    libjpeg7_compatibility: bool = True
    libjpeg8_compatibility: bool = True
    mem_src_dst: bool = True
    turbojpeg: bool = True
    java: bool = False
    enable12bit: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libjpeg-turbo"
    version = "3.2.0"
    license = "BSD-3-Clause", "IJG", "Zlib"

    def latest_version(self):
        repo = GithubRepository(self, "libjpeg-turbo/libjpeg-turbo")
        return Version(repo.latest_release)

    def configure(self):
        self.options.enable12bit = False
        self.options.mem_src_dst = False

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

        if self.options.enable12bit:
            self.options.java = False
            self.options.turbojpeg = False
        if self.options.enable12bit or self.settings.os == "Emscripten":
            self.options.SIMD = False
        if self.options.enable12bit or self.options.libjpeg7_compatibility or self.options.libjpeg8_compatibility:
            self.options.arithmetic_encoder = False
            self.options.arithmetic_decoder = False
        if self.options.libjpeg8_compatibility:
            self.options.mem_src_dst = False

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.SIMD and self.settings.arch in ["X64"]:
            self.requires_tool("nasm")

    def source(self):
        get(
            self,
            url=f"https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/{self.version}/libjpeg-turbo-{self.version}.tar.gz",
            sha256="6f30092cef9fb839779646608f4ee14ae3cbac989c47fa05e841b0841f09878e",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = CMakeToolchain(self)
        tc.variables["ENABLE_STATIC"] = not self.options.shared
        tc.variables["ENABLE_SHARED"] = self.options.shared
        tc.variables["WITH_SIMD"] = self.options.SIMD
        tc.variables["WITH_ARITH_ENC"] = self._is_arithmetic_encoding_enabled
        tc.variables["WITH_ARITH_DEC"] = self._is_arithmetic_decoding_enabled
        tc.variables["WITH_JPEG7"] = self.options.libjpeg7_compatibility
        tc.variables["WITH_JPEG8"] = self.options.libjpeg8_compatibility
        tc.variables["WITH_TURBOJPEG"] = self.options.turbojpeg
        tc.variables["WITH_JAVA"] = self.options.java
        tc.cache_variables["WITH_TOOLS"] = False
        if is_msvc(self):
            tc.variables["WITH_CRT_DLL"] = True  # avoid replacing /MD by /MT in compiler flags
        if self.options.java:
            tc.cache_variables["CMAKE_INSTALL_JAVADIR"] = (self.folders.package / "lib" / "java").as_posix()
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "README.ijg", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        # remove unneeded directories
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "doc")
        # remove binaries and pdb files
        for pattern_to_remove in ["cjpeg*", "djpeg*", "jpegtran*", "tjbench*", "wrjpgcom*", "rdjpgcom*", "*.pdb"]:
            rm(self, pattern_to_remove, self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "libjpeg-turbo")

        cmake_target_suffix = "-static" if not self.options.shared else ""
        lib_suffix = "-static" if is_msvc(self) and not self.options.shared else ""

        self.info.components["jpeg"].set_property("cmake_target_name", f"libjpeg-turbo::jpeg{cmake_target_suffix}")
        self.info.components["jpeg"].set_property("pkg_config_name", "libjpeg")
        self.info.components["jpeg"].libs = [f"jpeg{lib_suffix}"]

        if self.options.turbojpeg:
            self.info.components["turbojpeg"].set_property("cmake_target_name", f"libjpeg-turbo::turbojpeg{cmake_target_suffix}")
            self.info.components["turbojpeg"].set_property("pkg_config_name", "libturbojpeg")
            self.info.components["turbojpeg"].libs = [f"turbojpeg{lib_suffix}"]

    @property
    def _is_arithmetic_encoding_enabled(self):
        return self.options.arithmetic_encoder or \
            self.options.libjpeg7_compatibility or self.options.libjpeg8_compatibility

    @property
    def _is_arithmetic_decoding_enabled(self):
        return self.options.arithmetic_decoder or \
            self.options.libjpeg7_compatibility or self.options.libjpeg8_compatibility
