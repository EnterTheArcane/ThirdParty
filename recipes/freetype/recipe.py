import os
from pathlib import Path
import re
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import (
    collect_libs, copy, load,
    get, replace_in_file, rmdir, save,
)
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_bzip2: bool = True
    subpixel: bool = False


class Recipe(RecipeBase[_Options]):
    name = "freetype"
    version = "2.14.3"
    license = "FTL"

    def latest_version(self):
        repo = GithubRepository(self, "freetype/freetype")
        return Version(repo.latest_release.removeprefix("VER-").replace("-", "."))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("brotli")
        self.requires("bzip2")
        self.requires("libpng")
        self.requires("zlib")

    def source(self):
        get(
            self,
            url=f"https://github.com/freetype/freetype/archive/refs/tags/VER-{self.version.replace('.', '-')}.tar.gz",
            sha256="dc49de6b01a266eef4876a4dd34d9842c475d3e28ff2eff63bd2fb760ab56261",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        deps = CMakeDeps(self)
        # freetype's CMakeLists does find_package(Brotli) and links target brotli::brotli;
        # Brotli has no builtin CMake Find module, so emit a "Brotli" config for it.
        deps.set_property("brotli", "cmake_file_name", "Brotli")
        deps.set_property("brotli", "cmake_target_name", "brotli::brotli")
        deps.generate()

        tc = CMakeToolchain(self)
        tc.variables["FT_REQUIRE_ZLIB"] = True
        tc.variables["FT_DISABLE_ZLIB"] = False
        tc.variables["FT_REQUIRE_PNG"] = True
        tc.variables["FT_DISABLE_PNG"] = False
        tc.variables["FT_REQUIRE_BZIP2"] = True
        tc.variables["FT_DISABLE_BZIP2"] = False
        # TODO: Harfbuzz can be added as an option as soon as it is available.
        tc.variables["FT_REQUIRE_HARFBUZZ"] = False
        tc.variables["FT_DISABLE_HARFBUZZ"] = True
        tc.variables["FT_REQUIRE_BROTLI"] = True
        tc.variables["FT_DISABLE_BROTLI"] = False
        # Generate a relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        tc.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

        libtool_version = self._extract_libtool_version()
        save(self, self._libtool_version_txt, libtool_version)
        self._make_freetype_config(libtool_version)

        doc_folder = self.folders.source / "docs"
        license_folder = self.folders.package / "licenses"
        copy(self, "FTL.TXT", doc_folder, license_folder)
        copy(self, "GPLv2.TXT", doc_folder, license_folder)
        copy(self, "LICENSE.TXT", doc_folder, license_folder)

        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        self._create_cmake_module_variables(
            self.folders.package / self._module_vars_rel_path
        )
        self._create_cmake_module_alias_targets(
            self.folders.package / self._module_target_rel_path,
            {"freetype": "Freetype::Freetype"}
        )

    def package_info(self):
        # Use config mode with the canonical "Freetype" name. The CMakeDeps generator
        # does not emit Find modules, so a split "both"/module setup would let consumers'
        # find_package(Freetype) fall through to CMake's builtin FindFreetype, which links
        # only freetype itself and drops freetype's private static deps (brotli, bzip2) -
        # causing unresolved BrotliDecoderDecompress / BZ2_* symbols downstream.
        self.info.set_property("cmake_find_mode", "config")
        self.info.set_property("cmake_file_name", "Freetype")
        self.info.set_property("cmake_target_name", "Freetype::Freetype")
        self.info.set_property("cmake_target_aliases", ["freetype"])  # other possible target name in upstream config file
        self.info.set_property("cmake_build_modules", [self._module_vars_rel_path])
        self.info.set_property("pkg_config_name", "freetype2")
        self.info.libs = collect_libs(self)
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
        self.info.includedirs.append(os.path.join("include", "freetype2"))

        libtool_version = load(self, self._libtool_version_txt).strip()
        self.info.conf.tools.freetype.libtool_version = libtool_version
        self.info.set_property("system_package_version", libtool_version)

        self.info.set_property("component_version", libtool_version)
        freetype_config = self.folders.package / "bin" / "freetype-config"
        _chmod_plus_x(freetype_config)

    def _patch_sources(self):
        # Do not accidentally enable dependencies we have disabled
        cmakelists = self.folders.source / "CMakeLists.txt"
        if_harfbuzz_found = "if (HarfBuzz_FOUND)"
        replace_in_file(self, cmakelists, "find_package(HarfBuzz ${HARFBUZZ_MIN_VERSION})", "", strict=False)
        replace_in_file(self, cmakelists, if_harfbuzz_found, "if(0)", strict=False)
        # the custom FindBrotliDec of upstream is too fragile
        replace_in_file(
            self, cmakelists,
            "find_package(BrotliDec REQUIRED)",
            "find_package(Brotli REQUIRED)\n"
            "set(BROTLIDEC_FOUND 1)\n"
            "set(BROTLIDEC_LIBRARIES \"brotli::brotli\")",
            strict=False)

        config_h = self.folders.source / "include" / "freetype" / "config" / "ftoption.h"
        if self.options.subpixel:
            replace_in_file(self, config_h, "/* #define FT_CONFIG_OPTION_SUBPIXEL_RENDERING */", "#define FT_CONFIG_OPTION_SUBPIXEL_RENDERING", strict=False)

    def _make_freetype_config(self, version: str):
        freetype_config_in = self.folders.source / "builds" / "unix" / "freetype-config.in"
        if not os.path.isdir(self.folders.package / "bin"):
            os.makedirs(self.folders.package / "bin")
        freetype_config = self.folders.package / "bin" / "freetype-config"
        save(self, freetype_config, load(self, freetype_config_in))
        libs = "-lfreetyped" if self.settings.build_type == "Debug" else "-lfreetype"
        staticlibs = f"-lm {libs}" if self.settings.os == "Linux" else libs
        replace_in_file(self, freetype_config, r"%PKG_CONFIG%", r"/bin/false")  # never use pkg-config
        replace_in_file(self, freetype_config, r"%prefix%", r"$recipe_prefix")
        replace_in_file(self, freetype_config, r"%exec_prefix%", r"$recipe_exec_prefix")
        replace_in_file(self, freetype_config, r"%includedir%", r"$recipe_includedir")
        replace_in_file(self, freetype_config, r"%libdir%", r"$recipe_libdir")
        replace_in_file(self, freetype_config, r"%ft_version%", r"$recipe_ftversion")
        replace_in_file(self, freetype_config, r"%LIBSSTATIC_CONFIG%", r"$recipe_staticlibs")
        replace_in_file(self, freetype_config, r"-lfreetype", libs)
        replace_in_file(
            self, freetype_config, r"export LC_ALL", textwrap.dedent(
                """
                export LC_ALL
                BINDIR=$(dirname $0)
                recipe_prefix=$(dirname $BINDIR)
                recipe_exec_prefix=${{recipe_prefix}}/bin
                recipe_includedir=${{recipe_prefix}}/include
                recipe_libdir=${{recipe_prefix}}/lib
                recipe_ftversion={version}
                recipe_staticlibs="{staticlibs}"
                """).format(version=version, staticlibs=staticlibs))

    def _extract_libtool_version(self):
        conf_raw = load(self, self.folders.source / "builds" / "unix" / "configure.raw")
        return next(re.finditer(r"^version_info='([0-9:]+)'", conf_raw, flags=re.M)).group(1).replace(":", ".")

    @property
    def _libtool_version_txt(self):
        return self.folders.package / "res" / "freetype-libtool-version.txt"

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            f"""
            set(FREETYPE_FOUND TRUE)
            if(DEFINED Freetype_INCLUDE_DIRS)
                set(FREETYPE_INCLUDE_DIRS ${{Freetype_INCLUDE_DIRS}})
            endif()
            if(DEFINED Freetype_LIBRARIES)
                set(FREETYPE_LIBRARIES ${{Freetype_LIBRARIES}})
            endif()
            set(FREETYPE_VERSION_STRING "{self.version}")
            """)
        save(self, module_file, content)

    def _create_cmake_module_alias_targets(self, module_file: Path, targets: dict[str, str]):
        content = ""
        for alias, aliased in targets.items():
            content += textwrap.dedent(
                """
                if(TARGET {aliased} AND NOT TARGET {alias})
                    add_library({alias} INTERFACE IMPORTED)
                    set_property(TARGET {alias} PROPERTY INTERFACE_LINK_LIBRARIES {aliased})
                endif()
                """.format(alias=alias, aliased=aliased))
        save(self, module_file, content)

    @property
    def _module_vars_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-variables.cmake")

    @property
    def _module_target_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-targets.cmake")

def _chmod_plus_x(filename: Path):
    if os.name == "posix" and (os.stat(filename).st_mode & 0o111) != 0o111:
        os.chmod(filename, os.stat(filename).st_mode | 0o111)
