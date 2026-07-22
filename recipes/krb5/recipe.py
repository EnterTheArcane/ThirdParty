from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os
from thirdparty.autotools import Autotools, AutotoolsDeps, AutotoolsToolchain
from thirdparty.build import can_run, cross_building
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import apply_patches, chdir, copy, get, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class _Options(RecipeOptions):
    use_thread: bool = True
    use_dns_realms: bool = False
    with_tls: Literal[False, "openssl"] = "openssl"
    with_keyutils: bool = True


class Recipe(RecipeBase[_Options]):
    name = "krb5"
    version = "1.22.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "krb5/krb5")
        return Version(repo.latest_tag_matching(r"krb5-(\d+\.\d+(?:\.\d+)?)-final"))

    def configure(self):
        if self.settings.os != "Linux":
            self.options.with_keyutils = False

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def validate(self):
        if self.settings.os not in ("Linux", "Mac"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux and Mac")

    def requirements(self):
        self.requires("libverto")
        if self.options.with_tls == "openssl":
            self.requires("openssl")

        self.requires_tool("automake")
        self.requires_tool("bison")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/krb5/krb5/archive/refs/tags/krb5-{self.version}-final.tar.gz",
            sha256="289f5bb81d1f2f8d5eecebe56a056aeed95d35fd9bb4a7071c5dd7ad4b3fe888",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        VirtualBuildEnv(self).generate()
        if can_run(self):
            VirtualRunEnv(self).generate(scope="build")

        deps = PkgConfigDeps(self)
        deps.generate()

        tls_impl = "openssl" if self.options.with_tls == "openssl" else "no"
        tc = AutotoolsToolchain(self)
        tc.configure_args.extend([
            f"--enable-thread-support={tc.yes_no("use_thread")}",
            f"--enable-dns-for-realm={tc.yes_no("use_dns_realms")}",
            f"--enable-pkinit={tc.yes_no("with_tls")}",
            "--with-crypto-impl=openssl" if self.options.with_tls == "openssl" else "--with-crypto-impl=builtin",
            f"--with-spake-openssl={tc.yes_no("with_tls")}",
            f"--with-tls-impl={tls_impl}",
            "--disable-nls",
            "--disable-rpath",
            "--without-libedit",
            "--without-readline",
            "--with-system-verto",
            f"--with-keyutils={self.folders.package}"
            if self.options.with_keyutils
            else "--without-keyutils",
        ])
        if cross_building(self):
            tc.configure_args.extend([
                "krb5_cv_attr_constructor_destructor=yes,yes",
                "ac_cv_printf_positional=yes",
            ])
        if is_apple_os(self):
            for dependency in self.dependencies.host.values():
                for libdir in dependency.info.aggregated_components().libdirs:
                    tc.extra_ldflags.append(f"-Wl,-rpath,{libdir}")
        tc.generate()
        AutotoolsDeps(self).generate()

    def build(self):
        autotools = Autotools(self)
        with chdir(self, self.folders.source / "src"):
            run(self,"autoreconf -vif")
        autotools.configure(build_script_folder="src")
        autotools.make()

    def package(self):
        copy(self, "NOTICE", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        fix_apple_shared_install_name(self)
        rm(self, "*.la", self.folders.package / "lib", recursive=True)
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "var")

    def package_info(self):
        self.info.components["mit-krb5"].libs = ["krb5", "k5crypto", "com_err"]
        if self.options.with_tls == "openssl":
            self.info.components["mit-krb5"].requires = ["openssl::crypto"]
        if self.settings.os == "Linux":
            self.info.components["mit-krb5"].system_libs = ["resolv"]

        self.info.components["libkrb5"].libs = []
        self.info.components["libkrb5"].requires = ["mit-krb5"]

        self.info.components["mit-krb5-gssapi"].libs = ["gssapi_krb5"]
        self.info.components["mit-krb5-gssapi"].requires = ["mit-krb5"]

        self.info.components["krb5-gssapi"].libs = []
        self.info.components["krb5-gssapi"].requires = ["mit-krb5-gssapi"]

        self.info.components["gssrpc"].libs = ["gssrpc"]
        self.info.components["gssrpc"].requires = ["mit-krb5-gssapi"]

        self.info.components["kadm-client"].libs = ["kadm5clnt_mit"]
        self.info.components["kadm-client"].requires = ["mit-krb5-gssapi", "gssrpc"]

        self.info.components["kdb"].libs = ["kdb5"]
        self.info.components["kdb"].requires = ["mit-krb5-gssapi", "mit-krb5", "gssrpc"]

        self.info.components["kadm-server"].libs = ["kadm5srv_mit"]
        self.info.components["kadm-server"].requires = ["kdb", "mit-krb5-gssapi"]

        self.info.components["krad"].libs = ["krad"]
        self.info.components["krad"].requires = ["libkrb5", "libverto::verto"]

        self.info.runenv.define_path("KRB5_CONFIG", self.folders.package / "bin" / "krb5-config")
