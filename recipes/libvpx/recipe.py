import re

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.build import stdcpp_library
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, rename, replace_in_file, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime, msvc_runtime_flag
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    mmx: bool = True
    sse: bool = True
    sse2: bool = True
    sse3: bool = True
    ssse3: bool = True
    sse4_1: bool = True
    avx: bool = False
    avx2: bool = False
    avx512: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libvpx"
    version = "1.16.0"
    license = "BSD-3-Clause"

    _arch_options = ["mmx", "sse", "sse2", "sse3", "ssse3", "sse4_1", "avx", "avx2", "avx512"]

    def latest_version(self):
        repo = GithubRepository(self, "webmproject/libvpx")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.arch not in ["X64"]:
            for name in self._arch_options:
                setattr(self.options, name, False)

        if self.settings.os == "Windows":
            self.options.shared = False
        if self.settings.os == "Android":
            self.options.shared = False

    def requirements(self):
        if self.settings.arch == "X64":
            self.requires_tool("nasm")
        if self.settings.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://github.com/webmproject/libvpx/archive/refs/tags/v{self.version}.tar.gz",
            sha256="7a479a3c66b9f5d5542a4c6a1b7d3768a983b1e5c14c60a9396edc9b649e015c",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)

        if is_apple_os(self) and self.settings.compiler_libcxx == "libc++":
            # special case, as gcc/g++ is hard-coded in makefile, it implicitly assumes -lstdc++
            tc.extra_ldflags.append("-stdlib=libc++")

        tc.configure_args.extend(
            [
                "--disable-examples",
                "--disable-unit-tests",
                "--disable-tools",
                "--disable-docs",
                "--enable-vp9-highbitdepth",
                "--as=nasm",
            ])
        # Note for MSVC: release libs are always built, we just avoid keeping the release lib
        # Note2: Can't use --enable-debug_libs (to help install on Windows),
        #     the makefile's install step fails as it wants to install a library that doesn't exist.
        #     Instead, we will copy the desired library manually in the package step.
        if self.settings.build_type == "Debug":
            tc.configure_args.extend(
                [
                    "--enable-debug",
                ])
        if is_msvc(self) and is_msvc_static_runtime(self):
            tc.configure_args.append("--enable-static-msvcrt")
        if str(self.settings.arch) in ["X64"]:
            for name in self._arch_options:
                if not getattr(self.options, name):
                    tc.configure_args.append(f"--disable-{name}")

        tc.update_configure_args(
            {
                # libvpx does not like --prefix=/ as it fails the test for "libdir
                # must be a subfolder of prefix" libvpx src/build/make/configure.sh:683
                "--prefix": f"/{self._install_tmp_folder}",
                "--libdir": f"/{self._install_tmp_folder}/lib",
                # Needed to let libvpx use the correct toolchain for the target platform
                "--target": self._target_name,
                # several options must not be injected as custom configure doesn't like them
                "--host": None,
                "--build": None,
                "--bindir": None,
                "--sbindir": None,
                "--includedir": None,
                "--oldincludedir": None,
                "--datarootdir": None,
            })

        if is_msvc(self):
            # gen_msvs_vcxproj.sh doesn't like custom flags
            env = Environment()
            env.define("CC", "")
        else:
            env = tc.environment()
        tc.generate(env)

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, pattern="LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()

        # The workaround requires us to move the outputs into place now
        rename(
            self,
            self.folders.package / self._install_tmp_folder / "include",
            self.folders.package / "include"
            )

        if is_msvc(self):
            # Libs are still in the build folder, get from there directly.
            # The makefile cannot correctly install the debug libs (see note about --enable-debug_libs)
            system = {"ARM": "ARM64"}
            libs_from = self.folders.build / system.get(str(self.settings.arch), "x64") / ("Debug" if self.settings.build_type == "Debug" else "Release")
            # Copy for msvc, as it will generate a release and debug library, so take what we want
            # Note that libvpx's configure/make doesn't support shared lib builds on windows yet.
            copy(self, f"{self._lib_name}.lib", libs_from, self.folders.package / "lib")
        else:
            # if not msvc, then libs were installed into package (in the wrong place), move them
            libs_from = self.folders.package / self._install_tmp_folder / "lib"
            rename(self, libs_from, self.folders.package / "lib")

        rmdir(self, self.folders.package / self._install_tmp_folder)
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("pkg_config_name", "vpx")
        self.info.libs = [self._lib_name]
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["m", "pthread"])

    @property
    def _install_tmp_folder(self):
        return "tmp_install"

    @property
    def _target_name(self):
        arch = {
            "X64": "x86_64",
            "ARM": "arm64",
        }.get(str(self.settings.arch))
        if arch is None:
            # Fallback for unknown architectures. This is supported by upstream to be used
            # when no specific target set is provided by the configure script.
            return "generic-gnu"

        compiler = str(self.settings.compiler)
        os_name = str(self.settings.os)
        if str(self.settings.compiler) == "Visual Studio":
            vc_version = self.settings.compiler_version
            compiler = f"vs{vc_version}"
        elif is_msvc(self):
            vc_version = str(self.settings.compiler_version)
            vc_version = {"170": "11", "180": "12", "190": "14", "191": "15", "192": "16", "193": "17", "194": "17", "195": "18"}[vc_version]
            compiler = f"vs{vc_version}"
        elif self.settings.compiler in ["gcc", "clang", "apple-clang"]:
            compiler = "gcc"
        host_os = str(self.settings.os)
        if host_os == "Windows":
            os_name = "win64"
        elif is_apple_os(self):
            if self.settings.arch in ["X64"]:
                if self.settings.os == "Mac":
                    os_name = f"darwin11"
                else:
                    os_name = "iphonesimulator"
            elif self.settings.arch == "ARM":
                os_name = "darwin21"
            else:
                os_name = "darwin"
        elif host_os == "Linux":
            os_name = "linux"
        elif host_os == "Solaris":
            os_name = "solaris"
        elif host_os == "Android":
            os_name = "android"
        return f"{arch}-{os_name}-{compiler}"

    def _patch_sources(self):
        apply_patches(self)

        # Disable LTO for Visual Studio when CFLAGS doesn't contain -GL
        if is_msvc(self):
            # nasm 3.02's CodeView writer (-gcv8) crashes (access violation) assembling
            # libvpx's .asm, corrupting the .obj -> LNK1136. libvpx only requests -gcv8 for the
            # Debug config, which is built alongside Release even for a Release build_type, so
            # drop it (Debug asm just loses CodeView line info, matching the Release command).
            replace_in_file(
                self,
                self.folders.source / "build" / "make" / "gen_msvs_vcxproj.sh",
                "-Xvc -gcv8 -f",
                "-Xvc -f",
                strict=False)

            # msbuild defaults to "normal" verbosity, which dumps every task/target for the whole
            # solution. Quiet the generated build rule down to errors/warnings unless asked to be
            # verbose.
            if not self.conf.tools.compilation.verbose:
                replace_in_file(
                    self,
                    self.folders.source / "build" / "make" / "gen_msvs_sln.sh",
                    "\\$(MSBUILD_TOOL) $outfile -m -t:Build",
                    "\\$(MSBUILD_TOOL) $outfile -m -nologo -v:quiet -t:Build",
                    strict=False)
                # The generated vcxproj hard-codes WarningLevel Level3 (/W3), which conflicts with
                # the framework's injected -w -> "D9025: overriding '/w' with '/W3'" for every one
                # of libvpx's ~thousand source files. Turn warnings off to match quiet mode.
                replace_in_file(
                    self,
                    self.folders.source / "build" / "make" / "gen_msvs_vcxproj.sh",
                    "tag_content WarningLevel Level3",
                    "tag_content WarningLevel TurnOffAllWarnings",
                    strict=False)

            cflags = " ".join(self.conf.tools.build.cflags)
            lto = any(re.finditer("(^| )[/-]GL($| )", cflags))
            if not lto:
                self.output.info("Disabling LTO")
                replace_in_file(
                    self,
                    self.folders.source / "build" / "make" / "gen_msvs_vcxproj.sh",
                    "tag_content WholeProgramOptimization true",
                    "tag_content WholeProgramOptimization false",
                    strict=False)
            else:
                self.output.info("Enabling LTO")

        # The compile script wants to use CC for some of the platforms (Linux, etc),
        # but incorrectly assumes gcc is the compiler for those platforms.
        # This can fail some of the configure tests, and -lpthread isn't added to the link command.
        replace_in_file(
            self,
            self.folders.source / "build" / "make" / "configure.sh",
            "  LD=${LD:-${CROSS}${link_with_cc:-ld}}",
            """
  LD=${LD:-${CROSS}${link_with_cc:-ld}}
  if [ "${link_with_cc}" = "gcc" ]
  then
   echo "using compiler as linker"
   LD=${CC}
  fi
"""
            )

    @property
    def _lib_name(self):
        suffix = msvc_runtime_flag(self).lower() if is_msvc(self) else ""
        return f"vpx{suffix}"
