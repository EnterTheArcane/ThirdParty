from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "metal-cpp"
    version = "27"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "apple/metal-cpp")
        return Version(repo.latest_tag_matching(r"release/metal-cpp_macOS(\d+)_iOS\1"))

    def source(self):
        get(
            self,
            url=f"https://github.com/apple/metal-cpp/archive/refs/tags/release/metal-cpp_macOS{self.version}_iOS{self.version}.zip",
            sha256="16afce1932c476b254fca57c27ad9c0144134f9d1b9e329e09bb9df5cd07b69c",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(
            self,
            pattern="LICENSE.txt",
            dst=self.folders.package / "licenses",
            src=self.folders.source)
        copy(
            self,
            pattern="**.hpp",
            dst=self.folders.package / "include",
            src=self.folders.source,
            keep_path=True)

    def package_info(self):
        self.info.set_property("cmake_file_name", "metal-cpp")
        self.info.set_property("cmake_target_name", "metal-cpp::metal-cpp")
        self.info.set_property("pkg_config_name", "metal-cpp")
        self.info.bindirs = []
        self.info.frameworkdirs = []
        self.info.libdirs = []
        self.info.resdirs = []

        self.info.frameworks = ["Foundation", "Metal", "MetalKit", "QuartzCore"]
        self.info.frameworks.append("MetalFX")
