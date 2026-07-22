import os
import stat

from thirdparty import RecipeBase
from thirdparty.files import chdir, copy, get, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class Recipe(RecipeBase):
    name = "premake"
    version = "5.0.0-beta8"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "premake/premake-core")
        return Version(repo.latest_tag("v").removeprefix("v"))

    def source(self):
        if self.settings.os == "Linux" and self.settings.arch == "ARM":
            # Upstream only publishes an x64 Linux binary. Bootstrap the tagged
            # sources so build-tool packages on aarch64 contain a native tool.
            get(
                self,
                url=f"https://github.com/premake/premake-core/archive/refs/tags/v{self.version}.tar.gz",
                sha256="2a55195fd2b27e5aa3de8ff6d22cdb127232a86f801d06e7f673d30a0eba09ac",
                destination=self.folders.source,
                strip_root=True)
            # The Docker build image does not provide libuuid headers. Premake's
            # existing non-Linux fallback reads /dev/urandom and provides the
            # same public os.uuid() behavior without an external build dependency.
            replace_in_file(
                self, self.folders.source / "src" / "host" / "os_uuid.c",
                "#elif PLATFORM_LINUX", "#elif PLATFORM_LINUX && 0")
            replace_in_file(
                self, self.folders.source / "Bootstrap.mak", " -luuid", "")
            replace_in_file(
                self, self.folders.source / "premake5.lua",
                '\n\t\tfilter { "system:linux", "toolset:not cosmocc" }\n\t\t\tlinks\t\t{ "uuid" }\n',
                "\n")

    def build(self):
        if self.settings.os == "Linux" and self.settings.arch == "ARM":
            with chdir(self, self.folders.source):
                run(self, "make -f Bootstrap.mak linux CONFIG=release")
            return

        if self.settings.os == "Windows":
            url = f"https://github.com/premake/premake-core/releases/download/v{self.version}/premake-{self.version}-windows.zip"
            sha256 = "e64ce2ed8778e0098f63674cca61fe33941b5f0c8d9a4afd651152bdea3758ab"
        elif self.settings.os == "Linux":
            url = f"https://github.com/premake/premake-core/releases/download/v{self.version}/premake-{self.version}-linux.tar.gz"
            sha256 = "63edd3e7461eebdd45b500a3c7e8ad4e7a67d68f230010f9a97cbb71b4ec59c8"
        elif self.settings.os == "Mac":
            url = f"https://github.com/premake/premake-core/releases/download/v{self.version}/premake-{self.version}-macosx.tar.gz"
            sha256 = "fa73a46f093fa6f17494a3d063421aa6cae3ea825a61c62dd59fc2f07a256d03"
        else:
            raise Exception(f"Unsupported OS: {self.settings.os}")
        get(
            self,
            url=url,
            sha256=sha256,
            destination=self.folders.build,
            strip_root=False)

    def package(self):
        if self.settings.os == "Linux" and self.settings.arch == "ARM":
            source_dir = self.folders.source
            executable_dir = source_dir / "bin" / "release"
        else:
            source_dir = self.folders.build
            executable_dir = self.folders.build

        copy(self, "LICENSE.txt", src=source_dir, dst=self.folders.package / "licenses")
        suffix = ".exe" if self.settings.os == "Windows" else ""
        copy(self, f"premake5{suffix}", src=executable_dir, dst=self.folders.package / "bin")
        if self.settings.os != "Windows":
            premake5_path = self.folders.package / "bin" / "premake5"
            os.chmod(premake5_path, os.stat(premake5_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def package_info(self):
        self.info.includedirs = []
        self.info.libdirs = []
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)
