from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, replace_in_file
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.scm import GnuFtp, Version


class Recipe(RecipeBase):
    name = "bison"
    version = "3.8.2"
    license = "GPL-3.0-or-later"

    def latest_version(self):
        return Version(GnuFtp(self, "bison").latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def validate(self):
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration("Windows is not supported")

    def requirements(self):
        self.requires_tool("flex")
        self.requires_tool("m4")
        self.requires("m4")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/bison/bison-{self.version}.tar.gz",
            sha256="06c9e13bdf7eb24d4ceb6b59205a4f67c2c7e7213119644430fe82fbd14a0abb",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend([
            "--enable-relocatable",
            "--disable-nls",
            "--datarootdir=${prefix}/res",
        ])
        tc.generate()

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source,
             dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()

    def package_info(self):
        self.info.includedirs = []
        self.info.libs = ["y"]
        self.info.resdirs = ["res"]
        self.info.buildenv.define_path("CONAN_BISON_ROOT", self.folders.package.as_posix())
        self.info.buildenv.define_path(
            "BISON_PKGDATADIR", self.folders.package / "res" / "bison")

    def _patch_sources(self):
        # Make the installed ``yacc`` wrapper relocatable.
        yacc = self.folders.source / "src" / "yacc.in"
        replace_in_file(self, yacc, "@prefix@", "$CONAN_BISON_ROOT")
        replace_in_file(self, yacc, "@bindir@", "$CONAN_BISON_ROOT/bin")
