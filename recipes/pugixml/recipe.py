from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import collect_libs, copy, get, load, replace_in_file, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    header_only: bool = False
    wchar_mode: bool = False
    no_exceptions: bool = False


class Recipe(RecipeBase[_Options]):
    name = "pugixml"
    version = "1.16"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "zeux/pugixml")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        if not self.options.header_only:
            self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/zeux/pugixml/releases/download/v{self.version}/pugixml-{self.version}.tar.gz",
            sha256="4cee1ca4aad395170f4c7a07824f3bdd41f28316c6e1e1090a1425b278ec0b4b",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        if not self.options.header_only:
            tc = CMakeToolchain(self)
            tc.variables["BUILD_TESTS"] = False
            # For msvc shared
            tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
            tc.generate()

    def build(self):
        if not self.options.header_only:
            header_file = self.folders.source / "src" / "pugiconfig.hpp"
            # For the library build mode, options applied via change the configuration file
            if self.options.wchar_mode:
                replace_in_file(self, header_file, "// #define PUGIXML_WCHAR_MODE", "#define PUGIXML_WCHAR_MODE", strict=False)
            if self.options.no_exceptions:
                replace_in_file(self, header_file, "// #define PUGIXML_NO_EXCEPTIONS", "#define PUGIXML_NO_EXCEPTIONS", strict=False)
            cmake = CMake(self)
            cmake.configure()
            cmake.build()

    def package(self):
        readme_contents = load(self, self.folders.source / "readme.txt")
        license_contents = readme_contents[readme_contents.find("This library is"):]
        save(self, self.folders.package / "licenses" / "LICENSE", license_contents)
        if self.options.header_only:
            source_dir = self.folders.source / "src"
            copy(self, "*", src=source_dir, dst=self.folders.package / "include")
        else:
            cmake = CMake(self)
            cmake.install()
            rmdir(self, self.folders.package / "lib" / "cmake")
            rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "pugixml")
        self.info.set_property("cmake_target_name", "pugixml::pugixml")
        self.info.set_property("pkg_config_name", "pugixml")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
        if self.options.header_only:
            # For the "header_only" mode, options applied via global definitions
            self.info.defines.append("PUGIXML_HEADER_ONLY")
            if self.options.wchar_mode:
                self.info.defines.append("PUGIXML_WCHAR_MODE")
            if self.options.no_exceptions:
                self.info.defines.append("PUGIXML_NO_EXCEPTIONS")
            self.info.bindirs = []
            self.info.libdirs = []
        else:
            self.info.set_property(
                "cmake_target_aliases",
                ["pugixml::shared"] if self.options.shared else ["pugixml::static"],
            )
            self.info.libs = collect_libs(self)
