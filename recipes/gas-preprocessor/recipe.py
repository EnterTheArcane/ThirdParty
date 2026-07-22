from thirdparty import RecipeBase
from thirdparty.files import copy, download
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "gas-preprocessor"
    version = "20260401"
    license = "GPL-2.0-or-later"

    def latest_version(self):
        return Version(GithubRepository(self, "FFmpeg/gas-preprocessor").latest_commit_date())

    def source(self):
        download(
            self,
            url="https://raw.githubusercontent.com/FFmpeg/gas-preprocessor/ac1836309c2e77023c228b7184485597286289d3/gas-preprocessor.pl",
            sha256="7124d70cdecba7c5612f9a71fbf3f28514dd9c2ca3022f58ad793f88bb925fcf",
            filename=self.folders.source / "gas-preprocessor.pl")

    def package(self):
        copy(self, "gas-preprocessor.pl", src=self.folders.source, dst=self.folders.package / "bin")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.buildenv.prepend_path("PATH", self.folders.package / "bin")
