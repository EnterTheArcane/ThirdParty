from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import get, load, save, apply_patches, collect_libs
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    compile_as_cpp: bool = False
    with_tools: bool = False
    with_readline: bool = False


class Recipe(RecipeBase[_Options]):
    name = "lua"
    version = "5.5.0"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.lua.org/ftp/")
        return Version(index.latest_release(r"lua-([\d.]+)\.tar\.gz"))

    def configure(self):
        if not self.options.compile_as_cpp:
            self.settings.compiler_libcxx = None
            self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_tools and self.options.with_readline:
            self.requires("readline")

    def source(self):
        get(
            self,
            url=f"https://www.lua.org/ftp/lua-{self.version}.tar.gz",
            sha256="57ccc32bbbd005cab75bcc52444052535af691789dba2b9016d5c50640d68b3d",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["LUA_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["COMPILE_AS_CPP"] = self.options.compile_as_cpp
        tc.variables["SKIP_INSTALL_TOOLS"] = not self.options.with_tools
        tc.variables["WITH_READLINE"] = self.options.with_readline
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        # Extract the License/s from the header to a file
        tmp = load(self, self.folders.source / "src" / "lua.h")
        license_contents = tmp[tmp.find("/***", 1):tmp.find("****/", 1)]
        save(self, self.folders.package / "licenses" / "COPYING.txt", license_contents)
        cmake = CMake(self)
        cmake.install()
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.libs = collect_libs(self)
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["dl", "m"]
        if self.settings.os in ["Linux", "Mac"]:
            self.info.defines.extend(["LUA_USE_DLOPEN", "LUA_USE_POSIX"])
        elif self.settings.os == "Windows" and self.options.shared:
            self.info.defines.append("LUA_BUILD_AS_DLL")
