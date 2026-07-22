import glob
import os
from pathlib import Path
import platform
import textwrap
from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import cross_building, default_cppstd
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import Environment, VirtualBuildEnv, VirtualRunEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, replace_in_file, apply_patches, save, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.microsoft import msvc_runtime_flag, is_msvc
from thirdparty.scm import Version, WebReleaseIndex

# X.Org libraries the XCB platform plugin needs. Depend on the individual libx* recipes directly
# rather than a meta package, so each library's own pkg-config .pc (with correct Libs) is used.
_X11_RECIPE_REQUIRES = [
    "libx11", "libxau", "libxcb", "libxdmcp", "libxext", "libxfixes",
    "libxrandr", "libxrender", "libxv", "libice", "libsm", "libxt",
]
_X11_COMPONENT_REQUIRES = [
    "libx11::x11", "libx11::x11-xcb", "libxau::libxau", "libxcb::xcb",
    "libxcb::shape", "libxcb::shm", "libxcb::xfixes", "libxdmcp::libxdmcp",
    "libxext::libxext", "libxfixes::libxfixes", "libxrandr::libxrandr",
    "libxrender::libxrender", "libxv::libxv", "libice::libice",
    "libsm::libsm", "libxt::libxt",
]

SUBMODULES = [
    "qt3d",
    "qt5compat",
    "qtactiveqt",
    "qtcanvaspainter",
    "qtcharts",
    "qtcoap",
    "qtconnectivity",
    "qtdatavis3d",
    "qtdeclarative",
    "qtdoc",
    "qtgraphs",
    "qtgrpc",
    "qthttpserver",
    "qtimageformats",
    "qtlanguageserver",
    "qtlocation",
    "qtlottie",
    "qtmqtt",
    "qtmultimedia",
    "qtnetworkauth",
    "qtopcua",
    "qtopenapi",
    "qtpositioning",
    "qtquick3d",
    "qtquick3dphysics",
    "qtquickcontrols2",
    "qtquickeffectmaker",
    "qtquicktimeline",
    "qtremoteobjects",
    "qtscxml",
    "qtsensors",
    "qtserialbus",
    "qtserialport",
    "qtshadertools",
    "qtspeech",
    "qtsvg",
    "qttasktree",
    "qttools",
    "qttranslations",
    "qtvirtualkeyboard",
    "qtwayland",
    "qtwebchannel",
    "qtwebengine",
    "qtwebsockets",
    "qtwebview",
]


_MODULE_DEPENDS: dict[str, list[str]] = {
    "qt3d": ["qtbase"],
    "qt5compat": ["qtbase", "qtdeclarative"],
    "qtactiveqt": ["qtbase"],
    "qtcanvaspainter": ["qtbase", "qtdeclarative", "qtshadertools"],
    "qtcharts": ["qtbase"],
    "qtcoap": ["qtbase"],
    "qtconnectivity": ["qtbase"],
    "qtdatavis3d": ["qtbase"],
    "qtdeclarative": ["qtbase"],
    "qtdoc": ["qtdeclarative", "qttools"],
    "qtgraphs": ["qtbase", "qtdeclarative", "qtquick3d"],
    "qtgrpc": ["qtbase"],
    "qthttpserver": ["qtbase", "qtwebsockets"],
    "qtimageformats": ["qtbase"],
    "qtlanguageserver": ["qtbase"],
    "qtlocation": ["qtbase", "qtpositioning"],
    "qtlottie": ["qtbase", "qtdeclarative"],
    "qtmqtt": ["qtbase", "qtdeclarative"],
    "qtmultimedia": ["qtbase", "qtshadertools"],
    "qtnetworkauth": ["qtbase"],
    "qtopcua": ["qtbase", "qtdeclarative"],
    "qtopenapi": ["qtbase"],
    "qtpositioning": ["qtbase"],
    "qtquick3d": ["qtbase", "qtdeclarative", "qtshadertools"],
    "qtquick3dphysics": ["qtbase", "qtdeclarative", "qtquick3d", "qtshadertools"],
    "qtquickeffectmaker": ["qtbase", "qtdeclarative", "qtshadertools"],
    "qtquicktimeline": ["qtbase", "qtdeclarative"],
    "qtremoteobjects": ["qtbase"],
    "qtscxml": ["qtbase", "qtdeclarative"],
    "qtsensors": ["qtbase"],
    "qtserialbus": ["qtbase"],
    "qtserialport": ["qtbase"],
    "qtshadertools": ["qtbase"],
    "qtspeech": ["qtbase", "qtmultimedia"],
    "qtsvg": ["qtbase"],
    "qttasktree": ["qtbase"],
    "qttools": ["qtbase"],
    "qttranslations": ["qttools"],
    "qtvirtualkeyboard": ["qtbase", "qtdeclarative", "qtsvg"],
    "qtwayland": ["qtbase"],
    "qtwebchannel": ["qtbase"],
    "qtwebengine": ["qtdeclarative"],
    "qtwebsockets": ["qtbase"],
    "qtwebview": ["qtdeclarative"],
}


class _Options(RecipeOptions):
    with_brotli: bool = True
    with_dbus: bool = False
    with_doubleconversion: bool = True
    with_egl: bool = False
    with_fontconfig: bool = True
    with_freetype: bool = True
    with_glib: bool = False
    with_gssapi: bool = True
    with_gstreamer: bool = True
    with_harfbuzz: bool = True
    with_icu: bool = True
    with_libalsa: bool = True
    with_libjpeg: bool = True
    with_libpng: bool = True
    with_md4c: bool = True
    with_mysql: bool = False
    with_odbc: bool = False
    with_openal: bool = True
    with_opengl: Literal["no", "desktop", "dynamic"] = "no"
    with_openssl: bool = True
    with_pcre2: bool = True
    with_pq: bool = False
    with_pulseaudio: bool = True
    with_sqlite: bool = True
    with_tiff: bool = True
    with_vulkan: bool = True
    with_webp: bool = True
    with_x11: bool = True
    with_zstd: bool = True

    gui: bool = True
    widgets: bool = True
    device: str | None = None
    cross_compile: str | None = None
    sysroot: str | None = None
    disabled_features: str | None = ""

    qt3d: bool = False
    qt5compat: bool = False
    qtactiveqt: bool = False
    qtcanvaspainter: bool = False # but i want it
    qtcharts: bool = False
    qtcoap: bool = False
    qtconnectivity: bool = False
    qtdatavis3d: bool = False
    qtdeclarative: bool = False
    qtdoc: bool = False
    qtgraphs: bool = False
    qtgrpc: bool = True
    qthttpserver: bool = True
    qtimageformats: bool = True
    qtlanguageserver: bool = False
    qtlocation: bool = False
    qtlottie: bool = False
    qtmqtt: bool = False
    qtmultimedia: bool = False
    qtnetworkauth: bool = False
    qtopcua: bool = False
    qtopenapi: bool = False
    qtpositioning: bool = False
    qtquick3d: bool = False
    qtquick3dphysics: bool = False
    qtquickcontrols2: bool = False
    qtquickeffectmaker: bool = False
    qtquicktimeline: bool = False
    qtremoteobjects: bool = False
    qtscxml: bool = False
    qtsensors: bool = False
    qtserialbus: bool = False
    qtserialport: bool = False
    qtshadertools: bool = True
    qtspeech: bool = False
    qtsvg: bool = True
    qttasktree: bool = False
    qttools: bool = True
    qttranslations: bool = True
    qtvirtualkeyboard: bool = False
    qtwayland: bool = True
    qtwebchannel: bool = False
    qtwebengine: bool = False
    qtwebsockets: bool = True
    qtwebview: bool = False


