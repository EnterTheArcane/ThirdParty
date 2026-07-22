from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, get, copy, rm, rmdir, replace_in_file
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    use_sse: bool = True


class Recipe(RecipeBase[_Options]):
    name = "opencolorio"
    version = "2.5.2"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "AcademySoftwareFoundation/OpenColorIO")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.arch not in ["X64"]:
            self.options.use_sse = False

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("imath")
        self.requires("libexpat")
        self.requires("little-cms")
        self.requires("minizip-ng")
        self.requires("openexr")
        self.requires("pystring")
        self.requires("yaml-cpp")

    def source(self):
        get(
            self,
            url=f"https://github.com/AcademySoftwareFoundation/OpenColorIO/releases/download/v{self.version}/OpenColorIO-{self.version}.tar.gz",
            sha256="cb8b0ae38fa523be8f899a0b2d6b8ca8cbcda7bc4322c91d1ac2b6b2a0082474",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        # Strip the hardcoded /W3 (added to PLATFORM_COMPILE_OPTIONS) so the quiet -w wins without
        # cl's D9025 spam - it's applied via a variable, so the toolchain filter can't catch it.
        replace_in_file(
            self,
            self.folders.source / "share" / "cmake" / "utils" / "CompilerFlags.cmake",
            '"${PLATFORM_COMPILE_OPTIONS};/W3"',
            '"${PLATFORM_COMPILE_OPTIONS}"',
            strict=False)
        for module in ("expat", "lcms2", "pystring", "yaml-cpp", "Imath", "minizip-ng"):
            rm(self, f"Find{module}.cmake", self.folders.source / "share" / "cmake" / "modules")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_VERBOSE_MAKEFILE"] = self.conf.tools.compilation.verbose
        tc.variables["OCIO_BUILD_PYTHON"] = False

        tc.variables["OCIO_USE_SSE"] = self.options.use_sse

        # openexr 2.x provides Half library
        tc.variables["OCIO_USE_OPENEXR_HALF"] = True

        tc.variables["OCIO_BUILD_APPS"] = True
        tc.variables["OCIO_BUILD_DOCS"] = False
        tc.variables["OCIO_BUILD_TESTS"] = False
        tc.variables["OCIO_BUILD_GPU_TESTS"] = False
        tc.variables["OCIO_USE_BOOST_PTR"] = False

        # avoid downloading dependencies
        tc.variables["OCIO_INSTALL_EXT_PACKAGE"] = "NONE"

        if is_msvc(self) and not self.options.shared:
            # define any value because ifndef is used
            tc.variables["OpenColorIO_SKIP_IMPORTS"] = True

        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0077"] = "NEW"
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0091"] = "NEW"

        if self.settings.os == "Linux":
            # Workaround for: upstream issue 13560
            libdirs_host = [l for dependency in self.dependencies.host.values() for l in dependency.info.aggregated_components().libdirs]
            tc.variables["CMAKE_BUILD_RPATH"] = ";".join(libdirs_host)

        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

        if not self.options.shared:
            copy(
                self, "*",
                src=self.folders.package / "lib" / "static",
                dst=self.folders.package / "lib")
            rmdir(self, self.folders.package / "lib" / "static")

        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "share")
        # nop for 2.x
        rm(self, "OpenColorIOConfig*.cmake", self.folders.package)
        rm(self, "*.pdb", self.folders.package / "bin")
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenColorIO")
        self.info.set_property("cmake_target_name", "OpenColorIO::OpenColorIO")
        self.info.set_property("pkg_config_name", "OpenColorIO")

        self.info.libs = ["OpenColorIO"]

        if is_apple_os(self):
            self.info.frameworks.extend(["Foundation", "IOKit", "ColorSync", "CoreGraphics"])

        if is_msvc(self) and not self.options.shared:
            self.info.defines.append("OpenColorIO_SKIP_IMPORTS")
