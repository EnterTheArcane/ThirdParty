import glob
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import cross_building
from thirdparty.env import Environment, VirtualBuildEnv, VirtualRunEnv
from thirdparty.files import (
    chdir, copy, get, rename,
    replace_in_file, rm, rmdir, save, load,
)
from thirdparty.autotools import Autotools, AutotoolsDeps, AutotoolsToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.microsoft import check_min_vs, is_msvc, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    avdevice: bool = True
    avcodec: bool = True
    avformat: bool = True
    swresample: bool = True
    swscale: bool = True
    postproc: bool = True
    avfilter: bool = True
    with_asm: bool = True
    with_zlib: bool = True
    with_bzip2: bool = True
    with_lzma: bool = True
    with_libiconv: bool = True
    with_freetype: bool = True
    with_libxml2: bool = True
    with_fontconfig: bool = True
    with_fribidi: bool = False
    with_harfbuzz: bool = True
    with_libjxl: bool = True
    with_openapv: bool = False
    with_openjpeg: bool = True
    with_openh264: bool = True
    with_opus: bool = True
    with_vorbis: bool = True
    with_zeromq: bool = False
    with_sdl: bool = False
    with_libx264: bool = True
    with_libx265: bool = True
    with_libvpx: bool = True
    with_libmp3lame: bool = True
    with_libfdk_aac: bool = True
    with_libwebp: bool = True
    with_ssl: Literal[False, "openssl", "securetransport"] = "openssl"
    with_libalsa: bool = True
    with_pulse: bool = True
    with_vaapi: bool = True
    with_vdpau: bool = True
    with_vulkan: bool = False
    with_whisper: bool = False
    with_xcb: bool = True
    with_soxr: bool = False
    with_appkit: bool = True
    with_avfoundation: bool = True
    with_coreimage: bool = True
    with_audiotoolbox: bool = True
    with_videotoolbox: bool = True
    with_programs: bool = True
    with_libsvtav1: bool = True
    with_libaom: bool = True
    with_libdav1d: bool = True
    with_libdrm: bool = False
    with_jni: bool = False
    with_mediacodec: bool = False
    with_xlib: bool = True
    disable_everything: bool = False
    disable_all_encoders: bool = False
    disable_encoders: str | None = None
    enable_encoders: str | None = None
    disable_all_decoders: bool = False
    disable_decoders: str | None = None
    enable_decoders: str | None = None
    disable_all_hardware_accelerators: bool = False
    disable_hardware_accelerators: str | None = None
    enable_hardware_accelerators: str | None = None
    disable_all_muxers: bool = False
    disable_muxers: str | None = None
    enable_muxers: str | None = None
    disable_all_demuxers: bool = False
    disable_demuxers: str | None = None
    enable_demuxers: str | None = None
    disable_all_parsers: bool = False
    disable_parsers: str | None = None
    enable_parsers: str | None = None
    disable_all_bitstream_filters: bool = False
    disable_bitstream_filters: str | None = None
    enable_bitstream_filters: str | None = None
    disable_all_protocols: bool = False
    disable_protocols: str | None = None
    enable_protocols: str | None = None
    disable_all_devices: bool = False
    disable_all_input_devices: bool = False
    disable_input_devices: str | None = None
    enable_input_devices: str | None = None
    disable_all_output_devices: bool = False
    disable_output_devices: str | None = None
    enable_output_devices: str | None = None
    disable_all_filters: bool = False
    disable_filters: str | None = None
    enable_filters: str | None = None


