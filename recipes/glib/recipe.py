import os
import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, replace_in_file, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    # These integrations are optional in GLib, and this repository does not
    # currently provide elfutils, libselinux, or libmount recipes. Keeping
    # them off by default also prevents native system packages from masking a
    # missing target dependency during cross-builds.
    with_elf: bool = False
    with_selinux: bool = False
    with_mount: bool = False


class Recipe(RecipeBase[_Options]):
    name = "glib"
    version = "2.89.2"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "GNOME/glib")
        return Version(repo.latest_release)

    def configure(self):
        if self.settings.os != "Linux":
            self.options.with_mount = False
            self.options.with_selinux = False
        if is_msvc(self):
            self.options.with_elf = False

        if self.settings.os == "Neutrino":
            self.options.with_elf = False

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("meson")
        self.requires("zlib")
        self.requires("libffi")
        self.requires("pcre2")
        if self.options.with_elf:
            self.requires("elfutils")
        if self.options.with_mount:
            self.requires("libmount")
        if self.options.with_selinux:
            self.requires("libselinux")
        if self.settings.os != "Linux":
            # for Linux, gettext is provided by libc
            self.requires("gettext")

        if is_apple_os(self):
            self.requires("libiconv")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        ver = Version(self.version)
        get(
            self,
            url=f"https://download.gnome.org/sources/glib/{ver.major}.{ver.minor}/glib-{self.version}.tar.xz",
            sha256="894fd527e305041f7723071297d79a78af4719dbd0d8fb77f6b1a85c9f5475b9",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)

        tc.project_options["selinux"] = "enabled" if self.options.with_selinux else "disabled"
        tc.project_options["libmount"] = "enabled" if self.options.with_mount else "disabled"
        if self.settings.os == "FreeBSD" or self.settings.os == "Neutrino":
            tc.project_options["xattr"] = "false"
        tc.project_options["tests"] = "false"
        tc.project_options["libelf"] = "enabled" if self.options.with_elf else "disabled"

        if self.settings.os == "Neutrino":
            tc.cross_build["host"]["system"] = "qnx"
            tc.c_link_args.append("-lm")
            tc.c_link_args.append("-lsocket")

        tc.generate()

    def build(self):
        self._patch_sources()
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, pattern="LGPL-2.1-or-later.txt", dst=self.folders.package / "licenses", src=self.folders.source / "LICENSES")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "libexec")
        shutil.move(
            self.folders.package / "share",
            self.folders.package / "res",
        )
        rm(self, "*.pdb", self.folders.package / "bin")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.components["glib-2.0"].set_property("pkg_config_name", "glib-2.0")
        self.info.components["glib-2.0"].libs = ["glib-2.0"]
        self.info.components["glib-2.0"].includedirs += [
            os.path.join("include", "glib-2.0"),
            os.path.join("lib", "glib-2.0", "include"),
        ]
        self.info.components["glib-2.0"].resdirs = ["res"]

        self.info.components["gmodule-no-export-2.0"].set_property("pkg_config_name", "gmodule-no-export-2.0")
        self.info.components["gmodule-no-export-2.0"].libs = ["gmodule-2.0"]
        self.info.components["gmodule-no-export-2.0"].resdirs = ["res"]
        self.info.components["gmodule-no-export-2.0"].requires.append("glib-2.0")

        self.info.components["gmodule-export-2.0"].set_property("pkg_config_name", "gmodule-export-2.0")
        self.info.components["gmodule-export-2.0"].requires += ["gmodule-no-export-2.0", "glib-2.0"]

        self.info.components["gmodule-2.0"].set_property("pkg_config_name", "gmodule-2.0")
        self.info.components["gmodule-2.0"].requires += ["gmodule-no-export-2.0", "glib-2.0"]

        self.info.components["gobject-2.0"].set_property("pkg_config_name", "gobject-2.0")
        self.info.components["gobject-2.0"].libs = ["gobject-2.0"]
        self.info.components["gobject-2.0"].resdirs = ["res"]
        self.info.components["gobject-2.0"].requires += ["glib-2.0", "libffi::libffi"]

        self.info.components["gthread-2.0"].set_property("pkg_config_name", "gthread-2.0")
        self.info.components["gthread-2.0"].libs = ["gthread-2.0"]
        self.info.components["gthread-2.0"].resdirs = ["res"]
        self.info.components["gthread-2.0"].requires.append("glib-2.0")

        self.info.components["gio-2.0"].set_property("pkg_config_name", "gio-2.0")
        self.info.components["gio-2.0"].libs = ["gio-2.0"]
        self.info.components["gio-2.0"].resdirs = ["res"]
        self.info.components["gio-2.0"].requires += ["glib-2.0", "gobject-2.0", "gmodule-2.0", "zlib::zlib"]

        self.info.components["gresource"].set_property("pkg_config_name", "gresource")
        self.info.components["gresource"].libs = []  # this is actually an executable

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["glib-2.0"].system_libs.append("pthread")
            self.info.components["gmodule-no-export-2.0"].system_libs.append("pthread")
            self.info.components["gmodule-no-export-2.0"].system_libs.append("dl")
            self.info.components["gmodule-export-2.0"].sharedlinkflags.append("-Wl,--export-dynamic")
            self.info.components["gmodule-2.0"].sharedlinkflags.append("-Wl,--export-dynamic")
            self.info.components["gthread-2.0"].system_libs.append("pthread")
            self.info.components["gio-2.0"].system_libs.append("dl")

        if self.settings.os == "Neutrino":
            self.info.components["gmodule-export-2.0"].sharedlinkflags.append("-Wl,--export-dynamic")
            self.info.components["gmodule-2.0"].sharedlinkflags.append("-Wl,--export-dynamic")
            self.info.components["glib-2.0"].system_libs.append("m")
            self.info.components["glib-2.0"].system_libs.append("socket")
            self.info.components["gmodule-no-export-2.0"].system_libs.append("c")
            self.info.components["gio-2.0"].system_libs.append("c")
            self.info.components["gio-2.0"].system_libs.append("socket")

        if self.settings.os == "Windows":
            self.info.components["glib-2.0"].system_libs += ["ws2_32", "ole32", "shell32", "user32", "advapi32"]
            self.info.components["gio-2.0"].system_libs.extend(["iphlpapi", "dnsapi", "shlwapi"])
            self.info.components["gio-windows-2.0"].set_property("pkg_config_name", "gio-windows-2.0")
            self.info.components["gio-windows-2.0"].requires = ["gobject-2.0", "gmodule-no-export-2.0", "gio-2.0"]
            self.info.components["gio-windows-2.0"].includedirs = [os.path.join("include", "gio-win32-2.0")]
        else:
            self.info.components["gio-unix-2.0"].set_property("pkg_config_name", "gio-unix-2.0")
            self.info.components["gio-unix-2.0"].requires += ["gobject-2.0", "gio-2.0"]
            self.info.components["gio-unix-2.0"].includedirs = [os.path.join("include", "gio-unix-2.0")]

        if self.settings.os == "Mac":
            self.info.components["glib-2.0"].system_libs.append("resolv")
            self.info.components["glib-2.0"].frameworks += ["Foundation", "CoreServices", "CoreFoundation"]
            self.info.components["gio-2.0"].frameworks.append("AppKit")

            if is_apple_os(self):
                self.info.components["glib-2.0"].requires.append("libiconv::libiconv")

        self.info.components["glib-2.0"].requires.append("pcre2::pcre2")

        if self.settings.os == "Linux":
            self.info.components["gio-2.0"].system_libs.append("resolv")
        else:
            self.info.components["glib-2.0"].requires.append("gettext::gettext")

        if self.options.with_mount:
            self.info.components["gio-2.0"].requires.append("libmount::libmount")

        if self.options.with_selinux:
            self.info.components["gio-2.0"].requires.append("libselinux::libselinux")

        if self.options.with_elf:
            self.info.components["gresource"].requires.append("elfutils::libelf")  # this is actually an executable

        pkgconfig_variables = {
            "datadir": "${prefix}/res",
            "schemasdir": "${datadir}/glib-2.0/schemas",
            "bindir": "${prefix}/bin",
            # Can't use libdir here as it is libdir1 when using the PkgConfigDeps generator.
            "giomoduledir": "${prefix}/lib/gio/modules",
            "gio": "${bindir}/gio",
            "gio_querymodules": "${bindir}/gio-querymodules",
            "glib_compile_schemas": "${bindir}/glib-compile-schemas",
            "glib_compile_resources": "${bindir}/glib-compile-resources",
            "gdbus": "${bindir}/gdbus",
            "gdbus_codegen": "${bindir}/gdbus-codegen",
            "gresource": "${bindir}/gresource",
            "gsettings": "${bindir}/gsettings",
        }
        self.info.components["gio-2.0"].set_property(
            "pkg_config_custom_content",
            "\n".join(f"{key}={value}" for key, value in pkgconfig_variables.items()))

        pkgconfig_variables = {
            "bindir": "${prefix}/bin",
            "glib_genmarshal": "${bindir}/glib-genmarshal",
            "gobject_query": "${bindir}/gobject-query",
            "glib_mkenums": "${bindir}/glib-mkenums",
        }
        self.info.components["glib-2.0"].set_property(
            "pkg_config_custom_content",
            "\n".join(f"{key}={value}" for key, value in pkgconfig_variables.items()))

    def _patch_sources(self):
        apply_patches(self)
        replace_in_file(
            self,
            self.folders.source / "meson.build",
            "subdir('fuzzing')",
            "#subdir('fuzzing')",
            )  # https://gitlab.gnome.org/GNOME/glib/-/issues/2152
        if self.settings.os != "Linux" and self.settings.os != "Neutrino":
            # allow to find gettext
            replace_in_file(
                self,
                self.folders.source / "meson.build",
                "libintl = dependency('intl', required: false",
                "libintl = dependency('gettext', method : 'pkg-config', required : false",
                strict=False)

        replace_in_file(
            self,
            self.folders.source / "gio" / "gdbus-2.0" / "codegen" / "gdbus-codegen.in",
            "'share'",
            "'res'",
            strict=False)
