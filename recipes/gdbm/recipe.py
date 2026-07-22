import os
from typing import Any

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.files import apply_patches, copy, get, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsDeps, AutotoolsToolchain
from thirdparty.scm import GnuFtp
from thirdparty.scm import Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    libgdbm_compat: bool = False
    gdbmtool_debug: bool = True
    with_libiconv: bool = False
    with_readline: bool = False
    with_nls: bool = True


class Recipe(RecipeBase[_Options]):
    name = "gdbm"
    version = "1.26"
    license = "GPL-3.0-or-later"

    def latest_version(self):
        repo = GnuFtp(self, "gdbm")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None
        if not self.options.with_nls:
            self.options.with_libiconv = False

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} is not supported on Windows")

    def requirements(self):
        self.requires_tool("bison")
        self.requires_tool("flex")
        self.requires_tool("gnu-config")
        if self.options.with_libiconv:
            self.requires("libiconv")
        if self.options.with_readline:
            self.requires("readline")

    def source(self):
        get(
            self,
            url=f"https://ftp.gnu.org/gnu/gdbm/gdbm-{self.version}.tar.gz",
            sha256="6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        if not cross_building(self):
            VirtualRunEnv(self).generate(scope="build")
        tc = AutotoolsToolchain(self)
        
        def yes_no(v: Any) -> str:
            return "yes" if v else "no"
        
        enable_debug = self.settings.build_type in ["Debug", "RelWithDebInfo"]
        tc.configure_args.extend(
            [
                f"--enable-debug={yes_no(enable_debug)}",
                f"--enable-libgdbm-compat={yes_no(self.options.libgdbm_compat)}",
                f"--enable-gdbmtool-debug={yes_no(self.options.gdbmtool_debug)}",
                f"--enable-nls={yes_no(self.options.with_nls)}",
                f"--with-readline={yes_no(self.options.with_readline)}",
                f"--with-pic={yes_no(self.options.pic)}",
            ])
        if self.options.gdbmtool_debug:
            tc.extra_defines.append("YYDEBUG=1")
        if self.options.with_libiconv:
            libiconv_package_folder = self.dependencies.direct_host["libiconv"].folders.package
            tc.configure_args.extend(
                [
                    f"--with-libiconv-prefix={libiconv_package_folder}"
                    "--with-libintl-prefix",
                ])
        else:
            tc.configure_args.extend(
                [
                    "--without-libiconv-prefix",
                    "--without-libintl-prefix",
                ])
        if is_apple_os(self):
            # Inject -headerpad_max_install_names, otherwise fix_apple_shared_install_name() may fail.
            # See https://github.com/recipe-io/recipe-center-index/issues/20002
            tc.extra_ldflags.append("-headerpad_max_install_names")
        tc.generate()
        deps = AutotoolsDeps(self)
        deps.generate()

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make(target="maintainer-clean-generic")
        autotools.make()

    def package(self):
        copy(self, "COPYING", self.folders.source, self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "share")
        fix_apple_shared_install_name(self)

    def package_info(self):
        if self.options.libgdbm_compat:
            self.info.libs.append("gdbm_compat")
        self.info.libs.append("gdbm")

        bin_path = self.folders.package / "bin"
        self.output.info(f"Appending PATH environment variable: {bin_path}")

    def _patch_sources(self):
        apply_patches(self)
        for gnu_config in [
            self.conf.tools.gnu_config.config_guess,
            self.conf.tools.gnu_config.config_sub,
        ]:
            if gnu_config:
                copy(self, os.path.basename(gnu_config), os.path.dirname(gnu_config), self.folders.source / "build-aux")
