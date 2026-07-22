import os
from pathlib import Path
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import copy, get, rm, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libxml2"
    version = "2.15.3"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "GNOME/libxml2")
        return Version(repo.latest_tag("v").removeprefix("v"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("icu")
        self.requires("libiconv")
        self.requires("zlib")

    def source(self):
        get(
            self,
            url=f"https://github.com/GNOME/libxml2/archive/refs/tags/v{self.version}.tar.gz",
            sha256="5c6060277173270356c3f1c321a640ab629bdabc5e5ba9095b99e00759ba0c39",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["LIBXML2_WITH_C14N"] = True
        tc.variables["LIBXML2_WITH_CATALOG"] = True
        tc.variables["LIBXML2_WITH_DOCS"] = False
        tc.variables["LIBXML2_WITH_HTML"] = True
        tc.variables["LIBXML2_WITH_HTTP"] = True
        tc.variables["LIBXML2_WITH_ICONV"] = True
        tc.variables["LIBXML2_WITH_ICU"] = True
        tc.variables["LIBXML2_WITH_ISO8859X"] = True
        tc.variables["LIBXML2_WITH_LEGACY"] = True
        tc.variables["LIBXML2_WITH_OUTPUT"] = True
        tc.variables["LIBXML2_WITH_PATTERN"] = True
        tc.variables["LIBXML2_WITH_PROGRAMS"] = True
        tc.variables["LIBXML2_WITH_PUSH"] = True
        tc.variables["LIBXML2_WITH_PYTHON"] = False
        tc.variables["LIBXML2_WITH_READER"] = True
        tc.variables["LIBXML2_WITH_REGEXPS"] = True
        tc.variables["LIBXML2_WITH_SAX1"] = True
        tc.variables["LIBXML2_WITH_SCHEMAS"] = True
        tc.variables["LIBXML2_WITH_SCHEMATRON"] = True
        tc.variables["LIBXML2_WITH_TESTS"] = False
        tc.variables["LIBXML2_WITH_THREADS"] = True
        tc.variables["LIBXML2_WITH_VALID"] = True
        tc.variables["LIBXML2_WITH_WRITER"] = True
        tc.variables["LIBXML2_WITH_XINCLUDE"] = True
        tc.variables["LIBXML2_WITH_XPATH"] = True
        tc.variables["LIBXML2_WITH_XPTR"] = True
        tc.variables["LIBXML2_WITH_ZLIB"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses", ignore_case=True, keep_path=False)
        cmake = CMake(self)
        cmake.install()
        rm(self, "*.pdb", self.folders.package / "bin")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")
        for header in ["win32config.h", "wsockcompat.h"]:
            copy(
                self, pattern=header, src=self.folders.source / "include",
                dst=self.folders.package / "include" / "libxml2", keep_path=False)
        self._create_cmake_module_variables(
            self.folders.package / self._module_file_rel_path
        )

    def package_info(self):
        self.info.set_property("cmake_file_name", "libxml2")
        self.info.set_property("cmake_target_name", "LibXml2::LibXml2")
        self.info.set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.set_property("pkg_config_name", "libxml-2.0")

        prefix = "lib" if self.settings.os == "Windows" else ""
        postfix = ""
        if self.settings.os == "Windows":
            if not self.options.shared:
                postfix += "s"
            if self.settings.build_type == "Debug":
                postfix += "d"
        self.info.libs = [f"{prefix}xml2{postfix}"]
        self.info.includedirs.append(os.path.join("include", "libxml2"))
        if not self.options.shared:
            self.info.defines = ["LIBXML_STATIC"]

        if self.settings.os in ["Linux", "FreeBSD", "Android"]:
            self.info.system_libs += ["m", "dl"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.system_libs.append("pthread")
        elif self.settings.os == "Windows":
            self.info.system_libs += ["ws2_32", "bcrypt"]

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            f"""
            set(LibXml2_FOUND TRUE)
            set(LIBXML2_FOUND TRUE)
            if(DEFINED LibXml2_INCLUDE_DIRS)
                set(LIBXML2_INCLUDE_DIR ${{LibXml2_INCLUDE_DIRS}})
                set(LIBXML2_INCLUDE_DIRS ${{LibXml2_INCLUDE_DIRS}})
            elseif(DEFINED libxml2_INCLUDE_DIRS)
                set(LIBXML2_INCLUDE_DIR ${{libxml2_INCLUDE_DIRS}})
                set(LIBXML2_INCLUDE_DIRS ${{libxml2_INCLUDE_DIRS}})
            endif()
            if(DEFINED LibXml2_LIBRARIES)
                set(LIBXML2_LIBRARIES ${{LibXml2_LIBRARIES}})
                set(LIBXML2_LIBRARY ${{LibXml2_LIBRARIES}})
            elseif(DEFINED libxml2_LIBRARIES)
                set(LIBXML2_LIBRARIES ${{libxml2_LIBRARIES}})
                set(LIBXML2_LIBRARY ${{libxml2_LIBRARIES}})
            endif()
            if(DEFINED LibXml2_DEFINITIONS)
                set(LIBXML2_DEFINITIONS ${{LibXml2_DEFINITIONS}})
            elseif(DEFINED libxml2_DEFINITIONS)
                set(LIBXML2_DEFINITIONS ${{libxml2_DEFINITIONS}})
            else()
                set(LIBXML2_DEFINITIONS "")
            endif()
            set(LIBXML2_VERSION_STRING "{self.version}")
            """)
        save(self, module_file, content)

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")
