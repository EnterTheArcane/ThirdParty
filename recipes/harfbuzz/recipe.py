import os
from typing import Any

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.build import stdcpp_library
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir, replace_in_file
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_glib: bool = False
    with_gdi: bool = True
    with_uniscribe: bool = True
    with_directwrite: bool = False
    with_subset: bool = True
    with_coretext: bool = True


class Recipe(RecipeBase[_Options]):
    name = "harfbuzz"
    version = "14.2.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "harfbuzz/harfbuzz")
        return Version(repo.latest_release)

    def configure(self):
        if self.settings.os != "Windows":
            self.options.with_gdi = False
            self.options.with_uniscribe = False
            self.options.with_directwrite = False
        if not is_apple_os(self):
            self.options.with_coretext = False

    def requirements(self):
        self.requires_tool("meson")
        self.requires("freetype")
        self.requires("icu")
        if self.options.with_glib:
            self.requires("glib")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")
        if self.options.with_glib:
            self.requires_tool("glib")
        if self.settings.os == "Mac":
            # Ensure that the gettext we use at build time is compatible
            # with the libiconv that is transitively exposed by glib
            self.requires_tool("gettext")

    def source(self):
        get(
            self,
            url=f"https://github.com/harfbuzz/harfbuzz/releases/download/{self.version}/harfbuzz-{self.version}.tar.xz",
            sha256="a54a5d8e9380a41fbb762ce367bcbf7704792dfca0d93f1bbca86c5a57902e0e",
            destination=self.folders.source,
            strip_root=True)

        # Upstream src/meson.build creates the GPU shader-header custom_targets in a foreach loop
        # but throws away their handles, so nothing tells ninja that libharfbuzz-gpu's sources
        # (hb-gpu-draw.cc, ...) depend on the generated *.hh. On a clean parallel build a .cc can
        # compile before its header is generated -> intermittent C1083 (e.g. missing
        # 'hb-gpu-draw-fragment-msl.hh'). Capture the custom_target outputs and add them to the
        # library so meson emits the proper ordering edge.
        src_meson = self.folders.source / "src" / "meson.build"
        replace_in_file(
            self, src_meson,
            "foreach p: hb_gpu_shader_sources\n  custom_target('@0@'.format(p.get(1)),",
            "hb_gpu_generated_headers = []\nforeach p: hb_gpu_shader_sources\n"
            "  hb_gpu_generated_headers += custom_target('@0@'.format(p.get(1)),")
        replace_in_file(
            self, src_meson,
            "  libharfbuzz_gpu = library('harfbuzz-gpu',\n    hb_gpu_sources,\n    include_directories: incconfig,",
            "  libharfbuzz_gpu = library('harfbuzz-gpu',\n    hb_gpu_sources,\n    hb_gpu_generated_headers,\n    include_directories: incconfig,")

    def generate(self):
        def is_enabled(value: Any):
            return "enabled" if value else "disabled"

        def meson_backend_and_flags() -> tuple[str, list[str]]:
            def is_vs_2017():
                version = Version(self.settings.compiler_version)
                return version == "15" or version == "191"

            if is_msvc(self) and is_vs_2017() and self.settings.build_type == "Debug":
                # Mitigate https://learn.microsoft.com/en-us/cpp/build/reference/zf?view=msvc-170
                return "vs", ["/bigobj"]
            return "ninja", []

        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()

        # Avoid conflicts with libiconv
        # see: https://github.com/recipe-io/recipe-center-index/pull/17046#issuecomment-1554629094
        if self.settings_build.os == "Mac":
            env = Environment()
            env.define_path("DYLD_FALLBACK_LIBRARY_PATH", "$DYLD_LIBRARY_PATH")
            env.define_path("DYLD_LIBRARY_PATH", "")
            env.vars(self, scope="build").save_script("buildenv_macos_runtimepath")

        backend, cxxflags = meson_backend_and_flags()
        tc = MesonToolchain(self, backend=backend)
        tc.project_options["auto_features"] = "disabled"
        tc.project_options.update(
            {
                "glib": is_enabled(self.options.with_glib),
                "icu": is_enabled(True),
                "freetype": is_enabled(True),
                "gdi": is_enabled(self.options.with_gdi),
                "coretext": is_enabled(self.options.with_coretext),
                "directwrite": is_enabled(self.options.with_directwrite),
                "gobject": is_enabled(self.options.with_glib),
                "introspection": is_enabled(False),
                "tests": "disabled",
                "docs": "disabled",
                "benchmark": "disabled",
                "icu_builtin": "false",
            })
        tc.cpp_args += cxxflags
        tc.generate()

    def build(self):
        replace_in_file(self, self.folders.source / "meson.build", "subdir('util')", "", strict=False)
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", self.folders.source, self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rm(self, "*.pdb", self.folders.package / "bin")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "harfbuzz")
        self.info.set_property("pkg_config_name", "harfbuzz")

        # TODO in next Harfbuzz major version:
        # - rename "core" component to "harfbuzz"
        # - add self.info.set_property("pkg_config_name", "none")
        # - set "harfbuzz" as the pkg_config_name of the harfbuzz component
        self.info.components["core"].set_property("cmake_target_name", "harfbuzz::harfbuzz")
        self.info.components["core"].libs = ["harfbuzz"]
        self.info.components["core"].includedirs.append(os.path.join("include", "harfbuzz"))
        self.info.components["core"].requires.append("freetype::freetype")
        if self.options.with_glib:
            self.info.components["core"].requires.append("glib::glib")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["core"].system_libs.append("m")
        if self.settings.os == "Windows" and not self.options.shared:
            self.info.components["core"].system_libs.append("user32")
            if self.options.with_gdi or self.options.with_uniscribe:
                self.info.components["core"].system_libs.append("gdi32")
            if self.options.with_uniscribe or self.options.with_directwrite:
                self.info.components["core"].system_libs.append("rpcrt4")
            if self.options.with_uniscribe:
                self.info.components["core"].system_libs.append("usp10")
            if self.options.with_directwrite:
                self.info.components["core"].system_libs.append("dwrite")
        if is_apple_os(self) and self.options.with_coretext:
            if self.settings.os == "Mac":
                self.info.components["core"].frameworks.append("ApplicationServices")
            else:
                self.info.frameworks.extend(["CoreFoundation", "CoreGraphics", "CoreText"])
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.components["core"].system_libs.append(libcxx)

        self.info.components["icu"].libs = ["harfbuzz-icu"]
        self.info.components["icu"].set_property("cmake_target_name", "harfbuzz::icu")
        self.info.components["icu"].set_property("pkg_config_name", "harfbuzz-icu")
        self.info.components["icu"].requires = ["core", "icu::icu"]

        if self.options.with_subset:
            self.info.components["subset"].libs = ["harfbuzz-subset"]
            self.info.components["subset"].set_property("cmake_target_name", "harfbuzz::subset")
            self.info.components["subset"].set_property("pkg_config_name", "harfbuzz-subset")
            self.info.components["subset"].requires = ["core"]

        if self.options.with_glib:
            self.info.components["gobject"].libs = ["harfbuzz-gobject"]
            self.info.components["gobject"].set_property("cmake_target_name", "harfbuzz::gobject")
            self.info.components["gobject"].set_property("pkg_config_name", "harfbuzz-gobject")
            self.info.components["gobject"].requires = ["core", "glib::glib"]


