import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, get, copy, rm, rmdir, replace_in_file, collect_libs
from thirdparty.microsoft import is_msvc, VCVars
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    secure: bool = False
    override: bool = False
    inject: bool = False
    single_object: bool = False
    guarded: bool = False
    win_redirect: bool = False


class Recipe(RecipeBase[_Options]):
    name = "mimalloc"
    version = "3.4.3"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/mimalloc")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.os != "Windows":
            self.options.win_redirect = False

        # single_object and inject are options
        # only when overriding on Unix-like platforms:
        if is_msvc(self):
            self.options.single_object = False
            self.options.inject = False

        if self.options.shared:
            # single_object is valid only for static override:
            self.options.single_object = False

        # inject is valid only for Unix-like dynamic override:
        if not self.options.shared:
            self.options.inject = False

        # single_object and inject are valid only when
        # overriding on Unix-like platforms:
        if not self.options.override:
            self.options.single_object = False
            self.options.inject = False

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/mimalloc/archive/v{self.version}.tar.gz",
            sha256="7b043c26b64dde66344d144fbcac3664858a4eb32197793ea2a18feb32741ca1",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["MI_BUILD_TESTS"] = "OFF"
        tc.variables["MI_BUILD_SHARED"] = self.options.shared
        tc.variables["MI_BUILD_STATIC"] = not self.options.shared
        tc.variables["MI_BUILD_OBJECT"] = self.options.single_object
        tc.variables["MI_OVERRIDE"] = "ON" if self.options.override else "OFF"
        tc.variables["MI_SECURE"] = "ON" if self.options.secure else "OFF"
        tc.variables["MI_WIN_REDIRECT"] = "ON" if self.options.win_redirect else "OFF"
        tc.variables["MI_INSTALL_TOPLEVEL"] = "ON"
        tc.variables["MI_GUARDED"] = self.options.guarded
        tc.variables["MI_NO_OPT_ARCH"] = True
        tc.generate()

        VirtualBuildEnv(self).generate(scope="build")

        if is_msvc(self):
            vcvars = VCVars(self)
            vcvars.generate()

    def build(self):
        apply_patches(self)
        if is_msvc(self) and self.settings.arch == "x86" and self.options.shared:
            replace_in_file(
                self,
                self.folders.source / "CMakeLists.txt",
                "mimalloc-redirect.lib",
                "mimalloc-redirect32.lib",
                strict=False)
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        cmake = CMake(self)
        cmake.install()

        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

        if self.options.single_object:
            rm(self, "*.a", self.folders.package / "lib")
            shutil.copy(
                self.folders.package / "lib" / (self._obj_name + ".o"),
                self.folders.package / "lib" / self._obj_name)

        if self.settings.os == "Windows" and self.options.shared:
            if self.settings.arch == "X64":
                copy(
                    self, "mimalloc-redirect.dll",
                    src=self.folders.source / "bin",
                    dst=self.folders.package / "bin")
                copy(
                    self, "minject.exe",
                    src=self.folders.source / "bin",
                    dst=self.folders.package / "bin")
            elif self.settings.arch == "x86":
                copy(
                    self, "mimalloc-redirect32.dll",
                    src=self.folders.source / "bin",
                    dst=self.folders.package / "bin")
                copy(
                    self, "minject32.exe",
                    src=self.folders.source / "bin",
                    dst=self.folders.package / "bin")

        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "mimalloc")
        self.info.set_property("cmake_target_name", "mimalloc" if self.options.shared else "mimalloc-static")

        if self.options.inject:
            self.info.includedirs = []
            self.info.libdirs = []
            self.info.resdirs = []
            return

        if self.options.single_object:
            obj_ext = "o"
            obj_file = f"{self._obj_name}.{obj_ext}"
            obj_path = self.folders.package / "lib" / obj_file
            self.info.exelinkflags = [obj_path.as_posix()]
            self.info.sharedlinkflags = [obj_path.as_posix()]
            self.info.libdirs = []
            self.info.bindirs = []
        else:
            self.info.libs = collect_libs(self)

        if self.settings.os == "Linux":
            self.info.system_libs.append("pthread")
        if not self.options.shared:
            if self.settings.os == "Windows":
                self.info.system_libs.extend(["psapi", "shell32", "user32", "bcrypt"])
            elif self.settings.os == "Linux":
                self.info.system_libs.append("rt")

    @property
    def _obj_name(self):
        name = "mimalloc"
        if self.options.secure:
            name += "-secure"
        if self.settings.build_type not in ("Release", "RelWithDebInfo", "MinSizeRel"):
            name += f"-{str(self.settings.build_type).lower()}"
        return name

    @property
    def _lib_name(self):
        name = "mimalloc" if self.settings.os == "Windows" else "libmimalloc"

        if self.settings.os == "Windows" and not self.options.shared:
            name += "-static"
        if self.options.secure:
            name += "-secure"
        if self.settings.build_type not in ("Release", "RelWithDebInfo", "MinSizeRel"):
            name += f"-{str(self.settings.build_type).lower()}"
        return name
