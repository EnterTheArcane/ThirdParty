from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "ispc"
    version = "1.31.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "ispc/ispc")
        return Version(repo.latest_release.removeprefix("v"))

    def build(self):
        if self.settings.os == "Windows":
            url = f"https://github.com/ispc/ispc/releases/download/v{self.version}/ispc-v{self.version}-windows.zip"
            sha256 = "9a18793800b91d5be7b851513672cd9a81a985a5a5dfec5611c2318e8ad4140a"
        elif self.settings.os == "Linux":
            if self.settings.arch == "ARM":
                url = f"https://github.com/ispc/ispc/releases/download/v{self.version}/ispc-v{self.version}-linux.aarch64.tar.gz"
                sha256 = "660ccac47ff7e0980b89b00a3ebd70201acf55f9e816c127fc28e868ab456193"
            else:
                url = f"https://github.com/ispc/ispc/releases/download/v{self.version}/ispc-v{self.version}-linux.tar.gz"
                sha256 = "d74089c835e10fd7e2c4b9225ced38b87d1fb53d35c7ceabd48cdf035da11b11"
        elif self.settings.os == "Mac":
            url = f"https://github.com/ispc/ispc/releases/download/v{self.version}/ispc-v{self.version}-macOS.universal.tar.gz"
            sha256 = "98c47aa9543f9f99f2c6778181d5c2f247c01c82653dd62f0c83e1fba923800e"
        else:
            raise RecipeInvalidConfiguration("Unsupported platform")
        get(self, url=url, sha256=sha256, destination=self.folders.build, strip_root=True)

    def package(self):
        copy(
            self,
            "*",
            src=self.folders.build / "bin",
            dst=self.folders.package / "bin")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.buildenv.prepend_path("PATH", self.folders.package / "bin")
