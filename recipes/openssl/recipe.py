import fnmatch
import os
from pathlib import Path
import textwrap
from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os, XCRun
from thirdparty.build import build_jobs
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import chdir, copy, get, replace_in_file, rm, rmdir, save
from thirdparty.autotools import AutotoolsToolchain
from thirdparty.microsoft import is_msvc, msvc_runtime_flag, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    enable_weak_ssl_ciphers: bool = False
    capieng_dialog: bool = False
    enable_capieng: bool = False
    enable_trace: bool = False
    no_aria: bool = False
    no_apps: bool = False
    no_autoload_config: bool = False
    no_asm: bool = False
    no_async: bool = False
    no_blake2: bool = False
    no_bf: bool = False
    no_camellia: bool = False
    no_chacha: bool = False
    no_cms: bool = False
    no_comp: bool = False
    no_ct: bool = False
    no_cast: bool = False
    no_deprecated: bool = False
    no_des: bool = False
    no_dgram: bool = False
    no_dh: bool = False
    no_dsa: bool = False
    no_dso: bool = False
    no_ec: bool = False
    no_ecdh: bool = False
    no_ecdsa: bool = False
    no_engine: bool = False
    no_filenames: bool = False
    no_fips: bool = False
    no_gost: bool = False
    no_idea: bool = False
    no_legacy: bool = False
    no_md2: bool = True
    no_md4: bool = False
    no_mdc2: bool = False
    no_module: bool = False
    no_ocsp: bool = False
    no_pinshared: bool = False
    no_rc2: bool = False
    no_rc4: bool = False
    no_rc5: bool = False
    no_rfc3779: bool = False
    no_rmd160: bool = False
    no_sm2: bool = False
    no_sm3: bool = False
    no_sm4: bool = False
    no_srp: bool = False
    no_srtp: bool = False
    no_sse2: bool = False
    no_ssl: bool = False
    no_stdio: bool = False
    no_seed: bool = False
    no_sock: bool = False
    no_ssl3: bool = False
    no_threads: bool = False
    no_tls1: bool = False
    no_ts: bool = False
    no_whirlpool: bool = False
    no_zlib: bool = False
    openssldir: str | None = None
    tls_security_level: Literal[None, 0, 1, 2, 3, 4, 5] = None


_Options.__annotations__["386"] = bool
_Options.__defaults__ = {"386": False}


