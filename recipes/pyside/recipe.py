import os
import shutil
from pathlib import Path

from thirdparty import RecipeBase
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import apply_patches, chmod, copy, get, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "pyside"
    version = "6.11.1"
    license = "LGPL-3.0-only"

    def latest_version(self):
        repo = GithubRepository(self, "qtproject/pyside-pyside-setup")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("cpython")
        self.requires_tool("shiboken-generator")
        self.requires("cpython")
        self.requires("qt")
        self.requires("shiboken")
        if cross_building(self):
            self.requires_tool("qt")

    def source(self):
        major = Version(self.version).major
        get(
            self,
            url=(f"https://download.qt.io/official_releases/QtForPython/pyside{major}/"
                 f"PySide{major}-{self.version}-src/"
                 f"pyside-setup-everywhere-src-{self.version}.tar.xz"),
            sha256="6ffd9835bb0dd2c56f061d62f1616bb1707cfc0202b80e3165d6be087f3965e2",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        build_env = VirtualBuildEnv(self)
        if self.settings.os == "Mac" and "llvm" in self.dependencies.build:
            environment = build_env.environment()
            llvm_root = self.dependencies.build["llvm"].folders.package
            # Shiboken asks `clang++` for macOS' implicit SDK include paths. Let that
            # resolve to Apple's driver; the packaged LLVM driver has no implicit SDK
            # and otherwise mixes its libc++ headers with the host's bare C headers.
            _remove_all(environment, "PATH", llvm_root / "bin")
            _remove_all(environment, "DYLD_LIBRARY_PATH", llvm_root / "lib")

        if cross_building(self):
            # PySide forwards CMAKE_SYSTEM_PROCESSOR to shiboken6 --arch. Recipe
            # architecture names such as X64 are not accepted there, so keep the
            # CMake target processor in the compiler/tooling spelling upstream expects.
            processor = self.settings.arch
            if processor == "X64":
                processor = "AMD64" if self.settings.os == "Windows" else "x86_64"
            elif processor == "ARM":
                processor = {
                    "Windows": "ARM64",
                    "Mac": "arm64",
                }.get(self.settings.os, "aarch64")
            self.conf.tools.cmake.toolchain.system_processor = processor

        python = self.dependencies["cpython"]
        qt = self.dependencies["qt"]
        shiboken = self.dependencies["shiboken"]
        generator = self.dependencies.build["shiboken-generator"]
        python_root, python_exe, python_include, python_library, _ = (
            _python_layout(python))
        shiboken_site = _python_site_packages(shiboken.folders.package, python) / "shiboken6"
        qt_root = qt.folders.package
        shiboken_root = shiboken.folders.package

        tc = CMakeToolchain(self)
        tc.variables["PYSIDE_SOURCE_DIR"] = self.folders.source.as_posix()
        tc.variables["BUILD_TESTS"] = False
        tc.variables["INSTALL_TESTS"] = False
        tc.variables["BUILD_DOCS"] = "no"
        tc.variables["QUIET_BUILD"] = True
        tc.variables["FORCE_LIMITED_API"] = "no"
        # Qt, Shiboken, and PySide are separate package roots whose run environments
        # provide their shared-library paths. Do not embed temporary build-root paths.
        tc.variables["CMAKE_SKIP_INSTALL_RPATH"] = True
        tc.variables["SHIBOKEN_PYTHON_MODULE_DIR"] = shiboken_site.as_posix()
        tc.variables["QFP_QT_TARGET_PATH"] = qt_root.as_posix()
        tc.variables["QFP_SHIBOKEN_TARGET_PATH"] = shiboken_root.as_posix()
        tc.variables["Shiboken6_DIR"] = (
            shiboken_root / "lib" / "cmake" / "Shiboken6").as_posix()
        tc.variables["Qt6_DIR"] = (qt_root / "lib" / "cmake" / "Qt6").as_posix()
        tc.variables["QT6_INSTALL_PREFIX"] = qt_root.as_posix()
        tc.variables["QT6_INSTALL_BINS"] = "bin"
        tc.variables["QT6_INSTALL_LIBS"] = "lib"
        tc.variables["QT6_INSTALL_LIBEXECS"] = (
            "bin" if self.settings.os == "Windows" else "libexec")

        if cross_building(self):
            host_python = self.dependencies.build["cpython"]
            _, host_python_exe, _, _, _ = _python_layout(host_python)
            host_qt_root = self.dependencies.build["qt"].folders.package
            tc.variables["Python_ROOT_DIR"] = python_root.as_posix()
            tc.variables["Python3_ROOT_DIR"] = python_root.as_posix()
            # Same cross FindPython workaround as shiboken: the cpython recipe installs an
            # unversioned libpython, but FindPython's cross Development search needs a versioned
            # library name plus the module ABI tag (it will not run the target interpreter).
            # Provide a versioned-named copy, the target headers, the host interpreter, and SOABI.
            discovery_library = _versioned_python_library(self, python, python_library)
            soabi = _python_soabi(python)
            for prefix in ("Python", "Python3"):
                tc.variables[f"{prefix}_EXECUTABLE"] = host_python_exe.as_posix()
                tc.variables[f"{prefix}_INCLUDE_DIR"] = python_include.as_posix()
                tc.variables[f"{prefix}_LIBRARY"] = discovery_library.as_posix()
                tc.variables[f"{prefix}_SOABI"] = soabi
            tc.variables["QFP_PYTHON_TARGET_PATH"] = python_root.as_posix()
            tc.variables["QFP_PYTHON_HOST_PATH"] = host_python_exe.as_posix()
            tc.variables["QFP_QT_HOST_PATH"] = host_qt_root.as_posix()
            tc.variables["QFP_SHIBOKEN_HOST_PATH"] = generator.folders.package.as_posix()
            if self.settings.os in ("Linux", "FreeBSD"):
                triplet = (
                    "aarch64-linux-gnu"
                    if self.settings.arch == "ARM"
                    else "x86_64-linux-gnu"
                )
                environment = Environment()
                environment.define("CPATH", f"/usr/{triplet}/include")
                environment.vars(self).save_script("buildenv_shiboken_target_headers")
        else:
            for prefix in ("Python", "Python3"):
                tc.variables[f"{prefix}_ROOT_DIR"] = python_root.as_posix()
                tc.variables[f"{prefix}_FIND_STRATEGY"] = "LOCATION"
                tc.variables[f"{prefix}_EXECUTABLE"] = python_exe.as_posix()
                tc.variables[f"{prefix}_INCLUDE_DIR"] = python_include.as_posix()
                tc.variables[f"{prefix}_LIBRARY"] = python_library.as_posix()
                if self.settings.os == "Windows":
                    tc.variables[f"{prefix}_FIND_REGISTRY"] = "NEVER"
            tc.variables["Shiboken6Tools_DIR"] = (
                generator.folders.package / "lib" / "cmake" / "Shiboken6Tools").as_posix()

        tc.presets_build_environment = build_env.environment()
        tc.generate()
        build_env.generate()

        deps = CMakeDeps(self)
        for dependency in ("cpython", "qt", "shiboken"):
            deps.set_property(dependency, "cmake_find_mode", "none")
        for dependency in ("cpython", "shiboken-generator"):
            deps.set_property(dependency, "cmake_find_mode", "none", build_context=True)
        if cross_building(self):
            deps.set_property("qt", "cmake_find_mode", "none", build_context=True)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        CMake(self).install()

        # Install the console entry points normally supplied by the wheel build.
        bin_dir = self.folders.package / "bin"
        if self.settings.os == "Windows":
            save(
                self,
                bin_dir / "pyside6-uic.cmd",
                '@"%~dp0uic.exe" -g python %*\n',
            )
            save(
                self,
                bin_dir / "pyside6-rcc.cmd",
                "@setlocal\n"
                '@set "_PYSIDE_RCC_ARGS=-g python"\n'
                '@for %%A in (%*) do @if "%%~A"=="--binary" set "_PYSIDE_RCC_ARGS="\n'
                '@"%~dp0rcc.exe" %_PYSIDE_RCC_ARGS% %*\n',
            )
        else:
            loader_environment = ""
            if self.settings.os == "Mac":
                # macOS strips DYLD_* variables while starting a script through /bin/sh.
                # Reconstruct the fallback path from Qt's surviving QT_PLUGIN_PATH.
                loader_environment = (
                    'qt_plugin_dir="${QT_PLUGIN_PATH%%:*}"\n'
                    'if [ -n "$qt_plugin_dir" ]; then\n'
                    '    qt_root="${qt_plugin_dir%/plugins}"\n'
                    '    export DYLD_FALLBACK_LIBRARY_PATH="${qt_root}/lib'
                    '${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"\n'
                    'fi\n'
                )

            save(
                self,
                bin_dir / "pyside6-uic",
                '#!/bin/sh\n' + loader_environment
                + 'exec "$(dirname "$0")/uic" -g python "$@"\n',
            )
            save(
                self,
                bin_dir / "pyside6-rcc",
                "#!/bin/sh\n" + loader_environment
                + 'for arg in "$@"; do\n'
                '    if [ "$arg" = "--binary" ]; then\n'
                '        exec "$(dirname "$0")/rcc" "$@"\n'
                "    fi\n"
                "done\n"
                'exec "$(dirname "$0")/rcc" -g python "$@"\n',
            )
            chmod(self, str(bin_dir / "pyside6-uic"), execute=True)
            chmod(self, str(bin_dir / "pyside6-rcc"), execute=True)

    def package_info(self):
        self.info.set_property("cmake_find_mode", "none")
        self.info.set_property("cmake_file_name", "PySide6")
        self.info.builddirs = [os.path.join("lib", "cmake", "PySide6")]

        binding = self.info.components["pyside6"]
        binding.set_property("cmake_target_name", "PySide6::pyside6")
        binding.includedirs = [os.path.join("PySide6", "include")]
        binding.requires = ["shiboken::shiboken6", "qt::qtCore"]

        site_packages = _python_site_packages(
            self.folders.package, self.dependencies["cpython"])
        root = self.folders.package
        for environment in (self.info.buildenv, self.info.runenv):
            environment.prepend_path("PATH", root / "bin")
            environment.prepend_path("PYTHONPATH", site_packages)
            if self.settings.os == "Mac":
                environment.prepend_path("DYLD_LIBRARY_PATH", root / "lib")
            elif self.settings.os in ("Linux", "FreeBSD"):
                environment.prepend_path("LD_LIBRARY_PATH", root / "lib")
        self.info.conf.tools.pyside.root = self.folders.package


def _python_soabi(dependency: RecipeBase) -> str:
    """Extension-module ABI tag (e.g. ``cpython-314-darwin``) that FindPython cannot derive in a
    cross build (it will not run the target interpreter and the cpython recipe's unversioned
    config-dir defeats its fallback). Matches CPython's release naming for the cross targets."""
    major, minor = str(dependency.version).split(".")[:2]
    if dependency.settings.os == "Mac":
        return f"cpython-{major}{minor}-darwin"
    arch = "aarch64" if dependency.settings.arch == "ARM" else "x86_64"
    return f"cpython-{major}{minor}-{arch}-linux-gnu"


def _versioned_python_library(recipe: RecipeBase, dependency: RecipeBase, python_library: Path) -> Path:
    """Copy the version-neutral target libpython to a versioned filename in the build folder, so
    FindPython (which derives the ABI from a versioned library name) can resolve it cross-building."""
    major, minor = str(dependency.version).split(".")[:2]
    if dependency.settings.os == "Windows":
        discovery_name = f"python{major}{minor}.lib"
    else:
        extension = "dylib" if dependency.settings.os == "Mac" else "so"
        discovery_name = f"libpython{major}.{minor}.{extension}"
    discovery_library = Path(recipe.folders.build) / discovery_name
    shutil.copy2(python_library, discovery_library)
    return discovery_library


def _python_layout(dependency: RecipeBase) -> tuple[Path, Path, Path, Path, Path]:
    # The cpython recipe installs an unversioned / major-only layout (bin/python3,
    # include/python, lib/libpython3.<ext>, lib/python/site-packages). Keep in lockstep
    # with shiboken's _python_layout.
    root = Path(dependency.folders.package)
    if dependency.settings.os == "Windows":
        return (
            root,
            root / "bin" / "python3.exe",
            root / "bin" / "include",
            root / "bin" / "libs" / "python3.lib",
            root / "bin" / "Lib" / "site-packages",
        )
    extension = "dylib" if dependency.settings.os == "Mac" else "so"
    return (
        root,
        root / "bin" / "python3",
        root / "include" / "python",
        root / "lib" / f"libpython3.{extension}",
        root / "lib" / "python" / "site-packages",
    )


def _python_site_packages(root: Path, dependency: RecipeBase) -> Path:
    if dependency.settings.os == "Windows":
        return root / "Lib" / "site-packages"
    return root / "lib" / "python" / "site-packages"


def _remove_all(environment: Environment, name: str, value: Path):
    for candidate in (value, str(value)):
        while True:
            try:
                environment.remove(name, candidate)  # type: ignore[arg-type]
            except (KeyError, ValueError):
                break
