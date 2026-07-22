from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rm, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "slang"
    version = "2026.13.1"
    license = "Apache-2.0", "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "shader-slang/slang")
        return Version(repo.latest_tag("v").removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        if cross_building(self):
            self.requires_tool(self.name)
        self.requires("fast-float")
        self.requires("lua")  # TODO
        self.requires("lz4")
        self.requires("miniz")
        self.requires("spirv-headers")
        self.requires("unordered-dense")
        self.requires("vulkan-headers")
        self.requires("zstd")

    def source(self):
        get(
            self,
            url=f"https://github.com/shader-slang/slang/archive/refs/tags/v{self.version}.tar.gz",
            sha256="2d112770f4af5459b0963473237523c4b1295ebe5627aa043c48cd3c8531158e",
            destination=self.folders.source,
            strip_root=True)
        get(
            self,
            url="https://github.com/lua/lua/archive/3fe7be956f23385aa1950dc31e2f25127ccfc0ea.tar.gz",
            sha256="4776526f89abeea61cce41a056577859180dbb2d4cb6c1dad00955872a1007bb",
            destination=self.folders.source / "external" / "lua",
            strip_root=True)
        get(
            self,
            url="https://github.com/swiftlang/swift-cmark/archive/924936d0427cb25a61169739a7660230bffa6ea6.tar.gz",
            sha256="1c51659bd47c34df1c8976f893adc43ba039a98f6eac4fa95d53d1e08ba6072a",
            destination=self.folders.source / "external" / "cmark",
            strip_root=True)
        apply_patches(self)
        # slang's CompilerFlags adds /W4 under USE_EXTRA_WARNINGS; drop it so the quiet -w wins
        # without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "cmake" / "CompilerFlags.cmake",
            "list(APPEND warning_flags /W4)", "list(APPEND warning_flags)", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["SLANG_LIB_TYPE"] = "SHARED" if self.options.shared else "STATIC"
        tc.cache_variables["SLANG_SLANG_LLVM_FLAVOR"] = "DISABLE"
        tc.cache_variables["SLANG_STANDARD_MODULE_DIR_NAME"] = "slang-standard-module"
        tc.variables["SLANG_ENABLE_GFX"] = False
        tc.variables["SLANG_ENABLE_SLANGD"] = False
        tc.variables["SLANG_ENABLE_SLANGRT"] = False
        tc.variables["SLANG_ENABLE_SLANG_GLSLANG"] = False
        tc.variables["SLANG_ENABLE_TESTS"] = False
        tc.variables["SLANG_ENABLE_EXAMPLES"] = False
        tc.variables["SLANG_ENABLE_SLANG_RHI"] = False
        tc.variables["SLANG_ENABLE_SLANGI"] = False
        tc.variables["SLANG_ENABLE_REPLAYER"] = False
        tc.variables["SLANG_ENABLE_SLANGC"] = True
        tc.variables["SLANG_ENABLE_DXIL"] = False
        tc.variables["SLANG_EXCLUDE_DAWN"] = True
        tc.variables["SLANG_EXCLUDE_TINT"] = True
        tc.variables["SLANG_USE_SYSTEM_LZ4"] = True
        tc.variables["SLANG_USE_SYSTEM_MINIZ"] = True
        tc.variables["SLANG_USE_SYSTEM_SPIRV_HEADERS"] = True
        tc.variables["SLANG_USE_SYSTEM_UNORDERED_DENSE"] = True
        tc.variables["SLANG_USE_SYSTEM_VULKAN_HEADERS"] = True
        if cross_building(self):
            # Reuse the build-machine generators (imported as executables by tools/CMakeLists.txt)
            # instead of building/running target-arch ones.
            host_generators = self.dependencies.build[self.name].folders.package / "bin"
            tc.cache_variables["SLANG_GENERATORS_PATH"] = host_generators.as_posix()
        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("lz4", "cmake_target_name", "LZ4::lz4")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        # Slang excludes its build-machine generators from the default install. Install the
        # upstream component explicitly so another architecture can consume the complete set.
        cmake.install(component="generators")
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.pdb", self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "slang")
        self.info.set_property("cmake_target_name", "slang::slang")
        self.info.libs = ["slang-compiler"]