class Recipe(RecipeBase[_Options]):
    name = "qt"
    version = "6.11.1"
    license = "LGPL-3.0-only"

    def latest_version(self):
        root = "https://download.qt.io/official_releases/qt/"
        series = WebReleaseIndex(self, root).latest_release(r'href="([\d.]+)/"')
        release = WebReleaseIndex(self, f"{root}{series}/")
        return Version(release.latest_release(r'href="([\d.]+)/"'))

    def configure(self):
        if self.settings.os in ("Linux", "FreeBSD"):
            # Qt requires a GNU-extensions C++ mode to enable __int128: strict -std=c++NN defines
            # __STRICT_ANSI__, which makes qtbase/src/corelib/global/qtypes.cpp #error out on GCC.
            std = str(self.settings.compiler_cxx_standard or "17").replace("gnu", "")
            self.settings.compiler_cxx_standard = f"gnu{std}"
        if self.settings.os not in ["Linux", "FreeBSD"]:
            self.options.with_icu = False
            self.options.with_fontconfig = False
            self.options.with_glib = False
            self.options.with_libalsa = False
            self.options.with_x11 = False
            self.options.with_egl = False

        if self.settings.os == "Windows":
            self.options.with_gssapi = False
        if self.settings.os != "Linux":
            self.options.qtwayland = False

        for submodule in SUBMODULES:
            if submodule not in _MODULE_DEPENDS:
                self.output.debug(f"Qt6: Removing {submodule} option as it is not in the module tree for this version")
                setattr(self.options, submodule, False)

        if not self.options.gui:
            self.options.with_opengl = "no"
            self.options.with_vulkan = False
            self.options.with_freetype = False
            self.options.with_fontconfig = False
            self.options.with_harfbuzz = False
            self.options.with_libjpeg = False
            self.options.with_libpng = False
            self.options.with_md4c = False
            self.options.with_x11 = False
            self.options.with_egl = False

        requested_modules = set([module for module in SUBMODULES if self.options.get_safe(module)])

        self.output.debug(f"qt6: requested modules {list(requested_modules)}")

        required_modules: dict[str, list[str]] = {}
        for module in requested_modules:
            deps = _MODULE_DEPENDS[module]
            for dep in deps:
                required_modules.setdefault(dep, []).append(module)

        required_but_disabled = [m for m in required_modules.keys() if self.options.get_safe(m) == False]
        if required_modules:
            self.output.debug(f"qt6: required_modules modules {list(required_modules.keys())}")
        if required_but_disabled:
            required_by: set[str] = set()
            for m in required_but_disabled:
                required_by.update(required_modules[m])
            raise RecipeInvalidConfiguration(
                f"Modules {required_but_disabled} are explicitly disabled, "
                f"but are required by {list(required_by)}, enabled by other options")

        enabled_modules = requested_modules.union(set(required_modules.keys()))
        enabled_modules.discard("qtbase")

        for module in list(enabled_modules):
            setattr(self.options, module, True)

        for module in SUBMODULES:
            if module in self.options and not self.options.get_safe(module):
                setattr(self.options, module, False)

        if not self.options.qtmultimedia:
            self.options.with_libalsa = False
            self.options.with_openal = False
            self.options.with_gstreamer = False
            self.options.with_pulseaudio = False

        if self.settings.os in ("FreeBSD", "Linux"):
            if self.options.qtwebengine:
                self.options.with_fontconfig = True

        for option in self.options.items():
            self.output.debug(f"qt6 option: {option}")

    def requirements(self):
        self.requires("zlib")
        if self.options.with_openssl:
            self.requires("openssl")
        if self.options.with_pcre2:
            self.requires("pcre2")
        if self.options.with_vulkan:
            self.requires("vulkan-loader")
            self.requires("vulkan-headers")
            if is_apple_os(self):
                self.requires("moltenvk")
        if self.options.with_glib:
            self.requires("glib")
        if self.options.with_doubleconversion:
            self.requires("double-conversion")
        if self.options.with_freetype:
            self.requires("freetype")
        if self.options.with_fontconfig:
            self.requires("fontconfig")
        if self.options.with_icu:
            self.requires("icu")
        if self.options.with_harfbuzz:
            self.requires("harfbuzz")
        if self.options.with_libjpeg:
            self.requires("libjpeg-turbo")
        if self.options.with_libpng:
            self.requires("libpng")
        if self.options.qtimageformats and self.options.with_tiff:
            self.requires("libtiff")
        if self.options.qtimageformats and self.options.with_webp:
            self.requires("libwebp")
        if self.options.with_sqlite:
            self.requires("sqlite")
        if self.options.with_mysql:
            self.requires("libmysqlclient")
        if self.options.with_pq:
            self.requires("libpq")
        if self.options.with_odbc:
            if self.settings.os != "Windows":
                self.requires("odbc")
        if self.options.with_openal:
            self.requires("openal-soft")
        if self.options.with_libalsa:
            self.requires("libalsa")
        if self.options.with_x11 or self.options.qtwayland:
            self.requires("xkbcommon")
        if self.options.with_x11:
            for _x11_recipe in _X11_RECIPE_REQUIRES:
                self.requires(_x11_recipe)
        if self.options.with_egl:
            self.requires("egl")
        if self.settings.os != "Windows" and self.options.with_opengl != "no":
            self.requires("opengl")
        if self.options.with_zstd:
            self.requires("zstd")
        if self.options.qtwayland:
            self.requires("wayland")
        if self.options.with_brotli:
            self.requires("brotli")
        if self.options.qtwebengine and self.settings.os == "Linux":
            self.requires("libexpat")
            self.requires("opus")
            self.requires("xorg-proto")
            self.requires("libxshmfence")
            self.requires("nss")
            self.requires("libdrm")
        if self.options.with_gstreamer:
            self.requires("gstreamer")
            self.requires("gst-plugins-base")
        if self.options.with_pulseaudio:
            self.requires("pulseaudio")
        if self.options.with_dbus:
            self.requires("dbus")
        if self.settings.os in ["Linux", "FreeBSD"] and self.options.with_gssapi:
            self.requires("krb5")
        if self.options.with_md4c:
            self.requires("md4c")  # stable API since 0.3x as per md4c wiki
        self.requires_tool("cmake")
        self.requires_tool("ninja")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

        if self.options.qtwebengine:
            self.requires_tool("nodejs")
            self.requires_tool("gperf")
            # gperf, bison, flex, python >= 2.7.5 & < 3
            if self.settings_build.os == "Windows":
                self.requires_tool("winflexbison")
            else:
                self.requires_tool("bison")
                self.requires_tool("flex")

        if self.options.qtwayland:
            self.requires_tool("wayland")
        if cross_building(self):
            self.requires_tool("qt")

    def source(self):
        ver = Version(self.version)
        destination = self.folders.source
        if platform.system() == "Windows":
            # Don't use os.path.join, or it removes the \\?\ prefix, which enables long paths
            destination = Path(rf"\\?\{self.folders.source}")
        get(
            self,
            url=f"https://download.qt.io/official_releases/qt/{ver.major}.{ver.minor}/{self.version}/single/qt-everywhere-src-{self.version}.tar.xz",
            sha256="252acef8c5ae68074d91cadba2ee4a83465051bbb970dd26e8f0daa0f3904e03",
            strip_root=True,
            destination=destination,
            excludes=self._excluded_module_patterns())

        apply_patches(self)
        if self.options.qtwebengine:
            for f in ["renderer", os.path.join("renderer", "core"), os.path.join("renderer", "platform")]:
                replace_in_file(
                    self, self.folders.source / "qtwebengine" / "src" / "3rdparty" / "chromium" / "third_party" / "blink" / f / "BUILD.gn",
                    "  if (enable_precompiled_headers) {\n    if (is_win) {",
                    "  if (enable_precompiled_headers) {\n    if (false) {"
                    )

        for f in ["FindPostgreSQL.cmake"]:
            file = self.folders.source / "qtbase" / "cmake" / f
            if os.path.isfile(file):
                os.remove(file)

        # qt_internal_disable_find_package_global_promotion calls set_target_properties, which
        # CMake forbids on ALIAS targets. zstd ships alias targets (e.g. zstd::libzstd ->
        # zstd::libzstd_static), so guard with ALIASED_TARGET before setting properties.
        replace_in_file(
            self,
            self.folders.source / "qtbase" / "cmake" / "QtPublicFindPackageHelpers.cmake",
            textwrap.dedent(
                """\
                function(qt_internal_disable_find_package_global_promotion target)
                    set_target_properties("${target}" PROPERTIES _qt_no_promote_global TRUE)
                endfunction()"""),
            textwrap.dedent(
                """\
                function(qt_internal_disable_find_package_global_promotion target)
                    get_target_property(_aliased_target "${target}" ALIASED_TARGET)
                    if(_aliased_target)
                        return()
                    endif()
                    set_target_properties("${target}" PROPERTIES _qt_no_promote_global TRUE)
                endfunction()"""))

        # workaround QTBUG-94356
        replace_in_file(self, self.folders.source / "qtbase" / "cmake" / "FindWrapSystemZLIB.cmake", '"-lz"', "ZLIB::ZLIB")
        replace_in_file(
            self, self.folders.source / "qtbase" / "configure.cmake",
            "set_property(TARGET ZLIB::ZLIB PROPERTY IMPORTED_GLOBAL TRUE)",
            "")

        replace_in_file(
            self,
            self.folders.source / "qtbase" / "cmake" / "QtAutoDetectHelpers.cmake",
            "qt_auto_detect_vcpkg()",
            "# qt_auto_detect_vcpkg()")

        # Handle locating moltenvk headers when vulkan is enabled on macOS
        replace_in_file(
            self, self.folders.source / "qtbase" / "cmake" / "FindWrapVulkanHeaders.cmake",
            "if(APPLE)", "if(APPLE)\n"
                         " find_package(moltenvk REQUIRED QUIET)\n"
                         " target_include_directories(WrapVulkanHeaders::WrapVulkanHeaders INTERFACE ${moltenvk_INCLUDE_DIR})"
            )

        # qt appends /W3 to _qt_compiler_warning_flags_on and applies it through a genex fed to
        # add_compile_options; the toolchain's warning filter preserves genexes intact, so the
        # /W3 survives and conflicts with the quiet -w -> "D9025: overriding '/w' with '/W3'" for
        # every one of qt's ~thousand+ source files. Drop the /W3 (keeping /wd5105) so -w wins.
        replace_in_file(
            self,
            self.folders.source / "qtbase" / "cmake" / "QtCompilerFlags.cmake",
            "list(APPEND _qt_compiler_warning_flags_on /W3)",
            "list(APPEND _qt_compiler_warning_flags_on)",
            strict=False)

    def generate(self):
        ms = VirtualBuildEnv(self)
        ms.generate()

        deps = CMakeDeps(self)
        deps.set_property("libdrm", "cmake_file_name", "Libdrm")
        deps.set_property("libdrm::libdrm_libdrm", "cmake_target_name", "Libdrm::Libdrm")
        deps.set_property("wayland", "cmake_file_name", "Wayland")
        deps.set_property("wayland::wayland-client", "cmake_target_name", "Wayland::Client")
        deps.set_property("wayland::wayland-server", "cmake_target_name", "Wayland::Server")
        deps.set_property("wayland::wayland-cursor", "cmake_target_name", "Wayland::Cursor")
        deps.set_property("wayland::wayland-egl", "cmake_target_name", "Wayland::Egl")

        # CMakeDeps generates EGL-config.cmake and sets EGL_DIR in recipe_cmakedeps_paths.cmake,
        # so find_package(EGL) prefers the Recipe-installed config over Qt's bundled FindEGL.cmake.
        deps.set_property("egl", "cmake_file_name", "EGL")
        deps.set_property("egl", "cmake_find_mode", "config")
        deps.set_property("egl::egl", "cmake_target_name", "EGL::EGL")

        # Don't generate any file for gstreamer - let Qt's own FindGStreamer.cmake handle
        # detection via CMAKE_PREFIX_PATH (same intent as the previous gstreamer_recipe hack).
        deps.set_property("gstreamer", "cmake_find_mode", "none")

        if self.options.with_libjpeg:
            # Present libjpeg-turbo as libjpeg so Qt's find_package(JPEG) resolves
            deps.set_property("libjpeg-turbo", "cmake_file_name", "JPEG")
            deps.set_property("libjpeg-turbo", "cmake_target_name", "JPEG::JPEG")

        if cross_building(self):
            # When cross-building, the host Qt is provided via QT_HOST_PATH with its full,
            # real CMake package (including internal components such as Qt6BuildInternals).
            # Don't let CMakeDeps emit a competing Qt6Config for the host qt tool_require:
            # it lacks those components and would shadow the real config, making Qt's own
            # submodule find_package(Qt6 ... COMPONENTS BuildInternals) fail. qt is a build
            # context dependency, so build_context=True is required for the property to apply.
            deps.set_property("qt", "cmake_find_mode", "none", build_context=True)

        deps.generate()

        for f in glob.glob("*.cmake"):
            replace_in_file(
                self,
                Path(f),
                " IMPORTED)\n",
                " IMPORTED GLOBAL)\n", strict=False)

        deps = PkgConfigDeps(self)
        deps.generate()

        vbe = VirtualBuildEnv(self)
        vbe.generate()
        vre: VirtualRunEnv | None = None
        if not cross_building(self):
            vre = VirtualRunEnv(self)
            vre.generate(scope="build")
        env = Environment()
        # Tell Python to assume UTF-8 encoding to work around character encoding issues while building Qt WebEngine on Polish locale on Windows.
        env.define("PYTHONUTF8", "1")
        # TODO: to remove when properly handled by recipe (see upstream issue 11962)
        env.unset("VCPKG_ROOT")
        env.prepend_path("PKG_CONFIG_PATH", self.folders.generators)
        env.vars(self).save_script("buildenvenv_pkg_config_path")
        if self.settings_build.os == "Mac":
            # On macOS, SIP resets DYLD_LIBRARY_PATH injected by VirtualBuildEnv & VirtualRunEnv
            dyld_library_path = "$DYLD_LIBRARY_PATH"
            dyld_library_path_build = vbe.vars().get("DYLD_LIBRARY_PATH")
            if dyld_library_path_build:
                dyld_library_path = f"{dyld_library_path_build}:{dyld_library_path}"
            if not cross_building(self) and vre is not None:
                dyld_library_path_host = vre.vars().get("DYLD_LIBRARY_PATH")
                if dyld_library_path_host:
                    dyld_library_path = f"{dyld_library_path_host}:{dyld_library_path}"
            save(self, "bash_env", f'export DYLD_LIBRARY_PATH="{dyld_library_path}"')
            env.define_path("BASH_ENV", os.path.abspath("bash_env"))

        tc = CMakeToolchain(self, generator="Ninja")

        tc.absolute_paths = True
        # A cross linker does not consult the target's LD_LIBRARY_PATH when it resolves
        # DT_NEEDED entries of imported shared libraries. Give it link-time-only search
        # paths for those transitive dependencies (for example, libgssapi_krb5.so needs
        # the other Kerberos shared libraries from the same package).
        if cross_building(self) and self.settings.os == "Linux":
            tc.add_rpath_link = True

        tc.variables["QT_BUILD_TESTS"] = "OFF"
        tc.variables["QT_BUILD_EXAMPLES"] = "OFF"
        # Qt is distributed dynamically. Static Qt is intentionally unsupported.
        tc.variables["BUILD_SHARED_LIBS"] = True
        tc.variables["FEATURE_shared"] = "ON"
        tc.variables["FEATURE_static"] = "OFF"

        if is_msvc(self) and "MT" in msvc_runtime_flag(self):
            tc.variables["FEATURE_static_runtime"] = "ON"

        tc.variables["FEATURE_optimize_size"] = ("ON" if self.settings.build_type == "MinSizeRel" else "OFF")

        for module in _MODULE_DEPENDS:
            tc.variables[f"BUILD_{module}"] = ("ON" if self.options.get_safe(module) else "OFF")
        tc.variables["BUILD_qtqa"] = "OFF"
        tc.variables["BUILD_qtrepotools"] = "OFF"

        tc.variables["FEATURE_system_zlib"] = "ON"

        tc.variables["INPUT_opengl"] = self.options.with_opengl

        # openSSL
        if not self.options.with_openssl:
            tc.variables["INPUT_openssl"] = "no"
        else:
            tc.variables["HAVE_openssl"] = "ON"
            if self.dependencies["openssl"].options.shared:
                tc.variables["INPUT_openssl"] = "runtime"
                tc.variables["QT_FEATURE_openssl_runtime"] = "ON"
            else:
                tc.variables["INPUT_openssl"] = "linked"
                tc.variables["QT_FEATURE_openssl_linked"] = "ON"

        # TODO: Remove after fixing upstream issue 12012
        # Required for qt_config_compile_test() calls against CMakeDeps targets to work correctly.
        tc.cache_variables["CMAKE_TRY_COMPILE_CONFIGURATION"] = str(self.settings.build_type)

        if self.options.with_dbus:
            tc.variables["INPUT_dbus"] = "linked"
        else:
            tc.variables["FEATURE_dbus"] = "OFF"
        tc.variables["CMAKE_FIND_DEBUG_MODE"] = "FALSE"

        if not self.options.with_zstd:
            tc.variables["CMAKE_DISABLE_FIND_PACKAGE_WrapZSTD"] = "ON"

        if not self.options.with_vulkan:
            tc.variables["CMAKE_DISABLE_FIND_PACKAGE_WrapVulkanHeaders"] = "ON"

        # Prevent finding LibClang from the system
        # this is needed by the QDoc tool inside Qt Tools
        # See: https://github.com/recipe-io/recipe-center-index/issues/24729#issuecomment-2255291495
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_WrapLibClang"] = "ON"

        for opt, conf_arg in [
            ("with_glib", "glib"),
            ("with_icu", "icu"),
            ("with_fontconfig", "fontconfig"),
            ("with_mysql", "sql_mysql"),
            ("with_pq", "sql_psql"),
            ("with_odbc", "sql_odbc"),
            ("gui", "gui"),
            ("widgets", "widgets"),
            ("with_zstd", "zstd"),
            ("with_vulkan", "vulkan"),
            ("with_brotli", "brotli"),
            ("with_gssapi", "gssapi"),
            ("with_egl", "egl"),
            ("with_gstreamer", "gstreamer"),
        ]:
            tc.variables[f"FEATURE_{conf_arg}"] = ("ON" if getattr(self.options, opt, False) else "OFF")

        for opt, conf_arg in [
            ("with_doubleconversion", "doubleconversion"),
            ("with_freetype", "freetype"),
            ("with_harfbuzz", "harfbuzz"),
            ("with_libjpeg", "jpeg"),
            ("with_libpng", "png"),
            ("with_sqlite", "sqlite"),
            ("with_pcre2", "pcre2"),
        ]:
            if getattr(self.options, opt, False):
                tc.variables[f"FEATURE_system_{conf_arg}"] = "ON"
            else:
                tc.variables[f"FEATURE_{conf_arg}"] = "OFF"
                tc.variables[f"FEATURE_system_{conf_arg}"] = "OFF"

        for opt, conf_arg in [
            ("with_doubleconversion", "doubleconversion"),
            ("with_freetype", "freetype"),
            ("with_harfbuzz", "harfbuzz"),
            ("with_libjpeg", "libjpeg"),
            ("with_libpng", "libpng"),
            ("with_md4c", "libmd4c"),
            ("with_pcre2", "pcre"),
        ]:
            if getattr(self.options, opt, False):
                tc.variables[f"INPUT_{conf_arg}"] = "system"
            else:
                tc.variables[f"INPUT_{conf_arg}"] = "no"

        for feature in str(self.options.disabled_features).split():
            tc.variables[f"FEATURE_{feature}"] = "OFF"

        tc.variables["INPUT_tiff"] = "system" if self.options.with_tiff else "no"
        tc.variables["INPUT_webp"] = "system" if self.options.with_webp else "no"
        tc.variables["INPUT_jasper"] = "no"

        # The androiddeployqt/androidtestrunner host tools are gated by
        # "CONDITION NOT CMAKE_CROSSCOMPILING", so a native build enables them while a cross
        # build (e.g. windows-arm, mac-x64 from a mac-arm host) disables them. That makes the
        # host CoreTools export set (13 tools) disagree with the cross-build's expected set (11
        # tools), and importing the host tools then fails Qt's export consistency check. O3DE
        # doesn't use androiddeployqt/androidtestrunner at all, so disable them unconditionally
        # (both the host tool build and the cross-target build get this same setting) to keep
        # the host and target tool sets identical everywhere, regardless of host OS.
        tc.variables["FEATURE_androiddeployqt"] = "OFF"
        # qmlcontextpropertydump is another host tool that a native build produces but a
        # cross build does not, causing the same Qt export-set consistency failure when the
        # cross build imports the host QmlTools package. Its CMake feature also guards the
        # generator expression that references the tool, so disable via the feature (not by
        # removing the tool subdirectory) to keep both consistent.
        tc.variables["FEATURE_qmlcontextpropertydump"] = "OFF"

        if self.settings.os == "Mac":
            tc.variables["FEATURE_framework"] = "OFF"
        elif self.settings.os == "Android":
            tc.variables["CMAKE_ANDROID_NATIVE_API_LEVEL"] = self.settings.os_api_level
            tc.variables["ANDROID_ABI"] = {
                "ARM": "arm64-v8a",
                "X64": "x86_64",
            }.get(str(self.settings.arch))

        if self.options.sysroot:
            tc.variables["CMAKE_SYSROOT"] = self.options.sysroot

        if self.options.device:
            tc.variables["QT_QMAKE_TARGET_MKSPEC"] = f"devices/{self.options.device}"
        else:
            xplatform_val = self._xplatform()
            if xplatform_val:
                tc.variables["QT_QMAKE_TARGET_MKSPEC"] = xplatform_val
            else:
                self.output.warning(f"host not supported: {self.settings.os} {self.settings.compiler} {self.settings.compiler_version} {self.settings.arch}")
        if self.options.cross_compile:
            tc.variables["QT_QMAKE_DEVICE_OPTIONS"] = f"CROSS_COMPILE={self.options.cross_compile}"
        if cross_building(self):
            # Mainly to locate Qt6HostInfoConfig.cmake
            tc.cache_variables["QT_HOST_PATH"] = self.dependencies.direct_build["qt"].folders.package.as_posix()
            # Stand-in for Qt6CoreTools - which is loaded for the executable targets
            tc.cache_variables["CMAKE_PROJECT_Qt_INCLUDE"] = (self.dependencies.direct_build["qt"].folders.package / self._cmake_executables_file).as_posix()
            # Ensure tools for host are always built
            tc.cache_variables["QT_FORCE_BUILD_TOOLS"] = True

        tc.variables["FEATURE_pkg_config"] = "ON"
        current_cpp_std = (self.settings.compiler_cxx_standard or default_cppstd(self))
        current_cpp_std = str(current_cpp_std).replace("gnu", "")
        cpp_std_map = {
            11: "FEATURE_cxx11",
            14: "FEATURE_cxx14",
            17: "FEATURE_cxx17",
            20: "FEATURE_cxx20",
            23: "FEATURE_cxx2b",
        }

        for std, feature in cpp_std_map.items():
            tc.variables[feature] = "ON" if int(current_cpp_std) >= std else "OFF"

        tc.cache_variables["QT_USE_VCPKG"] = False

        with_wayland = self.options.qtwayland
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_Wayland"] = not with_wayland
        tc.variables["FEATURE_wayland"] = with_wayland

        with_egl = self.options.with_egl
        tc.variables["CMAKE_DISABLE_FIND_PACKAGE_EGL"] = not with_egl

        tc.generate()

    def build(self):
        if self.settings.os == "Mac":
            save(self, ".qmake.stash", "")
            save(self, ".qmake.super", "")
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        if self.settings.os == "Mac":
            save(self, ".qmake.stash", "")
            save(self, ".qmake.super", "")
        cmake = CMake(self)
        cmake.install()
        copy(
            self,
            "*LICENSE*",
            self.folders.source,
            self.folders.package / "licenses",
            excludes="qtbase/examples/*")
        for module in _MODULE_DEPENDS:
            if not self.options.get_safe(module):
                rmdir(self, self.folders.package / "licenses" / module)
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        for mask in ["Find*.cmake", "*Config.cmake", "*-config.cmake"]:
            rm(self, mask, self.folders.package, recursive=True, excludes=["Qt6*Config.cmake", "FindWrap*.cmake"])
        rm(self, "*.la*", self.folders.package / "lib", recursive=True)
        rm(self, "*.pdb*", self.folders.package, recursive=True)
        rm(self, "ensure_pro_file.cmake", self.folders.package, recursive=True)
        os.remove(self.folders.package / ("libexec" if self.settings.os != "Windows" else "bin") / "qt-cmake-private-install.cmake")

        for m in os.listdir(self.folders.package / "lib" / "cmake"):
            if os.path.isfile(self.folders.package / "lib" / "cmake" / m / f"{m}Macros.cmake"):
                continue
            if (self.folders.package / "lib" / "cmake" / m).glob("QtPublic*Helpers.cmake"):
                continue
            if (self.folders.package / "lib" / "cmake" / m).glob("Qt6QmlPublic*Helpers.cmake"):
                continue
            if m.endswith("Tools"):
                if os.path.isfile(self.folders.package / "lib" / "cmake" / m / f"{m[:-5]}Macros.cmake"):
                    continue
            if m.endswith("Private"):
                continue
            if (self.folders.package / "lib" / "cmake" / m).glob("Qt6*Config.cmake"):
                continue
            if m != "Qt6HostInfo":
                rmdir(self, self.folders.package / "lib" / "cmake" / m)

        extension = ""
        if self.settings.os == "Windows":
            extension = ".exe"
        filecontents = "set(QT_CMAKE_EXPORT_NAMESPACE Qt6)\n"
        ver = Version(self.version)
        filecontents += f"set(QT_VERSION_MAJOR {ver.major})\n"
        filecontents += f"set(QT_VERSION_MINOR {ver.minor})\n"
        filecontents += f"set(QT_VERSION_PATCH {ver.patch})\n"
        if self.settings.os == "Mac":
            filecontents += 'set(__qt_internal_cmake_apple_support_files_path "${CMAKE_CURRENT_LIST_DIR}/../../../lib/cmake/Qt6/macos")\n'
        targets = ["moc", "qlalr", "rcc", "tracegen", "cmake_automoc_parser", "qmake", "qtpaths", "syncqt", "tracepointgen"]
        disabled_features = str(self.options.disabled_features).split()
        if self.options.with_dbus:
            targets.extend(["qdbuscpp2xml", "qdbusxml2cpp"])
        if self.options.gui:
            targets.append("qvkgen")
        if self.options.widgets:
            targets.append("uic")
        if self.settings_build.os == "Mac" and self.settings.os != "iOS":
            targets.extend(["macdeployqt"])
        if self.settings.os == "Windows":
            targets.extend(["windeployqt"])
        targets.extend(["wasmdeployqt"])
        if self.options.qttools:
            if "qtattributionsscanner" not in disabled_features:
                targets.extend(["qtattributionsscanner"])
            if (not any(item in disabled_features for item in ["assistant", "toolbutton", "pushbutton"])) and self.options.widgets and self.options.with_libpng:
                # https://github.com/qt/qttools/blob/d5f3f624717092dde55a93e1212c5b7c63d360b8/configure.cmake#L102-L108
                # and `qhelpgenerator` is a subdirectory of assistant in qttools
                targets.extend(["qhelpgenerator"])
            if "linguist" not in disabled_features:
                #targets.extend(["lconvert", "lprodump", "lrelease", "lrelease-pro", "lupdate", "lupdate-pro"])
                # qt 6.11's LinguistTools export set includes lcheck + ltext2id too; the imported-target
                # executables file must define ALL of them, else the cross build's host-tools precheck
                # (_qt_internal_check_multiple_inclusion) fails with "some but not all targets defined".
                targets.extend(["lconvert", "lrelease", "lrelease-pro", "lupdate", "lupdate-pro", "lcheck", "ltext2id"])
        if self.options.qtshadertools:
            targets.append("qsb")
        if self.options.qtdeclarative:
            targets.extend(["qmltyperegistrar", "qmlcachegen", "qmllint", "qmlimportscanner"])
            targets.extend(["qmlformat", "qml", "qmlprofiler", "qmlpreview", "qmltc"])
            targets.extend(["qmlaotstats"])

            # Note: consider "qmltestrunner", see https://github.com/recipe-io/recipe-center-index/issues/24276
        if self.options.qtremoteobjects:
            targets.append("repc")
        if self.options.qtscxml:
            targets.append("qscxmlc")
        for target in targets:
            exe_path = None
            for path_ in [
                f"bin/{target}{extension}",
                f"lib/{target}{extension}",
                f"libexec/{target}{extension}",
            ]:
                if os.path.isfile(self.folders.package / path_):
                    exe_path = path_
                    break
            else:
                assert False, f"Could not find executable {target}{extension} in {self.folders.package}"
            if not exe_path:
                self.output.warning(f"Could not find path to {target}{extension}")
            filecontents += textwrap.dedent(
                f"""
                if(NOT TARGET ${{QT_CMAKE_EXPORT_NAMESPACE}}::{target})
                    add_executable(${{QT_CMAKE_EXPORT_NAMESPACE}}::{target} IMPORTED)
                    set_target_properties(${{QT_CMAKE_EXPORT_NAMESPACE}}::{target} PROPERTIES IMPORTED_LOCATION ${{CMAKE_CURRENT_LIST_DIR}}/../../../{exe_path})
                endif()
                """)

        filecontents += textwrap.dedent(
            f"""
            if(NOT DEFINED QT_DEFAULT_MAJOR_VERSION)
                set(QT_DEFAULT_MAJOR_VERSION {ver.major})
            endif()
            """)
        filecontents += 'set(CMAKE_AUTOMOC_MACRO_NAMES "Q_OBJECT" "Q_GADGET" "Q_GADGET_EXPORT" "Q_NAMESPACE" "Q_NAMESPACE_EXPORT")\n'
        save(self, self.folders.package / self._cmake_executables_file, filecontents)

        def _create_private_module(module: str, dependencies: list[str]):
            dependencies_string = ";".join(f"Qt6::{dependency}" for dependency in dependencies)
            contents = textwrap.dedent(
                f"""
                if(NOT TARGET Qt6::{module}Private)
                    add_library(Qt6::{module}Private INTERFACE IMPORTED)

                    set_target_properties(Qt6::{module}Private PROPERTIES
                        INTERFACE_INCLUDE_DIRECTORIES "${{CMAKE_CURRENT_LIST_DIR}}/../../../include/Qt{module}/{self.version};${{CMAKE_CURRENT_LIST_DIR}}/../../../include/Qt{module}/{self.version}/Qt{module}"
                        INTERFACE_LINK_LIBRARIES "{dependencies_string}"
                    )

                    add_library(Qt::{module}Private INTERFACE IMPORTED)
                    set_target_properties(Qt::{module}Private PROPERTIES
                        INTERFACE_LINK_LIBRARIES "Qt6::{module}Private"
                        _qt_is_versionless_target "TRUE"
                    )
                endif()
                """)

            save(self, self.folders.package / self._cmake_qt6_private_file(module), contents)

        _create_private_module("Core", ["Core"])

        if self.options.gui:
            _create_private_module("Gui", ["CorePrivate", "Gui"])

        if self.options.widgets:
            _create_private_module("Widgets", ["CorePrivate", "GuiPrivate", "Widgets"])

        if self.options.qtdeclarative:
            _create_private_module("Qml", ["CorePrivate", "Qml"])
            save(
                self, self.folders.package / "lib" / "cmake" / "Qt6Qml" / "recipe_qt_qt6_policies.cmake", textwrap.dedent(
                    """
                    set(QT_KNOWN_POLICY_QTP0001 TRUE)
                    set(QT_KNOWN_POLICY_QTP0004 TRUE)
                    set(QT_KNOWN_POLICY_QTP0005 TRUE)
                    """))
            if self.options.gui and self.options.qtshadertools:
                _create_private_module("Quick", ["CorePrivate", "GuiPrivate", "QmlPrivate", "Quick"])

        if self.settings.os in ["Windows", "iOS"]:
            contents = textwrap.dedent(
                """
                set(entrypoint_conditions "$<NOT:$<BOOL:$<TARGET_PROPERTY:qt_no_entrypoint>>>")
                list(APPEND entrypoint_conditions "$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>")
                if(WIN32)
                    list(APPEND entrypoint_conditions "$<BOOL:$<TARGET_PROPERTY:WIN32_EXECUTABLE>>")
                endif()
                list(JOIN entrypoint_conditions "," entrypoint_conditions)
                set(entrypoint_conditions "$<AND:${entrypoint_conditions}>")
                # When this module is pulled in from the host Qt during a cross-build,
                # ::Core is imported as an ALIAS target, which set_property() rejects.
                get_target_property(_recipe_core_aliased ${QT_CMAKE_EXPORT_NAMESPACE}::Core ALIASED_TARGET)
                if(NOT _recipe_core_aliased)
                    set_property(
                        TARGET ${QT_CMAKE_EXPORT_NAMESPACE}::Core
                        APPEND PROPERTY INTERFACE_LINK_LIBRARIES "$<${entrypoint_conditions}:${QT_CMAKE_EXPORT_NAMESPACE}::EntryPointPrivate>"
                    )
                endif()""")
            save(self, self.folders.package / self._cmake_entry_point_file, contents)

        # https://github.com/qt/qtbase/blob/6.7.3/cmake/QtPlatformTargetHelpers.cmake#L68
        # https://github.com/qt/qtbase/blob/6.7.3/cmake/QtPlatformTargetHelpers.cmake#L71
        # https://github.com/qt/qtbase/blob/6.7.3/cmake/QtFlagHandlingHelpers.cmake#L384
        # https://github.com/qt/qtbase/blob/6.7.3/cmake/QtFlagHandlingHelpers.cmake#L402
        if self.settings.os == "Windows" or is_msvc(self):
            contents = textwrap.dedent(
                """
                set(utf8_flags "")
                if(MSVC)
                    list(APPEND utf8_flags "$<$<CXX_COMPILER_ID:MSVC>:-utf-8>")
                endif()

                # When this module is pulled in from the host Qt during a cross-build,
                # Qt6::Platform is imported as an ALIAS target, which target_compile_*()
                # reject. Skip re-applying the flags in that case.
                get_target_property(_recipe_platform_aliased Qt6::Platform ALIASED_TARGET)

                if(utf8_flags AND NOT _recipe_platform_aliased)
                    set(opt_out_condition "$<NOT:$<BOOL:$<TARGET_PROPERTY:QT_NO_UTF8_SOURCE>>>")
                    set(language_condition "$<COMPILE_LANGUAGE:C,CXX>")
                    set(genex_condition "$<AND:${opt_out_condition},${language_condition}>")
                    set(utf8_flags "$<${genex_condition}:${utf8_flags}>")
                    target_compile_options(Qt6::Platform INTERFACE "${utf8_flags}")
                endif()

                if(WIN32 AND NOT _recipe_platform_aliased)
                    set(no_unicode_condition
                        "$<NOT:$<BOOL:$<TARGET_PROPERTY:QT_NO_UNICODE_DEFINES>>>")
                    target_compile_definitions(Qt6::Platform
                        INTERFACE "$<${no_unicode_condition}:UNICODE$<SEMICOLON>_UNICODE>")
                endif()""")
            save(self, self.folders.package / self._cmake_platform_target_setup_file, contents)

    def package_info(self):
        disabled_features = str(self.options.disabled_features).split()

        self.info.set_property("cmake_file_name", "Qt6")
        self.info.set_property("pkg_config_name", "qt6")

        # consumers will need the QT_PLUGIN_PATH defined in runenv
        self.info.runenv.define("QT_PLUGIN_PATH", str(self.folders.package / "plugins"))
        self.info.buildenv.define("QT_PLUGIN_PATH", str(self.folders.package / "plugins"))

        self.info.buildenv.define("QT_HOST_PATH", str(self.folders.package))

        build_modules: dict[str, list[str | Path]] = {}

        def _add_build_module(component: str, module: str | Path):
            if component not in build_modules:
                build_modules[component] = []
            build_modules[component].append(module)

        libsuffix = ""
        if self.settings.build_type == "Debug":
            if is_msvc(self):
                libsuffix = "d"
            if is_apple_os(self):
                libsuffix = "_debug"

        def _get_corrected_reqs(requires: list[str]) -> list[str]:
            reqs: list[str] = []
            for r in requires:
                if "::" in r:
                    corrected_req = r
                else:
                    corrected_req = f"qt{r}"
                    assert corrected_req in self.info.components, f"{corrected_req} required but not yet present in self.info.components"
                reqs.append(corrected_req)
            return reqs

        def _create_module(module: str, requires: list[str], has_include_dir: bool = True):
            componentname = f"qt{module}"
            assert componentname not in self.info.components, f"Module {module} already present in self.info.components"
            self.info.components[componentname].set_property("cmake_target_name", f"Qt6::{module}")
            self.info.components[componentname].set_property("cmake_target_aliases", [f"Qt::{module}"])
            self.info.components[componentname].set_property("pkg_config_name", f"Qt6{module}")
            if module.endswith("Private"):
                libname = module[:-7]
            else:
                libname = module
            self.info.components[componentname].libs = [f"Qt6{libname}{libsuffix}"]
            if has_include_dir:
                self.info.components[componentname].includedirs = ["include", os.path.join("include", f"Qt{module}")]
            self.info.components[componentname].defines = [f"QT_{module.upper()}_LIB"]
            if module != "Core" and "Core" not in requires:
                requires.append("Core")
            self.info.components[componentname].requires = _get_corrected_reqs(requires)

        def _plugin_exists(libname: str, plugintype: str) -> bool:
            # Some plugins are only built when their backing library/feature is available (e.g. qjp2 needs jasper, qmng needs libmng)
            # or are  platform-specific (qmacjp2/qmacheif on Apple).
            # Only declare a plugin component when its artifact is actually present in the package.
            plugin_dir = os.path.join(str(self.folders.package), "plugins", plugintype)
            return bool(glob.glob(os.path.join(plugin_dir, f"{libname}*")))

        def _create_plugin(
            pluginname: str,
            libname: str,
            plugintype: str,
            requires: list[str]):
            if not _plugin_exists(libname, plugintype):
                return
            componentname = f"qt{pluginname}"
            assert componentname not in self.info.components, f"Plugin {pluginname} already present in self.info.components"
            self.info.components[componentname].set_property("cmake_target_name", f"Qt6::{pluginname}")
            self.info.components[componentname].set_property("cmake_target_aliases", [f"Qt::{pluginname}"])
            self.info.components[componentname].libdirs = [os.path.join("plugins", plugintype)]
            self.info.components[componentname].includedirs = []
            if "Core" not in requires:
                requires.append("Core")
            self.info.components[componentname].requires = _get_corrected_reqs(requires)

        # https://github.com/qt/qtbase/blob/v6.7.3/cmake/QtPlatformTargetHelpers.cmake
        self.info.components["qtPlatform"].set_property("cmake_target_name", "Qt6::Platform")
        self.info.components["qtPlatform"].set_property("cmake_target_aliases", ["Qt::Platform"])
        self.info.components["qtPlatform"].includedirs = [os.path.join("mkspecs", self._xplatform() or "")]
        if self.settings.os == "Android":
            self.info.components["qtPlatform"].system_libs.append("log")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["qtPlatform"].system_libs.append("pthread")
        if is_msvc(self):
            self.info.components["qtPlatform"].cxxflags.append("-permissive-")
            self.info.components["qtPlatform"].cxxflags.append("-Zc:__cplusplus")

        core_reqs = ["Platform", "zlib::zlib"]
        if self.options.with_pcre2:
            core_reqs.append("pcre2::pcre2")
        if self.options.with_doubleconversion:
            core_reqs.append("double-conversion::double-conversion")
        if self.options.with_icu:
            core_reqs.append("icu::icu")
        if self.options.with_zstd:
            core_reqs.append("zstd::zstd")
        if self.options.with_glib:
            core_reqs.append("glib::glib")
        if self.options.with_openssl:
            core_reqs.append("openssl::openssl")  # used by QCryptographicHash

        _create_module("Core", core_reqs)
        pkg_config_vars = [
            "bindir=${prefix}/bin",
            "libexecdir=${prefix}/libexec",
            "exec_prefix=${prefix}",
        ]
        self.info.components["qtCore"].set_property("pkg_config_custom_content", "\n".join(pkg_config_vars))

        if self.settings.build_type != "Debug":
            self.info.components["qtCore"].defines.append("QT_NO_DEBUG")
        if self.settings.os == "Windows":
            self.info.components["qtCore"].system_libs.append("authz")
        if is_msvc(self):
            self.info.components["qtCore"].system_libs.append("synchronization")
            self.info.components["qtCore"].system_libs.append("runtimeobject")
        if self.options.with_dbus:
            _create_module("DBus", ["dbus::dbus"])
            if self.settings.os == "Windows":
                # https://github.com/qt/qtbase/blob/v6.6.1/src/dbus/CMakeLists.txt#L71-L77
                self.info.components["qtDBus"].system_libs.append("advapi32")
                self.info.components["qtDBus"].system_libs.append("netapi32")
                self.info.components["qtDBus"].system_libs.append("user32")
                self.info.components["qtDBus"].system_libs.append("ws2_32")
        if self.options.gui:
            gui_reqs: list[str] = []
            if self.options.with_dbus:
                gui_reqs.append("DBus")
            if self.options.with_freetype:
                gui_reqs.append("freetype::freetype")
            if self.options.with_libpng:
                gui_reqs.append("libpng::libpng")
            if self.options.with_fontconfig:
                gui_reqs.append("fontconfig::fontconfig")
            if self.settings.os in ["Linux", "FreeBSD"]:
                if self.options.qtwayland or self.options.with_x11:
                    gui_reqs.append("xkbcommon::xkbcommon")
                if self.options.with_x11:
                    gui_reqs.extend(_X11_COMPONENT_REQUIRES)
                if self.options.with_egl:
                    gui_reqs.append("egl::egl")
            if self.settings.os != "Windows" and self.options.with_opengl != "no":
                gui_reqs.append("opengl::opengl")
            if self.options.with_vulkan:
                gui_reqs.append("vulkan-loader::vulkan-loader")
                gui_reqs.append("vulkan-headers::vulkan-headers")
                if is_apple_os(self):
                    gui_reqs.append("moltenvk::moltenvk")
            if self.options.with_harfbuzz:
                gui_reqs.append("harfbuzz::harfbuzz")
            if self.options.with_glib:
                gui_reqs.append("glib::glib")
            if self.options.with_md4c:
                gui_reqs.append("md4c::md4c")
            _create_module("Gui", gui_reqs)

            _add_build_module("qtGui", self._cmake_qt6_private_file("Gui"))

            if self.settings.os == "Windows":
                # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L419-L429
                self.info.components["qtGui"].system_libs += [
                    "advapi32", "gdi32", "ole32", "shell32", "user32", "d3d11", "dxgi", "dxguid",
                ]
                # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L729
                self.info.components["qtGui"].system_libs.append("d2d1")
                # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L732-L742
                self.info.components["qtGui"].system_libs.append("dwrite")
                if self.settings.compiler == "gcc":
                    # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L746
                    self.info.components["qtGui"].system_libs.append("uuid")

                # https://github.com/qt/qtbase/blob/v6.6.0/src/gui/CMakeLists.txt#L428
                self.info.components["qtGui"].system_libs.append("d3d12")
                # https://github.com/qt/qtbase/blob/v6.7.0-beta1/src/gui/CMakeLists.txt#L430
                self.info.components["qtGui"].system_libs.append("uxtheme")
                # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/direct2d/CMakeLists.txt#L60-L82
                self.info.components["qtGui"].system_libs += [
                    "advapi32", "d2d1", "d3d11", "dwmapi", "dwrite", "dxgi", "dxguid", "gdi32", "imm32", "ole32",
                    "oleaut32", "setupapi", "shell32", "shlwapi", "user32", "version", "winmm", "winspool",
                    "wtsapi32", "shcore", "comdlg32", "d3d9", "runtimeobject",
                ]
                _create_plugin("QWindowsIntegrationPlugin", "qwindows", "platforms", ["Core", "Gui"])
                # https://github.com/qt/qtbase/commit/65d58e6c41e3c549c89ea4f05a8e467466e79ca3
                _create_plugin("QModernWindowsStylePlugin", "qmodernwindowsstyle", "styles", ["Core", "Gui"])
                # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/windows/CMakeLists.txt#L53-L69
                self.info.components["qtQWindowsIntegrationPlugin"].system_libs += [
                    "advapi32", "dwmapi", "gdi32", "imm32", "ole32", "oleaut32", "setupapi", "shell32", "shlwapi",
                    "user32", "winmm", "winspool", "wtsapi32", "shcore", "comdlg32", "d3d9", "runtimeobject",
                ]
                # https://github.com/qt/qtbase/blob/6.8.3/src/plugins/platforms/windows/CMakeLists.txt#L204
                self.info.components["qtQWindowsIntegrationPlugin"].system_libs.append("uiautomationcore")
            elif self.settings.os == "Android":
                _create_plugin("QAndroidIntegrationPlugin", "qtforandroid", "platforms", ["Core", "Gui"])
                # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/android/CMakeLists.txt#L68-L70
                self.info.components["qtQAndroidIntegrationPlugin"].system_libs = ["android", "jnigraphics"]
            elif is_apple_os(self):
                # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L388-L394
                self.info.components["qtGui"].frameworks = ["CoreFoundation", "CoreGraphics", "CoreText", "Foundation", "ImageIO"]
                # https://github.com/qt/qtbase/blob/6.8.0/src/gui/configure.cmake#L834-L837
                has_metal = "metal" not in disabled_features and self.settings.os in ["Mac", "iOS", "visionOS"]
                if has_metal:
                    # https://github.com/qt/qtbase/blob/6.8.0/src/gui/CMakeLists.txt#L432-L437
                    self.info.components["qtGui"].frameworks.append("QuartzCore")
                if self.settings.os == "Mac":
                    # https://github.com/qt/qtbase/blob/v6.6.1/src/gui/CMakeLists.txt#L362-L370
                    self.info.components["qtGui"].frameworks += ["AppKit", "Carbon"]
                    _create_plugin("QCocoaIntegrationPlugin", "qcocoa", "platforms", ["Core", "Gui"])
                    # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/cocoa/CMakeLists.txt#L51-L58
                    self.info.components["QCocoaIntegrationPlugin"].frameworks = [
                        "AppKit", "Carbon", "CoreServices", "CoreVideo", "IOKit", "IOSurface", "Metal", "QuartzCore",
                    ]
                if self.settings.os in ["Mac", "iOS"]:
                    # https://github.com/qt/qtbase/blob/v6.5.3/src/gui/CMakeLists.txt#L963
                    self.info.components["qtGui"].frameworks.append("Metal")
                if self.settings.os in ["iOS", "tvOS"]:
                    _create_plugin("QIOSIntegrationPlugin", "qios", "platforms", [])
                    # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/ios/CMakeLists.txt#L32-L37
                    self.info.components["QIOSIntegrationPlugin"].frameworks = [
                        "AudioToolbox", "Foundation", "Metal", "QuartzCore", "UIKit", "CoreGraphics",
                    ]
                    if self.settings.os != "tvOS":
                        # https://github.com/qt/qtbase/blob/v6.6.1/src/plugins/platforms/ios/CMakeLists.txt#L66-L68
                        self.info.components["QIOSIntegrationPlugin"].frameworks += [
                            "AssetsLibrary", "UniformTypeIdentifiers", "Photos",
                        ]
                elif self.settings.os == "watchOS":
                    _create_plugin("QMinimalIntegrationPlugin", "qminimal", "platforms", [])
            elif self.settings.os == "Emscripten":
                _create_plugin("QWasmIntegrationPlugin", "qwasm", "platforms", ["Core", "Gui"])
            elif self.options.with_x11:
                _create_module("XcbQpaPrivate", ["xkbcommon::libxkbcommon-x11", *_X11_COMPONENT_REQUIRES], has_include_dir=False)
                _create_plugin("QXcbIntegrationPlugin", "qxcb", "platforms", ["Core", "Gui", "XcbQpaPrivate"])

            _create_plugin("QGifPlugin", "qgif", "imageformats", ["Gui"])
            _create_plugin("QIcoPlugin", "qico", "imageformats", ["Gui"])
            if self.options.with_libjpeg:
                jpeg_reqs = ["Gui", "libjpeg-turbo::jpeg"]
                _create_plugin("QJpegPlugin", "qjpeg", "imageformats", jpeg_reqs)

        if self.options.with_mysql:
            _create_plugin("QMYSQLDriverPlugin", "qsqlmysql", "sqldrivers", ["libmysqlclient::libmysqlclient"])
        if self.options.with_sqlite:
            _create_plugin("QSQLiteDriverPlugin", "qsqlite", "sqldrivers", ["sqlite::sqlite"])
        if self.options.with_pq:
            _create_plugin("QPSQLDriverPlugin", "qsqlpsql", "sqldrivers", ["libpq::libpq"])
        if self.options.with_odbc:
            _create_plugin("QODBCDriverPlugin", "qsqlodbc", "sqldrivers", [])
            if self.settings.os != "Windows":
                self.info.components["qtQODBCDriverPlugin"].requires.append("odbc::odbc")
            else:
                self.info.components["qtQODBCDriverPlugin"].system_libs.append("odbc32")
        networkReqs: list[str] = []
        if self.options.with_openssl:
            networkReqs.append("openssl::openssl")
        if self.options.with_brotli:
            networkReqs.append("brotli::brotli")
        if self.settings.os in ["Linux", "FreeBSD"] and self.options.with_gssapi:
            networkReqs.append("krb5::krb5-gssapi")
        _create_module("Network", networkReqs)
        _create_module("Sql", [])
        _create_module("Test", [])
        if self.options.widgets:
            _create_module("Widgets", ["Gui"])
            _add_build_module("qtWidgets", self._cmake_qt6_private_file("Widgets"))
            if self.settings.os == "Windows":
                # https://github.com/qt/qtbase/blob/v6.6.1/src/widgets/CMakeLists.txt#L316-L321
                self.info.components["qtWidgets"].system_libs += [
                    "dwmapi", "shell32", "uxtheme",
                ]
        if self.options.gui and self.options.widgets:
            _create_module("PrintSupport", ["Gui", "Widgets"])
        if self.options.with_opengl != "no" and self.options.gui:
            _create_module("OpenGL", ["Gui"])
        if self.options.widgets and self.options.with_opengl != "no":
            _create_module("OpenGLWidgets", ["OpenGL", "Widgets"])
        _create_module("Concurrent", [])
        _create_module("Xml", [])

        if self.options.qt5compat:
            _create_module("Core5Compat", [])

        # since https://github.com/qt/qtdeclarative/commit/4fb84137f1c0a49d64b8bef66fef8a4384cc2a68
        qt_quick_enabled = self.options.gui and self.options.qtshadertools

        if self.options.qtdeclarative:
            _create_module("Qml", ["Network"])
            _add_build_module("qtQml", self._cmake_qt6_private_file("Qml"))
            _create_module("QmlModels", ["Qml"])
            self.info.components["qtQmlImportScanner"].set_property("cmake_target_name", "Qt6::QmlImportScanner")
            self.info.components["qtQmlImportScanner"].set_property("cmake_target_aliases", ["Qt::QmlImportScanner"])
            self.info.components["qtQmlImportScanner"].requires = _get_corrected_reqs(["Qml"])
            if qt_quick_enabled:
                _create_module("Quick", ["Gui", "Qml", "QmlModels"])
                _add_build_module("qtQuick", self._cmake_qt6_private_file("Quick"))
                if self.options.widgets:
                    _create_module("QuickWidgets", ["Gui", "Qml", "Quick", "Widgets"])
                _create_module("QuickShapes", ["Gui", "Qml", "Quick"])
                _create_module("QuickTest", ["Test", "Quick"])
            _create_module("QmlWorkerScript", ["Qml"])

        if self.options.qttools and self.options.gui and self.options.widgets:
            self.info.components["qtLinguistTools"].set_property("cmake_target_name", "Qt6::LinguistTools")
            self.info.components["qtLinguistTools"].set_property("cmake_target_aliases", ["Qt::LinguistTools"])
            _create_module("UiPlugin", ["Gui", "Widgets"])
            self.info.components["qtUiPlugin"].libs = []  # this is a collection of abstract classes, so this is header-only
            self.info.components["qtUiPlugin"].libdirs = []
            _create_module("UiTools", ["UiPlugin", "Gui", "Widgets"])
            if "designer" not in disabled_features:
                _create_module("Designer", ["Gui", "UiPlugin", "Widgets", "Xml"])
            if "assistant" not in disabled_features:
                _create_module("Help", ["Gui", "Sql", "Widgets"])

        if self.options.qtshadertools and self.options.gui:
            _create_module("ShaderTools", ["Gui"])

        if self.options.qtquick3d and qt_quick_enabled:
            _create_module("Quick3DUtils", ["Gui"])
            _create_module("Quick3DAssetImport", ["Gui", "Qml", "Quick3DUtils"])
            _create_module("Quick3DRuntimeRender", ["Gui", "Quick", "Quick3DAssetImport", "Quick3DUtils", "ShaderTools"])
            _create_module("Quick3D", ["Gui", "Qml", "Quick", "Quick3DRuntimeRender"])

        if (self.options.qtquickcontrols2 or self.options.qtdeclarative) and qt_quick_enabled:
            _create_module("QuickControls2", ["Gui", "Quick"])
            _create_module("QuickTemplates2", ["Gui", "Quick"])

        if self.options.qtsvg and self.options.gui:
            _create_module("Svg", ["Gui"])
            _create_plugin("QSvgIconPlugin", "qsvgicon", "iconengines", [])
            _create_plugin("QSvgPlugin", "qsvg", "imageformats", [])
            if self.options.widgets:
                _create_module("SvgWidgets", ["Gui", "Svg", "Widgets"])

        if self.options.qtwayland and self.options.gui:
            _create_module("WaylandClient", ["Gui", "wayland::wayland-client"])
            _create_module("WaylandCompositor", ["Gui", "wayland::wayland-server"])

        if self.options.qtactiveqt and self.settings.os == "Windows":
            _create_module("AxBase", ["Gui", "Widgets"])
            _create_module("AxServer", ["AxBase"])
            self.info.components["qtAxServer"].system_libs.append("shell32")
            self.info.components["qtAxServer"].defines.append("QAXSERVER")
            _create_module("AxContainer", ["AxBase"])

        if self.options.qtcharts:
            _create_module("Charts", ["Gui", "Widgets"])
        if self.options.qtgraphs:
            _create_module("Graphs", ["Gui", "Widgets", "Quick", "Quick3D"])

        if self.options.qtdatavis3d and qt_quick_enabled:
            _create_module("DataVisualization", ["Gui", "OpenGL", "Qml", "Quick"])
        if self.options.qtlottie:
            _create_module("Bodymovin", ["Gui"])
        if self.options.qtscxml:
            _create_module("StateMachine", [])
            _create_module("StateMachineQml", ["StateMachine", "Qml"])
            _create_module("Scxml", [])
            _create_plugin("QScxmlEcmaScriptDataModelPlugin", "qscxmlecmascriptdatamodel", "scxmldatamodel", ["Scxml", "Qml"])
            _create_module("ScxmlQml", ["Scxml", "Qml"])
        if self.options.qtvirtualkeyboard and qt_quick_enabled:
            _create_module("VirtualKeyboard", ["Gui", "Qml", "Quick"])
            _create_plugin("QVirtualKeyboardPlugin", "qtvirtualkeyboardplugin", "platforminputcontexts", ["Gui", "Qml", "VirtualKeyboard"])
            _create_plugin("QtVirtualKeyboardHangulPlugin", "qtvirtualkeyboard_hangul", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])
            _create_plugin("QtVirtualKeyboardMyScriptPlugin", "qtvirtualkeyboard_myscript", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])
            _create_plugin("QtVirtualKeyboardThaiPlugin", "qtvirtualkeyboard_thai", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])
        if self.options.qt3d:
            _create_module("3DCore", ["Gui", "Network"])
            _create_module("3DRender", ["3DCore", "OpenGL"])
            _create_module("3DAnimation", ["3DCore", "3DRender", "Gui"])
            _create_module("3DInput", ["3DCore", "Gui"])
            _create_module("3DLogic", ["3DCore", "Gui"])
            _create_module("3DExtras", ["Gui", "3DCore", "3DInput", "3DLogic", "3DRender"])
            _create_plugin("DefaultGeometryLoaderPlugin", "defaultgeometryloader", "geometryloaders", ["3DCore", "3DRender", "Gui"])
            _create_plugin("fbxGeometryLoaderPlugin", "fbxgeometryloader", "geometryloaders", ["3DCore", "3DRender", "Gui"])
            if qt_quick_enabled:
                _create_module("3DQuick", ["3DCore", "Gui", "Qml", "Quick"])
                _create_module("3DQuickAnimation", ["3DAnimation", "3DCore", "3DQuick", "3DRender", "Gui", "Qml"])
                _create_module("3DQuickExtras", ["3DCore", "3DExtras", "3DInput", "3DQuick", "3DRender", "Gui", "Qml"])
                _create_module("3DQuickInput", ["3DCore", "3DInput", "3DQuick", "Gui", "Qml"])
                _create_module("3DQuickRender", ["3DCore", "3DQuick", "3DRender", "Gui", "Qml"])
                _create_module("3DQuickScene2D", ["3DCore", "3DQuick", "3DRender", "Gui", "Qml"])
        if self.options.qtimageformats:
            _create_plugin("ICNSPlugin", "qicns", "imageformats", ["Gui"])
            _create_plugin("QJp2Plugin", "qjp2", "imageformats", ["Gui"])
            _create_plugin("QMacHeifPlugin", "qmacheif", "imageformats", ["Gui"])
            _create_plugin("QMacJp2Plugin", "qmacjp2", "imageformats", ["Gui"])
            _create_plugin("QMngPlugin", "qmng", "imageformats", ["Gui"])
            _create_plugin("QTgaPlugin", "qtga", "imageformats", ["Gui"])
            _create_plugin("QTiffPlugin", "qtiff", "imageformats", ["Gui"])
            _create_plugin("QWbmpPlugin", "qwbmp", "imageformats", ["Gui"])
            _create_plugin("QWebpPlugin", "qwebp", "imageformats", ["Gui"])
        if self.options.qtnetworkauth:
            _create_module("NetworkAuth", ["Network"])
        if self.options.qtcoap:
            _create_module("Coap", ["Network"])
        if self.options.qtmqtt:
            _create_module("Mqtt", ["Network"])
        if self.options.qtopcua:
            _create_module("OpcUa", ["Network"])
            _create_plugin("QOpen62541Plugin", "open62541_backend", "opcua", ["Network", "OpcUa"])
            _create_plugin("QUACppPlugin", "uacpp_backend", "opcua", ["Network", "OpcUa"])

        if self.options.qtmultimedia:
            multimedia_reqs = ["Network", "Gui"]
            if self.options.with_libalsa:
                multimedia_reqs.append("libalsa::libalsa")
            if self.options.with_openal:
                multimedia_reqs.append("openal-soft::openal-soft")
            if self.options.with_pulseaudio:
                multimedia_reqs.append("pulseaudio::pulse")
            _create_module("Multimedia", multimedia_reqs)
            _create_module("MultimediaWidgets", ["Multimedia", "Widgets", "Gui"])
            if self.options.qtdeclarative and qt_quick_enabled:
                _create_module("MultimediaQuick", ["Multimedia", "Quick"])
            if self.options.with_gstreamer:
                _create_plugin(
                    "QGstreamerMediaPlugin", "gstreamermediaplugin", "multimedia", [
                        "gstreamer::gstreamer",
                        "gst-plugins-base::gst-plugins-base",
                    ])

        if self.options.qtpositioning:
            _create_module("Positioning", [])
            _create_plugin("QGeoPositionInfoSourceFactoryGeoclue2", "qtposition_geoclue2", "position", [])
            _create_plugin("QGeoPositionInfoSourceFactoryPoll", "qtposition_positionpoll", "position", [])

        if self.options.qtsensors:
            _create_module("Sensors", [])
            _create_plugin("genericSensorPlugin", "qtsensors_generic", "sensors", [])
            _create_plugin("IIOSensorProxySensorPlugin", "qtsensors_iio-sensor-proxy", "sensors", [])
            if self.settings.os == "Linux":
                _create_plugin("LinuxSensorPlugin", "qtsensors_linuxsys", "sensors", [])
            _create_plugin("QtSensorGesturePlugin", "qtsensorgestures_plugin", "sensorgestures", [])
            _create_plugin("QShakeSensorGesturePlugin", "qtsensorgestures_shakeplugin", "sensorgestures", [])

        if self.options.qtconnectivity:
            _create_module("Bluetooth", ["Network"])
            _create_module("Nfc", [])

        if self.options.qtserialport:
            _create_module("SerialPort", [])

        if self.options.qtserialbus:
            _create_module("SerialBus", ["SerialPort"] if self.options.qtserialport else [])
            _create_plugin("PassThruCanBusPlugin", "qtpassthrucanbus", "canbus", [])
            _create_plugin("PeakCanBusPlugin", "qtpeakcanbus", "canbus", [])
            _create_plugin("SocketCanBusPlugin", "qtsocketcanbus", "canbus", [])
            _create_plugin("TinyCanBusPlugin", "qttinycanbus", "canbus", [])
            _create_plugin("VirtualCanBusPlugin", "qtvirtualcanbus", "canbus", [])

        if self.options.qtwebsockets:
            _create_module("WebSockets", ["Network"])

        if self.options.qtwebchannel:
            _create_module("WebChannel", ["Qml"])

        if self.options.qtwebengine and qt_quick_enabled:
            webenginereqs = ["Gui", "Quick", "WebChannel"]
            if self.options.qtpositioning:
                webenginereqs.append("Positioning")
            if self.settings.os == "Linux":
                webenginereqs.extend(
                    [
                        "libexpat::libexpat", "opus::libopus", "xorg-proto::xorg-proto", "libxshmfence::libxshmfence", \
                        "nss::nss", "libdrm::libdrm",
                    ])
            _create_module("WebEngineCore", webenginereqs)
            _create_module("WebEngineQuick", ["WebEngineCore"])
            _create_module("WebEngineWidgets", ["WebEngineCore", "Quick", "PrintSupport", "Widgets", "Gui", "Network"])

        if self.options.qtremoteobjects:
            _create_module("RemoteObjects", [])

        if self.options.qtwebview:
            _create_module("WebView", ["Core", "Gui"])

        if self.options.qtspeech:
            _create_module("TextToSpeech", [])

        if self.options.qthttpserver:
            http_server_deps = ["Core", "Network"]
            if self.options.qtwebsockets:
                http_server_deps.append("WebSockets")
            _create_module("HttpServer", http_server_deps)

        if self.options.qtgrpc:
            _create_module("Protobuf", [])
            _create_module("Grpc", ["Core", "Protobuf", "Network"])

        if self.options.qttasktree:
            _create_module("TaskTree", [])

        if self.options.qtcanvaspainter and self.options.gui:
            canvas_reqs = ["Gui"]
            if self.options.qtdeclarative and qt_quick_enabled:
                canvas_reqs.append("Quick")
            if self.options.widgets:
                canvas_reqs.append("Widgets")
            _create_module("CanvasPainter", canvas_reqs)

        if self.settings.os in ["Windows", "iOS"]:
            if self.settings.os == "Windows":
                self.info.components["qtEntryPointImplementation"].set_property("cmake_target_name", "Qt6::EntryPointImplementation")
                self.info.components["qtEntryPointImplementation"].set_property("cmake_target_aliases", ["Qt::EntryPointImplementation"])
                self.info.components["qtEntryPointImplementation"].libs = [f"Qt6EntryPoint{libsuffix}"]
                self.info.components["qtEntryPointImplementation"].system_libs = ["shell32"]

                if self.settings.compiler == "gcc":
                    self.info.components["qtEntryPointMinGW32"].set_property("cmake_target_name", "Qt6::EntryPointMinGW32")
                    self.info.components["qtEntryPointMinGW32"].set_property("cmake_target_aliases", ["Qt::EntryPointMinGW32"])
                    self.info.components["qtEntryPointMinGW32"].system_libs = ["mingw32"]
                    self.info.components["qtEntryPointMinGW32"].requires = ["qtEntryPointImplementation"]

            self.info.components["qtEntryPointPrivate"].set_property("cmake_target_name", "Qt6::EntryPointPrivate")
            self.info.components["qtEntryPointPrivate"].set_property("cmake_target_aliases", ["Qt::EntryPointPrivate"])
            if self.settings.os == "Windows":
                if self.settings.compiler == "gcc":
                    self.info.components["qtEntryPointPrivate"].defines.append("QT_NEEDS_QMAIN")
                    self.info.components["qtEntryPointPrivate"].requires.append("qtEntryPointMinGW32")
                else:
                    self.info.components["qtEntryPointPrivate"].requires.append("qtEntryPointImplementation")
            if self.settings.os == "iOS":
                self.info.components["qtEntryPointPrivate"].exelinkflags.append("-Wl,-e,_qt_main_wrapper")

        if self.settings.os != "Windows":
            self.info.components["qtCore"].cxxflags.append("-fPIC")

        if self.settings.os == "Windows" or is_msvc(self):
            _add_build_module("qtPlatform", self._cmake_platform_target_setup_file)

        self.info.components["qtCore"].builddirs.append(os.path.join("bin"))
        _add_build_module("qtCore", self._cmake_executables_file)
        _add_build_module("qtCore", self._cmake_qt6_private_file("Core"))
        if self.settings.os in ["Windows", "iOS"]:
            _add_build_module("qtCore", self._cmake_entry_point_file)

        qt_cmake_dir = self.folders.package / "lib" / "cmake"
        for m in os.listdir(qt_cmake_dir):
            component_name = m.replace("Qt6", "qt")
            if component_name == "qt":
                component_name = "qtCore"

            if component_name in self.info.components:
                module = qt_cmake_dir / m / f"{m}Macros.cmake"
                if os.path.isfile(module):
                    _add_build_module(component_name, module)

                module = qt_cmake_dir / m / f"{m}ConfigExtras.cmake"
                if os.path.isfile(module):
                    _add_build_module(component_name, module)

                for helper_modules in (qt_cmake_dir / m).glob("QtPublic*Helpers.cmake"):
                    _add_build_module(component_name, helper_modules)
                for helper_modules in (qt_cmake_dir / m).glob("Qt6QmlPublic*Helpers.cmake"):
                    _add_build_module(component_name, helper_modules)
                self.info.components[component_name].builddirs.append(os.path.join("lib", "cmake", m))

            elif component_name.endswith("Tools") and component_name[:-5] in self.info.components:
                module = qt_cmake_dir / m / f"{m[:-5]}Macros.cmake"
                if os.path.isfile(module):
                    _add_build_module(component_name[:-5], module)
                self.info.components[component_name[:-5]].builddirs.append(os.path.join("lib", "cmake", m))

        build_modules_list: list[str | Path] = []

        if self.options.qtdeclarative:
            build_modules_list.append(self.folders.package / "lib" / "cmake" / "Qt6Qml" / "recipe_qt_qt6_policies.cmake")

        def _add_build_modules_for_component(component: str):
            for req in self.info.components[component].requires:
                if "::" in req:  # not a qt component
                    continue
                _add_build_modules_for_component(req)
            build_modules_list.extend(build_modules.pop(component, []))

        for c in self.info.components:
            _add_build_modules_for_component(c)

        self.info.set_property("cmake_build_modules", build_modules_list)

        self.info.conf.tools.qt.tools_directory = self.folders.package / ("bin" if self.settings.os == "Windows" else "libexec")

    def _excluded_module_patterns(self) -> list[str]:
        root = f"qt-everywhere-src-{self.version}"
        patterns: list[str] = []
        for module in _MODULE_DEPENDS:
            if not self.options.get_safe(module):
                patterns.append(f"{root}/{module}")
                patterns.append(f"{root}/{module}/*")
        return patterns

    def _xplatform(self) -> str | None:
        if self.settings.os == "Linux":
            if self.settings.compiler == "gcc":
                return {"ARM": "linux-aarch64-gnu-g++"}.get(str(self.settings.arch), "linux-g++")
            if self.settings.compiler == "clang":
                if self.settings.arch == "X64":
                    return "linux-clang-libc++" if self.settings.compiler_libcxx == "libc++" else "linux-clang"

        elif self.settings.os == "Mac":
            return {
                "clang": "macx-clang",
                "apple-clang": "macx-clang",
                "gcc": "macx-g++",
            }.get(str(self.settings.compiler))

        elif self.settings.os == "iOS":
            if self.settings.compiler == "apple-clang":
                return "macx-ios-clang"

        elif self.settings.os == "tvOS":
            if self.settings.compiler == "apple-clang":
                return "macx-tvos-clang"

        elif self.settings.os == "Android":
            if self.settings.compiler == "clang":
                return "android-clang"

        elif self.settings.os == "Windows":
            return {
                "Visual Studio": "win32-msvc",
                "msvc": "win32-msvc",
                "gcc": "win32-g++",
                "clang": "win32-clang-g++",
            }.get(str(self.settings.compiler))

        elif self.settings.os == "WindowsStore":
            if is_msvc(self):
                if self.settings.compiler == "Visual Studio":
                    msvc_version = str(self.settings.compiler_version)
                else:
                    msvc_version = {
                        "190": "14",
                        "191": "15",
                        "192": "16",
                    }.get(str(self.settings.compiler_version), "")
                return {
                    "14": {
                        "armv7": "winrt-arm-msvc2015",
                        "x86": "winrt-x86-msvc2015",
                        "x86_64": "winrt-x64-msvc2015",
                    },
                    "15": {
                        "armv7": "winrt-arm-msvc2017",
                        "x86": "winrt-x86-msvc2017",
                        "x86_64": "winrt-x64-msvc2017",
                    },
                    "16": {
                        "armv7": "winrt-arm-msvc2019",
                        "x86": "winrt-x86-msvc2019",
                        "x86_64": "winrt-x64-msvc2019",
                    },
                }.get(msvc_version, {}).get(str(self.settings.arch))

        elif self.settings.os == "FreeBSD":
            return {
                "clang": "freebsd-clang",
                "gcc": "freebsd-g++",
            }.get(str(self.settings.compiler))

        elif self.settings.os == "SunOS":
            if self.settings.compiler == "sun-cc":
                if self.settings.arch == "sparc":
                    return "solaris-cc-stlport" if self.settings.compiler_libcxx == "libstlport" else "solaris-cc"
                if self.settings.arch == "sparcv9":
                    return "solaris-cc64-stlport" if self.settings.compiler_libcxx == "libstlport" else "solaris-cc64"
            elif self.settings.compiler == "gcc":
                return {
                    "sparc": "solaris-g++",
                    "sparcv9": "solaris-g++-64",
                }.get(str(self.settings.arch))
        elif self.settings.os == "Neutrino" and self.settings.compiler == "qcc":
            return {
                "armv8": "qnx-aarch64le-qcc",
                "armv8.3": "qnx-aarch64le-qcc",
                "armv7": "qnx-armle-v7-qcc",
                "armv7hf": "qnx-armle-v7-qcc",
                "armv7s": "qnx-armle-v7-qcc",
                "armv7k": "qnx-armle-v7-qcc",
                "x86": "qnx-x86-qcc",
                "x86_64": "qnx-x86-64-qcc",
            }.get(str(self.settings.arch))
        elif self.settings.os == "Emscripten" and self.settings.arch == "wasm":
            return "wasm-emscripten"

        return None

    @property
    def _cmake_executables_file(self):
        return os.path.join("lib", "cmake", "Qt6Core", "recipe_qt_executables_variables.cmake")

    @property
    def _cmake_entry_point_file(self):
        return os.path.join("lib", "cmake", "Qt6Core", "recipe_qt_entry_point.cmake")

    @property
    def _cmake_platform_target_setup_file(self):
        return os.path.join("lib", "cmake", "Qt6", "recipe_qt_platform_target_setup.cmake")

    def _cmake_qt6_private_file(self, module: str):
        return os.path.join("lib", "cmake", f"Qt6{module}", f"recipe_qt_qt6_{module.lower()}private.cmake")
