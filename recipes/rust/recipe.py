import os
import re
import urllib.request

from thirdparty import RecipeBase
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version


_VERSION = "1.97.1"
_DIST_DATE = "2026-07-16"
_CHANNEL_MANIFEST_URL = "https://static.rust-lang.org/dist/channel-rust-stable.toml"

_COMPONENTS = ("cargo", "rustc", "rust-std")

_HOST_TRIPLES = {
    "Windows": {
        "X64": "x86_64-pc-windows-msvc",
        "ARM": "aarch64-pc-windows-msvc",
    },
    "Linux": {
        "X64": "x86_64-unknown-linux-gnu",
        "ARM": "aarch64-unknown-linux-gnu",
    },
    "Mac": {
        "X64": "x86_64-apple-darwin",
        "ARM": "aarch64-apple-darwin",
    },
}

_SOURCES = {
    "x86_64-pc-windows-msvc": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-x86_64-pc-windows-msvc.tar.xz",
            "sha256": "1180ac0cd30ee98af682528c10505f5cba118f122aec9b7ca18ae605b1db38a0",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-x86_64-pc-windows-msvc.tar.xz",
            "sha256": "0119e2788f3391a891b2e0fe611e82b433670eeae76c45995b081d0ac7715c6d",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-x86_64-pc-windows-msvc.tar.xz",
            "sha256": "05f356609926e663a81e9697077214236514b2f9ff7a36e63b0070f43f073f66",
        },
    },
    "aarch64-pc-windows-msvc": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-aarch64-pc-windows-msvc.tar.xz",
            "sha256": "f0a7bdfcea4ff8d5420e4ebb6f6522c4a2beab4e5b343d47fb0c3f417ad36f1b",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-aarch64-pc-windows-msvc.tar.xz",
            "sha256": "63034fe17a2f7c7d6fadf3618600bc573cab94d56de85295225f2b7f86426317",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-aarch64-pc-windows-msvc.tar.xz",
            "sha256": "2b920577f215e98e9b56f63e845fbf96b268f7b3c9151805a9e75c0dc250a327",
        },
    },
    "x86_64-unknown-linux-gnu": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-x86_64-unknown-linux-gnu.tar.xz",
            "sha256": "e1be5f5ff7f7f80ca506fb65770b759edbdc6d303781ed71c5de8ec8a8394779",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-x86_64-unknown-linux-gnu.tar.xz",
            "sha256": "9819d0a32d56bd339585319c80260e332779f5541fd66838ab7e016d6c814819",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-x86_64-unknown-linux-gnu.tar.xz",
            "sha256": "1c1e704ae80126b7de34f72ea2825f7fd01736dec20732faed47374b95282fba",
        },
    },
    "aarch64-unknown-linux-gnu": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-aarch64-unknown-linux-gnu.tar.xz",
            "sha256": "8f70bcaccea5ba4db187c3fd4d64e24592b4e16af513497201f5909d61691dbe",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-aarch64-unknown-linux-gnu.tar.xz",
            "sha256": "b344b81f0cd4c2246c7da8b197fe7a339d7dd02bb15cb69b2524115d9c75224c",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-aarch64-unknown-linux-gnu.tar.xz",
            "sha256": "46aed8e63186350004d8ec6afca798811e6530b514352e5a8a26f3dc4939b3be",
        },
    },
    "x86_64-apple-darwin": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-x86_64-apple-darwin.tar.xz",
            "sha256": "1bd1029b579d0563ca851ebd095914871535bfd1978a123eeaa03107e89b0e03",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-x86_64-apple-darwin.tar.xz",
            "sha256": "3c38289f319bf02fa1c8149ce3e00f261e4efd14813a99f7f7ae4f180c7d1173",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-x86_64-apple-darwin.tar.xz",
            "sha256": "0fa78653023be5bdfeb419edc82e3b1346ccaa23eaa036491cce084101c741dd",
        },
    },
    "aarch64-apple-darwin": {
        "cargo": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/cargo-{_VERSION}-aarch64-apple-darwin.tar.xz",
            "sha256": "2d84a74e9558192a7de674aca6aa3ab7464bed2df97e0377156ddb7e09a0fd7a",
        },
        "rustc": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rustc-{_VERSION}-aarch64-apple-darwin.tar.xz",
            "sha256": "6076cad38ccabaa24325f26a74080a363a2633a9cd34c473a8977255d8a593cb",
        },
        "rust-std": {
            "url": f"https://static.rust-lang.org/dist/{_DIST_DATE}/rust-std-{_VERSION}-aarch64-apple-darwin.tar.xz",
            "sha256": "a4895f5c6995e83cab8687e46b14324592398049def71ce75ca308c981cf200d",
        },
    },
}


class Recipe(RecipeBase):
    name = "rust"
    version = _VERSION
    license = "MIT OR Apache-2.0"

    def latest_version(self):
        with urllib.request.urlopen(_CHANNEL_MANIFEST_URL, timeout=30) as response:
            manifest = response.read().decode("utf-8")

        match = re.search(r"rustc-([0-9]+\.[0-9]+\.[0-9]+)-src\.tar", manifest)
        if not match:
            match = re.search(r"rustc-([0-9]+\.[0-9]+\.[0-9]+)-", manifest)
        if not match:
            raise RecipeException("Could not find Rust stable version in channel manifest")
        return Version(match.group(1))

    def validate(self):
        self._target_triple

    def build(self):
        triple = self._target_triple
        for component in _COMPONENTS:
            entry = _SOURCES[triple][component]
            component_folder = self.folders.build / component
            os.makedirs(component_folder, exist_ok=True)
            get(
                self,
                url=entry["url"],
                sha256=entry["sha256"],
                destination=component_folder,
                strip_root=True)

    def package(self):
        triple = self._target_triple
        os.makedirs(self.folders.package / ".cargo", exist_ok=True)

        for component in _COMPONENTS:
            component_folder = self.folders.build / component
            payload_name = f"rust-std-{triple}" if component == "rust-std" else component
            payload_folder = component_folder / payload_name
            if not os.path.isdir(payload_folder):
                raise RecipeException(f"Could not find Rust component payload: {payload_folder}")

            copy(self, "*", src=payload_folder, dst=self.folders.package)
            copy(
                self,
                "LICENSE*",
                src=component_folder,
                dst=self.folders.package / "licenses" / component,
                keep_path=False,
            )

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []

        bin_dir = self.folders.package / "bin"
        cargo = bin_dir / f"cargo{self._exe_suffix}"
        rustc = bin_dir / f"rustc{self._exe_suffix}"

        self.info.buildenv.prepend_path("PATH", bin_dir)
        self.info.buildenv.define("RUSTUP_TOOLCHAIN", "stable")
        self.info.buildenv.define_path("CARGO_HOME", self.folders.package / ".cargo")
        self.info.buildenv.define_path("CARGO", cargo)
        self.info.buildenv.define_path("RUSTC", rustc)
        self.info.conf.tools.rust.dir = self.folders.package

    @property
    def _target_triple(self):
        os_name = str(self.settings.os)
        arch = str(self.settings.arch)
        try:
            return _HOST_TRIPLES[os_name][arch]
        except KeyError as exc:
            raise RecipeInvalidConfiguration(
                f"{self.name} has no prebuilt toolchain for {os_name}/{arch}"
            ) from exc

    @property
    def _exe_suffix(self):
        return ".exe" if self.settings.os == "Windows" else ""
