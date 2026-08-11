from pathlib import Path

from thirdparty import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty.errors import RecipeInvalidConfiguration


_LLVM_HOSTS = {("Windows", "X64"), ("Windows", "ARM"), ("Linux", "X64"), ("Linux", "ARM"), ("Mac", "ARM")}
_WINDOWS_TRIPLES = {"X64": "x86_64-pc-windows-msvc", "ARM": "aarch64-pc-windows-msvc"}
_LINUX_TRIPLES = {"X64": "x86_64-linux-gnu", "ARM": "aarch64-linux-gnu"}


class Recipe(RecipeBase):
    name = "clang-cl"
    version = "1"
    license = "Apache-2.0"

    def validate(self):
        build_os = str(self.settings_build.os)
        build_arch = str(self.settings_build.arch)
        if (build_os, build_arch) not in _LLVM_HOSTS:
            raise RecipeInvalidConfiguration(
                f"the llvm package has no prebuilt clang for a {build_os}/{build_arch} build "
                f"machine (LLVM no longer publishes Intel macOS binaries)")
        target_os = str(self.settings.os)
        if target_os in ("iOS", "tvOS", "visionOS"):
            raise RecipeInvalidConfiguration(f"use the apple-clang toolchain for {target_os} targets")
        if target_os == "Android":
            raise RecipeInvalidConfiguration("Android targets use the android-ndk toolchain")

    def toolchain_settings(self, settings: Settings):
        settings.compiler = "clang-cl"
        if settings.os == "Windows":
            settings.compiler_runtime = "dynamic"
        elif settings.os == "Linux":
            settings.compiler_libcxx = "libstdc++11"
        elif settings.os == "Mac":
            settings.compiler_libcxx = "libc++"

    def requirements(self):
        self.requires_tool("llvm")
        if self.settings.os == "Windows":
            self.requires("msvc")
            self.requires("windows-sdk")
        elif self.settings.os == "Linux":
            self.requires("linux-sysroot")
        elif self.settings.os == "Mac":
            self.requires("apple-sdk")

    def package_info(self):
        self.info.redistributable = False
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = []

        llvm_bin = Path(self.dependencies.build["llvm"].folders.package) / "bin"
        exe = ".exe" if self.settings_build.os == "Windows" else ""
        self.info.toolchain.family = "clang"
        # The same LLVM, driven through its cl.exe-compatible front. That is what recipes
        # branch on (flag syntax, .lib inputs, MSVC-ABI conventions), so it stays fixed for
        # every target rather than following settings.os.
        self.info.toolchain.front_kind = "clang-cl"
        self.info.toolchain.stdlib = str(self.settings.compiler_libcxx) if self.settings.compiler_libcxx else None
        self.info.toolchain.compilers = {
            "c": str(llvm_bin / f"clang-cl{exe}"),
            "cpp": str(llvm_bin / f"clang-cl{exe}"),
            "rc": str(llvm_bin / f"llvm-rc{exe}"),
        }
        self.info.toolchain.ar = str(llvm_bin / f"llvm-ar{exe}")
        self.info.toolchain.ranlib = str(llvm_bin / f"llvm-ranlib{exe}")
        self.info.toolchain.nm = str(llvm_bin / f"llvm-nm{exe}")
        self.info.toolchain.lib = str(llvm_bin / f"llvm-lib{exe}")

        if self.settings.os == "Windows":
            self.info.toolchain.linker = str(llvm_bin / f"lld-link{exe}")
            self.info.toolchain.mt = str(llvm_bin / f"llvm-mt{exe}")
            self.info.toolchain.target_triple = _WINDOWS_TRIPLES[str(self.settings.arch)]
            for dep_name in ("msvc", "windows-sdk"):
                dep = self.dependencies[dep_name]
                self.info.toolchain.msvc_include_dirs += [str(d) for d in dep.info.includedirs]
                self.info.toolchain.msvc_lib_dirs += [str(d) for d in dep.info.libdirs]
            self.info.toolchain.msbuild_toolset = "ClangCL"
            self.info.toolchain.msbuild_properties = {"LLVMInstallDir": str(llvm_bin.parent)}
            tools_version = self._llvm_tools_version(llvm_bin.parent)
            if tools_version:
                self.info.toolchain.msbuild_properties["LLVMToolsVersion"] = tools_version
            # The ClangCL toolset compiles with clang-cl but still links against the MSVC
            # CRT/STL and uses its headers/import libs, so MSBuild's Microsoft.CppBuild
            # targets must resolve the MSVC toolset. Merge the msvc package's MSBuild props
            # (VCToolsInstallDir/VCToolsVersion) so the toolset is found there rather than in
            # the payload-only msbuild package.
            msvc_props = self.dependencies["msvc"].info.toolchain.msbuild_properties or {}
            self.info.toolchain.msbuild_properties.update(msvc_props)
        else:
            # Off Windows the front end is still cl-style but the object format is not, so the
            # binutils and linker are the ELF/Mach-O ones (clang-cl drives them via /link).
            self.info.toolchain.strip = str(llvm_bin / f"llvm-strip{exe}")
            self.info.toolchain.objcopy = str(llvm_bin / f"llvm-objcopy{exe}")

        if self.settings.os == "Linux":
            sysroot = Path(self.dependencies["linux-sysroot"].folders.package)
            self.info.toolchain.sysroot = str(sysroot)
            self.info.toolchain.gcc_toolchain = str(sysroot / "usr")
            self.info.toolchain.target_triple = _LINUX_TRIPLES[str(self.settings.arch)]
        elif self.settings.os == "Mac":
            sdk = self.dependencies["apple-sdk"].info
            self.info.toolchain.apple_sysroot = sdk.get_property("sdk_path")
            self.info.toolchain.apple_sdk_name = sdk.get_property("sdk_name")
            self.info.toolchain.apple_min_version_flag = sdk.get_property("min_version_flag")

    @staticmethod
    def _llvm_tools_version(llvm_root: Path) -> "str | None":
        # The ClangCL msbuild toolset resolves clang's resource dir via LLVMToolsVersion,
        # which must match the lib/clang/<version> folder inside the LLVM package.
        clang_lib = llvm_root / "lib" / "clang"
        if clang_lib.is_dir():
            versions = sorted(p.name for p in clang_lib.iterdir() if p.is_dir())
            if versions:
                return versions[-1]
        return None
