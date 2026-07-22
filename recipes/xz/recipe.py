import os
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_tools: bool = False


class Recipe(RecipeBase[_Options]):
    name = "xz"
    version = "5.8.3"
    license = "GPL-2.0-or-later", "GPL-3.0-or-later", "LGPL-2.1-or-later", "Unlicense"

    def latest_version(self):
        repo = GithubRepository(self, "tukaani-project/xz")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.settings_build.os == "Windows" and self.settings.os == "Android":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://github.com/tukaani-project/xz/archive/refs/tags/v{self.version}.tar.gz",
            sha256="8ec1767fa517642ecb4cf08b891ce667ba6f143551e382b07c7ef437bda335e2",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        if not self.options.with_tools:
            tc.cache_variables["XZ_TOOL_XZ"] = False
            tc.cache_variables["XZ_TOOL_XZDEC"] = False
            tc.cache_variables["XZ_TOOL_LZMADEC"] = False
            tc.cache_variables["XZ_TOOL_LZMAINFO"] = False
            tc.cache_variables["ENABLE_SCRIPTS"] = False
            tc.cache_variables["XZ_TOOL_SYMLINKS"] = False
            tc.cache_variables["XZ_TOOL_SYMLINKS_LZMA"] = False
            tc.cache_variables["XZ_DOC"] = False
            # sandbox should only apply to the tools, so if the tools are enabled
            # the sandboxing features will be enabled.
            tc.cache_variables["XZ_SANDBOX"] = "no"
        tc.generate()
        if self.settings.build_type == "Debug":
            tc.configure_args.append("--enable-debug")
        tc.generate()

    def build(self):
        cmake = CMake(self)
        rmdir(self, self.folders.source / "tests")  # optionally included
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

        # TODO: also add LIBLZMA_HAS_AUTO_DECODER, LIBLZMA_HAS_EASY_ENCODER & LIBLZMA_HAS_LZMA_PRESET
        content = textwrap.dedent(
            f"""
            set(LIBLZMA_FOUND TRUE)
            if(DEFINED LibLZMA_INCLUDE_DIRS)
                set(LIBLZMA_INCLUDE_DIRS ${{LibLZMA_INCLUDE_DIRS}})
            endif()
            if(DEFINED LibLZMA_LIBRARIES)
                set(LIBLZMA_LIBRARIES ${{LibLZMA_LIBRARIES}})
            endif()
            set(LIBLZMA_VERSION_MAJOR {Version(self.version).major})
            set(LIBLZMA_VERSION_MINOR {Version(self.version).minor})
            set(LIBLZMA_VERSION_PATCH {Version(self.version).patch})
            set(LIBLZMA_VERSION_STRING "{self.version}")
            """)
        module_file = self.folders.package / self._module_file_rel_path
        save(self, module_file, content)

    def package_info(self):
        self.info.set_property("cmake_file_name", "LibLZMA")
        self.info.set_property("cmake_target_name", "LibLZMA::LibLZMA")
        self.info.set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.set_property("pkg_config_name", "liblzma")
        self.info.libs = ["lzma"]
        if not self.options.shared:
            self.info.defines.append("LZMA_API_STATIC")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("pthread")

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")
