import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name, is_apple_os, XCRun
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain, AutotoolsDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_python_bindings: bool = False


class Recipe(RecipeBase[_Options]):
    name = "util-linux"
    version = "2.42.2"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "util-linux/util-linux")
        return Version(repo.latest_tag_matching(r"v(\d+\.\d+(?:\.\d+)?)"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os != "Linux":
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux")

    def requirements(self):
        if self.settings.os == "Mac":
            self.requires("gettext")

    def source(self):
        # Use the kernel.org release tarball, which ships a pre-generated ./configure. The GitHub
        # archive does not, and regenerating it needs autopoint (from gettext), which is unavailable.
        major_minor = ".".join(self.version.split(".")[:2])
        get(
            self,
            url=f"https://mirrors.edge.kernel.org/pub/linux/utils/util-linux/v{major_minor}/util-linux-{self.version}.tar.xz",
            sha256="03a05d3adf9602ef128f2da05b84b3205ce60c351e5737c0370f74000679ce8a",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.append("--disable-all-programs")
        tc.configure_args.append("--enable-libuuid")
        if not self.options.with_python_bindings:
            tc.configure_args.append("--without-python")
        if self._has_sys_file_header:
            tc.extra_defines.append("HAVE_SYS_FILE_H")
        if "x86" in self.settings.arch:
            tc.extra_cflags.append("-mstackrealign")

        # Based on https://github.com/recipe-io/recipe-center-index/blob/c647b1/recipes/x264/all/recipe.py#L94
        if is_apple_os(self) and self.settings.arch == "ARM":
            tc.configure_args.append("--host=aarch64-apple-darwin")
            tc.extra_asflags = ["-arch arm64"]
            tc.extra_ldflags = ["-arch arm64"]
            if self.settings.os != "Mac":
                xcrun = XCRun(self)
                platform_flags = ["-isysroot", xcrun.sdk_path]
                apple_min_version_flag = AutotoolsToolchain(self).apple_min_version_flag
                if apple_min_version_flag:
                    platform_flags.append(apple_min_version_flag)
                tc.extra_asflags.extend(platform_flags)
                tc.extra_cflags.extend(platform_flags)
                tc.extra_ldflags.extend(platform_flags)

        tc.generate()

        deps = AutotoolsDeps(self)
        deps.generate()
        deps.generate()

    def build(self):
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING.BSD-3-Clause", src=self.folders.source / "Documentation" / "licenses", dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "bin")
        rmdir(self, self.folders.package / "sbin")
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "usr")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("pkg_config_name", "uuid")
        self.info.set_property("cmake_target_name", "libuuid::libuuid")
        self.info.set_property("cmake_file_name", "libuuid")
        self.info.set_property("cmake_target_aliases", ["util-linux::util-linux", "LibUUID::LibUUID"])

        self.info.libs = ["uuid"]
        self.info.includedirs.append(os.path.join("include", "uuid"))

        if self.settings.os == "Linux":
            self.info.system_libs.extend(["pthread"])

    @property
    def _has_sys_file_header(self):
        return self.settings.os in ["Linux", "Mac"]
