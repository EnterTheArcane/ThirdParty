from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    build_cube: bool = True
    build_vulkaninfo: bool = True
    build_icd: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vulkan-tools"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/Vulkan-Tools")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))
        
    def configure(self):
        if self.settings.os == "Mac" and cross_building(self):
            self.options.build_cube = False

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("vulkan-headers")
        self.requires("vulkan-loader")
        # vulkaninfo/cube use the X11/XCB/Wayland WSI system libraries on Linux.
        if self.settings.os in ("Linux", "FreeBSD"):
            self.requires("libxcb")
            self.requires("libx11")
            self.requires("libxrandr")
            self.requires("wayland")
            self.requires("wayland-protocols")
            self.requires("xkbcommon")
            if cross_building(self):
                # cube generates its Wayland protocol glue with wayland-scanner, which must run on
                # the build machine. The target (aarch64) scanner can't execute here, so pull in a
                # build-context wayland to provide a runnable host scanner (see generate()).
                self.requires_tool("wayland")
            if not self.conf.tools.gnu.pkg_config:
                self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/Vulkan-Tools/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="502b53a585f49036e45372724f652bacc1fad2c62396e321bc8f5fbc031c14d5",
            destination=self.folders.source,
            strip_root=True)
        # cube reads the wayland-scanner path from pkg-config (target -> aarch64 binary). When
        # cross-compiling that binary can't run on the build host, so let the recipe override
        # WAYLAND_SCANNER_EXECUTABLE with a runnable host scanner (set in generate()).
        replace_in_file(
            self,
            self.folders.source / "cube" / "CMakeLists.txt",
            "pkg_get_variable(WAYLAND_SCANNER_EXECUTABLE wayland-scanner wayland_scanner)",
            "if(NOT WAYLAND_SCANNER_EXECUTABLE)\n"
            "        pkg_get_variable(WAYLAND_SCANNER_EXECUTABLE wayland-scanner wayland_scanner)\n"
            "    endif()",
            strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        vulkan_headers_pkg = self.dependencies["vulkan-headers"].folders.package
        tc.variables["VULKAN_HEADERS_INSTALL_DIR"] = vulkan_headers_pkg.as_posix()
        tc.variables["BUILD_CUBE"] = self.options.build_cube
        tc.variables["BUILD_VULKANINFO"] = self.options.build_vulkaninfo
        tc.variables["BUILD_ICD"] = self.options.build_icd
        tc.variables["VULKAN_TOOLS_TESTS"] = False
        if self.settings.os == "Mac":
            # Use system ICD discovery instead of requiring MoltenVK source tree layout
            tc.variables["APPLE_USE_SYSTEM_ICD"] = True
        if self.settings.os in ("Linux", "FreeBSD"):
            # cube/vulkaninfo include vulkan.h + X11/Xlib.h with the platform macros defined, so the
            # xcb/X11 headers (in package dirs, not /usr/include) must be visible to every target.
            include_flags: list[str] = []
            for dep in self.dependencies.host.topological_sort.values():
                inc = dep.folders.package / "include"
                if inc.is_dir():
                    include_flags.append(f"-I{inc.as_posix()}")
            tc.extra_cflags.extend(include_flags)
            tc.extra_cxxflags.extend(include_flags)
        if self.settings.os in ("Linux", "FreeBSD") and cross_building(self):
            # Point cube at the build-context (host) wayland-scanner so protocol-code generation
            # runs natively instead of trying to execute the aarch64 target scanner.
            host_scanner = self.dependencies.build["wayland"].folders.package / "bin" / "wayland-scanner"
            tc.cache_variables["WAYLAND_SCANNER_EXECUTABLE"] = host_scanner.as_posix()
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()
        if self.settings.os in ("Linux", "FreeBSD"):
            VirtualBuildEnv(self).generate()
            PkgConfigDeps(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = ["bin"]
