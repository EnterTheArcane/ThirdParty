from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rmdir, replace_in_file, apply_patches
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import unix_path, is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "autoconf"
    version = "2.73"
    license = "GPL-2.0-or-later", "GPL-3.0-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "autotools-mirror/autoconf")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("m4")
        self.requires("m4")  # Needed at runtime by downstream clients as well
        if self.settings.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/autoconf/autoconf-{self.version}.tar.xz",
            sha256="9fd672b1c8425fac2fa67fa0477b990987268b90ff36d5f016dae57be0d6b52e",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.append("--datarootdir=${prefix}/res")

        if self.settings.os == "Windows":
            if is_msvc(self):
                build = "{}-{}-{}".format(
                    "x86_64" if self.settings.arch == "X64" else "i686",
                    "pc" if self.settings.arch == "x86" else "win64",
                    "mingw32")
                host = "{}-{}-{}".format(
                    "x86_64" if self.settings.arch == "X64" else "i686",
                    "pc" if self.settings.arch == "x86" else "win64",
                    "mingw32")
                tc.configure_args.append(f"--build={build}")
                tc.configure_args.append(f"--host={host}")

        env = tc.environment()
        env.define_path("INSTALL", unix_path(self, self.folders.source / "build-aux" / "install-sh"))
        tc.generate(env)

    def build(self):
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        autotools = Autotools(self)
        autotools.install()

        copy(self, "COPYING*", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "res" / "info")
        rmdir(self, self.folders.package / "res" / "man")

        autom4te_cfg = self.folders.package / "res" / "autoconf" / "autom4te.cfg"
        if self.settings.os == "Windows":
            actual_data_path = unix_path(self, self.folders.package / "res" / "autoconf")
            replace_in_file(self, autom4te_cfg, "'/res/autoconf'", f"'{actual_data_path}'")
        else:
            actual_data_path = self.folders.package / "res" / "autoconf"
            replace_in_file(self, autom4te_cfg, "'//res/autoconf'", f"'{actual_data_path}'")

    def package_info(self):
        self.info.frameworkdirs = []
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.resdirs = ["res"]

        bin_path = self.folders.package / "bin"
        self.info.buildenv.define_path("AUTOCONF", bin_path / "autoconf")
        self.info.buildenv.define_path("AUTORECONF", bin_path / "autoreconf")
        self.info.buildenv.define_path("AUTOHEADER", bin_path / "autoheader")
        self.info.buildenv.define_path("AUTOM4TE", bin_path / "autom4te")

        perllib_path = self.folders.package / "res" / "autoconf"
        self.info.buildenv.define_path("autom4te_perllibdir", perllib_path)
        self.info.buildenv.define_path("AC_MACRODIR", perllib_path)
        self.info.buildenv.define_path("trailer_m4", perllib_path / "autoconf" / "trailer.m4")
