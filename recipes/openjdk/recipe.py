from pathlib import Path

from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, rm, symlinks
from thirdparty.scm import Version, WebReleaseIndex

class Recipe(RecipeBase):
    name = "openjdk"
    version = "26.0.2"
    license = (
        "GPL-2.0-only WITH Classpath-exception-2.0",
        "GPL-2.0-only WITH OpenJDK-assembly-exception-1.0",
    )

    def latest_version(self):
        home = WebReleaseIndex(self, "https://jdk.java.net/")
        feature = home.latest_release(
            r'GA Releases[\s\S]{0,500}?href="(?:\./|\.\./|/)?(\d+)/">JDK \d+</a>')
        release = WebReleaseIndex(self, f"https://jdk.java.net/{feature}/")
        return Version(release.latest_release(r"OpenJDK JDK ([\d.]+) GA Release"))

    _SOURCE_DATA = {
        ("Linux", "ARM"): {
            "url": "https://download.java.net/java/GA/jdk{version}/818d462d89b645c7a1aad49066c454e5/10/GPL/openjdk-{version}_linux-aarch64_bin.tar.gz",
            "sha256": "0ce6516c459e635d9f263f9b3492d83ec2c1ee26db128a6d904cae3d3096ceee",
        },
        ("Linux", "X64"): {
            "url": "https://download.java.net/java/GA/jdk{version}/818d462d89b645c7a1aad49066c454e5/10/GPL/openjdk-{version}_linux-x64_bin.tar.gz",
            "sha256": "2da09e9db53e5c4f9eeec045f49e7d8fbcd8e4153edbf0c269f520ff82fd4198",
        },
        ("Mac", "ARM"): {
            "url": "https://download.java.net/java/GA/jdk{version}/818d462d89b645c7a1aad49066c454e5/10/GPL/openjdk-{version}_macos-aarch64_bin.tar.gz",
            "sha256": "c99b35ad3063ef555361a243c44280b048e24e3cbbc4a59ee3b368e5a8958f3a",
        },
        ("Mac", "X64"): {
            "url": "https://download.java.net/java/GA/jdk{version}/818d462d89b645c7a1aad49066c454e5/10/GPL/openjdk-{version}_macos-x64_bin.tar.gz",
            "sha256": "c258f17d4095c0cda0489d33fc4988d4be193a280b7e1f045e961699dedbfc65",
        },
        ("Windows", "X64"): {
            "url": "https://download.java.net/java/GA/jdk{version}/818d462d89b645c7a1aad49066c454e5/10/GPL/openjdk-{version}_windows-x64_bin.zip",
            "sha256": "a4974cff5ec4c1042ebb070b2e582354786289e0448fd78a2c7b1a6a177f1080",
        },
    }

    def validate(self):
        if (self.settings.os, self.settings.arch) not in self._SOURCE_DATA:
            raise RecipeInvalidConfiguration("OpenJDK not available for this platform")

    def build(self):
        source = self._source
        get(
            self,
            url=source["url"],
            sha256=source["sha256"],
            destination=self.folders.build,
            strip_root=True)

    def package(self):
        symlinks.remove_broken_symlinks(self, str(self._jdk_home))

        copy(self, "*", src=self._jdk_home / "bin", dst=self.folders.package / "bin")
        copy(self, "*", src=self._jdk_home / "include", dst=self.folders.package / "include")
        copy(self, "*", src=self._jdk_home / "lib", dst=self.folders.package / "lib")
        copy(self, "*", src=self._jdk_home / "jmods", dst=self.folders.package / "lib" / "jmods")
        copy(self, "*", src=self._jdk_home / "conf", dst=self.folders.package / "conf")
        copy(self, "*", src=self._jdk_home / "legal", dst=self.folders.package / "licenses")
        copy(self, "release", src=self._jdk_home, dst=self.folders.package, keep_path=False)

        if self.settings.os == "Windows":
            for runtime_dll in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
                rm(self, runtime_dll, self.folders.package / "bin")

    def package_info(self):
        java_home = self.folders.package
        bin_dir = java_home / "bin"
        java_exe = bin_dir / ("java.exe" if self.settings.os == "Windows" else "java")

        self.info.buildenv.define_path("JAVA_HOME", java_home)
        self.info.runenv.define_path("JAVA_HOME", java_home)
        self.info.buildenv.prepend_path("PATH", bin_dir)
        self.info.runenv.prepend_path("PATH", bin_dir)
        self.info.conf.tools.openjdk.java_home = str(java_home)
        self.info.conf.tools.openjdk.java = str(java_exe)

    @property
    def _jdk_home(self) -> Path:
        if self.settings.os == "Mac":
            return self.folders.build / "Contents" / "Home"
        return self.folders.build

    @property
    def _source(self) -> dict[str, str]:
        source = dict(self._SOURCE_DATA[(self.settings.os, self.settings.arch)])
        source["url"] = source["url"].format(version=self.version)
        return source
