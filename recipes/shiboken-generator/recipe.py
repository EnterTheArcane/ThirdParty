import os
import shutil
from pathlib import Path

from thirdparty import RecipeBase
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import apply_patches, copy, get, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "shiboken-generator"
    version = "6.11.1"
    license = "LGPL-3.0-only"

    def latest_version(self):
        repo = GithubRepository(self, "qtproject/pyside-pyside-setup")
        return Version(repo.latest_release.removeprefix("v"))

    def validate(self):
        if cross_building(self):
            raise RecipeInvalidConfiguration(
                "shiboken-generator is a build-machine tool; require it with requires_tool()")

    def requirements(self):
        self.requires_tool("cmake")
        # These libraries belong to the machine that executes shiboken, not the bindings target.
        # Explicit native config paths in generate() provide their headers and link interfaces.
        self.requires_tool("cpython")
        self.requires_tool("llvm")
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
        # shiboken skips the C++ wrapper for classes with a private (inaccessible) destructor -
        # the wrapper's destructor would be implicitly deleted - but only when the generator is
        # NOT built with MSVC. clang-cl defines _MSC_VER (so Qt sets Q_CC_MSVC) and the skip is
        # wrongly disabled; the generated code is then compiled by clang-cl, which - unlike real
        # cl.exe - rejects a deleted destructor overriding a non-deleted virtual one
        # ("deleted function '~QClipboardWrapper' cannot override a non-deleted function"). Apply
        # the skip for clang too, so private-dtor singletons (QClipboard, QNetworkInformation, ...)
        # get no wrapper. This is the generator that produces every module's bindings, so the fix
        # is global.
        replace_in_file(
            self,
            self.folders.source / "sources" / "shiboken6_generator" / "ApiExtractor" / "abstractmetalang.cpp",
            "#ifndef Q_CC_MSVC\n    // PYSIDE-504:",
            "#if !defined(Q_CC_MSVC) || defined(Q_CC_CLANG)\n    // PYSIDE-504:")

    def generate(self):
        python = self.dependencies.build["cpython"]
        llvm = self.dependencies.build["llvm"]
        qt = self.dependencies.build["qt"]
        python_root, python_exe, python_include, python_library, _ = _python_layout(python)
        if self.settings.os == "Windows":
            # CMake's FindPython derives the Python version from the import-library filename and
            # cannot parse the unversioned python3.lib the cpython recipe intentionally ships, so
            # Development is reported missing. Point FindPython at a versioned-named copy in the
            # build dir (the import lib still references python3.dll). See the cpython recipe.
            major, minor = str(python.version).split(".")[:2]
            versioned_lib = self.folders.build / f"python{major}{minor}.lib"
            shutil.copy2(python_library, versioned_lib)
            python_library = versioned_lib
        qt_root = qt.folders.package
        llvm_root = llvm.folders.package

        build_env = VirtualBuildEnv(self)
        if self.settings.os == "Mac":
            # LLVM bundles libc++, so exposing its lib directory through
            # DYLD_LIBRARY_PATH can replace the system libc++ for every build-time
            # process. The Shiboken wrapper uses the fallback path instead.
            environment = build_env.environment()
            _remove_all(environment, "PATH", llvm_root / "bin")
            _remove_all(environment, "DYLD_LIBRARY_PATH", llvm_root / "lib")

        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTS"] = False
        tc.variables["BUILD_DOCS"] = False
        tc.variables["QUIET_BUILD"] = True
        # Consumers compose the generator with its Qt and LLVM tool dependencies.
        # Their package paths must not be baked into the installed executable.
        tc.variables["CMAKE_SKIP_INSTALL_RPATH"] = True
        # Keep the native install layout and omit wheel-only duplicate targets/configs.
        tc.variables["is_pyside6_superproject_build"] = True
        tc.variables["CLANG_INSTALL_DIR"] = llvm_root.as_posix()
        tc.variables["Clang_DIR"] = (llvm_root / "lib" / "cmake" / "clang").as_posix()
        for prefix in ("Python", "Python3"):
            tc.variables[f"{prefix}_ROOT_DIR"] = python_root.as_posix()
            tc.variables[f"{prefix}_FIND_STRATEGY"] = "LOCATION"
            tc.variables[f"{prefix}_EXECUTABLE"] = python_exe.as_posix()
            tc.variables[f"{prefix}_INCLUDE_DIR"] = python_include.as_posix()
            tc.variables[f"{prefix}_LIBRARY"] = python_library.as_posix()
            if self.settings.os == "Windows":
                tc.variables[f"{prefix}_FIND_REGISTRY"] = "NEVER"
        tc.variables["Qt6_DIR"] = (qt_root / "lib" / "cmake" / "Qt6").as_posix()
        tc.variables["QT6_INSTALL_PREFIX"] = qt_root.as_posix()
        tc.variables["QT6_INSTALL_BINS"] = "bin"
        tc.variables["QT6_INSTALL_LIBS"] = "lib"
        tc.variables["QT6_INSTALL_LIBEXECS"] = (
            "bin" if self.settings.os == "Windows" else "libexec")

        if self.settings.os == "Mac":
            llvm_lib = (llvm_root / "lib").as_posix()
            tc.variables["CMAKE_EXE_LINKER_FLAGS"] = f"-L{llvm_lib} -lc++abi"
            tc.variables["CMAKE_SHARED_LINKER_FLAGS"] = f"-L{llvm_lib} -lc++abi"
            tc.variables["CMAKE_BUILD_RPATH"] = llvm_lib

        tc.presets_build_environment = build_env.environment()
        tc.generate()
        # CMakeToolchain emits a default environment script; replace it with the filtered one.
        build_env.generate()

        deps = CMakeDeps(self)
        for dependency in ("cpython", "llvm", "qt"):
            deps.set_property(dependency, "cmake_find_mode", "none", build_context=True)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=Path("sources/shiboken6_generator"))
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        CMake(self).install()

    def package_info(self):
        self.info.set_property("cmake_find_mode", "none")
        self.info.set_property("cmake_file_name", "Shiboken6Tools")
        self.info.builddirs = [os.path.join("lib", "cmake", "Shiboken6Tools")]

        root = self.folders.package
        generator = root / "bin" / ("shiboken6.exe" if self.settings.os == "Windows" else "shiboken6")
        python = self.dependencies.build["cpython"]
        if python.settings.os == "Windows":
            site_packages = root / "Lib" / "site-packages"
        else:
            site_packages = root / "lib" / "python" / "site-packages"
        for environment in (self.info.buildenv, self.info.runenv):
            environment.prepend_path("PATH", root / "bin")
            environment.prepend_path("PYTHONPATH", site_packages)

        self.info.conf.tools.shiboken.generator = generator
        self.info.conf.tools.shiboken.generator_root = root


def _python_layout(dependency: RecipeBase) -> tuple[Path, Path, Path, Path, Path]:
    # The cpython recipe installs an unversioned / major-only layout (bin/python3,
    # include/python, lib/libpython3.<ext>, lib/python/site-packages) - NOT the classic
    # versioned python3.X names. Keep this in lockstep with shiboken's _python_layout.
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


def _remove_all(environment: Environment, name: str, value: Path):
    for candidate in (value, str(value)):
        while True:
            try:
                environment.remove(name, candidate)  # type: ignore[arg-type]
            except (KeyError, ValueError):
                break
