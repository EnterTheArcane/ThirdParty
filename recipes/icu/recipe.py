import os
import shutil
from typing import Any, Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import cross_building, stdcpp_library
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import copy, get, mkdir, rename, replace_in_file, rm, rmdir, save
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import check_min_vs, is_msvc, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    data_packaging: Literal["files", "archive", "library", "static"] = "archive"
    with_dyload: bool = True
    dat_package_file: str | None = None
    with_icuio: bool = True
    with_extras: bool = False


class Recipe(RecipeBase[_Options]):
    name = "icu"
    version = "78.3"
    license = "Unicode-3.0"

    def latest_version(self):
        repo = GithubRepository(self, "unicode-org/icu")
        return Version(repo.latest_release.removeprefix("release-"))

    def requirements(self):
        if self.settings.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

        if cross_building(self) and hasattr(self, "settings_build"):
            self.requires_tool(self.name)

    def source(self):
        get(
            self,
            url=f"https://github.com/unicode-org/icu/releases/download/release-{self.version}/icu4c-{self.version}-sources.tgz",
            sha256="3a2e7a47604ba702f345878308e6fefeca612ee895cf4a5f222e7955fabfe0c0",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        if check_min_vs(self, "180", raise_invalid=False):
            tc.extra_cflags.append("-FS")
            tc.extra_cxxflags.append("-FS")
        if not self.settings.compiler_cxx_standard and is_msvc(self):
            tc.extra_cxxflags.append(f"-std:c++17")
        if not self.options.shared:
            tc.extra_defines.append("U_STATIC_IMPLEMENTATION")
        if is_apple_os(self):
            tc.extra_defines.append("_DARWIN_C_SOURCE")
            
        def yes_no(v: Any) -> str:
            return "yes" if v else "no"
            
        tc.configure_args.extend(
            [
                "--datarootdir=${prefix}/lib",  # do not use share
                f"--enable-release={yes_no(self.settings.build_type != "Debug")}",
                f"--enable-debug={yes_no(self.settings.build_type == "Debug")}",
                f"--enable-dyload={yes_no(self.options.with_dyload)}",
                f"--enable-extras={yes_no(self.options.with_extras)}",
                f"--enable-icuio={yes_no(self.options.with_icuio)}",
                "--disable-layoutex",
                "--disable-layout",
                f"--enable-tools={yes_no(self._enable_icu_tools)}",
                "--disable-tests",
                "--disable-samples",
            ])
        if cross_building(self):
            base_path = unix_path(self, self.dependencies.build["icu"].folders.package)
            tc.configure_args.append(f"--with-cross-build={base_path}")
            if self.settings.os in ["iOS", "tvOS", "watchOS"]:
                # ICU build scripts interpret all Apple platforms as 'darwin'.
                # Since this can coincide with the `build` triple, we need to tweak
                # the build triple to avoid the collision and ensure the scripts
                # know we are cross-building.
                host_triplet = f"{str(self.settings.arch)}-apple-darwin"
                build_triplet = f"{str(self.settings.arch)}-apple"
                tc.update_configure_args(
                    {
                        "--host": host_triplet,
                        "--build": build_triplet,
                    })
        else:
            arch64 = ["X64", "ARM"]
            bits = "64" if self.settings.arch in arch64 else "32"
            tc.configure_args.append(f"--with-library-bits={bits}")
        if self.settings.os != "Windows":
            # http://userguide.icu-project.org/icudata
            # This is the only directly supported behavior on Windows builds.
            tc.configure_args.append(f"--with-data-packaging={self.options.data_packaging}")
        tc.generate()

        if is_msvc(self):
            env = Environment()
            env.define("CC", "cl -nologo")
            env.define("CXX", "cl -nologo")
            if cross_building(self):
                env.define("icu_cv_host_frag", "mh-msys-msvc")
            env.vars(self).save_script("buildenv_icu_msvc")

    def build(self):
        self._patch_sources()

        if self.options.dat_package_file:
            dat_package_file = list((self.folders.source / "source" / "data" / "in").glob("*.dat"))
            if dat_package_file:
                shutil.copy(str(self.options.dat_package_file), dat_package_file[0])

        autotools = Autotools(self)
        autotools.configure(build_script_folder=self.folders.source / "source")
        autotools.make()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()

        dll_files = (self.folders.package / "lib").glob("*.dll")
        if dll_files:
            bin_dir = self.folders.package / "bin"
            mkdir(self, bin_dir)
            for dll in dll_files:
                dll_name = os.path.basename(dll)
                rm(self, dll_name, bin_dir)
                rename(self, src=dll, dst=bin_dir / dll_name)

        if self.settings.os != "Windows" and self.options.data_packaging in ["files", "archive"]:
            mkdir(self, self.folders.package / "res")
            rename(self, src=self._data_path, dst=self.folders.package / "res" / self._data_filename)

        # Copy some files required for cross-compiling
        config_dir = self.folders.package / "config"
        copy(self, "icucross.mk", src=self.folders.build / "config", dst=config_dir)
        copy(self, "icucross.inc", src=self.folders.build / "config", dst=config_dir)

        rmdir(self, self.folders.package / "lib" / "icu")
        rmdir(self, self.folders.package / "lib" / "man")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "ICU")

        prefix = "s" if self.settings.os == "Windows" and not self.options.shared else ""
        suffix = "d" if self.settings.os == "Windows" and self.settings.build_type == "Debug" else ""

        # icudata
        self.info.components["icu-data"].set_property("cmake_target_name", "ICU::data")
        icudata_libname = "icudt" if self.settings.os == "Windows" else "icudata"
        self.info.components["icu-data"].libs = [f"{prefix}{icudata_libname}{suffix}"]
        if not self.options.shared:
            self.info.components["icu-data"].defines.append("U_STATIC_IMPLEMENTATION")
            # icu uses c++, so add the c++ runtime
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.components["icu-data"].system_libs.append(libcxx)

        # Alias of data CMake component
        self.info.components["icu-data-alias"].set_property("cmake_target_name", "ICU::dt")
        self.info.components["icu-data-alias"].requires = ["icu-data"]

        # icuuc
        self.info.components["icu-uc"].set_property("cmake_target_name", "ICU::uc")
        self.info.components["icu-uc"].set_property("pkg_config_name", "icu-uc")
        self.info.components["icu-uc"].libs = [f"{prefix}icuuc{suffix}"]
        self.info.components["icu-uc"].requires = ["icu-data"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["icu-uc"].system_libs = ["m", "pthread"]
            if self.options.with_dyload:
                self.info.components["icu-uc"].system_libs.append("dl")
        elif self.settings.os == "Windows":
            self.info.components["icu-uc"].system_libs = ["advapi32"]

        # icui18n
        self.info.components["icu-i18n"].set_property("cmake_target_name", "ICU::i18n")
        self.info.components["icu-i18n"].set_property("pkg_config_name", "icu-i18n")
        icui18n_libname = "icuin" if self.settings.os == "Windows" else "icui18n"
        self.info.components["icu-i18n"].libs = [f"{prefix}{icui18n_libname}{suffix}"]
        self.info.components["icu-i18n"].requires = ["icu-uc"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["icu-i18n"].system_libs = ["m"]

        # Alias of i18n CMake component
        self.info.components["icu-i18n-alias"].set_property("cmake_target_name", "ICU::in")
        self.info.components["icu-i18n-alias"].requires = ["icu-i18n"]

        # icuio
        if self.options.with_icuio:
            self.info.components["icu-io"].set_property("cmake_target_name", "ICU::io")
            self.info.components["icu-io"].set_property("pkg_config_name", "icu-io")
            self.info.components["icu-io"].libs = [f"{prefix}icuio{suffix}"]
            self.info.components["icu-io"].requires = ["icu-i18n", "icu-uc"]

        if self.settings.os != "Windows" and self.options.data_packaging in ["files", "archive"]:
            self.info.components["icu-data"].resdirs = ["res"]
            data_path = (self.folders.package / "res" / self._data_filename).as_posix()
            self.info.runenv.prepend_path("ICU_DATA", data_path)
            if self._enable_icu_tools or self.options.with_extras:
                self.info.buildenv.prepend_path("ICU_DATA", data_path)

        if self._enable_icu_tools:
            # icutu
            self.info.components["icu-tu"].set_property("cmake_target_name", "ICU::tu")
            self.info.components["icu-tu"].libs = [f"{prefix}icutu{suffix}"]
            self.info.components["icu-tu"].requires = ["icu-i18n", "icu-uc"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["icu-tu"].system_libs = ["pthread"]

            # icutest
            self.info.components["icu-test"].set_property("cmake_target_name", "ICU::test")
            self.info.components["icu-test"].libs = [f"{prefix}icutest{suffix}"]
            self.info.components["icu-test"].requires = ["icu-tu", "icu-uc"]

    @property
    def _enable_icu_tools(self):
        return self.settings.os not in ["iOS", "tvOS", "watchOS", "Emscripten"]

    def _patch_sources(self):
        replace_in_file(
            self,
            self.folders.source / "source" / "configure",
            "if test -z \"$PYTHON\"",
            "if true",
            strict=False)
        # icu's configure appends /W4 to CFLAGS for MSVC; drop it so the quiet -w wins (D9025).
        replace_in_file(
            self,
            self.folders.source / "source" / "configure",
            'CFLAGS="$CFLAGS /W4"',
            'CFLAGS="$CFLAGS"',
            strict=False)

        if self.settings.os == "Windows":
            # https://unicode-org.atlassian.net/projects/ICU/issues/ICU-20545
            makeconv_cpp = self.folders.source / "source" / "tools" / "makeconv" / "makeconv.cpp"
            replace_in_file(
                self,
                makeconv_cpp,
                "pathBuf.appendPathPart(arg, localError);",
                "pathBuf.append(\"/\", localError); pathBuf.append(arg, localError);",
                strict=False)

        # relocatable shared libs on macOS
        if self.settings.os == "Mac":
            mh_darwin = self.folders.source / "source" / "config" / "mh-darwin"
            replace_in_file(self, mh_darwin, "-install_name $(libdir)/$(notdir", "-install_name @rpath/$(notdir")
            replace_in_file(
                self,
                mh_darwin,
                "-install_name $(notdir $(MIDDLE_SO_TARGET)) $(PKGDATA_TRAILING_SPACE)",
                "-install_name @rpath/$(notdir $(MIDDLE_SO_TARGET))")

        # workaround for https://unicode-org.atlassian.net/browse/ICU-20531
        mkdir(self, self.folders.build / "data" / "out" / "tmp")

        # workaround for "No rule to make target 'out/tmp/dirs.timestamp'"
        save(self, self.folders.build / "data" / "out" / "tmp" / "dirs.timestamp", "")

        # Quiet ICU's own chatter: every platform fragment echoes "generating dependency
        # information for <file>" (one line per source file), and each subdir's install rule
        # echoes an "install -c ... <header>" line per installed header. Both are pure noise that
        # `-s`/`V=0` can't suppress (explicit @echo/echo), so drop them.
        for mh in (self.folders.source / "source" / "config").glob("mh-*"):
            replace_in_file(
                self, mh,
                '@echo "generating dependency information for $<"', "@true", strict=False)
        for mf in (self.folders.source / "source").glob("*/Makefile.in"):
            for subdir in ("unicode", "layout"):
                replace_in_file(
                    self, mf,
                    f'echo "$(INSTALL_DATA) $$file $(DESTDIR)$(includedir)/{subdir}"', "true",
                    strict=False)

    @property
    def _data_filename(self):
        vtag = Version(self.version).major
        arch = self.settings.arch
        suffix = "b" if arch in {
            "ppc32", "ppc64",
            "sparc", "sparcv9",
            "s390", "s390x",
            "mips", "mips64",
        } else "l"
        return f"icudt{vtag}{suffix}.dat"

    @property
    def _data_path(self):
        data_dir_name = "icu"
        if self.settings.os == "Windows" and self.settings.build_type == "Debug":
            data_dir_name += "d"
        data_dir = self.folders.package / "lib" / data_dir_name / str(self.version)
        return data_dir / self._data_filename
