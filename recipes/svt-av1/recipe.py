from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMakeToolchain, CMakeDeps, CMake
from thirdparty.files import copy, get, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    minimal_build: bool = False
    with_neon: bool = True
    with_arm_crc32: bool = True
    with_neon_dotprod: bool = True
    with_neon_i8mm: bool = True
    with_neon_sve: bool = True
    with_neon_sve2: bool = True


class Recipe(RecipeBase[_Options]):
    name = "svt-av1"
    version = "4.2.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GitlabRepository(self, "AOMediaCodec/SVT-AV1")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.arch != "ARM" or self._arm_simd_unsupported:
            self.options.with_neon = False
            self.options.with_arm_crc32 = False
            self.options.with_neon_dotprod = False
            self.options.with_neon_i8mm = False
            self.options.with_neon_sve = False
            self.options.with_neon_sve2 = False

    @property
    def _arm_simd_unsupported(self) -> bool:
        # SVT-AV1's ARM optimizations require a GCC/Clang toolchain: the CMake ARM branch calls enable_language(ASM) for GNU .S files and passes -march=... flags.
        # MSVC has no compatible assembler and rejects -march, so on Windows ARM64 the library can only be built C-only (no NEON/SVE).
        return self.settings.arch == "ARM" and self.settings.os == "Windows"

    def requirements(self):
        self.requires_tool("cmake")
        if self.settings.arch in ("X64",):
            self.requires_tool("nasm")

    def source(self):
        get(
            self,
            url=f"https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v{self.version}/SVT-AV1-v{self.version}.tar.gz",
            sha256="c7b13c4a84bd3751aa35fcc72be13e6875467e7c2216879251a486e5b1e4e740",
            destination=self.folders.source,
            strip_root=True)
        # SVT-AV1 prepends /W3 to the compile flags; it's applied via a variable the toolchain
        # filter can't intercept, so drop it so the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "check_both_flags_add(PREPEND /W3)", "# check_both_flags_add(PREPEND /W3)", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_APPS"] = False
        tc.cache_variables["BUILD_TESTING"] = False
        tc.cache_variables["MINIMAL_BUILD"] = self.options.minimal_build
        tc.cache_variables["SVT_AV1_LTO"] = False
        if self._arm_simd_unsupported:
            tc.cache_variables["COMPILE_C_ONLY"] = True
        elif self.settings.arch == "ARM":
            tc.cache_variables["ENABLE_NEON"] = self.options.with_neon
            tc.cache_variables["ENABLE_ARM_CRC32"] = self.options.with_arm_crc32
            tc.cache_variables["ENABLE_NEON_DOTPROD"] = self.options.with_neon_dotprod
            tc.cache_variables["ENABLE_NEON_I8MM"] = self.options.with_neon_i8mm
            tc.cache_variables["ENABLE_SVE"] = self.options.with_neon_sve
            tc.cache_variables["ENABLE_SVE2"] = self.options.with_neon_sve2
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        for license_file in ("LICENSE.md", "PATENTS.md"):
            copy(self, license_file, self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.configure()
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.components["encoder"].libs = ["SvtAv1Enc"]
        self.info.components["encoder"].includedirs = ["include/svt-av1"]
        self.info.components["encoder"].set_property("pkg_config_name", "SvtAv1Enc")
        if self.settings.os in ("FreeBSD", "Linux"):
            self.info.components["encoder"].system_libs = ["pthread", "dl", "m"]
        if self.settings.os == "Android":
            self.info.components["encoder"].system_libs = ["m"]
