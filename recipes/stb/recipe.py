from thirdparty import RecipeBase
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "stb"
    version = "20260415"
    license = "MIT", "Unlicense"

    def latest_version(self):
        return Version(GithubRepository(self, "nothings/stb").latest_commit_date())

    def source(self):
        get(
            self,
            url="https://github.com/nothings/stb/archive/31c1ad37456438565541f4919958214b6e762fb4.zip",
            sha256="617266695cf191a45bec2405427207011a09b057133134594b0db6ccbf9ee0b2",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*.h", src=self.folders.source, dst=self.folders.package / "include")
        copy(self, "stb_vorbis.c", src=self.folders.source, dst=self.folders.package / "include")
        rmdir(self, self.folders.package / "include" / "tests")
        rmdir(self, self.folders.package / "include" / "deprecated")
        copy(self, "*.h", src=self.folders.source / "deprecated", dst=self.folders.package / "include")
        copy(self, "stb_image.c", src=self.folders.source / "deprecated", dst=self.folders.package / "include")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
        self.info.defines.append("STB_TEXTEDIT_KEYTYPE=unsigned")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")

    @property
    def _version(self):
        return str(self.version)[4:]
