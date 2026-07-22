from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "neon2sse"
    version = "20260428"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "intel/ARM_NEON_2_x86_SSE")
        return Version(repo.latest_commit_date())

    def source(self):
        get(
            self,
            url="https://github.com/intel/ARM_NEON_2_x86_SSE/archive/ed59be8546632d5126ff69c87122ae5de20ffe4f.zip",
            sha256="10796c02ef44ac02478c41a7b68e4cec204c9de04d2d9374cecdaa2adf2cdbd7",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "NEON_2_SSE.h", src=self.folders.source, dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "NEON_2_SSE")
        self.info.set_property("cmake_target_name", "NEON_2_SSE::NEON_2_SSE")
        self.info.bindirs = []
        self.info.libdirs = []
