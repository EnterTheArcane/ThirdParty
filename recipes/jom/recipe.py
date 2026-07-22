from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version, WebReleaseIndex


class Recipe(RecipeBase):
    name = "jom"
    version = "1.1.7"
    license = "GPL-3.0-only"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://download.qt.io/official_releases/jom/")
        value = index.latest_release(r"jom_([\d_]+)\.zip")
        return Version(value.replace("_", "."))

    def validate(self):
        if self.settings.os != "Windows":
            raise RecipeInvalidConfiguration("jom is only available on Windows")

    def build(self):
        get(
            self,
            url="https://download.qt.io/official_releases/jom/jom_1_1_7.zip",
            sha256="4c8af345586a9a08fbfd2f613fcac748226d91a75627aa3581b297dd513046fe",
            destination=self.folders.build)

    def package(self):
        copy(self, "jom.exe", src=self.folders.build, dst=self.folders.package / "bin")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.buildenv.prepend_path("PATH", self.folders.package / "bin")
