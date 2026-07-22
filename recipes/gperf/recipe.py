from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import chdir, copy, get, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import GnuFtp, Version


class Recipe(RecipeBase):
    name = "gperf"
    version = "3.3"
    license = "GPL-3.0-or-later"

    def latest_version(self):
        return Version(GnuFtp(self, "gperf").latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/gperf/gperf-{self.version}.tar.gz",
            sha256="fd87e0aba7e43ae054837afd6cd4db03a3f2693deb3619085e6ed9d8d9604ad8",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tcenv = tc.environment()
        if is_msvc(self):
            compile_wrapper = unix_path(self, self.folders.source / "build-aux" / "compile")
            ar_wrapper = unix_path(self, self.folders.source / "build-aux" / "ar-lib")
            tcenv.define("CC", f"{compile_wrapper} cl -nologo")
            tcenv.define("CXX", f"{compile_wrapper} cl -nologo")
            tcenv.append("CPPFLAGS", "-D_WIN32_WINNT=_WIN32_WINNT_WIN8")
            tcenv.define("LD", "link -nologo")
            tcenv.define("AR", f'{ar_wrapper} "lib -nologo"')
            tcenv.define("NM", "dumpbin -symbols")
            tcenv.define("OBJDUMP", ":")
            tcenv.define("RANLIB", ":")
            tcenv.define("STRIP", ":")
            # Prevent msys2 from converting the -Tp C++ flag handled by the compile wrapper.
            tcenv.define("MSYS2_ARG_CONV_EXCL", "-Tp")
        tc.generate(tcenv)

    def build(self):
        autotools = Autotools(self)
        with chdir(self, self.folders.source):
            autotools.configure()
            autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source,
             dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        with chdir(self, self.folders.source):
            autotools.install()
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.includedirs = []
        self.info.libdirs = []
