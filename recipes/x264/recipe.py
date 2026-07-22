import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, XCRun, fix_apple_shared_install_name
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import copy, rename, get, rmdir, chdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import GitlabRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "x264"
    version = "20250910"
    license = "GPL-2.0"

    def latest_version(self):
        repo = GitlabRepository(self, "videolan/x264", host="code.videolan.org")
        return Version(repo.latest_commit_date("master"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if self._with_nasm:
            self.requires_tool("nasm")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url="https://code.videolan.org/videolan/x264/-/archive/0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee/x264-0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee.tar.bz2",
            sha256="f05c59f2e83d494c36307025dca2d3afc6b4d185f3a3453d06cc4fecd7094057",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)

        extra_asflags: list[str] = []
        extra_cflags: list[str] = []
        extra_ldflags: list[str] = []
        args = {
            "--bit-depth": "all",
            "--disable-cli": "",
            "--sbindir": None,  # Not understood by configure
            "--oldincludedir": None,  # Not understood by configure
        }
        args["--disable-shared"] = None  # --disable-shared is not understood
        if self.options.shared:
            args["--enable-shared"] = ""
        else:
            args["--enable-static"] = ""
        if self.options.pic and self.settings.os != "Windows":
            args["--enable-pic"] = ""
        if self.settings.build_type == "Debug":
            args["--enable-debug"] = ""

        if is_apple_os(self) and self.settings.arch == "ARM":
            # bitstream-a.S:29:18: error: unknown token in expression
            extra_asflags.append("-arch arm64")
            extra_ldflags.append("-arch arm64")
            args["--host"] = "aarch64-apple-darwin"
            if self.settings.os != "Mac":  # TODO not sure why this is != "Macos" ... shouldn't it be == ??
                xcrun = XCRun(self)
                platform_flags = ["-isysroot", xcrun.sdk_path]
                apple_min_version_flag = AutotoolsToolchain(self).apple_min_version_flag
                if apple_min_version_flag:
                    platform_flags.append(apple_min_version_flag)
                extra_asflags.extend(platform_flags)
                extra_cflags.extend(platform_flags)
                extra_ldflags.extend(platform_flags)

        if self._with_nasm:
            env = Environment()
            nasm_exe: str = "nasm{}".format(".exe" if self.settings.os == "Windows" else "")
            as_path = unix_path(self, self.dependencies.build["nasm"].folders.package / "bin" / nasm_exe)
            env.define("AS", as_path or "")
            env.vars(self).save_script("buildenv_nasm")

        if is_msvc(self):
            env = Environment()
            env.define("CC", "cl -nologo")
            env.vars(self).save_script("buildenv_msvc")

        if is_msvc(self) or self.settings.os in ["iOS", "watchOS", "tvOS"]:
            # autotools does not know about the msvc and Apple embedded OS canonical name(s)
            args["--build"] = None
            args["--host"] = None

        # The finite-math-only optimization has no effect and can cause linking errors
        # when linked against glibc >= 2.31
        extra_cflags += ["-fno-finite-math-only"]

        if extra_asflags:
            args["--extra-asflags"] = " ".join(extra_asflags)
        if extra_cflags:
            args["--extra-cflags"] = " ".join(extra_cflags)
        if extra_ldflags:
            args["--extra-ldflags"] = " ".join(extra_ldflags)
        tc.update_configure_args(args)
        tc.generate()

    def build(self):
        with chdir(self, self.folders.source):
            autotools = Autotools(self)
            autotools.configure()
            autotools.make()

    def package(self):
        copy(self, pattern="COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        with chdir(self, self.folders.source):
            autotools = Autotools(self)
            autotools.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        if is_msvc(self):
            ext = ".dll.lib" if self.options.shared else ".lib"
            libdir = self.folders.package / "lib"
            rename(
                self, libdir / f"libx264{ext}",
                libdir / "x264.lib")
            # ffmpeg's MSVC configure hardcodes `-lx264` -> `libx264.lib` (x264's native
            # MSVC library name; see ffmpeg's configure msvc_flags filter).  Provide that
            # name as well so such consumers link successfully, while keeping x264.lib for
            # pkg-config (`-lx264`) / CMake consumers.
            shutil.copy2(libdir / "x264.lib",
                         libdir / "libx264.lib")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "x264")
        self.info.set_property("cmake_target_name", "x264::x264")
        self.info.set_property("pkg_config_name", "x264")
        self.info.libs = ["x264"]
        if is_msvc(self) and self.options.shared:
            self.info.defines.append("X264_API_IMPORTS")
        if self.settings.os in ["FreeBSD", "Linux"]:
            self.info.system_libs.extend(["dl", "pthread", "m"])
        elif self.settings.os == "Android":
            self.info.system_libs.extend(["dl", "m"])

    @property
    def _with_nasm(self):
        return self.settings.arch in ("X64",)
