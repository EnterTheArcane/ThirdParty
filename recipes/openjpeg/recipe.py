import os
from pathlib import Path
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir, save, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openjpeg"
    version = "2.5.4"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "uclouvain/openjpeg")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/uclouvain/openjpeg/archive/refs/tags/v{self.version}.tar.gz",
            sha256="a695fbe19c0165f295a8531b1e4e855cd94d0875d2f88ec4b61080677e27188a",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "-ffast-math", "-ffast-math;-fno-finite-math-only")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP"] = True
        tc.variables["BUILD_DOC"] = False
        tc.variables["BUILD_STATIC_LIBS"] = not self.options.shared
        tc.variables["BUILD_LUTS_GENERATOR"] = False
        tc.variables["BUILD_CODEC"] = False
        tc.variables["BUILD_JPIP"] = False
        tc.variables["BUILD_VIEWER"] = False
        tc.variables["BUILD_JAVA"] = False
        tc.variables["BUILD_TESTING"] = False
        tc.variables["BUILD_PKGCONFIG_FILES"] = False
        tc.variables["OPJ_DISABLE_TPSOT_FIX"] = False
        tc.variables["OPJ_USE_THREAD"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / self._openjpeg_subdir)
        rmdir(self, self.folders.package / "lib" / "cmake" / self._openjpeg_subdir)
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        self._create_cmake_module_variables(self.folders.package / self._module_vars_rel_path)
        self._create_cmake_module_alias_targets(
            self.folders.package / self._module_target_rel_path,
            {"openjp2": "OpenJPEG::OpenJPEG"}
        )

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenJPEG")
        self.info.set_property("cmake_target_name", "openjp2")
        self.info.set_property("cmake_build_modules", [self._module_vars_rel_path])
        self.info.set_property("pkg_config_name", "libopenjp2")
        self.info.includedirs.append(os.path.join("include", self._openjpeg_subdir))
        self.info.builddirs.append(os.path.join("lib", "cmake"))
        self.info.libs = ["openjp2"]
        if self.settings.os == "Windows" and not self.options.shared:
            self.info.defines.append("OPJ_STATIC")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["pthread", "m"]
        elif self.settings.os == "Android":
            self.info.system_libs = ["m"]

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            f"""
            set(OPENJPEG_FOUND TRUE)
            if(DEFINED OpenJPEG_INCLUDE_DIRS)
                set(OPENJPEG_INCLUDE_DIRS ${{OpenJPEG_INCLUDE_DIRS}})
            endif()
            if(DEFINED OpenJPEG_LIBRARIES)
                set(OPENJPEG_LIBRARIES ${{OpenJPEG_LIBRARIES}})
            endif()
            set(OPENJPEG_MAJOR_VERSION "{Version(self.version).major}")
            set(OPENJPEG_MINOR_VERSION "{Version(self.version).minor}")
            set(OPENJPEG_BUILD_VERSION "{Version(self.version).patch}")
            set(OPENJPEG_BUILD_SHARED_LIBS {"TRUE" if self.options.shared else "FALSE"})
            """)
        save(self, module_file, content)

    def _create_cmake_module_alias_targets(self, module_file: Path, targets: dict[str, str]):
        content = ""
        for alias, aliased in targets.items():
            content += textwrap.dedent(
                f"""
                if(TARGET {aliased} AND NOT TARGET {alias})
                    add_library({alias} INTERFACE IMPORTED)
                    set_property(TARGET {alias} PROPERTY INTERFACE_LINK_LIBRARIES {aliased})
                endif()
                """)
        save(self, module_file, content)

    @property
    def _module_vars_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")

    @property
    def _module_target_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-targets.cmake")

    @property
    def _openjpeg_subdir(self):
        openjpeg_version = Version(self.version)
        return f"openjpeg-{openjpeg_version.major}.{openjpeg_version.minor}"
