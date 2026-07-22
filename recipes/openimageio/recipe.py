from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_libjxl: bool = True
    with_libpng: bool = True
    with_freetype: bool = True
    with_opencolorio: bool = True
    with_opencv: bool = False
    with_tbb: bool = True
    with_dicom: bool = False
    with_ffmpeg: bool = True
    with_giflib: bool = True
    with_libheif: bool = True
    with_raw: bool = False
    with_openjpeg: bool = True
    with_openjph: bool = True
    with_openvdb: bool = False
    with_ptex: bool = True
    with_libwebp: bool = True
    with_libultrahdr: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openimageio"
    version = "3.1.15.0"
    license = "Apache-2.0", "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "AcademySoftwareFoundation/OpenImageIO")
        return Version(repo.latest_tag_matching(r"v(\d+\.\d+\.\d+\.\d+)"))

    def requirements(self):
        # Required libraries
        self.requires("zlib")
        self.requires("libtiff")
        self.requires("imath")
        self.requires("openexr")
        self.requires("libjpeg-turbo")
        if self.options.with_libjxl:
            self.requires("libjxl")
        self.requires("pugixml")
        self.requires("libsquish")
        self.requires("robin-map")
        self.requires("fmt")

        # Optional libraries
        if self.options.with_libpng:
            self.requires("libpng")
        if self.options.with_freetype:
            self.requires("freetype")
        if self.options.with_opencolorio:
            self.requires("opencolorio")
        if self.options.with_opencv:
            self.requires("opencv")
        if self.options.with_tbb:
            self.requires("onetbb")
        if self.options.with_dicom:
            self.requires("dcmtk")
        if self.options.with_ffmpeg:
            self.requires("ffmpeg")
        # TODO: Field3D dependency
        if self.options.with_giflib:
            self.requires("giflib")
        if self.options.with_libheif:
            self.requires("libheif")
        if self.options.with_raw:
            self.requires("libraw")
        if self.options.with_openjpeg:
            self.requires("openjpeg")
        if self.options.with_openjph:
            self.requires("openjph")
        if self.options.with_openvdb:
            self.requires("openvdb")
        if self.options.with_ptex:
            self.requires("ptex")
        if self.options.with_libwebp:
            self.requires("libwebp")
        if self.options.with_libultrahdr:
            self.requires("libultrahdr")
        # TODO: R3DSDK dependency
        # TODO: Nuke dependency
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/AcademySoftwareFoundation/OpenImageIO/releases/download/v{self.version}/OpenImageIO-{self.version}.tar.gz",
            sha256="2c17eb34aa9d645629caf26a1c90e14556ae558f429e1ff6f0e41fbe4c80d42e",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)

        # CMake options
        tc.variables["CMAKE_DEBUG_POSTFIX"] = ""  # Needed for 2.3.x.x+ versions
        tc.variables["OIIO_BUILD_TOOLS"] = True
        tc.variables["OIIO_BUILD_TESTS"] = False
        tc.variables["BUILD_DOCS"] = False
        tc.variables["INSTALL_DOCS"] = False
        tc.variables["INSTALL_FONTS"] = False
        tc.variables["INSTALL_CMAKE_HELPER"] = False
        tc.variables["EMBEDPLUGINS"] = True
        tc.variables["USE_PYTHON"] = False
        tc.variables["USE_EXTERNAL_PUGIXML"] = True
        tc.variables["BUILD_MISSING_FMT"] = False

        # Recipe is normally not used for testing, so fixing this option to not build the tests
        tc.variables["BUILD_TESTING"] = False

        # OIIO CMake files are patched to check USE_* flags to require or not use dependencies
        tc.variables["USE_JPEGTURBO"] = True
        tc.variables[
            "USE_JPEG"
        ] = True  # Needed for jpeg.imageio plugin, libjpeg/libjpeg-turbo selection still works
        tc.cache_variables["USE_JXL"] = self.options.with_libjxl
        tc.variables["USE_OPENCOLORIO"] = self.options.with_opencolorio
        tc.variables["USE_OPENCV"] = self.options.with_opencv
        tc.variables["USE_TBB"] = self.options.with_tbb
        tc.variables["USE_DCMTK"] = self.options.with_dicom
        tc.variables["USE_FIELD3D"] = False
        tc.variables["USE_GIF"] = self.options.with_giflib
        tc.variables["USE_LIBHEIF"] = self.options.with_libheif
        tc.variables["USE_LIBRAW"] = self.options.with_raw
        tc.variables["USE_OPENVDB"] = self.options.with_openvdb
        tc.variables["USE_PTEX"] = self.options.with_ptex
        tc.variables["USE_R3DSDK"] = False
        tc.variables["USE_NUKE"] = False
        tc.variables["USE_OPENGL"] = False
        tc.variables["USE_QT"] = False
        tc.variables["USE_LIBPNG"] = self.options.with_libpng
        tc.variables["USE_FREETYPE"] = self.options.with_freetype
        tc.variables["USE_LIBWEBP"] = self.options.with_libwebp
        tc.variables["USE_OPENJPEG"] = self.options.with_openjpeg
        tc.cache_variables["USE_OPENJPH"] = self.options.with_openjph

        tc.cache_variables["USE_FFMPEG"] = self.options.with_ffmpeg
        if self.options.with_ffmpeg:
            tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_FFmpeg"] = True
            tc.cache_variables["FFMPEG_VERSION"] = f'"{str(self.dependencies["ffmpeg"].version)}"'

        tc.cache_variables["BUILD_MISSING_ROBINMAP"] = False
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_Robinmap"] = True
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_pugixml"] = True
        tc.cache_variables["OIIO_INTERNALIZE_FMT"] = False
        tc.cache_variables["ROBINMAP_INCLUDES"] = self.dependencies["robin-map"].info.includedirs[0].replace("\\", "/")
        tc.cache_variables["IMATH_INCLUDES"] = self.dependencies["imath"].info.includedirs[0].replace("\\", "/")
        tc.cache_variables["OPENEXR_INCLUDES"] = self.dependencies["openexr"].info.includedirs[0].replace("\\", "/")
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_PNG"] = self.options.with_libpng
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_Freetype"] = self.options.with_freetype
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_OpenColorIO"] = self.options.with_opencolorio
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_OpenCV"] = self.options.with_opencv
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_TBB"] = self.options.with_tbb
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_DCMTK"] = self.options.with_dicom
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_GIF"] = self.options.with_giflib
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_Libheif"] = self.options.with_libheif
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_LibRaw"] = self.options.with_raw
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_OpenJPEG"] = self.options.with_openjpeg
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_openjph"] = self.options.with_openjph
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_Ptex"] = self.options.with_ptex
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_WebP"] = self.options.with_libwebp
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_JXL"] = self.options.with_libjxl

        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_libjpeg-turbo"] = False
        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_R3DSDK"] = True
        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_Nuke"] = True
        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_JXL"] = not self.options.with_libjxl

        if self.settings.os == "Linux":
            # Workaround for: upstream issue 13560
            # note: should not be needed if CMakeDeps is used
            libdirs_host = [l for dependency in self.dependencies.host.values() for l in dependency.info.aggregated_components().libdirs]
            tc.cache_variables["CMAKE_BUILD_RPATH"] = ";".join(libdirs_host)
        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("fmt", "cmake_additional_variables_prefixes", ["FMT"])
        deps.set_property("ffmpeg", "cmake_additional_variables_prefixes", ["FFMPEG"])
        deps.set_property("ffmpeg", "cmake_file_name", "FFmpeg")
        deps.set_property("libheif", "cmake_additional_variables_prefixes", ["LIBHEIF"])
        deps.set_property("robin-map", "cmake_file_name", "Robinmap")
        deps.set_property("robin-map", "cmake_additional_variables_prefixes", ["ROBINMAP"])
        deps.set_property("openexr", "cmake_target_name", "OpenEXR::OpenEXR")
        deps.set_property("libultrahdr", "cmake_file_name", "libuhdr")
        deps.set_property("libultrahdr", "cmake_target_name", "libuhdr::libuhdr")
        deps.set_property("libjxl", "cmake_file_name", "JXL")
        deps.set_property("openjph", "cmake_target_name", "openjph")
        deps.set_property("libheif", "cmake_target_name", "heif")
        deps.set_property("ptex", "cmake_file_name", "Ptex")
        deps.set_property("freetype", "cmake_file_name", "Freetype")
        deps.set_property("libheif", "cmake_file_name", "Libheif")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*.md", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")
        if self.settings.os == "Windows":
            for vc_file in ("concrt", "msvcp", "vcruntime"):
                rm(self, f"{vc_file}*.dll", self.folders.package / "bin")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenImageIO")
        self.info.set_property("pkg_config_name", "OpenImageIO")

        # OpenImageIO::OpenImageIO_Util
        open_image_io_util = self._add_component("OpenImageIO_Util")
        open_image_io_util.libs = ["OpenImageIO_Util"]
        open_image_io_util.requires = [
            "imath::imath",
            "openexr::openexr",
        ]
        if self.settings.os in ["Linux", "FreeBSD"]:
            open_image_io_util.system_libs.extend(
                ["dl", "m", "pthread"]
            )
        if self.options.with_tbb:
            open_image_io_util.requires.append("onetbb::onetbb")

        # OpenImageIO::OpenImageIO
        open_image_io = self._add_component("OpenImageIO")
        open_image_io.libs = ["OpenImageIO"]
        open_image_io.requires = [
            "openimageio_openimageio_util",
            "zlib::zlib",
            "libtiff::libtiff",
            "pugixml::pugixml",
            "robin-map::robin-map",
            "libsquish::libsquish",
            "fmt::fmt",
            "imath::imath",
            "openexr::openexr",
        ]

        open_image_io.requires.append("libjpeg-turbo::jpeg")
        if self.options.with_libpng:
            open_image_io.requires.append("libpng::libpng")
        if self.options.with_freetype:
            open_image_io.requires.append("freetype::freetype")
        if self.options.with_opencolorio:
            open_image_io.requires.append("opencolorio::opencolorio")
        if self.options.with_opencv:
            open_image_io.requires.append("opencv::opencv")
        if self.options.with_dicom:
            open_image_io.requires.append("dcmtk::dcmtk")
        if self.options.with_ffmpeg:
            open_image_io.requires.append("ffmpeg::ffmpeg")
        if self.options.with_giflib:
            open_image_io.requires.append("giflib::giflib")
        if self.options.with_libheif:
            open_image_io.requires.append("libheif::libheif")
        if self.options.with_raw:
            open_image_io.requires.append("libraw::libraw")
        if self.options.with_openjpeg:
            open_image_io.requires.append("openjpeg::openjpeg")
        if self.options.with_openjph:
            open_image_io.requires.append("openjph::openjph")
        if self.options.with_openvdb:
            open_image_io.requires.append("openvdb::openvdb")
        if self.options.with_ptex:
            open_image_io.requires.append("ptex::ptex")
        if self.options.with_libwebp:
            open_image_io.requires.append("libwebp::libwebp")
        if self.options.with_libultrahdr:
            open_image_io.requires.append("libultrahdr::libultrahdr")
        if self.options.with_libjxl:
            open_image_io.requires.extend(["libjxl::libjxl", "libjxl::jxl_threads"])
        if self.settings.os in ["Linux", "FreeBSD"]:
            open_image_io.system_libs.extend(["dl", "m", "pthread"])
        if not self.options.shared:
            open_image_io.defines.append("OIIO_STATIC_DEFINE")

    def _add_component(self, name: str):
        component = self.info.components[_recipe_comp(name)]
        component.set_property("cmake_target_name", f"OpenImageIO::{name}")
        return component

def _recipe_comp(name: str):
    return f"openimageio_{name.lower()}"
