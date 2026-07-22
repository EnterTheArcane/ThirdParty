import os

from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "directxshadercompiler"
    version = "1.10.2605.24"
    license = "NCSA"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/DirectXShaderCompiler")
        return Version(repo.latest_release.removeprefix("v"))

    def validate(self):
        if self.settings.os not in ["Windows", "Linux"]:
            raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {self.settings.os}")

    def build(self):
        if self.settings.os == "Windows":
            url = f"https://github.com/microsoft/DirectXShaderCompiler/releases/download/v{self.version}/dxc_preview_2026_05_22.zip"
            sha256 = "045e2cfd900135f640954553038febbc98692599c5606376726d00541dae69b6"
        elif self.settings.os == "Linux":
            url = f"https://github.com/microsoft/DirectXShaderCompiler/releases/download/v{self.version}/linux_dxc_preview_2026_05_22.x86_64.tar.gz"
            sha256 = "6119f59c4f758973cadc170607ba83e657dd2c6fb7ca3dfb7362717a4ece8d9e"
        else:
            raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {self.settings.os}")
        get(self, url=url, sha256=sha256, destination=self.folders.build)

    def package(self):
        for subdir in ("bin", "include", "lib"):
            src = self.folders.build / subdir
            if os.path.isdir(src):
                copy(self, "*", src=src, dst=self.folders.package / subdir)

    def package_info(self):
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)

        if self.settings.os == "Windows":
            self.info.libs = ["dxcompiler"]
        else:
            self.info.libs = ["dxcompiler"]
            self.info.system_libs = ["dl", "pthread"]
