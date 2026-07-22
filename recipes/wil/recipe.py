from thirdparty import RecipeBase
from thirdparty.files import apply_patches, get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "wil"
    version = "1.0.260126.7"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/wil")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/wil/archive/refs/tags/v{self.version}.tar.gz",
            sha256="de9e03b38ff0ff8d22048f00b111cb631d21c550328f12530ccba71c05c9e361",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        copy(
            self,
            pattern="*.h",
            dst=self.folders.package / "include",
            src=self.folders.source / "include",
        )

    def package_info(self):
        # Folders not used for header-only
        self.info.bindirs = []
        self.info.libdirs = []

        # https://github.com/microsoft/wil/blob/56e3e5aa79234f8de3ceeeaf05b715b823bc2cca/CMakeLists.txt#L53
        self.info.set_property("cmake_file_name", "wil")
        self.info.set_property("cmake_target_name", "WIL::WIL")