class Recipe(RecipeBase[_Options]):
    name = "ffmpeg"
    version = "8.1.2"
    license = "GPL-2.0-or-later", "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "FFmpeg/FFmpeg")
        return Version(repo.latest_release.removeprefix("n"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

        if self.settings.os == "Windows":
            if is_msvc(self) and self.settings.arch == "ARM":
                self.options.with_libsvtav1 = False

        self.options.postproc = False

        if self.settings.os not in ["Linux", "FreeBSD"]:
            self.options.with_vaapi = False
            self.options.with_vdpau = False
            self.options.with_vulkan = False
            self.options.with_xcb = False
            self.options.with_libalsa = False
            self.options.with_pulse = False
            self.options.with_xlib = False
            self.options.with_libdrm = False
        if self.settings.os != "Mac":
            self.options.with_appkit = False
        if self.settings.os not in ["Mac", "iOS", "tvOS"]:
            self.options.with_coreimage = False
            self.options.with_audiotoolbox = False
            self.options.with_videotoolbox = False
        if not is_apple_os(self):
            self.options.with_avfoundation = False
        if not self.settings.os == "Android":
            self.options.with_jni = False
            self.options.with_mediacodec = False
        if self.settings.os == "Android":
            self.options.with_libfdk_aac = False

    def requirements(self):
        if self.options.with_zlib:
            self.requires("zlib")
        if self.options.with_bzip2:
            self.requires("bzip2")
        if self.options.with_lzma:
            self.requires("xz")
        if self.options.with_libiconv:
            self.requires("libiconv")
        if self.options.with_freetype:
            self.requires("freetype")
        if self.options.with_libxml2:
            self.requires("libxml2")
        if self.options.with_fontconfig:
            self.requires("fontconfig")
        if self.options.with_fribidi:
            self.requires("fribidi")
        if self.options.with_harfbuzz:
            self.requires("harfbuzz")
        if self.options.with_libjxl:
            self.requires("libjxl")
        if self.options.with_openjpeg:
            self.requires("openjpeg")
        if self.options.with_openh264:
            self.requires("openh264")
        if self.options.with_vorbis:
            self.requires("vorbis")
        if self.options.with_opus:
            self.requires("opus")
        if self.options.with_zeromq:
            self.requires("zeromq")
        if self.options.with_sdl:
            self.requires("sdl")
        if self.options.with_libx264:
            self.requires("x264")
        if self.options.with_libx265:
            self.requires("x265")
        if self.options.with_libvpx:
            self.requires("libvpx")
        if self.options.with_libmp3lame:
            self.requires("libmp3lame")
        if self.options.with_libfdk_aac:
            self.requires("fdk-aac")
        if self.options.with_libwebp:
            self.requires("libwebp")
        if self.options.with_ssl == "openssl":
            self.requires("openssl")
        if self.options.with_libalsa:
            self.requires("libalsa")
        if self.options.with_xcb or self.options.with_xlib:
            self.requires("libx11")
            self.requires("libxext")
            self.requires("libxv")
        if self.options.with_xcb:
            self.requires("libxcb")
        if self.options.with_soxr:
            self.requires("soxr")
        if self.options.with_pulse:
            self.requires("pulseaudio")
        if self.options.with_vaapi:
            self.requires("vaapi")
        if self.options.with_vdpau:
            self.requires("vdpau")
        if self.options.with_vulkan:
            self.requires("vulkan-loader")
        if self.options.with_libsvtav1:
            self.requires("svt-av1")
        if self.options.with_libaom:
            self.requires("aom")
        if self.options.with_libdav1d:
            self.requires("dav1d")
        if self.options.with_libdrm:
            self.requires("libdrm")
        if self.options.with_whisper:
            self.requires("whisper-cpp")
        if self.options.with_openapv:
            self.requires("openapv")
        if self.settings.arch == "X64":
            self.requires_tool("nasm")

        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")
        if self.settings.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")
            if self.settings.arch == "ARM" and is_msvc(self):
                self.requires_tool("gas-preprocessor")
                # gas-preprocessor.pl has a "#!/usr/bin/env perl" shebang and is invoked by
                # ffmpeg's configure as the aarch64 assembler wrapper; without perl on PATH it
                # fails with "command not found". strawberryperl provides the interpreter.
                self.requires_tool("strawberryperl")

    def source(self):
        get(
            self,
            url=f"https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n{self.version}.tar.gz",
            sha256="9fd092511605bbebafe095ea6d38d9e40f34d12f7386e1258372df8be0576eb7",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        if not cross_building(self):
            env = VirtualRunEnv(self).generate(scope="build")

        def opt_enable_disable(what: str, v: Any) -> str:
            return "--{}-{}".format("enable" if v else "disable", what)

        def opt_append_disable_if_set(args: list[str], what: str, v: Any):
            if v:
                args.append(f"--disable-{what}")

        tc = self._create_toolchain()

        args = [
            "--pkg-config-flags=--static",
            "--disable-doc",
            opt_enable_disable("cross-compile", cross_building(self)),
            opt_enable_disable("asm", self.options.with_asm),
            # Libraries
            opt_enable_disable("shared", self.options.shared),
            opt_enable_disable("static", not self.options.shared),
            opt_enable_disable("pic", self.options.pic),
            # Components
            opt_enable_disable("avdevice", self.options.avdevice),
            opt_enable_disable("avcodec", self.options.avcodec),
            opt_enable_disable("avformat", self.options.avformat),
            opt_enable_disable("swresample", self.options.swresample),
            opt_enable_disable("swscale", self.options.swscale),
            opt_enable_disable("avfilter", self.options.avfilter),

            # Dependencies
            opt_enable_disable("bzlib", self.options.with_bzip2),
            opt_enable_disable("zlib", self.options.with_zlib),
            opt_enable_disable("libxml2", self.options.with_libxml2),
            opt_enable_disable("lzma", self.options.with_lzma),
            opt_enable_disable("iconv", self.options.with_libiconv),
            opt_enable_disable("libfreetype", self.options.with_freetype),
            opt_enable_disable("libfontconfig", self.options.with_fontconfig),
            opt_enable_disable("libfribidi", self.options.with_fribidi),
            opt_enable_disable("libopenjpeg", self.options.with_openjpeg),
            opt_enable_disable("libopenh264", self.options.with_openh264),
            opt_enable_disable("libvorbis", self.options.with_vorbis),
            opt_enable_disable("libopus", self.options.with_opus),
            opt_enable_disable("libzmq", self.options.with_zeromq),
            opt_enable_disable("sdl2", self.options.with_sdl),
            opt_enable_disable("libx264", self.options.with_libx264),
            opt_enable_disable("libx265", self.options.with_libx265),
            opt_enable_disable("libvpx", self.options.with_libvpx),
            opt_enable_disable("libmp3lame", self.options.with_libmp3lame),
            opt_enable_disable("libfdk-aac", self.options.with_libfdk_aac),
            opt_enable_disable("libwebp", self.options.with_libwebp),
            opt_enable_disable("libaom", self.options.with_libaom),
            opt_enable_disable("openssl", self.options.with_ssl == "openssl"),
            opt_enable_disable("alsa", self.options.with_libalsa),
            opt_enable_disable("libpulse", self.options.with_pulse),
            opt_enable_disable("vaapi", self.options.with_vaapi),
            opt_enable_disable("libdrm", self.options.with_libdrm),
            opt_enable_disable("vdpau", self.options.with_vdpau),
            opt_enable_disable("libxcb", self.options.with_xcb),
            opt_enable_disable("libxcb-shm", self.options.with_xcb),
            opt_enable_disable("libxcb-shape", self.options.with_xcb),
            opt_enable_disable("libxcb-xfixes", self.options.with_xcb),
            opt_enable_disable("libsoxr", self.options.with_soxr),
            opt_enable_disable("appkit", self.options.with_appkit),
            opt_enable_disable("avfoundation", self.options.with_avfoundation),
            opt_enable_disable("coreimage", self.options.with_coreimage),
            opt_enable_disable("audiotoolbox", self.options.with_audiotoolbox),
            opt_enable_disable("videotoolbox", self.options.with_videotoolbox),
            opt_enable_disable("securetransport", self.options.with_ssl == "securetransport"),
            opt_enable_disable("vulkan", self.options.with_vulkan),
            opt_enable_disable("libdav1d", self.options.with_libdav1d),
            opt_enable_disable("jni", self.options.with_jni),
            opt_enable_disable("mediacodec", self.options.with_mediacodec),
            opt_enable_disable("xlib", self.options.with_xlib),
            "--disable-cuda",  # FIXME: CUDA support
            "--disable-cuvid",  # FIXME: CUVID support
            # Licenses
            opt_enable_disable(
                "nonfree", self.options.with_libfdk_aac or (self.options.with_ssl and (
                        self.options.with_libx264 or self.options.with_libx265 or self.options.postproc))),
            opt_enable_disable("gpl", self.options.with_libx264 or self.options.with_libx265 or self.options.postproc),
        ]

        # Individual Component Options
        opt_append_disable_if_set(args, "everything", self.options.disable_everything)
        opt_append_disable_if_set(args, "encoders", self.options.disable_all_encoders)
        opt_append_disable_if_set(args, "decoders", self.options.disable_all_decoders)
        opt_append_disable_if_set(args, "hwaccels", self.options.disable_all_hardware_accelerators)
        opt_append_disable_if_set(args, "muxers", self.options.disable_all_muxers)
        opt_append_disable_if_set(args, "demuxers", self.options.disable_all_demuxers)
        opt_append_disable_if_set(args, "parsers", self.options.disable_all_parsers)
        opt_append_disable_if_set(args, "bsfs", self.options.disable_all_bitstream_filters)
        opt_append_disable_if_set(args, "protocols", self.options.disable_all_protocols)
        opt_append_disable_if_set(args, "devices", self.options.disable_all_devices)
        opt_append_disable_if_set(args, "indevs", self.options.disable_all_input_devices)
        opt_append_disable_if_set(args, "outdevs", self.options.disable_all_output_devices)
        opt_append_disable_if_set(args, "filters", self.options.disable_all_filters)

        args.extend(
            self._split_and_format_options_string(
                "enable-encoder", self.options.enable_encoders))
        args.extend(
            self._split_and_format_options_string(
                "disable-encoder", self.options.disable_encoders))
        args.extend(
            self._split_and_format_options_string(
                "enable-decoder", self.options.enable_decoders))
        args.extend(
            self._split_and_format_options_string(
                "disable-decoder", self.options.disable_decoders))
        args.extend(
            self._split_and_format_options_string(
                "enable-hwaccel", self.options.enable_hardware_accelerators))
        args.extend(
            self._split_and_format_options_string(
                "disable-hwaccel", self.options.disable_hardware_accelerators))
        args.extend(
            self._split_and_format_options_string(
                "enable-muxer", self.options.enable_muxers))
        args.extend(
            self._split_and_format_options_string(
                "disable-muxer", self.options.disable_muxers))
        args.extend(
            self._split_and_format_options_string(
                "enable-demuxer", self.options.enable_demuxers))
        args.extend(
            self._split_and_format_options_string(
                "disable-demuxer", self.options.disable_demuxers))
        args.extend(
            self._split_and_format_options_string(
                "enable-parser", self.options.enable_parsers))
        args.extend(
            self._split_and_format_options_string(
                "disable-parser", self.options.disable_parsers))
        args.extend(
            self._split_and_format_options_string(
                "enable-bsf", self.options.enable_bitstream_filters))
        args.extend(
            self._split_and_format_options_string(
                "disable-bsf", self.options.disable_bitstream_filters))
        args.extend(
            self._split_and_format_options_string(
                "enable-protocol", self.options.enable_protocols))
        args.extend(
            self._split_and_format_options_string(
                "disable-protocol", self.options.disable_protocols))
        args.extend(
            self._split_and_format_options_string(
                "enable-indev", self.options.enable_input_devices))
        args.extend(
            self._split_and_format_options_string(
                "disable-indev", self.options.disable_input_devices))
        args.extend(
            self._split_and_format_options_string(
                "enable-outdev", self.options.enable_output_devices))
        args.extend(
            self._split_and_format_options_string(
                "disable-outdev", self.options.disable_output_devices))
        args.extend(
            self._split_and_format_options_string(
                "enable-filter", self.options.enable_filters))
        args.extend(
            self._split_and_format_options_string(
                "disable-filter", self.options.disable_filters))

        args.append(opt_enable_disable("libjxl", self.options.with_libjxl))
        args.append(opt_enable_disable("whisper", self.options.with_whisper))
        args.append(opt_enable_disable("liboapv", self.options.with_openapv))

        args.append(opt_enable_disable("libsvtav1", self.options.with_libsvtav1))
        args.append(opt_enable_disable("libharfbuzz", self.options.with_harfbuzz))
        if is_apple_os(self):
            # relocatable shared libs
            args.append("--install-name-dir=@rpath")
        args.append(f"--arch={self._target_arch}")
        if self.settings.build_type == "Debug":
            args.extend(
                [
                    "--disable-optimizations",
                    "--disable-mmx",
                    "--disable-stripping",
                    "--enable-debug",
                ])
        if not self.options.with_programs:
            args.append("--disable-programs")
        # since ffmpeg"s build system ignores CC and CXX
        compilers_from_conf = self.conf.tools.build.compiler_executables
        buildenv_vars = VirtualBuildEnv(self).vars()
        nm = buildenv_vars.get("NM")
        if nm:
            args.append(f"--nm={unix_path(self, nm)}")
        ar = buildenv_vars.get("AR")
        if ar:
            args.append(f"--ar={unix_path(self, ar)}")
        if self.options.with_asm:
            asm = compilers_from_conf.get("asm", buildenv_vars.get("AS"))
            if asm:
                args.append(f"--as={unix_path(self, asm)}")
        strip = buildenv_vars.get("STRIP")
        if strip:
            args.append(f"--strip={unix_path(self, strip)}")
        cc = compilers_from_conf.get("c", buildenv_vars.get("CC", self._default_compilers.get("cc")))
        if cc:
            args.append(f"--cc={unix_path(self, cc)}")
        cxx = compilers_from_conf.get("cpp", buildenv_vars.get("CXX", self._default_compilers.get("cxx")))
        if cxx:
            args.append(f"--cxx={unix_path(self, cxx)}")
        ld = buildenv_vars.get("LD")
        if ld:
            args.append(f"--ld={unix_path(self, ld)}")
        ranlib = buildenv_vars.get("RANLIB")
        if ranlib:
            args.append(f"--ranlib={unix_path(self, ranlib)}")
        pkg_config = self.conf.tools.gnu.pkg_config or buildenv_vars.get("PKG_CONFIG")
        if pkg_config:
            # the ffmpeg configure script hardcodes the name of the executable,
            # unlike other tools that use the PKG_CONFIG environment variable
            # if we are aware the user has requested a specific pkg-config, we pass it to the configure script
            args.append(f"--pkg-config={unix_path(self, pkg_config)}")
        if is_msvc(self):
            args.append("--toolchain=msvc")
            if not check_min_vs(self, "190", raise_invalid=False):
                # Visual Studio 2013 (and earlier) doesn't support "inline" keyword for C (only for C++)
                tc.extra_defines.append("inline=__inline")
        if cross_building(self):
            args.append(f"--target-os={self._target_os}")
            if is_apple_os(self) and self.options.with_audiotoolbox:
                args.append("--disable-outdev=audiotoolbox")
            # ffmpeg builds and RUNS small helper tools (e.g. bin2c, which embeds the CLI's
            # graph.html/css resources) with its "host" compiler during the build. The default
            # host compiler is gcc, absent from the MSVC toolchain, and simply reusing the target
            # cl produces ARM64 helpers that cannot run on the x64 build host ("Exec format
            # error"). Point --host-cc at a wrapper that builds helper tools with the x64 host cl
            # (sibling of the arm64 cross cl) and x64 import libraries, yielding runnable helpers.
            if is_msvc(self) and cc:
                args.append(f"--host-cc={unix_path(self, self._write_host_cc_wrapper())}")

        if tc.cflags:
            cflags = tc.cflags
            if is_msvc(self):
                # AutotoolsToolchain injects -fPIC, a GCC/Clang concept. MSVC's cl merely warns
                # and ignores it (D9002), but ffmpeg also forwards --extra-cflags to the ARM
                # assembler (armasm64 via gas-preprocessor), which hard-errors on it (A2029).
                # Windows code is always position independent, so drop this GCC-only flag.
                cflags = [f for f in cflags if f != "-fPIC"]
            args.append(f"--extra-cflags={" ".join(cflags)}")
        if tc.ldflags:
            args.append(f"--extra-ldflags={" ".join(tc.ldflags)}")
        tc.configure_args.extend(args)
        tc.generate()

        if is_msvc(self):
            # Custom AutotoolsDeps for cl like compilers
            # workaround for upstream issue 12784
            includedirs: list[str] = []
            defines: list[str] = []
            libs: list[str] = []
            libdirs: list[str] = []
            linkflags: list[str] = []
            cxxflags: list[str] = []
            cflags: list[str] = []
            for dependency in self.dependencies.values():
                deps_cpp_info = dependency.info.aggregated_components()
                includedirs.extend(deps_cpp_info.includedirs)
                defines.extend(deps_cpp_info.defines)
                libs.extend(deps_cpp_info.libs + deps_cpp_info.system_libs)
                libdirs.extend(deps_cpp_info.libdirs)
                linkflags.extend(deps_cpp_info.sharedlinkflags + deps_cpp_info.exelinkflags)
                cxxflags.extend(deps_cpp_info.cxxflags)
                cflags.extend(deps_cpp_info.cflags)

            env = Environment()
            env.append("CPPFLAGS", [f"-I{unix_path(self, p)}" for p in includedirs] + [f"-D{d}" for d in defines])
            env.append("LDFLAGS", [f"-LIBPATH:{unix_path(self, p)}" for p in libdirs] + linkflags)
            env.append("CXXFLAGS", cxxflags)
            env.append("CFLAGS", cflags)
            env.vars(self).save_script("autotoolsdeps_cl_workaround")
        else:
            deps = AutotoolsDeps(self)
            deps.generate()

        deps = PkgConfigDeps(self)
        deps.set_property("whisper-cpp", "pkg_config_name", "whisper")
        deps.set_property("openapv", "pkg_config_name", "oapv")
        deps.generate()

        # Ensure .pc files generated by PkgConfigDeps are discoverable by pkg-config
        env_pkg = Environment()
        env_pkg.prepend_path("PKG_CONFIG_PATH", self.folders.generators)
        env_pkg.vars(self, scope="build").save_script("pkgconfigpath")

        if self.options.with_ssl == "openssl":
            openssl_cpp = self.dependencies["openssl"].info.aggregated_components()
            # Include system_libs (crypt32, ws2_32, ... on Windows) so configure's check_lib
            # link test for DTLS_get_data_mtu can actually resolve openssl's symbols.
            openssl_libs = " ".join([f"-l{lib}" for lib in openssl_cpp.libs] + [f"-l{lib}" for lib in openssl_cpp.system_libs])
            save(self, self.folders.build / "openssl_libs.list", openssl_libs)

    def build(self):
        self._patch_sources()
        if self.options.with_libx264:
            # ffmepg expects libx264.pc instead of x264.pc
            with chdir(self, self.folders.generators):
                shutil.copy("x264.pc", "libx264.pc")
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "LICENSE.md", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")
        if is_msvc(self):
            if self.options.shared:
                # ffmpeg created `.lib` files in the `/bin` folder
                for fn in os.listdir(self.folders.package / "bin"):
                    if fn.endswith(".lib"):
                        rename(
                            self, self.folders.package / "bin" / fn,
                            self.folders.package / "lib" / fn)
                rm(self, "*.def", self.folders.package / "lib")
            else:
                # ffmpeg produces `.a` files that are actually `.lib` files
                with chdir(self, self.folders.package / "lib"):
                    for lib in glob.glob("*.a"):
                        rename(self, Path(lib), Path(lib[3:-2] + ".lib"))

    def package_info(self):
        if self.options.with_programs:
            if self.options.with_sdl:
                self.info.components["programs"].requires = ["sdl::libsdl2"]

        def _add_component(name: str, dependencies: list[str]):
            component = self.info.components[name]
            component.set_property("pkg_config_name", f"lib{name}")
            self._set_component_version(name)
            component.libs = [name]
            if name != "avutil":
                component.requires = ["avutil"]
            for dep in dependencies:
                if self.options.get_safe(dep):
                    component.requires.append(dep)
            if self.settings.os in ("FreeBSD", "Linux"):
                component.system_libs.append("m")
            return component

        # These components are created and consumed under matching ``self.options.<name>`` guards;
        # initialize them so the (separate) consumer guards don't read a possibly-unbound name.
        avdevice: Any = None
        avfilter: Any = None
        avformat: Any = None
        avcodec: Any = None
        avutil = _add_component("avutil", [])
        if self.options.avdevice:
            avdevice = _add_component("avdevice", ["avfilter", "swscale", "avformat", "avcodec", "swresample", "postproc"])
        if self.options.avfilter:
            avfilter = _add_component("avfilter", ["swscale", "avformat", "avcodec", "swresample", "postproc"])
        if self.options.avformat:
            avformat = _add_component("avformat", ["avcodec", "swscale"])
        if self.options.avcodec:
            avcodec = _add_component("avcodec", ["swresample"])
        if self.options.swscale:
            _add_component("swscale", [])
        if self.options.swresample:
            swresample = _add_component("swresample", [])
            if self.options.with_soxr:
                swresample.requires.append("soxr::soxr")
        if self.options.postproc:
            _add_component("postproc", [])

        if self.settings.os in ("FreeBSD", "Linux"):
            avutil.system_libs.extend(["pthread", "dl"])
            if self.options.pic and self.options.avcodec and self.settings.compiler in ("gcc", "clang"):
                # https://trac.ffmpeg.org/ticket/1713
                # https://ffmpeg.org/platform.html#Advanced-linking-configuration
                # https://ffmpeg.org/pipermail/libav-user/2014-December/007719.html
                avcodec.exelinkflags.append("-Wl,-Bsymbolic")
                avcodec.sharedlinkflags.append("-Wl,-Bsymbolic")
            if self.options.avfilter:
                avfilter.system_libs.append("pthread")
        elif self.settings.os == "Windows":
            if self.options.avcodec:
                avcodec.system_libs = ["mfplat", "mfuuid", "strmiids"]
            if self.options.avdevice:
                avdevice.system_libs = ["ole32", "psapi", "strmiids", "uuid", "oleaut32", "shlwapi", "gdi32", "vfw32"]
            avutil.system_libs = ["user32", "bcrypt"]
            if self.options.avformat:
                avformat.system_libs = ["secur32"]
        elif is_apple_os(self):
            if self.options.avdevice:
                avdevice.frameworks = ["CoreFoundation", "Foundation", "CoreGraphics"]
            if self.options.avfilter:
                avfilter.frameworks = ["CoreGraphics"]
            if self.options.avcodec:
                avcodec.frameworks = ["CoreFoundation", "CoreVideo", "CoreMedia"]
            if self.settings.os == "Mac":
                if self.options.avdevice:
                    avdevice.frameworks.append("OpenGL")
                if self.options.avfilter:
                    avfilter.frameworks.append("OpenGL")

        if self.options.avdevice:
            if self.options.with_libalsa:
                avdevice.requires.append("libalsa::libalsa")
            if self.options.with_xcb:
                avdevice.requires.extend(["libxcb::xcb", "libxcb::shm", "libxcb::xfixes", "libxcb::shape", "libxv::libxv", "libxext::libxext"])
            if self.options.with_xlib:
                avdevice.requires.extend(["libx11::x11", "libxext::libxext", "libxv::libxv"])
            if self.options.with_pulse:
                avdevice.requires.append("pulseaudio::pulseaudio")
            if self.options.with_appkit:
                avdevice.frameworks.append("AppKit")
            if self.options.with_avfoundation:
                avdevice.frameworks.append("AVFoundation")
            if self.options.with_audiotoolbox:
                avdevice.frameworks.append("CoreAudio")
            if self.settings.os == "Android" and not self.options.shared:
                avdevice.system_libs.extend(["android", "camera2ndk", "mediandk"])

        if self.options.avcodec:
            if self.options.with_zlib:
                avcodec.requires.append("zlib::zlib")
            if self.options.with_lzma:
                avcodec.requires.append("xz::xz")
            if self.options.with_libiconv:
                avcodec.requires.append("libiconv::libiconv")
            if self.options.with_libxml2:
                avcodec.requires.append("libxml2::libxml2")
            if self.options.with_openjpeg:
                avcodec.requires.append("openjpeg::openjpeg")
            if self.options.with_openh264:
                avcodec.requires.append("openh264::openh264")
            if self.options.with_vorbis:
                avcodec.requires.append("vorbis::vorbis")
            if self.options.with_opus:
                avcodec.requires.append("opus::opus")
            if self.options.with_libx264:
                avcodec.requires.append("x264::x264")
            if self.options.with_libx265:
                avcodec.requires.append("x265::x265")
            if self.options.with_libvpx:
                avcodec.requires.append("libvpx::libvpx")
            if self.options.with_libmp3lame:
                avcodec.requires.append("libmp3lame::libmp3lame")
            if self.options.with_libfdk_aac:
                avcodec.requires.append("fdk-aac::fdk-aac")
            if self.options.with_libwebp:
                avcodec.requires.append("libwebp::libwebp")
            if self.options.with_audiotoolbox:
                avcodec.frameworks.append("AudioToolbox")
            if self.options.with_videotoolbox:
                avcodec.frameworks.append("VideoToolbox")
            if self.options.with_libsvtav1:
                avcodec.requires.append("svt-av1::encoder")
            if self.options.with_libaom:
                avcodec.requires.append("aom::aom")
            if self.options.with_libdav1d:
                avcodec.requires.append("dav1d::dav1d")
            if self.options.with_libjxl:
                avcodec.requires.append("libjxl::libjxl")
            if self.options.with_openapv:
                avcodec.requires.append("openapv::openapv")

        if self.options.avformat:
            if self.options.with_bzip2:
                avformat.requires.append("bzip2::bzip2")
            if self.options.with_zeromq:
                avformat.requires.append("zeromq::libzmq")
            if self.options.with_ssl == "openssl":
                avformat.requires.append("openssl::ssl")
            elif self.options.with_ssl == "securetransport":
                avformat.frameworks.append("Security")

        if self.options.avfilter:
            if self.options.with_freetype:
                avfilter.requires.append("freetype::freetype")
            if self.options.with_fontconfig:
                avfilter.requires.append("fontconfig::fontconfig")
            if self.options.with_fribidi:
                avfilter.requires.append("fribidi::fribidi")
            if self.options.with_harfbuzz:
                avfilter.requires.append("harfbuzz::harfbuzz")
            if self.options.with_zeromq:
                avfilter.requires.append("zeromq::libzmq")
            if self.options.with_appkit:
                avfilter.frameworks.append("AppKit")
            if self.options.with_coreimage:
                avfilter.frameworks.append("CoreImage")
            if is_apple_os(self):
                avfilter.frameworks.append("Metal")
            if self.options.with_whisper:
                avfilter.requires.append("whisper-cpp::whisper-cpp")

        if self.options.with_libdrm:
            avutil.requires.append("libdrm::libdrm_libdrm")
        if self.options.with_vaapi:
            avutil.requires.append("vaapi::vaapi")
        if self.options.with_xcb:
            avutil.requires.append("libx11::x11")

        if self.options.with_vdpau:
            avutil.requires.append("vdpau::vdpau")

        if self.options.with_ssl == "openssl":
            avutil.requires.append("openssl::ssl")

        if self.options.with_vulkan:
            avutil.requires.append("vulkan-loader::vulkan-loader")

    @property
    def _dependencies(self):
        return {
            "avformat": ["avcodec"],
            "avdevice": ["avcodec", "avformat"],
            "avfilter": ["avformat"],
            "with_bzip2": ["avformat"],
            "with_ssl": ["avformat"],
            "with_zlib": ["avcodec"],
            "with_lzma": ["avcodec"],
            "with_libiconv": ["avcodec"],
            "with_libxml2": ["avcodec"],
            "with_libjxl": ["avcodec"],
            "with_openapv": ["avcodec"],
            "with_openjpeg": ["avcodec"],
            "with_openh264": ["avcodec"],
            "with_vorbis": ["avcodec"],
            "with_opus": ["avcodec"],
            "with_libx264": ["avcodec"],
            "with_libx265": ["avcodec"],
            "with_libvpx": ["avcodec"],
            "with_libmp3lame": ["avcodec"],
            "with_libfdk_aac": ["avcodec"],
            "with_libwebp": ["avcodec"],
            "with_freetype": ["avfilter"],
            "with_fontconfig": ["avfilter"],
            "with_fribidi": ["avfilter"],
            "with_harfbuzz": ["avfilter"],
            "with_zeromq": ["avfilter", "avformat"],
            "with_libalsa": ["avdevice"],
            "with_xcb": ["avdevice"],
            "with_soxr": ["swresample"],
            "with_pulse": ["avdevice"],
            "with_sdl": ["with_programs"],
            "with_libsvtav1": ["avcodec"],
            "with_libaom": ["avcodec"],
            "with_libdav1d": ["avcodec"],
            "with_mediacodec": ["with_jni"],
            "with_xlib": ["avdevice"],
            "with_whisper": ["avfilter"],
        }

    @property
    def _target_arch(self):
        # Taken from acceptable values https://github.com/FFmpeg/FFmpeg/blob/0684e58886881a998f1a7b510d73600ff1df2b90/configure#L5010
        if self.settings.arch == "ARM":
            return "aarch64"
        elif self.settings.arch == "X64":
            return "x86_64"
        return str(self.settings.arch)

    @property
    def _target_os(self):
        if self.settings.os == "Windows":
            return "mingw32" if self.settings.compiler == "gcc" else "win32"
        elif is_apple_os(self):
            return "darwin"

        # Taken from https://github.com/FFmpeg/FFmpeg/blob/0684e58886881a998f1a7b510d73600ff1df2b90/configure#L5485
        # This is the map of Recipe OS settings to FFmpeg acceptable values
        return {
            "AIX": "aix",
            "Android": "android",
            "FreeBSD": "freebsd",
            "Linux": "linux",
            "Neutrino": "qnx",
            "SunOS": "sunos",
        }.get(str(self.settings.os), "none")

    def _patch_sources(self):
        if self.options.with_ssl == "openssl":
            # https://trac.ffmpeg.org/ticket/5675
            openssl_libs = load(self, self.folders.build / "openssl_libs.list")
            replace_in_file(
                self,
                self.folders.source / "configure",
                "check_lib openssl openssl/ssl.h DTLS_get_data_mtu -lssl -lcrypto ||",
                f"check_lib openssl openssl/ssl.h DTLS_get_data_mtu {openssl_libs} ||",
                strict=False)

            # replace_in_file(self, self.folders.source / "configure", "echo libx264.lib", "echo x264.lib")

        if is_msvc(self) and not self.conf.tools.compilation.verbose:
            # ffmpeg's configure adds -Wall/-Wextra by default and its cl wrapper (msvc_flags)
            # maps them to /W3 and /W4, which conflict with the quiet -w -> "D9025: overriding
            # '/w' with '/W3'|'/W4'" for ~every source file. Drop just the /W level (keep the -wd
            # warning suppressions) so the injected -w wins.
            replace_in_file(
                self, self.folders.source / "configure",
                "echo -W3 -wd4018 -wd4146", "echo -wd4018 -wd4146", strict=False)
            replace_in_file(
                self, self.folders.source / "configure",
                "echo -W4 -wd4244 -wd4127", "echo -wd4244 -wd4127", strict=False)

    @property
    def _default_compilers(self) -> dict[str, str]:
        if self.settings.compiler == "gcc":
            return {"cc": "gcc", "cxx": "g++"}
        elif self.settings.compiler in ["clang", "apple-clang"]:
            return {"cc": "clang", "cxx": "clang++"}
        elif is_msvc(self):
            return {"cc": "cl.exe", "cxx": "cl.exe"}
        return {}

    def _write_host_cc_wrapper(self) -> Path:
        # Written for msys2 /bin/sh. During the build the environment is the amd64_arm64 vcvars,
        # so cl.exe on PATH targets arm64 (.../bin/Hostx64/arm64/cl.exe) and LIB points at the
        # arm64 import libraries. The sibling .../bin/Hostx64/x64/cl.exe targets x64, and the x64
        # import libraries live at the same paths with "arm64" replaced by "x64". INCLUDE is
        # architecture independent, so it needs no change. The wrapper rewrites both at runtime so
        # ffmpeg's helper tools (bin2c, ...) are built as runnable x64 executables.
        wrapper = self.folders.generators / "ffmpeg_host_cc.sh"
        content = (
            "#!/bin/sh\n"
            'target_cl="$(command -v cl.exe)"\n'
            'host_cl="$(dirname "$(dirname "$target_cl")")/x64/cl.exe"\n'
            '[ -x "$host_cl" ] || host_cl="$target_cl"\n'
            "LIB=\"$(printf %s \"$LIB\" | sed 's/arm64/x64/gI')\"\n"
            "export LIB\n"
            'exec "$host_cl" -nologo "$@"\n'
        )
        with open(wrapper, "w", newline="\n") as f:
            f.write(content)
        os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return wrapper

    def _create_toolchain(self):
        tc = AutotoolsToolchain(self)
        # Custom configure script of ffmpeg understands:
        # --prefix, --bindir, --datadir, --docdir, --incdir, --libdir, --mandir
        # Options --datadir, --docdir, --incdir, and --mandir are not injected by AutotoolsToolchain  but their default value
        # in ffmpeg script matches expected recipe install layout.
        # Several options injected by AutotoolsToolchain are unknown from this configure script and must be pruned.
        # This must be done before modifying tc.configure_args, because update_configre_args currently removes
        # duplicate configuration keys, even when they have different values, such as list of encoder flags.
        # See https://github.com/recipe-io/recipe-center-index/issues/17140 for further information.
        tc.update_configure_args(
            {
                "--sbindir": None,
                "--includedir": None,
                "--oldincludedir": None,
                "--datarootdir": None,
                "--build": None,
                "--host": None,
                "--target": None,
            })
        return tc

    def _split_and_format_options_string(self, flag_name: str, options_list: Any) -> list[str]:
        if not options_list:
            return []

        def _format_options_list_item(flag_name: str, options_item: str) -> str:
            return f"--{flag_name}={options_item}"

        def _split_options_string(options_string: str) -> list[str]:
            return list(filter(None, "".join(options_string.split()).split(",")))

        options_string = str(options_list)
        return [_format_options_list_item(flag_name, item) for item in _split_options_string(options_string)]

    def _read_component_version(self, component_name: str):
        # since 5.1, major version may be defined in version_major.h instead of version.h
        component_folder = self.folders.package / "include" / f"lib{component_name}"
        version_file_name = component_folder / "version.h"
        version_major_file_name = component_folder / "version_major.h"
        pattern = f"define LIB{component_name.upper()}_VERSION_(MAJOR|MINOR|MICRO)[ \t]+(\\d+)"
        version: dict[str, str] = {}
        for file in (version_file_name, version_major_file_name):
            if os.path.isfile(file):
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        match = re.search(pattern, line)
                        if match:
                            version[match[1]] = match[2]
        if "MAJOR" in version and "MINOR" in version and "MICRO" in version:
            return f"{version["MAJOR"]}.{version["MINOR"]}.{version["MICRO"]}"
        return None

    def _set_component_version(self, component_name: str):
        version = self._read_component_version(component_name)
        if version is not None:
            self.info.components[component_name].set_property("component_version", version)
            # TODO: to remove once support of recipe v1 dropped
            self.info.components[component_name].version = version
        else:
            self.output.warning(f"cannot determine version of lib{component_name} packaged with ffmpeg!")
