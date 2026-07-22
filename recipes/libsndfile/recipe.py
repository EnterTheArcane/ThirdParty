from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libsndfile"
    version = "1.2.2"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "libsndfile/libsndfile")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/libsndfile/libsndfile/releases/download/{self.version}/libsndfile-{self.version}.tar.xz",
            sha256="3799ca9924d3125038880367bf1468e53a1b7e3686a934f098b7e1d286cdb80e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        # libsndfile 1.2.2 still declares cmake_minimum_required < 3.5, which CMake 4.x rejects.
        tc.cache_variables["CMAKE_POLICY_VERSION_MINIMUM"] = "3.5"
        tc.variables["ENABLE_EXTERNAL_LIBS"] = False
        tc.variables["ENABLE_MPEG"] = False
        tc.variables["BUILD_PROGRAMS"] = False
        tc.variables["BUILD_EXAMPLES"] = False
        tc.variables["BUILD_TESTING"] = False
        tc.variables["ENABLE_CPACK"] = False
        tc.variables["INSTALL_MANPAGES"] = False
        tc.generate()
        CMakeDeps(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "SndFile")
        self.info.set_property("cmake_target_name", "SndFile::sndfile")
        self.info.set_property("pkg_config_name", "sndfile")
        self.info.libs = ["sndfile"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs = ["m"]