class Recipe(RecipeBase[_Options]):
    name = "openssl"
    version = "3.6.3"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "openssl/openssl")
        return Version(repo.latest_release.removeprefix("openssl-"))

    def configure(self):
        if self.settings.os != "Windows":
            self.options.capieng_dialog = False
            self.options.enable_capieng = False

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if not self.options.no_zlib:
            self.requires("zlib")
        if self.settings_build.os == "Windows":
            self.requires_tool("jom")
            if not self.options.no_asm and self.settings.arch == "X64":
                self.requires_tool("nasm")
            if self._use_nmake:
                self.requires_tool("strawberryperl")
            else:
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://github.com/openssl/openssl/releases/download/openssl-{self.version}/openssl-{self.version}.tar.gz",
            sha256="243a86649cf6f23eeb6a2ff2456e09e5d77dd9018a54d3d96b0c6bdd6ba6c7f1",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)
        env = tc.environment()
        if self._use_nmake:
            env.define("CC", "cl")
            env.define("CXX", "cl")
            env.define("LD", "link")
        env.define_path("PERL", self._perl)
        if self.settings.compiler == "apple-clang":
            xcrun = XCRun(self)
            env.define_path("CROSS_SDK", os.path.basename(xcrun.sdk_path))
            env.define_path("CROSS_TOP", os.path.dirname(os.path.dirname(xcrun.sdk_path)))

        if is_apple_os(self) and self.options.shared:
            # Inject -headerpad_max_install_names for shared library, otherwise fix_apple_shared_install_name() may fail.
            # See https://github.com/recipe-io/recipe-center-index/issues/27424
            tc.extra_ldflags.append("-headerpad_max_install_names")

        self._create_targets(tc.cflags, tc.cxxflags, tc.defines, tc.ldflags)
        tc.generate(env)

    def build(self):
        self._make()
        configdata_pm = self._adjust_path(self.folders.source / "configdata.pm")
        run(self,f"{self._perl} {configdata_pm} --dump")

    def package(self):
        copy(self, "*LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        self._make_install()
        if is_apple_os(self):
            fix_apple_shared_install_name(self)

        rm(self, "*.pdb", self.folders.package / "lib")
        if self.options.shared:
            libdir = self.folders.package / "lib"
            for file in os.listdir(libdir):
                if self._is_mingw and file.endswith(".dll.a"):
                    continue
                if file.endswith(".a"):
                    os.unlink(libdir / file)

        if not self.options.no_fips:
            provdir = self.folders.source / "providers"
            modules_dir = self.folders.package / "lib" / "ossl-modules"
            if self.settings.os == "Mac":
                copy(self, "fips.dylib", src=provdir, dst=modules_dir)
            elif self.settings.os == "Windows":
                copy(self, "fips.dll", src=provdir, dst=modules_dir)
            else:
                copy(self, "fips.so", src=provdir, dst=modules_dir)

        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

        self._create_cmake_module_variables(self.folders.package / self._module_file_rel_path)

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenSSL")
        self.info.set_property("pkg_config_name", "openssl")
        self.info.set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.components["ssl"].builddirs.append(self._module_subfolder)
        self.info.components["ssl"].set_property("cmake_build_modules", [self._module_file_rel_path])
        self.info.components["crypto"].builddirs.append(self._module_subfolder)
        self.info.components["crypto"].set_property("cmake_build_modules", [self._module_file_rel_path])

        if self._use_nmake:
            self.info.components["ssl"].libs = ["libssl"]
            self.info.components["crypto"].libs = ["libcrypto"]
        else:
            self.info.components["ssl"].libs = ["ssl"]
            self.info.components["crypto"].libs = ["crypto"]

        self.info.components["ssl"].requires = ["crypto"]

        if not self.options.no_zlib:
            self.info.components["crypto"].requires.append("zlib::zlib")

        if self.settings.os == "Windows":
            self.info.components["crypto"].system_libs.extend(["crypt32", "ws2_32", "advapi32", "user32", "bcrypt"])
        elif self.settings.os == "Linux":
            self.info.components["crypto"].system_libs.extend(["dl", "rt"])
            self.info.components["ssl"].system_libs.append("dl")
            if not self.options.no_threads:
                self.info.components["crypto"].system_libs.append("pthread")
                self.info.components["ssl"].system_libs.append("pthread")
        elif self.settings.os == "Neutrino":
            self.info.components["crypto"].system_libs.append("atomic")
            self.info.components["ssl"].system_libs.append("atomic")
            self.info.components["crypto"].system_libs.append("socket")
            self.info.components["ssl"].system_libs.append("socket")

        self.info.components["crypto"].set_property("cmake_target_name", "OpenSSL::Crypto")
        self.info.components["crypto"].set_property("pkg_config_name", "libcrypto")
        self.info.components["ssl"].set_property("cmake_target_name", "OpenSSL::SSL")
        self.info.components["ssl"].set_property("pkg_config_name", "libssl")

        openssl_modules_dir = self.folders.package / "lib" / "ossl-modules"
        self.info.runenv.define_path("OPENSSL_MODULES", openssl_modules_dir)

    @property
    def _is_clang_cl(self) -> bool:
        return self.settings.os == "Windows" and self.settings.compiler == "clang" and self.settings.compiler_runtime # type: ignore

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _use_nmake(self):
        return self._is_clang_cl or is_msvc(self)

    @property
    def _target(self):
        target = f"recipe-{self.settings.build_type}-{self.settings.os}-{self.settings.arch}-{self.settings.compiler}-{self.settings.compiler_version}"
        if self._use_nmake:
            target = f"VC-{target}"  # VC- prefix is important as it's checked by Configure
        if self._is_mingw:
            target = f"mingw-{target}"
        return target

    @property
    def _perlasm_scheme(self):
        # right now, we need to tweak this for iOS & Android only, as they inherit from generic targets
        if self.settings.os in ("iOS", "tvOS"):
            return {
                "ARM": "ios64",
            }.get(str(self.settings.arch), None)
        elif self.settings.os == "Android":
            return {
                "ARM": "linux64",
                "X64": "elf",
            }.get(str(self.settings.arch), None)
        return None

    @property
    def _asm_target(self):
        if self.settings.os in ("Android", "iOS", "tvOS"):
            return {
                "X64": "x86_64_asm" if self.settings.os == "Android" else None,
                "ARM": "aarch64_asm",
            }.get(str(self.settings.arch), None)

    @property
    def _targets(self):
        return {
            "Linux-x86-clang": "linux-x86-clang",
            "Linux-X64-clang": "linux-x86_64-clang",
            "Linux-x86-*": "linux-x86",
            "Linux-X64-*": "linux-x86_64",
            "Linux-armv4-*": "linux-armv4",
            "Linux-armv4i-*": "linux-armv4",
            "Linux-armv5el-*": "linux-armv4",
            "Linux-armv5hf-*": "linux-armv4",
            "Linux-armv6-*": "linux-armv4",
            "Linux-armv7-*": "linux-armv4",
            "Linux-armv7hf-*": "linux-armv4",
            "Linux-armv7s-*": "linux-armv4",
            "Linux-armv7k-*": "linux-armv4",
            "Linux-ARM-*": "linux-aarch64",
            "Linux-armv8.3-*": "linux-aarch64",
            "Linux-armv8-32-*": "linux-arm64ilp32",
            "Linux-mips-*": "linux-mips32",
            "Linux-mips64-*": "linux-mips64",
            "Linux-ppc32-*": "linux-ppc32",
            "Linux-ppc32le-*": "linux-pcc32",
            "Linux-ppc32be-*": "linux-ppc32",
            "Linux-ppc64-*": "linux-ppc64",
            "Linux-ppc64le-*": "linux-ppc64le",
            "Linux-pcc64be-*": "linux-pcc64",
            "Linux-s390x-*": "linux64-s390x",
            "Linux-e2k-*": "linux-generic64",
            "Linux-sparc-*": "linux-sparcv8",
            "Linux-sparcv9-*": "linux64-sparcv9",
            "Linux-*-*": "linux-generic32",
            "Macos-x86-*": "darwin-i386-cc",
            "Mac-X64-*": "darwin64-x86_64-cc",
            "Macos-ppc32-*": "darwin-ppc-cc",
            "Macos-ppc32be-*": "darwin-ppc-cc",
            "Macos-ppc64-*": "darwin64-ppc-cc",
            "Macos-ppc64be-*": "darwin64-ppc-cc",
            "Mac-ARM-*": "darwin64-arm64-cc",
            "Mac-*-*": "darwin-common",
            "iOS-X64-*": "darwin64-x86_64-cc",
            "iOS-*-*": "iphoneos-cross",
            "watchOS-*-*": "iphoneos-cross",
            "tvOS-*-*": "iphoneos-cross",
            # Android targets are very broken, see https://github.com/openssl/openssl/issues/7398
            "Android-armv7-*": "linux-generic32",
            "Android-armv7hf-*": "linux-generic32",
            "Android-ARM-*": "linux-generic64",
            "Android-x86-*": "linux-x86-clang",
            "Android-X64-*": "linux-x86_64-clang",
            "Android-mips-*": "linux-generic32",
            "Android-mips64-*": "linux-generic64",
            "Android-*-*": "linux-generic32",
            "Windows-x86-gcc": "mingw",
            "Windows-X64-gcc": "mingw64",
            "Windows-*-gcc": "mingw-common",
            "Windows-ia64-Visual Studio": "VC-WIN64I",  # Itanium
            "Windows-x86-Visual Studio": "VC-WIN32",
            "Windows-X64-Visual Studio": "VC-WIN64A",
            "Windows-armv7-Visual Studio": "VC-WIN32-ARM",
            "Windows-ARM-Visual Studio": "VC-WIN64-CLANGASM-ARM",
            "Windows-*-Visual Studio": "VC-noCE-common",
            "Windows-ia64-clang": "VC-WIN64I",  # Itanium
            "Windows-x86-clang": "VC-WIN32",
            "Windows-X64-clang": "VC-WIN64A",
            "Windows-armv7-clang": "VC-WIN32-ARM",
            "Windows-ARM-clang": "VC-WIN64-ARM",
            "Windows-*-clang": "VC-noCE-common",
            "WindowsStore-x86-*": "VC-WIN32-UWP",
            "WindowsStore-x86_64-*": "VC-WIN64A-UWP",
            "WindowsStore-armv7-*": "VC-WIN32-ARM-UWP",
            "WindowsStore-armv8-*": "VC-WIN64-ARM-UWP",
            "WindowsStore-*-*": "VC-WIN32-ONECORE",
            "WindowsCE-*-*": "VC-CE",
            "SunOS-x86-gcc": "solaris-x86-gcc",
            "SunOS-x86_64-gcc": "solaris64-x86_64-gcc",
            "SunOS-sparc-gcc": "solaris-sparcv8-gcc",
            "SunOS-sparcv9-gcc": "solaris64-sparcv9-gcc",
            "SunOS-x86-suncc": "solaris-x86-cc",
            "SunOS-x86_64-suncc": "solaris64-x86_64-cc",
            "SunOS-sparc-suncc": "solaris-sparcv8-cc",
            "SunOS-sparcv9-suncc": "solaris64-sparcv9-cc",
            "SunOS-*-*": "solaris-common",
            "*BSD-x86-*": "BSD-x86",
            "*BSD-x86_64-*": "BSD-x86_64",
            "*BSD-ia64-*": "BSD-ia64",
            "*BSD-sparc-*": "BSD-sparcv8",
            "*BSD-sparcv9-*": "BSD-sparcv9",
            "*BSD-armv8-*": "BSD-generic64",
            "*BSD-mips64-*": "BSD-generic64",
            "*BSD-ppc64-*": "BSD-generic64",
            "*BSD-ppc64le-*": "BSD-generic64",
            "*BSD-ppc64be-*": "BSD-generic64",
            "AIX-ppc32-gcc": "aix-gcc",
            "AIX-ppc64-gcc": "aix64-gcc",
            "AIX-pcc32-*": "aix-cc",
            "AIX-ppc64-*": "aix64-cc",
            "AIX-*-*": "aix-common",
            "*BSD-*-*": "BSD-generic32",
            "Emscripten-*-*": "cc",
            "Neutrino-*-*": "BASE_unix",
        }

    @property
    def _ancestor_target(self):
        if "RECIPE_OPENSSL_CONFIGURATION" in os.environ:
            return os.environ["RECIPE_OPENSSL_CONFIGURATION"]
        compiler = "Visual Studio" if self.settings.compiler == "msvc" else self.settings.compiler
        query = f"{self.settings.os}-{self.settings.arch}-{compiler}"
        ancestor = next((self._targets[i] for i in self._targets if fnmatch.fnmatch(query, i)), None)
        if not ancestor:
            raise RecipeInvalidConfiguration(f"Unsupported configuration ({self.settings.os}/{self.settings.arch}/{self.settings.compiler}).")
        return ancestor

    def _get_default_openssl_dir(self):
        if self.settings.os == "Linux":
            return "/etc/ssl"
        return self.folders.package / "res"

    def _adjust_path(self, path: Path):
        if self._use_nmake:
            return os.fspath(path).replace("\\", "/")
        return unix_path(self, path)

    @property
    def _configure_args(self):
        openssldir = Path(self.options.openssldir or self._get_default_openssl_dir())
        openssldir = unix_path(self, openssldir) if self.win_bash else openssldir
        args = [
            f'"{self._target}"',
            "shared" if self.options.shared else "no-shared",
            "--debug" if self.settings.build_type == "Debug" else "--release",
            "--prefix=/",
            "--libdir=lib",
            f"--openssldir=\"{openssldir}\"",
            "no-threads" if self.options.no_threads else "threads",
            f"PERL={self._perl}",
            "no-unit-test",
            "no-tests",
        ]

        if self.settings.os == "Android":
            args.append(f" -D__ANDROID_API__={str(self.settings.os_api_level)}")  # see NOTES.ANDROID
        if self.settings.os == "Windows":
            if self.options.enable_capieng:
                args.append("enable-capieng")
            if self.options.capieng_dialog:
                args.append("-DOPENSSL_CAPIENG_DIALOG=1")
        else:
            args.append("-fPIC" if self.options.pic else "no-pic")

        args.append("no-fips" if self.options.no_fips else "enable-fips")
        args.append("no-md2" if self.options.no_md2 else "enable-md2")
        if str(self.options.tls_security_level) != "None":
            args.append(f"-DOPENSSL_TLS_SECURITY_LEVEL={self.options.tls_security_level}")

        if self.options.enable_trace:
            args.append("enable-trace")

        if self.settings.os == "Neutrino":
            args.append("no-asm -lsocket -latomic")

        if not self.options.no_zlib:
            zlib_cpp_info = self.dependencies["zlib"].info.aggregated_components()
            include_path = self._adjust_path(zlib_cpp_info.includedirs[0])
            is_shared_zlib = self.dependencies["zlib"].options.shared

            # the --with-zlib-lib flag takes a different value depending on platform and if ZLIB is shared
            # From https://github.com/openssl/openssl/blob/openssl-3.4.1/INSTALL.md#with-zlib-lib
            # On Unix: the directory where the zlib library is (for -L flag)
            # On Windows with static zlib: the path to the static library to link (assumed)
            # On Windows with shared zlib: the leaf name of the dll (its loaded with LoadLibrary)
            if self._use_nmake:
                # notes: consider where this should be "if on windows"
                #        zlib1 is assumed to be the name of the zlib1.dll for all windows configurations
                lib_path = self._adjust_path(Path(zlib_cpp_info.libdirs[0]) / f"{zlib_cpp_info.libs[0]}.lib")
                zlib_lib_flag = "zlib1" if is_shared_zlib else lib_path
            else:
                # Just path, GNU like compilers will find the right file
                zlib_lib_flag = self._adjust_path(Path(zlib_cpp_info.libdirs[0]))

            zlib_configure_arg = "zlib-dynamic" if is_shared_zlib else "zlib"
            args.append(zlib_configure_arg)

            args.extend(
                [
                    f'--with-zlib-include="{include_path}"',
                    f'--with-zlib-lib="{zlib_lib_flag}"',
                ])

        for option_name, _ in self.options.items():
            if self.options.get_safe(option_name, False) and option_name not in ("shared", "pic", "openssldir", "tls_security_level", "capieng_dialog", "enable_capieng", "zlib", "no_fips", "no_md2"):
                self.output.info(f"Activated option: {option_name}")
                args.append(option_name.replace("_", "-"))
        return args

    def _create_targets(
        self,
        cflags: list[str],
        cxxflags: list[str],
        defs: list[str],
        ldflags: list[str]):
        config_template = textwrap.dedent(
            """
            {targets} = (
                "{target}" => {{
                    inherit_from => {ancestor},
                    cflags => add("{cflags}"),
                    cxxflags => add("{cxxflags}"),
                    {defines}
                    lflags => add("{lflags}"),
                    {shared_target}
                    {shared_cflag}
                    {shared_extension}
                    {perlasm_scheme}
                }},
            );
            """)

        perlasm_scheme = ""
        if self._perlasm_scheme:
            perlasm_scheme = f'perlasm_scheme => "{self._perlasm_scheme}",'

        defines: str = '", "'.join(defs)
        defines = 'defines => add("%s"),' % defines if defines else ""
        targets = "my %targets"

        if self._asm_target:
            ancestor = f'[ "{self._ancestor_target}", asm("{self._asm_target}") ]'
        else:
            ancestor = f'[ "{self._ancestor_target}" ]'
        shared_cflag = ""
        shared_extension = ""
        shared_target = ""
        if self.settings.os == "Neutrino":
            if self.options.shared:
                shared_extension = r'shared_extension => ".so.\$(SHLIB_VERSION_NUMBER)",'
                shared_target = 'shared_target  => "gnu-shared",'
            if self.options.pic:
                shared_cflag = 'shared_cflag => "-fPIC",'

        if self.settings.os in ["iOS", "tvOS", "watchOS"] and self.conf.tools.apple.enable_bitcode:
            cflags.append("-fembed-bitcode")
            cxxflags.append("-fembed-bitcode")

        config = config_template.format(
            targets=targets,
            target=self._target,
            ancestor=ancestor,
            cflags=" ".join(cflags),
            cxxflags=" ".join(cxxflags),
            defines=defines,
            perlasm_scheme=perlasm_scheme,
            shared_target=shared_target,
            shared_extension=shared_extension,
            shared_cflag=shared_cflag,
            lflags=" ".join(ldflags)
        )
        self.output.info(f"using target: {self._target} -> {self._ancestor_target}")
        self.output.info(config)

        save(self, self.folders.source / "Configurations" / "20-thirdparty.conf", config)

    def _run_make(
        self,
        targets: list[str] | None = None,
        parallel: bool = True,
        install: bool = False):
        command = [self._make_program]
        if self._use_nmake and not self.conf.tools.compilation.verbose:
            # nmake/jom echo the full cl command line for every source file and print a logo
            # banner; /S silences the command echo and /NOLOGO drops the banner when quiet.
            command.append("/NOLOGO")
            command.append("/S")
        if install:
            command.append(f"DESTDIR={self._adjust_path(self.folders.package)}")
        if targets:
            command.extend(targets)
        if self._make_program in ["make", "jom"]:
            command.append(f"-j{build_jobs(self)}" if parallel else "-j1")
        run(self," ".join(command), env="env_build")

    @property
    def _perl(self):
        if self._use_nmake:
            return self.dependencies.build["strawberryperl"].info.conf.tools.strawberryperl.perl
        return "perl"

    def _make(self):
        with chdir(self, self.folders.source):
            args = " ".join(self._configure_args)

            if self._use_nmake:
                self._replace_runtime_in_file(Path("Configurations") / "10-main.conf")

            run(self,f"{self._perl} ./Configure {args}", env="env_build")
            if self._use_nmake:
                # When `--prefix=/`, the scripts derive `\` without escaping, which
                # causes issues on Windows
                replace_in_file(self, "Makefile", "INSTALLTOP_dir=\\", "INSTALLTOP_dir=\\\\")
                # replace backslashes in paths with forward slashes
                mkinstallvars_pl = self.folders.source / "util" / "mkinstallvars.pl"
                replace_in_file(self, mkinstallvars_pl, "push @{$values{$k}}, $v;", """$v =~ s|\\\\|/|g; push @{$values{$k}}, $v;""")
                replace_in_file(self, mkinstallvars_pl, "$values{$k} = $v;", """$v->[0] =~ s|\\\\|/|g; $values{$k} = $v;""")
            self._run_make()

    def _make_install(self):
        with chdir(self, self.folders.source):
            self._run_make(targets=["install_sw"], parallel=False, install=True)

    @property
    def _make_program(self):
        if self._use_nmake:
            return "jom" # if use_jom else "nmake"
        else:
            return "make"

    def _replace_runtime_in_file(self, filename: Path):
        runtime = msvc_runtime_flag(self)
        for e in ["MDd", "MD", "MT"]:
            replace_in_file(self, filename, f"/{e} ", f"/{runtime} ", strict=False)
            replace_in_file(self, filename, f"/{e}\"", f"/{runtime}\"", strict=False)

    def _create_cmake_module_variables(self, module_file: Path):
        content = textwrap.dedent(
            """
            set(OPENSSL_FOUND TRUE)
            if(DEFINED OpenSSL_INCLUDE_DIR)
                set(OPENSSL_INCLUDE_DIR ${OpenSSL_INCLUDE_DIR})
            endif()
            if(DEFINED OpenSSL_Crypto_LIBS)
                set(OPENSSL_CRYPTO_LIBRARY ${OpenSSL_Crypto_LIBS})
                set(OPENSSL_CRYPTO_LIBRARIES ${OpenSSL_Crypto_LIBS} ${OpenSSL_Crypto_DEPENDENCIES} ${OpenSSL_Crypto_FRAMEWORKS} ${OpenSSL_Crypto_SYSTEM_LIBS})
            elseif(DEFINED openssl_OpenSSL_Crypto_LIBS_%(config)s)
                set(OPENSSL_CRYPTO_LIBRARY ${openssl_OpenSSL_Crypto_LIBS_%(config)s})
                set(OPENSSL_CRYPTO_LIBRARIES ${openssl_OpenSSL_Crypto_LIBS_%(config)s} ${openssl_OpenSSL_Crypto_DEPENDENCIES_%(config)s} ${openssl_OpenSSL_Crypto_FRAMEWORKS_%(config)s} ${openssl_OpenSSL_Crypto_SYSTEM_LIBS_%(config)s})
            endif()
            if(DEFINED OpenSSL_SSL_LIBS)
                set(OPENSSL_SSL_LIBRARY ${OpenSSL_SSL_LIBS})
                set(OPENSSL_SSL_LIBRARIES ${OpenSSL_SSL_LIBS} ${OpenSSL_SSL_DEPENDENCIES} ${OpenSSL_SSL_FRAMEWORKS} ${OpenSSL_SSL_SYSTEM_LIBS})
            elseif(DEFINED openssl_OpenSSL_SSL_LIBS_%(config)s)
                set(OPENSSL_SSL_LIBRARY ${openssl_OpenSSL_SSL_LIBS_%(config)s})
                set(OPENSSL_SSL_LIBRARIES ${openssl_OpenSSL_SSL_LIBS_%(config)s} ${openssl_OpenSSL_SSL_DEPENDENCIES_%(config)s} ${openssl_OpenSSL_SSL_FRAMEWORKS_%(config)s} ${openssl_OpenSSL_SSL_SYSTEM_LIBS_%(config)s})
            endif()
            if(DEFINED OpenSSL_LIBRARIES)
                set(OPENSSL_LIBRARIES ${OpenSSL_LIBRARIES})
            endif()
            if(DEFINED OpenSSL_VERSION)
                set(OPENSSL_VERSION ${OpenSSL_VERSION})
            endif()
            """ % {"config": str(self.settings.build_type).upper()})
        save(self, module_file, content)

    @property
    def _module_subfolder(self):
        return os.path.join("lib", "cmake")

    @property
    def _module_file_rel_path(self):
        return os.path.join(
            self._module_subfolder,
            f"recipe-official-{self.name}-variables.cmake")
