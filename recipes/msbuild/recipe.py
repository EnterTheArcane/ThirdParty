import json
import re

import requests

from thirdparty import RecipeBase
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty.files import download, unzip
from thirdparty.scm import Version

# VSIX payloads are zips whose "Contents/" folder mirrors the VS installation root, so
# the package ends up shaped like a minimal VS root. Microsoft.Build.FileTracker.Msi is
# excluded (MSI, needs msiexec); MSBuild.command disables file tracking instead.
_PACKAGE_IDS = (
    "Microsoft.Build",
    "Microsoft.Build.Dependencies",
    "Microsoft.VisualStudio.VC.MSBuild.v170.Base",
    "Microsoft.VisualStudio.VC.MSBuild.v170.X64",
    "Microsoft.VisualStudio.VC.MSBuild.v170.X64.v143",
    "Microsoft.VisualStudio.VC.MSBuild.v170.ARM64",
    "Microsoft.VisualStudio.VC.MSBuild.v170.ARM64.v143",
    "Microsoft.VisualStudio.VC.MSBuild.Llvm",
)
# Resource packages are per-language; en-US is required for the task assemblies'
# .resources.dll neighbors.
_RESOURCE_PACKAGE_IDS = (
    "Microsoft.VisualStudio.VC.MSBuild.v170.Base.Resources",
    "Microsoft.VisualStudio.VC.MSBuild.Llvm.Resources",
)

_CHANNEL_URL = "https://aka.ms/vs/17/release/channel"


class Recipe(RecipeBase):
    name = "msbuild"
    version = "17.14"
    license = "Microsoft Visual Studio License"

    def latest_version(self):
        manifest = _load_manifest(self)
        build = next(
            (p for p in manifest["packages"] if p["id"] == "Microsoft.Build" and p.get("type") == "Vsix"),
            None)
        if build is None:
            return None
        return Version(".".join(str(build["version"]).split(".")[:2]))

    def validate(self):
        if str(self.settings.os) != "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} only runs on Windows")

    def build(self):
        manifest = _load_manifest(self)
        by_id: dict[str, list[dict]] = {}
        for pkg in manifest["packages"]:
            by_id.setdefault(str(pkg["id"]), []).append(pkg)

        wanted: list[dict] = []
        for pkg_id in _PACKAGE_IDS:
            candidates = by_id.get(pkg_id)
            if not candidates:
                raise RecipeException(
                    f"VS manifest no longer contains package '{pkg_id}'; "
                    f"update the id table in the {self.name} recipe")
            wanted.extend(c for c in candidates if _is_neutral(c))
        for pkg_id in _RESOURCE_PACKAGE_IDS:
            wanted.extend(
                c for c in by_id.get(pkg_id, ()) if str(c.get("language", "")) == "en-US")

        for pkg in wanted:
            for payload in pkg.get("payloads", ()):  # one vsix per package in practice
                filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(payload["fileName"]))
                download(
                    self, url=payload["url"], filename=filename,
                    sha256=str(payload["sha256"]).lower())
                unzip(self, filename, destination=self.folders.build / "vsix")
        self.output.info(f"downloaded {len(wanted)} VS feed packages")

    def package(self):
        from thirdparty.files import copy, save

        contents = self.folders.build / "vsix" / "Contents"
        if not contents.is_dir():
            raise RecipeException("no Contents/ extracted from the VSIX payloads")
        copy(self, "*", src=contents, dst=self.folders.package)
        save(
            self,
            self.folders.package / "licenses" / "NOTICE.txt",
            "Microsoft Build Tools components (MSBuild + Microsoft.Cpp targets)\n"
            "(c) Microsoft Corporation. All rights reserved.\n"
            "Licensed under the Microsoft Visual Studio License Terms.\n"
            "https://visualstudio.microsoft.com/license-terms/\n")

    def package_info(self):
        self.info.redistributable = False
        self.info.includedirs = []
        self.info.libdirs = []

        root = self.folders.package
        msbuild_bin = root / "MSBuild" / "Current" / "Bin"
        if str(self.settings.arch) == "ARM":
            msbuild_bin = msbuild_bin / "arm64"
        self.info.bindirs = [str(msbuild_bin)]
        self.info.buildenv.prepend_path("PATH", msbuild_bin)
        # MSBuild reads undefined properties from the environment: VCTargetsPath makes
        # .vcxproj imports resolve without any VS install/registry state.
        vc_targets = root / "MSBuild" / "Microsoft" / "VC" / "v170"
        self.info.buildenv.define_path("VCTargetsPath", f"{vc_targets}\\")
        # The package mirrors a VS installation root, so the existing conf that used to
        # point at an installed VS points here instead.
        self.info.conf.tools.msbuild.installation_path = str(root)
        self.info.set_property("msbuild_exe", str(msbuild_bin / "MSBuild.exe"))
        self.info.set_property("vc_targets_path", str(vc_targets))


def _is_neutral(pkg: dict) -> bool:
    lang = str(pkg.get("language", "neutral") or "neutral")
    return str(pkg.get("type")) == "Vsix" and lang in ("neutral", "en-US")


def _load_manifest(recipe: RecipeBase) -> dict:
    channel = requests.get(_CHANNEL_URL, timeout=60)
    channel.raise_for_status()
    manifest_url = next(
        item["payloads"][0]["url"] for item in channel.json()["channelItems"]
        if item["id"] == "Microsoft.VisualStudio.Manifests.VisualStudio")
    manifest = requests.get(manifest_url, timeout=300)
    manifest.raise_for_status()
    return json.loads(manifest.text)
