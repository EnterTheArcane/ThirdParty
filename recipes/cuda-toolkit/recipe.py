from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version, WebReleaseIndex

import os


_REDIST_BASE = "https://developer.download.nvidia.com/compute/cuda/redist/"

_REDIST_PLATFORMS = {
    ("Windows", "X64"): ("windows-x86_64", "zip"),
    ("Linux", "X64"): ("linux-x86_64", "tar.xz"),
    ("Linux", "ARM"): ("linux-sbsa", "tar.xz"),
}

_COMPONENTS = {
    "cuda_nvcc": ("13.3.73", {
        ("Windows", "X64"): "270214eaee58e49f8fca52a910a46afbfab227858e70897cba8afae10826280b",
        ("Linux", "X64"): "2ff9f9954060794a1c5134a933ccb45bec723d866b2629dadfe4a1a313f21068",
        ("Linux", "ARM"): "87044b338bf1cb062512c4bc790dd24d1c61b043119b5743f583128a954474a8",
    }),
    "cuda_crt": ("13.3.73", {
        ("Windows", "X64"): "9227ec7c80db10b7cb0d4ee71ed62ec7ae36e67890216413ab6f9afa35d577f0",
        ("Linux", "X64"): "1251aa9d668c607a103489cd2250773701e83a313e355578044622cf36713a9d",
        ("Linux", "ARM"): "d28e00e9455fac2c2defd6459a2dbcf118d13eb950646074290bc0d29e32a239",
    }),
    "cuda_cudart": ("13.3.29", {
        ("Windows", "X64"): "1feb7dd266813ffe8dbc24e115183a5ac35a4795c8d34aca0df85ab616b64d9c",
        ("Linux", "X64"): "1e59c4888267d27ba1a9bd0f3669a6439db1334a96e754cd9013c7c73e18dc9d",
        ("Linux", "ARM"): "0cdd73d11885062daf3aa98ad4d7b8bd84f89b398be11f7054edea9ed31f597d",
    }),
    "cccl": ("13.3.3.4.1", {
        ("Windows", "X64"): "48fab83097a636c4119da28bd3c9c9af9327e34c1efed17a14449cc2956ca6d1",
        ("Linux", "X64"): "26957cede74f9341174ecaf0372f3f886e7c46ceccb98d6dc775fe2b68d19268",
        ("Linux", "ARM"): "c0dd608d18ff7014c5fe0d3b2c7d1a6b9b855ec6fcad1f379cc3315610d22635",
    }),
    "cuda_nvrtc": ("13.3.33", {
        ("Windows", "X64"): "8519f678588610bf380ccaac130729aa1a624c407183e7ad9c319c19ecc63d2f",
        ("Linux", "X64"): "9e8f78278215babd1236b137252424ca7912c185bd093201f5d97f7dd763b74a",
        ("Linux", "ARM"): "d0502b25799be62a50b743c640e94a1722d20b1ee4ab70d697d71750f04d3b8a",
    }),
    "libnvjitlink": ("13.3.33", {
        ("Windows", "X64"): "43bc22509507c138c86885191bb2709b5d23506ea6abdc8bc64d9960e2b63363",
        ("Linux", "X64"): "f79e25bb1ef2f22f26c09897f6cb8719634f38e7330bd4700a1ea9ec9591eaff",
        ("Linux", "ARM"): "6ed3a14646bd53e25ccf03a52586cdd12b07ad48cf81fe79deac49b5d64c2ce6",
    }),
    "libnvvm": ("13.3.73", {
        ("Windows", "X64"): "ca8f11d5173ac16a166be8fafefbf9676542a097de1fce61b3f17696dffc1f27",
        ("Linux", "X64"): "206b1ab4979c09b5c32f8bf907c42bc9e16cd7454cf6036f524c45a58d060f93",
        ("Linux", "ARM"): "4bdb28ca53b714ae48887921f462a913b6806dd847978f8eba40434c85d1016f",
    }),
}

# Subdirectories of a merged CUDA toolkit tree we package (those that exist for the platform).
_TOOLKIT_DIRS = ("bin", "include", "lib", "lib64", "nvvm", "targets")


class Recipe(RecipeBase):
    name = "cuda-toolkit"
    version = "13.3.1"
    license = "NVIDIA CUDA Toolkit EULA"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://developer.nvidia.com/cuda-toolkit-archive")
        pattern = r"Latest Release[\s\S]*?CUDA Toolkit ([\d.]+)"
        return Version(index.latest_release(pattern))
    
    def validate(self):
        if self._platform_key not in _REDIST_PLATFORMS:
            raise RecipeInvalidConfiguration("Unsupported platform")

    def build(self):
        # Each component archive has a single <component>-<plat>-<ver>-archive/ root; strip_root drops
        # it so the bin/ include/ lib/ nvvm/ trees from every component merge into one toolkit root.
        for relpath, sha256 in _component_archives(self._platform_key):
            get(self, url=_REDIST_BASE + relpath, sha256=sha256,
                destination=self.folders.build, strip_root=True)

    def package(self):
        for subdir in _TOOLKIT_DIRS:
            src = self.folders.build / subdir
            if src.is_dir():
                copy(self, "*", src=src, dst=self.folders.package / subdir)
        # Each redist archive ships a LICENSE at its root (identical CUDA EULA across components).
        copy(self, "LICENSE", src=self.folders.build, dst=self.folders.package / "licenses")

        # CUDA 13's Linux redist ships libraries under lib/ (and lib/stubs/), but nvcc's profile
        # still searches lib64/ and lib64/stubs/ on 64-bit Linux. Add a lib64 -> lib symlink so
        # nvcc (and CMake's CUDA compiler detection) find libcudart_static/libcudadevrt/libcuda.
        if self.settings.os in ("Linux", "FreeBSD"):
            lib_dir = self.folders.package / "lib"
            lib64_dir = self.folders.package / "lib64"
            if lib_dir.is_dir() and not lib64_dir.exists():
                os.symlink("lib", lib64_dir)

    def package_info(self):
        # Build tool only: nothing for consumers to compile/link against directly.
        self.info.includedirs = []
        self.info.libdirs = []

        root = self.folders.package
        nvcc = root / "bin" / ("nvcc.exe" if self.settings.os == "Windows" else "nvcc")

        # Build-time discovery for consumers: nvcc on PATH plus the standard CUDA env vars. CMake's
        # ENABLE_LANGUAGE(CUDA) honors CUDACXX, and FindCUDAToolkit honors CUDAToolkit_ROOT/CUDA_PATH,
        # so a consumer just needs these in its build environment (composed in via requires_tool).
        self.info.buildenv.prepend_path("PATH", root / "bin")
        self.info.buildenv.define_path("CUDA_PATH", root)
        self.info.buildenv.define_path("CUDAToolkit_ROOT", root)
        self.info.buildenv.define_path("CUDACXX", nvcc)

    @property
    def _platform_key(self) -> tuple[str, str]:
        return str(self.settings.os), str(self.settings.arch)


def _component_archives(platform_key: tuple[str, str]):
    platform, extension = _REDIST_PLATFORMS[platform_key]
    for component, (version, hashes) in _COMPONENTS.items():
        filename = f"{component}-{platform}-{version}-archive.{extension}"
        yield f"{component}/{platform}/{filename}", hashes[platform_key]
