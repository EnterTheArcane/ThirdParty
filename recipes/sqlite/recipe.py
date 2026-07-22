from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, load, save
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    threadsafe: Literal[0, 1, 2] = 1
    enable_column_metadata: bool = True
    enable_dbstat_vtab: bool = False
    enable_explain_comments: bool = False
    enable_fts3: bool = False
    enable_fts3_parenthesis: bool = False
    enable_fts4: bool = False
    enable_fts5: bool = False
    enable_icu: bool = False
    enable_json1: bool = False
    enable_memsys5: bool = False
    enable_soundex: bool = False
    enable_preupdate_hook: bool = False
    enable_rtree: bool = True
    use_alloca: bool = False
    use_uri: bool = False
    omit_load_extension: bool = False
    omit_deprecated: bool = False
    enable_math_functions: bool = True
    enable_unlock_notify: bool = True
    enable_default_secure_delete: bool = False
    disable_gethostuuid: bool = False
    max_column: str | None = None
    max_variable_number: str | None = None
    max_blob_size: str | None = None
    build_executable: bool = True
    enable_default_vfs: bool = True
    enable_dbpage_vtab: bool = False


class Recipe(RecipeBase[_Options]):
    name = "sqlite"
    version = "3.53.3"
    license = "Unlicense"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.sqlite.org/download.html")
        return Version(index.latest_release(r"PRODUCT,([\d.]+),[^\n]*sqlite-amalgamation"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.enable_icu:
            self.requires("icu")

    def source(self):
        get(
            self,
            url="https://sqlite.org/2026/sqlite-amalgamation-3530300.zip",
            sha256="646421e12aac110282ef8cc68f1a62d4bb15fc7b8f09da0b53e29ee690500431",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["SQLITE3_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["SQLITE3_VERSION"] = self.version
        tc.variables["SQLITE3_BUILD_EXECUTABLE"] = self.options.build_executable
        tc.variables["THREADSAFE"] = self.options.threadsafe
        tc.variables["ENABLE_COLUMN_METADATA"] = self.options.enable_column_metadata
        tc.variables["ENABLE_DBSTAT_VTAB"] = self.options.enable_dbstat_vtab
        tc.variables["ENABLE_EXPLAIN_COMMENTS"] = self.options.enable_explain_comments
        tc.variables["ENABLE_FTS3"] = self.options.enable_fts3
        tc.variables["ENABLE_FTS3_PARENTHESIS"] = self.options.enable_fts3_parenthesis
        tc.variables["ENABLE_FTS4"] = self.options.enable_fts4
        tc.variables["ENABLE_FTS5"] = self.options.enable_fts5
        tc.variables["ENABLE_ICU"] = self.options.enable_icu
        tc.variables["ENABLE_JSON1"] = self.options.enable_json1
        tc.variables["ENABLE_MEMSYS5"] = self.options.enable_memsys5
        tc.variables["ENABLE_PREUPDATE_HOOK"] = self.options.enable_preupdate_hook
        tc.variables["ENABLE_SOUNDEX"] = self.options.enable_soundex
        tc.variables["ENABLE_RTREE"] = self.options.enable_rtree
        tc.variables["ENABLE_UNLOCK_NOTIFY"] = self.options.enable_unlock_notify
        tc.variables["ENABLE_DEFAULT_SECURE_DELETE"] = self.options.enable_default_secure_delete
        tc.variables["USE_ALLOCA"] = self.options.use_alloca
        tc.variables["USE_URI"] = self.options.use_uri
        tc.variables["OMIT_LOAD_EXTENSION"] = self.options.omit_load_extension
        tc.variables["OMIT_DEPRECATED"] = self.options.omit_deprecated
        tc.variables["ENABLE_MATH_FUNCTIONS"] = self.options.enable_math_functions
        tc.variables["HAVE_FDATASYNC"] = True
        tc.variables["HAVE_GMTIME_R"] = True
        tc.variables["HAVE_LOCALTIME_R"] = self.settings.os != "Windows"
        tc.variables["HAVE_POSIX_FALLOCATE"] = not (self.settings.os in ["Windows", "Android"] or is_apple_os(self))
        tc.variables["HAVE_STRERROR_R"] = True
        tc.variables["HAVE_USLEEP"] = True
        tc.variables["DISABLE_GETHOSTUUID"] = self.options.disable_gethostuuid
        if self.options.max_column:
            tc.variables["MAX_COLUMN"] = self.options.max_column
        if self.options.max_variable_number:
            tc.variables["MAX_VARIABLE_NUMBER"] = self.options.max_variable_number
        if self.options.max_blob_size:
            tc.variables["MAX_BLOB_SIZE"] = self.options.max_blob_size
        tc.variables["DISABLE_DEFAULT_VFS"] = not self.options.enable_default_vfs
        tc.variables["ENABLE_DBPAGE_VTAB"] = self.options.enable_dbpage_vtab
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        save(self, self.folders.package / "licenses" / "LICENSE", self._extract_license())
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "SQLite3")
        self.info.set_property("cmake_target_name", "SQLite::SQLite3")
        self.info.set_property("pkg_config_name", "sqlite3")

        self.info.components["sqlite"].libs = ["sqlite3"]
        if self.options.enable_icu:
            self.info.components["sqlite"].requires = ["icu::icu"]
        if self.options.omit_load_extension:
            self.info.components["sqlite"].defines.append("SQLITE_OMIT_LOAD_EXTENSION")
        if self.settings.os in ["Linux", "FreeBSD"]:
            if self.options.threadsafe:
                self.info.components["sqlite"].system_libs.append("pthread")
            if not self.options.omit_load_extension:
                self.info.components["sqlite"].system_libs.append("dl")
            if self.options.enable_fts5 or self.options.enable_math_functions:
                self.info.components["sqlite"].system_libs.append("m")
        elif self.settings.os == "Windows":
            if self.options.shared:
                self.info.components["sqlite"].defines.append("SQLITE_API=__declspec(dllimport)")

        self.info.components["sqlite"].set_property("cmake_target_name", "SQLite::SQLite3")
        self.info.components["sqlite"].set_property("pkg_config_name", "sqlite3")

    def _extract_license(self):
        header = load(self, self.folders.source / "sqlite3.h")
        license_content = header[3:header.find("***", 1)]
        return license_content
