import os
from pathlib import Path

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import collect_libs, copy, get, replace_in_file, rmdir, save
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    double_precision: bool = False
    with_3d: bool = True
    with_3ds: bool = True
    with_3ds_exporter: bool = True
    with_3mf: bool = True
    with_3mf_exporter: bool = True
    with_ac: bool = True
    with_amf: bool = True
    with_ase: bool = True
    with_assbin: bool = True
    with_assbin_exporter: bool = True
    with_assxml_exporter: bool = True
    with_assjson_exporter: bool = True
    with_b3d: bool = True
    with_blend: bool = True
    with_bvh: bool = True
    with_ms3d: bool = True
    with_cob: bool = True
    with_collada: bool = True
    with_collada_exporter: bool = True
    with_csm: bool = True
    with_dxf: bool = True
    with_fbx: bool = True
    with_fbx_exporter: bool = True
    with_gltf: bool = True
    with_gltf_exporter: bool = True
    with_hmp: bool = True
    with_ifc: bool = True
    with_irr: bool = True
    with_irrmesh: bool = True
    with_lwo: bool = True
    with_lws: bool = True
    with_md2: bool = True
    with_md3: bool = True
    with_md5: bool = True
    with_mdc: bool = True
    with_mdl: bool = True
    with_mmd: bool = True
    with_ndo: bool = True
    with_nff: bool = True
    with_obj: bool = True
    with_obj_exporter: bool = True
    with_off: bool = True
    with_ogre: bool = True
    with_opengex: bool = True
    with_opengex_exporter: bool = True
    with_pbrt_exporter: bool = True
    with_ply: bool = True
    with_ply_exporter: bool = True
    with_q3bsp: bool = True
    with_q3d: bool = True
    with_raw: bool = True
    with_sib: bool = True
    with_smd: bool = True
    with_step: bool = True
    with_step_exporter: bool = True
    with_stl: bool = True
    with_stl_exporter: bool = True
    with_terragen: bool = True
    with_x: bool = True
    with_x_exporter: bool = True
    with_x3d: bool = True
    with_x3d_exporter: bool = True
    with_xgl: bool = True
    with_m3d: bool = True
    with_m3d_exporter: bool = True
    with_iqm: bool = True


