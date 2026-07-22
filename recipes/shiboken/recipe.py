import os
from pathlib import Path

from thirdparty import RecipeBase
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "shiboken"
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
            _remove_all(environment, "PATH", llvm_root / "bin")
            _remove_all(environment, "DYLD_LIBRARY_PATH", llvm_root / "lib")

        python = self.dependencies["cpython"]
        qt = self.dependencies["qt"]
        generator = self.dependencies.build["shiboken-generator"]
        python_root, python_exe, python_include, python_library, _ = _python_layout(python)
        qt_root = qt.folders.package

        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTS"] = False
        tc.variables["BUILD_DOCS"] = False
        tc.variables["QUIET_BUILD"] = True
        tc.variables["FORCE_LIMITED_API"] = "no"
        # Keep the native install layout and omit wheel-only duplicate targets/configs.
        tc.variables["is_pyside6_superproject_build"] = True
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
            tc.variables["QFP_PYTHON_TARGET_PATH"] = python_root.as_posix()
            tc.variables["QFP_PYTHON_HOST_PATH"] = host_python_exe.as_posix()
            tc.variables["QFP_QT_TARGET_PATH"] = qt_root.as_posix()
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
        for dependency in ("cpython", "qt"):
            deps.set_property(dependency, "cmake_find_mode", "none")
        for dependency in ("cpython", "shiboken-generator"):
            deps.set_property(dependency, "cmake_find_mode", "none", build_context=True)
        if cross_building(self):
            deps.set_property("qt", "cmake_find_mode", "none", build_context=True)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=Path("sources/shiboken6"))
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        CMake(self).install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_find_mode", "none")
        self.info.set_property("cmake_file_name", "Shiboken6")
        self.info.builddirs = [os.path.join("lib", "cmake", "Shiboken6")]

        runtime = self.info.components["shiboken6"]
        runtime.set_property("cmake_target_name", "Shiboken6::libshiboken")
        runtime.includedirs = [os.path.join("shiboken6", "include")]
        runtime.requires = ["cpython::python"]

        root = self.folders.package
        python = self.dependencies["cpython"]
        if python.settings.os == "Windows":
            site_packages = root / "Lib" / "site-packages"
        else:
            site_packages = root / "lib" / "python" / "site-packages"
        for environment in (self.info.buildenv, self.info.runenv):
            environment.prepend_path("PATH", root / "bin")
            environment.prepend_path("PYTHONPATH", site_packages)
            if self.settings.os == "Mac":
                environment.prepend_path("DYLD_LIBRARY_PATH", root / "lib")
            elif self.settings.os in ("Linux", "FreeBSD"):
                environment.prepend_path("LD_LIBRARY_PATH", root / "lib")


def _python_layout(dependency: RecipeBase) -> tuple[Path, Path, Path, Path, Path]:
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
