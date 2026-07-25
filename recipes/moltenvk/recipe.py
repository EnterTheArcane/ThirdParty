from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import apply_patches, copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = True
    pic: bool = True
    hide_vulkan_symbols: bool = False
    tools: bool = True


class Recipe(RecipeBase[_Options]):
    name = "moltenvk"
    version = "1.4.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/MoltenVK")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if not self.options.shared:
            self.options.hide_vulkan_symbols = False

    def validate(self):
        if not is_apple_os(self):
            raise RecipeInvalidConfiguration(
                f"{self.name} is only supported on Apple platforms (Mac, iOS, tvOS)")

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("cereal")
        self.requires("glslang")
        self.requires("spirv-cross")
        self.requires("spirv-tools")
        self.requires("vulkan-headers")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/MoltenVK/archive/refs/tags/v{self.version}.tar.gz",
            sha256="9985f141902a17de818e264d17c1ce334b748e499ee02fcb4703e4dc0038f89c",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["MVK_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["MVK_VERSION"] = self.version
        tc.variables["MVK_WITH_SPIRV_TOOLS"] = True
        tc.variables["MVK_BUILD_SHADERCONVERTER_TOOL"] = self.options.tools
        if self.options.shared:
            tc.variables["MVK_HIDE_VULKAN_SYMBOLS"] = self.options.hide_vulkan_symbols
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        apply_patches(self)
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.libs = ["MoltenVK"]
        self.info.frameworks = ["Metal", "Foundation", "CoreFoundation", "QuartzCore", "IOSurface", "CoreGraphics"]
        if self.settings.os == "Mac":
            self.info.frameworks.extend(["AppKit", "IOKit"])
        elif self.settings.os in ["iOS", "tvOS"]:
            self.info.frameworks.append("UIKit")

        self.info.requires = [
            "cereal::cereal",
            "glslang::glslang-core",
            "glslang::spirv",
            "spirv-cross::spirv-cross-core",
            "spirv-cross::spirv-cross-msl",
            "spirv-cross::spirv-cross-reflect",
            "spirv-tools::spirv-tools-core",
            "vulkan-headers::vulkan-headers",
        ]

        if self.options.shared:
            moltenvk_icd_path = self.folders.package / "lib" / "MoltenVK_icd.json"
            self.info.runenv.prepend_path("VK_DRIVER_FILES", moltenvk_icd_path)
            self.info.runenv.prepend_path("VK_ICD_FILENAMES", moltenvk_icd_path)
