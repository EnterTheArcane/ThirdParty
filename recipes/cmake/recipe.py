import os

from thirdparty import RecipeBase
from thirdparty.errors import RecipeException
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "cmake"
    version = "4.4.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "Kitware/CMake")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("ninja")

    def build(self):
        if self.settings.os == "Windows":
            if self.settings.arch == "ARM":
                url = f"https://github.com/Kitware/CMake/releases/download/v{self.version}/cmake-{self.version}-windows-arm64.zip"
                sha256 = "57437e918b2929bbd25b8d427611120149df02d4b216872e0f48f361f03d71e5"
            else:
                url = f"https://github.com/Kitware/CMake/releases/download/v{self.version}/cmake-{self.version}-windows-x86_64.zip"
                sha256 = "156d70eb7625a7b469444df7d0861d2af8d5d0a437fce32c350372b08f5620e8"
        elif self.settings.os == "Linux":
            if self.settings.arch == "ARM":
                url = f"https://github.com/Kitware/CMake/releases/download/v{self.version}/cmake-{self.version}-linux-aarch64.tar.gz"
                sha256 = "e98bb53e0b00a8f672424517d34c05bb9b94fd1c888c89e0b81bc8df51d1a94b"
            else:
                url = f"https://github.com/Kitware/CMake/releases/download/v{self.version}/cmake-{self.version}-linux-x86_64.tar.gz"
                sha256 = "3864eb649b4466ae126a64bbde1657adad78efbbaa068bf38201de5cf1b5349f"
        elif self.settings.os == "Mac":
            url = f"https://github.com/Kitware/CMake/releases/download/v{self.version}/cmake-{self.version}-macos-universal.tar.gz"
            sha256 = "09d6382059aa1b986b25fd1809459f5eb3da6a1ab342d44d6084265f38541397"
        else:
            raise RecipeException(f"Unsupported OS: {self.settings.os}")
        get(
            self,
            url=url,
            sha256=sha256,
            destination=self.folders.build,
            strip_root=True)

    def package(self):
        content_root = self.folders.build
        if self.settings.os == "Mac":
            content_root = content_root / "CMake.app" / "Contents"
        for subdir in ("bin", "share", "lib"):
            src = content_root / subdir
            if os.path.isdir(src):
                copy(self, "*", src=src, dst=self.folders.package / subdir)

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)
