import os
import textwrap
from pathlib import Path

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, collect_libs, copy, get, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openal-soft"
    version = "1.25.2"
    license = "LGPL-2.0-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "kcat/openal-soft")
        return Version(repo.latest_release)

    def configure(self):
        # OpenAL's API is pure C, thus the c++ standard does not matter
        # Because the backend is C++, the C++ STL matters
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.settings.os == "Linux":
            self.requires("libalsa")

    def source(self):
        get(
            self,
            url=f"https://github.com/kcat/openal-soft/archive/refs/tags/{self.version}.tar.gz",
            sha256="fb27e5839aa11f0e5b9d33756965291fad5d6909ab928ea1f796f4a1a6877894",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["LIBTYPE"] = "SHARED" if self.options.shared else "STATIC"
        tc.variables["ALSOFT_UTILS"] = False
        tc.variables["ALSOFT_EXAMPLES"] = False
        tc.variables["ALSOFT_TESTS"] = False
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_SoundIO"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        self._create_cmake_module_variables(
            self.folders.package / self._module_file_rel_path
        )

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenAL")
        self.info.set_property("cmake_target_name", "OpenAL::OpenAL")
        self.info.set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.set_property("pkg_config_name", "openal")

        self.info.libs = collect_libs(self)
        self.info.includedirs.append(os.path.join("include", "AL"))
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["dl", "m"])
        elif is_apple_os(self):
            self.info.frameworks.extend(["AudioToolbox", "AudioUnit", "CoreAudio", "CoreFoundation"])
            if self.settings.os == "Mac":
                self.info.frameworks.append("ApplicationServices")
        elif self.settings.os == "Windows":
            self.info.system_libs.extend(["winmm", "ole32", "shell32", "user32"])
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)
        if not self.options.shared:
            self.info.defines.append("AL_LIBTYPE_STATIC")
        if self.settings.compiler_libcxx in ["libstdc++", "libstdc++11"]:
            self.info.system_libs.append("atomic")

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            f"""
            set(OPENAL_FOUND TRUE)
            if(DEFINED OpenAL_INCLUDE_DIR)
                set(OPENAL_INCLUDE_DIR ${{OpenAL_INCLUDE_DIR}})
            endif()
            if(DEFINED OpenAL_LIBRARIES)
                set(OPENAL_LIBRARY ${{OpenAL_LIBRARIES}})
            endif()
            set(OPENAL_VERSION_STRING {self.version})
            """)
        save(self, module_file, content)

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")
