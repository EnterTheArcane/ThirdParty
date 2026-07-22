import os

from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "ninja"
    version = "1.13.2"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "ninja-build/ninja")
        return Version(repo.latest_release.removeprefix("v"))

    def build(self):
        if self.settings.os == "Windows":
            if self.settings.arch == "ARM":
                url = f"https://github.com/ninja-build/ninja/releases/download/v{self.version}/ninja-winarm64.zip"
                sha256 = "e52f0bdef9dfb1003229dbd6508a508c4073fd017247002adc66e5e806cb0391"
            else:
                url = f"https://github.com/ninja-build/ninja/releases/download/v{self.version}/ninja-win.zip"
                sha256 = "07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65"
        elif self.settings.os == "Linux":
            if self.settings.arch == "ARM":
                url = f"https://github.com/ninja-build/ninja/releases/download/v{self.version}/ninja-linux-aarch64.zip"
                sha256 = "fd2cacc8050a7f12a16a2e48f9e06fca5c14fc4c2bee2babb67b58be17a607fc"
            else:
                url = f"https://github.com/ninja-build/ninja/releases/download/v{self.version}/ninja-linux.zip"
                sha256 = "5749cbc4e668273514150a80e387a957f933c6ed3f5f11e03fb30955e2bbead6"
        else:
            url = f"https://github.com/ninja-build/ninja/releases/download/v{self.version}/ninja-mac.zip"
            sha256 = "c99048673aa765960a99cf10c6ddb9f1fad506099ff0a0e137ad8960a88f321b"

        get(
            self,
            url=url,
            sha256=sha256,
            destination=self.folders.build,
            strip_root=False)

    def package(self):
        dst = self.folders.package / "bin"
        if str(self.settings.os) == "Windows":
            copy(self, "ninja.exe", src=self.folders.build, dst=dst)
        else:
            copy(self, "ninja", src=self.folders.build, dst=dst)
            import stat
            ninja_path = dst / "ninja"
            os.chmod(ninja_path, os.stat(ninja_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)
