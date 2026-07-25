from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    isa: Literal["avx2", "sse4.1", "sse2", "neon", "none", "native"] = "native"


class Recipe(RecipeBase[_Options]):
    name = "astc-encoder"
    version = "5.6.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "ARM-software/astc-encoder")
        return Version(repo.latest_release)

    def configure(self):
        if self.settings.arch in ["ARM"]:
            self.options.isa = "neon"
        elif str(self.options.isa) == "native":
            # -march=native tunes the library to whichever machine happened to build it, which is
            # wrong for a redistributable package (and a cross compiler cannot resolve it at all).
            # Pin the x86-64 SIMD baseline instead.
            self.options.isa = "avx2"

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/ARM-software/astc-encoder/archive/refs/tags/{self.version}.tar.gz",
            sha256="c77b4505792b36068b8ab5c548f606f8504f170e274e5870d3c5a405fe0bbc35",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        # astc-encoder wraps /W4 in a genex the toolchain warning filter preserves; empty it so
        # the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "Source" / "cmake_core.cmake",
            "$<${is_msvc_fe}:/W4>", "$<${is_msvc_fe}:>", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["ASTCENC_CLI"] = False
        tc.variables["ASTCENC_WERROR"] = False
        tc.variables["ASTCENC_SHAREDLIB"] = self.options.shared
        tc.variables["ASTCENC_UNIVERSAL_BUILD"] = False
        tc.variables["ASTCENC_ISA_AVX2"] = self.options.isa == "avx2"
        tc.variables["ASTCENC_ISA_SSE41"] = self.options.isa == "sse4.1"
        tc.variables["ASTCENC_ISA_SSE2"] = self.options.isa == "sse2"
        tc.variables["ASTCENC_ISA_NEON"] = self.options.isa == "neon"
        tc.variables["ASTCENC_ISA_NONE"] = self.options.isa == "none"
        tc.variables["ASTCENC_ISA_NATIVE"] = self.options.isa == "native"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.libs = [f"astcenc-{self.options.isa}"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["m", "pthread"])