class Recipe(RecipeBase[_Options]):
    name = "assimp"
    version = "6.0.5"
    license = "BSD-3-Clause"

    _format_option_map = {
        "with_3d": "ASSIMP_BUILD_3D_IMPORTER",
        "with_3ds": "ASSIMP_BUILD_3DS_IMPORTER",
        "with_3ds_exporter": "ASSIMP_BUILD_3DS_EXPORTER",
        "with_3mf": "ASSIMP_BUILD_3MF_IMPORTER",
        "with_3mf_exporter": "ASSIMP_BUILD_3MF_EXPORTER",
        "with_ac": "ASSIMP_BUILD_AC_IMPORTER",
        "with_amf": "ASSIMP_BUILD_AMF_IMPORTER",
        "with_ase": "ASSIMP_BUILD_ASE_IMPORTER",
        "with_assbin": "ASSIMP_BUILD_ASSBIN_IMPORTER",
        "with_assbin_exporter": "ASSIMP_BUILD_ASSBIN_EXPORTER",
        "with_assxml_exporter": "ASSIMP_BUILD_ASSXML_EXPORTER",
        "with_assjson_exporter": "ASSIMP_BUILD_ASSJSON_EXPORTER",
        "with_b3d": "ASSIMP_BUILD_B3D_IMPORTER",
        "with_blend": "ASSIMP_BUILD_BLEND_IMPORTER",
        "with_bvh": "ASSIMP_BUILD_BVH_IMPORTER",
        "with_ms3d": "ASSIMP_BUILD_MS3D_IMPORTER",
        "with_cob": "ASSIMP_BUILD_COB_IMPORTER",
        "with_collada": "ASSIMP_BUILD_COLLADA_IMPORTER",
        "with_collada_exporter": "ASSIMP_BUILD_COLLADA_EXPORTER",
        "with_csm": "ASSIMP_BUILD_CSM_IMPORTER",
        "with_dxf": "ASSIMP_BUILD_DXF_IMPORTER",
        "with_fbx": "ASSIMP_BUILD_FBX_IMPORTER",
        "with_fbx_exporter": "ASSIMP_BUILD_FBX_EXPORTER",
        "with_gltf": "ASSIMP_BUILD_GLTF_IMPORTER",
        "with_gltf_exporter": "ASSIMP_BUILD_GLTF_EXPORTER",
        "with_hmp": "ASSIMP_BUILD_HMP_IMPORTER",
        "with_ifc": "ASSIMP_BUILD_IFC_IMPORTER",
        "with_irr": "ASSIMP_BUILD_IRR_IMPORTER",
        "with_irrmesh": "ASSIMP_BUILD_IRRMESH_IMPORTER",
        "with_lwo": "ASSIMP_BUILD_LWO_IMPORTER",
        "with_lws": "ASSIMP_BUILD_LWS_IMPORTER",
        "with_md2": "ASSIMP_BUILD_MD2_IMPORTER",
        "with_md3": "ASSIMP_BUILD_MD3_IMPORTER",
        "with_md5": "ASSIMP_BUILD_MD5_IMPORTER",
        "with_mdc": "ASSIMP_BUILD_MDC_IMPORTER",
        "with_mdl": "ASSIMP_BUILD_MDL_IMPORTER",
        "with_mmd": "ASSIMP_BUILD_MMD_IMPORTER",
        "with_ndo": "ASSIMP_BUILD_NDO_IMPORTER",
        "with_nff": "ASSIMP_BUILD_NFF_IMPORTER",
        "with_obj": "ASSIMP_BUILD_OBJ_IMPORTER",
        "with_obj_exporter": "ASSIMP_BUILD_OBJ_EXPORTER",
        "with_off": "ASSIMP_BUILD_OFF_IMPORTER",
        "with_ogre": "ASSIMP_BUILD_OGRE_IMPORTER",
        "with_opengex": "ASSIMP_BUILD_OPENGEX_IMPORTER",
        "with_opengex_exporter": "ASSIMP_BUILD_OPENGEX_EXPORTER",
        "with_pbrt_exporter": "ASSIMP_BUILD_PBRT_EXPORTER",
        "with_ply": "ASSIMP_BUILD_PLY_IMPORTER",
        "with_ply_exporter": "ASSIMP_BUILD_PLY_EXPORTER",
        "with_q3bsp": "ASSIMP_BUILD_Q3BSP_IMPORTER",
        "with_q3d": "ASSIMP_BUILD_Q3D_IMPORTER",
        "with_raw": "ASSIMP_BUILD_RAW_IMPORTER",
        "with_sib": "ASSIMP_BUILD_SIB_IMPORTER",
        "with_smd": "ASSIMP_BUILD_SMD_IMPORTER",
        "with_step": "ASSIMP_BUILD_STEP_IMPORTER",
        "with_step_exporter": "ASSIMP_BUILD_STEP_EXPORTER",
        "with_stl": "ASSIMP_BUILD_STL_IMPORTER",
        "with_stl_exporter": "ASSIMP_BUILD_STL_EXPORTER",
        "with_terragen": "ASSIMP_BUILD_TERRAGEN_IMPORTER",
        "with_x": "ASSIMP_BUILD_X_IMPORTER",
        "with_x_exporter": "ASSIMP_BUILD_X_EXPORTER",
        "with_x3d": "ASSIMP_BUILD_X3D_IMPORTER",
        "with_x3d_exporter": "ASSIMP_BUILD_X3D_EXPORTER",
        "with_xgl": "ASSIMP_BUILD_XGL_IMPORTER",
        "with_m3d": "ASSIMP_BUILD_M3D_IMPORTER",
        "with_m3d_exporter": "ASSIMP_BUILD_M3D_EXPORTER",
        "with_iqm": "ASSIMP_BUILD_IQM_IMPORTER",
    }
    
    def latest_version(self):
        repo = GithubRepository(self, "assimp/assimp")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        # TODO: unvendor others libs:
        # - Open3DGC
        self.requires_tool("cmake")
        self.requires("minizip")
        self.requires("pugixml")
        self.requires("utfcpp")
        self.requires("zlib")
        if self._depends_on_kuba_zip:
            self.requires("kuba-zip")
        if self._depends_on_poly2tri:
            self.requires("poly2tri")
        if self._depends_on_rapidjson:
            self.requires("rapidjson")
        if self._depends_on_draco:
            self.requires("draco")
        if self._depends_on_clipper:
            self.requires("clipper")
        if self._depends_on_stb:
            self.requires("stb")
        if self._depends_on_openddlparser:
            self.requires("openddl-parser")

    def source(self):
        get(
            self,
            url=f"https://github.com/assimp/assimp/archive/refs/tags/v{self.version}.tar.gz",
            sha256="edf3749559c2b7d1f758ffb66fc5bec62186221e623b7f2e8969f17ee46ecb6f",
            destination=self.folders.source,
            strip_root=True)

        # Don't force several compiler and linker flags
        for pattern in [
            "-fPIC",
            "-g ",
            "SET(CMAKE_POSITION_INDEPENDENT_CODE ON)",
            'SET(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /D_DEBUG /Zi /Od")',
            'SET(CMAKE_SHARED_LINKER_FLAGS_RELEASE "${CMAKE_SHARED_LINKER_FLAGS_RELEASE} /DEBUG:FULL /PDBALTPATH:%_PDB% /OPT:REF /OPT:ICF")',
        ]:
            replace_in_file(self, self.folders.source / "CMakeLists.txt", pattern, "")

        for pattern in ["-Werror", "/WX"]:
            replace_in_file(self, self.folders.source / "CMakeLists.txt", pattern, "")
            replace_in_file(self, self.folders.source / "code" / "CMakeLists.txt", pattern, "")

        # Make sure vendored libs are not used by accident by removing their subdirs
        allow_vendored = ["Open3DGC", "earcut-hpp"]
        for contrib_dir in Path(self.folders.source).joinpath("contrib").iterdir():
            if contrib_dir.is_dir() and contrib_dir.name not in allow_vendored:
                rmdir(self, contrib_dir)

        # Do not include add vendored library sources to the build
        # https://github.com/assimp/assimp/blob/v5.3.1/code/CMakeLists.txt#L1151-L1159
        code_cmakelists = Path(self.folders.source).joinpath("code", "CMakeLists.txt")
        content = code_cmakelists.read_text(encoding="utf-8")
        for vendored_lib in [
            "unzip_compile",
            "Poly2Tri",
            "Clipper",
            "openddl_parser",
            # "open3dgc",
            "ziplib",
            "Pugixml",
            "stb",
        ]:
            content = content.replace("${%s_SRCS}" % vendored_lib, "")
        # Link recipe-provided targets in non-hunter mode so their include dirs propagate
        content = content.replace(
            "  if(TARGET pugixml::pugixml)\n    target_link_libraries(assimp pugixml::pugixml)\n  endif()\nENDIF()",
            "  if(TARGET pugixml::pugixml)\n    target_link_libraries(assimp pugixml::pugixml)\n  endif()\n"
            "  foreach(_recipe_target rapidjson::rapidjson utf8cpp::utf8cpp stb::stb openddlparser::openddlparser minizip::minizip poly2tri::poly2tri clipper::clipper zip::zip)\n"
            "    if(TARGET ${_recipe_target})\n"
            "      target_link_libraries(assimp ${_recipe_target})\n"
            "    endif()\n"
            "  endforeach()\n"
            "ENDIF()"
        )
        code_cmakelists.write_text(content, encoding="utf-8")

        # Make vendored headers redirect to external ones.
        for contrib_header, include in [
            (os.path.join("clipper", "clipper.hpp"), "polyclipping/clipper.hpp"),
            (os.path.join("poly2tri", "poly2tri", "poly2tri.h"), "poly2tri/poly2tri.h"),
            (os.path.join("stb", "stb_image.h"), "stb_image.h"),
            (os.path.join("utf8cpp", "source", "utf8.h"), "utf8.h"),
            (os.path.join("zip", "src", "zip.h"), "zip/zip.h"),
        ]:
            save(self, self.folders.source / "contrib" / contrib_header, f"#include <{include}>\n")

        rmdir(self, self.folders.source / "contrib" / "utf8cpp")

        # minizip is provided via recipe_deps.cmake, no need to use pkgconfig
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "use_pkgconfig(UNZIP minizip)",
            "set(UNZIP_FOUND TRUE)")

        # ZLIB is unvendored, no need to install it
        # https://github.com/assimp/assimp/blob/v5.3.1/CMakeLists.txt#L483-L487
        # https://github.com/assimp/assimp/blob/v5.1.6/CMakeLists.txt#L463-L466
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "INSTALL( TARGETS zlib", "set(_ #")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["ASSIMP_ANDROID_JNIIOSYSTEM"] = False
        tc.variables["ASSIMP_BUILD_ALL_IMPORTERS_BY_DEFAULT"] = False
        tc.variables["ASSIMP_BUILD_ALL_EXPORTERS_BY_DEFAULT"] = False
        tc.variables["ASSIMP_BUILD_ASSIMP_TOOLS"] = False
        tc.variables["ASSIMP_BUILD_DOCS"] = False
        tc.variables["ASSIMP_BUILD_DRACO"] = False
        tc.variables["ASSIMP_BUILD_FRAMEWORK"] = False
        tc.variables["ASSIMP_BUILD_MINIZIP"] = False
        tc.variables["ASSIMP_BUILD_SAMPLES"] = False
        tc.variables["ASSIMP_BUILD_TESTS"] = False
        tc.variables["ASSIMP_BUILD_ZLIB"] = False
        tc.variables["ASSIMP_DOUBLE_PRECISION"] = self.options.double_precision
        tc.variables["ASSIMP_HUNTER_ENABLED"] = False
        tc.variables["ASSIMP_IGNORE_GIT_HASH"] = True
        tc.variables["ASSIMP_INJECT_DEBUG_POSTFIX"] = False
        tc.variables["ASSIMP_INSTALL"] = True
        tc.variables["ASSIMP_INSTALL_PDB"] = False
        tc.variables["ASSIMP_NO_EXPORT"] = False
        tc.variables["ASSIMP_OPT_BUILD_PACKAGES"] = False
        tc.variables["ASSIMP_RAPIDJSON_NO_MEMBER_ITERATOR"] = False
        tc.variables["ASSIMP_UBSAN"] = False
        tc.variables["ASSIMP_WARNINGS_AS_ERRORS"] = False
        tc.variables["USE_STATIC_CRT"] = is_msvc_static_runtime(self)
        tc.cache_variables["ASSIMP_BUILD_USE_CCACHE"] = False

        for option, definition in self._format_option_map.items():
            value = self.options.get_safe(option)
            if value is not None:
                tc.variables[definition] = value
        if self.settings.os == "Windows":
            tc.preprocessor_definitions["NOMINMAX"] = 1

        tc.cache_variables["CMAKE_PROJECT_Assimp_INCLUDE"] = (self.folders.generators / "recipe_deps.cmake").as_posix()
        tc.cache_variables["WITH_CLIPPER"] = self._depends_on_clipper
        tc.cache_variables["WITH_DRACO"] = self._depends_on_draco
        tc.cache_variables["WITH_KUBAZIP"] = self._depends_on_kuba_zip
        tc.cache_variables["WITH_OPENDDL"] = self._depends_on_openddlparser
        tc.cache_variables["WITH_POLY2TRI"] = self._depends_on_poly2tri
        tc.cache_variables["WITH_RAPIDJSON"] = self._depends_on_rapidjson
        tc.cache_variables["WITH_STB"] = self._depends_on_stb
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("rapidjson", "cmake_target_name", "rapidjson::rapidjson")
        deps.set_property("utfcpp", "cmake_target_name", "utf8cpp::utf8cpp")
        deps.generate()

        # CMakeDeps does not generate the CMakeDeps `recipe_deps.cmake` find_package
        # aggregator that assimp injects via CMAKE_PROJECT_Assimp_INCLUDE.  Write an equivalent
        # so the dependency targets exist at project() time (assimp links them conditionally in
        # _patch_sources).  find_package names match each dep's cmake_file_name (same configs
        # CMakeDeps emits); calls are non-REQUIRED so options-disabled deps are harmless.
        _agg_pkgs = ["BZip2", "ZLIB", "minizip", "pugixml", "utf8cpp", "zip",
                     "poly2tri", "RapidJSON", "draco", "clipper", "stb", "openddlparser"]
        save(self, self.folders.generators / "recipe_deps.cmake",
             "".join(f"find_package({p})\n" for p in _agg_pkgs))

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "assimp")
        self.info.set_property("cmake_target_name", "assimp::assimp")
        self.info.set_property("pkg_config_name", "assimp")
        # Always ever just 1 library, but with some suffix variations
        # that make it hard to map manually
        self.info.libs = collect_libs(self)
        if is_msvc(self) and self.options.shared:
            self.info.defines.append("ASSIMP_DLL")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["rt", "m", "pthread"]
        elif self.settings.os == "WindowsStore":
            self.info.system_libs.append("advapi32")
            self.info.defines.append("WindowsStore")
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)
    
    @property
    def _depends_on_kuba_zip(self):
        return self.options.with_3mf_exporter

    @property
    def _depends_on_poly2tri(self):
        return self.options.with_blend or self.options.with_ifc

    @property
    def _depends_on_rapidjson(self):
        return self.options.with_gltf or self.options.with_gltf_exporter

    @property
    def _depends_on_draco(self):
        return self.options.with_gltf or self.options.with_gltf_exporter

    @property
    def _depends_on_clipper(self):
        return self.options.with_ifc

    @property
    def _depends_on_stb(self):
        return self.options.with_m3d or self.options.with_m3d_exporter or \
            self.options.with_pbrt_exporter

    @property
    def _depends_on_openddlparser(self):
        return self.options.with_opengex
