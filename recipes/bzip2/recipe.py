import os
from pathlib import Path
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, save
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_executable: bool = True


class Recipe(RecipeBase[_Options]):
    name = "bzip2"
    version = "1.0.8"
    license = "bzip2-1.0.6"

    def latest_version(self):
        repo = GitlabRepository(self, "bzip2/bzip2")
        return Version(repo.latest_release.removeprefix("bzip2-"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://gitlab.com/bzip2/bzip2/-/archive/bzip2-{self.version}/bzip2-bzip2-{self.version}.tar.gz",
            sha256="db106b740252669664fd8f3a1c69fe7f689d5cd4b132f82ba82b9afba27627df",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BZ2_BUILD_EXE"] = self.options.build_executable
        tc.variables["BZ2_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["BZ2_VERSION_MAJOR"] = Version(self.version).major
        tc.variables["BZ2_VERSION_STRING"] = self.version
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        self._create_cmake_module_variables(self.folders.package / self._module_file_rel_path)

    def package_info(self):
        self.info.set_property("cmake_file_name", "BZip2")
        self.info.set_property("cmake_target_name", "BZip2::BZip2")
        self.info.set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.libs = ["bz2"]

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            f"""
            set(BZIP2_NEED_PREFIX TRUE)
            set(BZIP2_FOUND TRUE)
            if(NOT DEFINED BZIP2_INCLUDE_DIRS AND DEFINED BZip2_INCLUDE_DIRS)
                set(BZIP2_INCLUDE_DIRS ${{BZip2_INCLUDE_DIRS}})
            endif()
            if(NOT DEFINED BZIP2_INCLUDE_DIR AND DEFINED BZip2_INCLUDE_DIR)
                set(BZIP2_INCLUDE_DIR ${{BZip2_INCLUDE_DIR}})
            endif()
            if(NOT DEFINED BZIP2_LIBRARIES AND DEFINED BZip2_LIBRARIES)
                set(BZIP2_LIBRARIES ${{BZip2_LIBRARIES}})
            endif()
            set(BZIP2_VERSION_STRING "{self.version}")
            """)
        save(self, module_file, content)

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")
