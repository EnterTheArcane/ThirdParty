import re

from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, load, rm, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "onetbb"
    version = "2023.1.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "uxlfoundation/oneTBB")
        return Version(repo.latest_tag_matching(r"v(\d{4}\.\d+(?:\.\d+)?)"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/uxlfoundation/oneTBB/archive/v{self.version}.tar.gz",
            sha256="191288b52e1e6b17198000b64d77d194bb65e791be46ebc606e9b091781e2070",
            destination=self.folders.source,
            strip_root=True)
        # onetbb sets TBB_WARNING_LEVEL to a genex-wrapped /W4; empty the /W4 branch so the quiet
        # -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "cmake" / "compilers" / "MSVC.cmake",
            "$<$<NOT:$<CXX_COMPILER_ID:Intel>>:/W4>", "$<$<NOT:$<CXX_COMPILER_ID:Intel>>:>",
            strict=False)
        # The framework spells the GNU cross target processor `X64`. oneTBB's
        # x86 test does not recognize that spelling, so it omits -mwaitpkg even
        # though its headers enable _tpause for modern GCC. Accept X64 here to
        # keep the upstream runtime-gated WAITPKG optimization buildable.
        replace_in_file(
            self,
            self.folders.source / "cmake" / "compilers" / "GNU.cmake",
            '(AMD64|amd64|i.86|x86)',
            '(AMD64|amd64|X64|x64|i.86|x86)',
        )

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_SHARED_LIBS"] = True
        tc.variables["TBB_DISABLE_HWLOC_AUTOMATIC_SEARCH"] = True
        tc.variables["TBB_ENABLE_IPO"] = True
        tc.variables["TBB_STRICT"] = False
        tc.variables["TBB_TEST"] = False
        tc.variables["TBBMALLOC_BUILD"] = True
        tc.variables["TBBMALLOC_PROXY_BUILD"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")
        rm(self, "*.pdb", self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "TBB")
        # oneTBB switched to a year-based versioning scheme (2021+), but consumers like
        # OpenImageIO still request legacy versions, e.g. find_package(TBB 2017). Upstream
        # oneTBB ships its TBBConfigVersion.cmake with AnyNewerVersion compatibility so those
        # requests succeed; the default SameMajorVersion would reject 2023 against a 2017
        # request and break the build.
        self.info.set_property("cmake_config_version_compat", "AnyNewerVersion")

        def lib_name(name: str) -> str:
            if self.settings.build_type == "Debug":
                return name + "_debug"
            return name

        tbb = self.info.components["libtbb"]
        tbb.set_property("cmake_target_name", "TBB::tbb")
        tbb.libs = [lib_name("tbb")]
        if self.settings.os == "Windows":
            version_info = load(
                self,
                self.folders.package / "include" / "oneapi" / "tbb" / "version.h")
            binary_version = re.sub(
                r".*" + re.escape("#define __TBB_BINARY_VERSION ") + r"(\d+).*",
                r"\1",
                version_info,
                flags=re.MULTILINE | re.DOTALL,
            )
            tbb.libs.append(lib_name(f"tbb{binary_version}"))
        if self.settings.os in ["Linux", "FreeBSD"]:
            tbb.system_libs = ["m", "dl", "rt", "pthread"]

        tbbmalloc = self.info.components["tbbmalloc"]
        tbbmalloc.set_property("cmake_target_name", "TBB::tbbmalloc")
        tbbmalloc.libs = [lib_name("tbbmalloc")]
        if self.settings.os in ["Linux", "FreeBSD"]:
            tbbmalloc.system_libs = ["dl", "pthread"]

        # oneTBB does not build tbbmalloc_proxy on Windows ARM64
        # (see the top-level CMakeLists guard: TBBMALLOC_PROXY_BUILD AND NOT MSVC_CXX_ARCHITECTURE_ID MATCHES "ARM64"),
        # so the component must not be declared there.
        if not (self.settings.os == "Windows" and self.settings.arch == "ARM"):
            tbbproxy = self.info.components["tbbmalloc_proxy"]
            tbbproxy.set_property("cmake_target_name", "TBB::tbbmalloc_proxy")
            tbbproxy.libs = [lib_name("tbbmalloc_proxy")]
            tbbproxy.requires = ["tbbmalloc"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                tbbproxy.system_libs = ["m", "dl", "pthread"]
