from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    sse: bool = True
    tools: bool = True


class Recipe(RecipeBase[_Options]):
    name = "ktx-software"
    version = "4.4.2"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/KTX-Software")
        return Version(repo.latest_release.lstrip("v"))

    def configure(self):
        if not self._has_sse_support:
            self.options.sse = False

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("zstd")
        if self.options.tools:
            self.requires("fmt")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/KTX-Software/archive/refs/tags/v{self.version}.tar.gz",
            sha256="9412cb45045a503005acd47d98f9e8b47154634a50b4df21e17a1dfa8971d323",
            destination=self.folders.source,
            strip_root=True)
        rmdir(self, self.folders.source / "tests")
        save(self, self.folders.source / "tests" / "CMakeLists.txt", "")
        replace_in_file(
            self,
            self.folders.source / "external" / "astc-encoder" / "CMakeLists.txt",
            "set(CMAKE_CXX_STANDARD", "#")
        # astc-encoder hard-codes MSVC /W4 in a genex, which the toolchain warning filter can't
        # strip (genexes are preserved intact); drop the /W4 so the quiet -w wins without D9025.
        replace_in_file(
            self,
            self.folders.source / "external" / "astc-encoder" / "Source" / "cmake_core.cmake",
            "$<${is_msvc_fe}:/W4>",
            "$<${is_msvc_fe}:>")
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["KTX_FEATURE_TOOLS"] = self.options.tools
        tc.variables["KTX_FEATURE_DOC"] = False
        tc.variables["KTX_FEATURE_LOADTEST_APPS"] = False
        tc.variables["KTX_FEATURE_TESTS"] = False
        tc.variables["BASISU_SUPPORT_SSE"] = self.options.sse
        if is_apple_os(self) and self.settings.arch == "X64":
            # astc-encoder's CMakeLists defaults to AVX2 codegen on x86_64 when no other ISA
            # option is set. Apple's clang tags AVX2 object code with the 'x86_64h' (Haswell)
            # Mach-O subtype, so libtool splits the merged libktx.a into separate x86_64/x86_64h
            # slices - and the plain x86_64 slice (the one CMAKE_OSX_ARCHITECTURES=x86_64 actually
            # links against) ends up missing the astcenc symbols entirely. SSE4.1 doesn't trigger
            # the subtype split and is guaranteed present on every 64-bit Intel Mac.
            tc.variables["ASTCENC_ISA_SSE41"] = True
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*", src=self.folders.source / "LICENSES", dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Ktx")
        self.info.set_property("cmake_target_name", "KTX::ktx")
        self.info.components["libktx"].libs = ["ktx"]
        self.info.components["libktx"].defines = [
            "KTX_FEATURE_KTX1", "KTX_FEATURE_KTX2", "KTX_FEATURE_WRITE",
        ]
        if not self.options.shared:
            self.info.components["libktx"].defines.append("KHRONOS_STATIC")
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.components["libktx"].system_libs.append(libcxx)
        if self.settings.os == "Windows":
            self.info.components["libktx"].defines.append("BASISU_NO_ITERATOR_DEBUG_LEVEL")
        elif self.settings.os == "Linux":
            self.info.components["libktx"].system_libs.extend(["m", "dl", "pthread"])
        self.info.components["libktx"].set_property("cmake_target_name", "KTX::ktx")
        self.info.components["libktx"].requires = ["zstd::zstd"]
        if self.options.tools:
            self.info.components["libktx"].requires.append("fmt::fmt")

    @property
    def _has_sse_support(self):
        return self.settings.arch in ["X64"]
