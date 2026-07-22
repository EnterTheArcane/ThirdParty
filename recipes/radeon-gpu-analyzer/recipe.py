from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "radeon-gpu-analyzer"
    version = "2.14.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "GPUOpen-Tools/radeon_gpu_analyzer")
        return Version(repo.latest_release)

    def validate(self):
        if self.settings.os not in ["Windows", "Linux"]:
            raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {self.settings.os}")

    def build(self):
        if self.settings.os == "Windows":
            url = f"https://github.com/GPUOpen-Tools/radeon_gpu_analyzer/releases/download/{self.version}/rga-windows-x64-{self.version}.zip"
            sha256 = "5b46941a72722ddb27c9427ca4413bccc6892b4185ec1d5b9120740687fa166d"
        elif self.settings.os == "Linux":
            url = f"https://github.com/GPUOpen-Tools/radeon_gpu_analyzer/releases/download/{self.version}/rga-{self.version}.tgz"
            sha256 = "341e7ca4f531e467be6de80a28342582230c54a42667a4eddda1b78489c35d62"
        else:
            raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {self.settings.os}")
        get(self, url=url, sha256=sha256, destination=self.folders.build, strip_root=False)

    def package(self):
        copy(self, "*", src=self.folders.build, dst=self.folders.package / "bin")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.buildenv.prepend_path("PATH", self.folders.package / "bin")
