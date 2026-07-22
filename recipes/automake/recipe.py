import os

from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, replace_in_file, rename, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "automake"
    version = "1.18.1"
    license = "GPL-2.0-or-later", "GPL-3.0-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "autotools-mirror/automake")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("autoconf")
        self.requires("autoconf")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/automake/automake-{self.version}.tar.gz",
            sha256="63e585246d0fc8772dffdee0724f2f988146d1a3f1c756a3dc5cfbefa3c01915",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        AutotoolsToolchain(self).generate()

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        autotools = Autotools(self)
        autotools.install()
        copy(self, "COPYING*", src=self.folders.source, dst=self.folders.package / "licenses")

        rmdir(self, self.folders.package / "share" / "info")
        rmdir(self, self.folders.package / "share" / "man")
        rmdir(self, self.folders.package / "share" / "doc")

        if self.settings.os == "Windows":
            # TODO: consider whether the following is still necessary on Windows
            binpath = self.folders.package / "bin"
            for filename in os.listdir(binpath):
                fullpath = binpath / filename
                if not os.path.isfile(fullpath):
                    continue
                rename(self, fullpath, fullpath.parent / (fullpath.name + ".exe"))

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.frameworkdirs = []

        # For consumers with new integrations (Recipe 1 and 2 compatible):
        ver = Version(self.version)
        automake_helper_scripts_dir = self.folders.package / "share" / f"automake-{ver.major}.{ver.minor}"
        compile_wrapper = automake_helper_scripts_dir / "compile"
        lib_wrapper = automake_helper_scripts_dir / "ar-lib"
        self.info.conf.tools.automake.compile_wrapper = compile_wrapper
        self.info.conf.tools.automake.lib_wrapper = lib_wrapper

    def _patch_sources(self):
        apply_patches(self)
        if self.settings.os == "Windows":
            # tracing using m4 on Windows returns Windows paths => use cygpath to convert to unix paths
            ac_local_in = self.folders.source / "bin" / "aclocal.in"
            with open(ac_local_in, encoding="utf-8") as _f:
                _content = _f.read()
            if "cygpath -u $file" not in _content:
                replace_in_file(
                    self,
                    ac_local_in,
                    "          $map_traced_defs{$arg1} = $file;",
                    "          $file = `cygpath -u $file`;\n"
                    "          $file =~ s/^\\s+|\\s+$//g;\n"
                    "          $map_traced_defs{$arg1} = $file;")
            # handle relative paths during aclocal.m4 creation
            replace_in_file(
                self,
                ac_local_in,
                "$map{$m} eq $map_traced_defs{$m}",
                "abs_path($map{$m}) eq abs_path($map_traced_defs{$m})",
                strict=False)
