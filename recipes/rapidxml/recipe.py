import os

from thirdparty import RecipeBase
from thirdparty.files import copy, get, apply_patches
from thirdparty.scm import SourceForgeProject, Version


class Recipe(RecipeBase):
    name = "rapidxml"
    version = "1.13"
    license = "BSL-1.0", "MIT"

    def latest_version(self):
        project = SourceForgeProject(self, "rapidxml")
        return Version(project.latest_release(r"rapidxml-([\d.]+)\.zip"))

    def source(self):
        get(
            self,
            url=f"https://sourceforge.net/projects/rapidxml/files/rapidxml/rapidxml%20{self.version}/rapidxml-{self.version}.zip/download",
            sha256="c3f0b886374981bb20fabcf323d755db4be6dba42064599481da64a85f5b3571",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        copy(self, "license.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*.hpp", src=self.folders.source, dst=self.folders.package / "include" / "rapidxml")

    def package_info(self):
        self.info.includedirs.append(os.path.join("include", "rapidxml"))
        self.info.bindirs = []
        self.info.frameworkdirs = []
        self.info.libdirs = []
        self.info.resdirs = []
