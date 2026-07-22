from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, download, get, replace_in_file, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_executable: bool = False
    with_ssl: Literal[False, "openssl", "wolfssl", "schannel", "mbedtls", "libressl"] = "openssl"
    with_file: bool = True
    with_ftp: bool = True
    with_http: bool = True
    with_ldap: bool = False
    with_rtsp: bool = True
    with_dict: bool = True
    with_telnet: bool = True
    with_tftp: bool = True
    with_pop3: bool = True
    with_imap: bool = True
    with_smb: bool = False
    with_smtp: bool = True
    with_gopher: bool = True
    with_mqtt: bool = True
    with_libssh2: bool = False
    with_libidn: bool = False
    with_libgsasl: bool = False
    with_libpsl: bool = False
    with_largemaxwritesize: bool = False
    with_nghttp2: bool = False
    with_zlib: bool = True
    with_brotli: bool = False
    with_zstd: bool = False
    with_c_ares: bool = False
    with_threaded_resolver: bool = True
    with_proxy: bool = True
    with_crypto_auth: bool = True
    with_ntlm: bool = False
    with_cookies: bool = True
    with_ipv6: bool = True
    with_docs: bool = False
    with_misc_docs: bool = False
    with_verbose_debug: bool = True
    with_symbol_hiding: bool = False
    with_unix_sockets: bool = True
    with_verbose_strings: bool = True
    with_ca_bundle: Literal[False, "auto"] | str = "auto"
    with_ca_path: Literal[False, "auto"] | str = "auto"
    with_ca_fallback: bool = False
    with_form_api: bool = True
    with_websockets: bool = True
    with_apple_sectrust: bool = False


class Recipe(RecipeBase[_Options]):
    name = "curl"
    version = "8.21.0"
    license = "curl"

    def latest_version(self):
        repo = GithubRepository(self, "curl/curl")
        return Version(repo.latest_tag("curl-").removeprefix("curl-").replace("_", "."))

    def configure(self):
        self.options.with_libgsasl = False
        if not is_apple_os(self):
            self.options.with_apple_sectrust = False

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if self.options.with_ssl == "openssl":
            self.requires("openssl")
        elif self.options.with_ssl == "libressl":
            self.requires("libressl")
        elif self.options.with_ssl == "wolfssl":
            self.requires("wolfssl")
        elif self.options.with_ssl == "mbedtls":
            self.requires("mbedtls")
        if self.settings.os == "Linux" and self.options.with_ldap:
            self.requires("openldap")
        if self.options.with_nghttp2:
            self.requires("libnghttp2")
        if self.options.with_libssh2:
            self.requires("libssh2")
        if self.options.with_zlib:
            self.requires("zlib")
        if self.options.with_brotli:
            self.requires("brotli")
        if self.options.with_zstd:
            self.requires("zstd")
        if self.options.with_c_ares:
            self.requires("c-ares")
        if self.options.with_libpsl:
            self.requires("libpsl")
        if self.options.with_libidn:
            self.requires("libidn2")
        if self._is_using_cmake_build:
            self.requires_tool("cmake")
            if self._is_win_x_android:
                self.requires_tool("ninja")
        else:
            self.requires_tool("libtool")
            if not self.conf.tools.gnu.pkg_config:
                self.requires_tool("pkgconf")
            if self.settings.os in ["tvOS", "watchOS"]:
                self.requires_tool("gnu-config")
            if self.settings_build.os == "Windows":
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://github.com/curl/curl/archive/refs/tags/curl-{self.version.replace('.', '_')}.tar.gz",
            sha256="ec753aa6f408a3ca9f0d6d5f7a77417aecd1544db13c03ae5d443612bf367364",
            destination=self.folders.source,
            strip_root=True)
        cert_url = self.conf.tools.curl.cert.url or "https://curl.se/ca/cacert-2025-11-04.pem"
        cert_sha256 = self.conf.tools.curl.cert.sha256 or "8ac40bdd3d3e151a6b4078d2b2029796e8f843e3f86fbf2adbc4dd9f05e79def"
        download(
            self,
            cert_url,
            self.folders.source / "cacert.pem",
            verify=True,
            sha256=cert_sha256)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "find_package(NGHTTP2 MODULE)", "find_package(NGHTTP2 CONFIG REQUIRED)")
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "find_package(Cares MODULE REQUIRED)", "find_package(Cares CONFIG REQUIRED)")
        macros_cmake = self.folders.source / "CMake" / "Macros.cmake"
        replace_in_file(self, macros_cmake, "find_package(${_find_name})", "find_package(${_find_name} CONFIG REQUIRED)")
        replace_in_file(self, macros_cmake, "find_package(${_find_name} MODULE)", "find_package(${_find_name} CONFIG REQUIRED)")
        replace_in_file(self, macros_cmake, "find_package(${_find_name} REQUIRED)", "find_package(${_find_name} CONFIG REQUIRED)")
        # curl's PickyWarnings adds -W4 for MSVC; drop it so the quiet -w wins without D9025.
        replace_in_file(
            self, self.folders.source / "CMake" / "PickyWarnings.cmake",
            'list(APPEND _picky "-W4")', "list(APPEND _picky)", strict=False)
        replace_in_file(self, macros_cmake, "find_package(${_find_name} MODULE REQUIRED)", "find_package(${_find_name} CONFIG REQUIRED)")

    def generate(self):
        VirtualBuildEnv(self).generate()
        if self._is_win_x_android:
            tc = CMakeToolchain(self, generator="Ninja")
        else:
            tc = CMakeToolchain(self)
        tc.variables["ENABLE_UNICODE"] = True
        tc.variables["BUILD_TESTING"] = False
        tc.variables["BUILD_CURL_EXE"] = self.options.build_executable
        tc.cache_variables["ENABLE_CURL_MANUAL"] = False
        tc.variables["CURL_DISABLE_LDAP"] = not self.options.with_ldap
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["CURL_STATICLIB"] = not self.options.shared
        tc.variables["CMAKE_DEBUG_POSTFIX"] = ""
        tc.variables["CURL_USE_SCHANNEL"] = self.options.with_ssl == "schannel"
        tc.variables["CURL_USE_OPENSSL"] = self.options.with_ssl in ("openssl", "libressl")
        tc.variables["CURL_USE_WOLFSSL"] = self.options.with_ssl == "wolfssl"
        tc.variables["CURL_USE_MBEDTLS"] = self.options.with_ssl == "mbedtls"
        tc.variables["USE_NGHTTP2"] = self.options.with_nghttp2
        tc.variables["CURL_ZLIB"] = self.options.with_zlib
        tc.variables["CURL_BROTLI"] = self.options.with_brotli
        tc.variables["CURL_ZSTD"] = self.options.with_zstd
        tc.variables["CURL_USE_LIBPSL"] = self.options.with_libpsl
        tc.variables["CURL_USE_LIBSSH2"] = self.options.with_libssh2
        tc.variables["ENABLE_ARES"] = self.options.with_c_ares
        tc.variables["CURL_ENABLE_SMB"] = self.options.with_smb
        if not self.options.with_c_ares:
            tc.variables["ENABLE_THREADED_RESOLVER"] = self.options.with_threaded_resolver
        tc.variables["CURL_DISABLE_PROXY"] = not self.options.with_proxy
        tc.variables["USE_LIBIDN2"] = self.options.with_libidn
        if self.options.with_libidn:
            # Recipe won't generate this variable as we're setting prefixes,
            # and CMake might not either as it's looking for Libidn2
            # Ensure it's there
            tc.cache_variables["LIBIDN2_FOUND"] = True
        tc.variables["CURL_DISABLE_RTSP"] = not self.options.with_rtsp
        tc.variables["CURL_DISABLE_CRYPTO_AUTH"] = not self.options.with_crypto_auth
        tc.variables["CURL_DISABLE_VERBOSE_STRINGS"] = not self.options.with_verbose_strings
        if self.options.with_ssl == "libressl":
            tc.variables["CURL_DISABLE_SRP"] = True
        tc.variables["CURL_DISABLE_FORM_API"] = not self.options.with_form_api
        tc.variables["CURL_DISABLE_WEBSOCKETS"] = not self.options.with_websockets

        # Also disables NTLM_WB if set to false
        tc.variables["CURL_ENABLE_NTLM"] = self.options.with_ntlm

        if self.options.with_ca_bundle:
            tc.cache_variables["CURL_CA_BUNDLE"] = str(self.options.with_ca_bundle)
        else:
            tc.cache_variables["CURL_CA_BUNDLE"] = "none"

        if self.options.with_ca_path:
            tc.cache_variables["CURL_CA_PATH"] = str(self.options.with_ca_path)
        else:
            tc.cache_variables["CURL_CA_PATH"] = "none"

        tc.cache_variables["CURL_CA_FALLBACK"] = self.options.with_ca_fallback

        # TODO: refactor this and consider `CMAKE_TRY_COMPILE_CONFIGURATION` for all platforms
        #       see upstream issue 12180
        tc.variables["HAVE_SSL_SET0_WBIO"] = False
        tc.variables["HAVE_OPENSSL_SRP"] = True
        tc.variables["HAVE_SSL_CTX_SET_QUIC_METHOD"] = True

        if is_msvc(self):
            tc.cache_variables["CMAKE_TRY_COMPILE_CONFIGURATION"] = str(self.settings.build_type)

        if self.options.with_libssh2:
            # Not generated automatically
            tc.cache_variables["LIBSSH2_FOUND"] = True

        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("wolfssl", "cmake_additional_variables_prefixes", ["WolfSSL", "WOLFSSL"])
        deps.set_property("wolfssl", "cmake_file_name", "WolfSSL")

        if self.options.with_brotli:
            deps.set_property("brotli", "cmake_file_name", "Brotli")
            deps.set_property("brotli", "cmake_target_name", "CURL::brotli")
            deps.set_property("brotli", "cmake_additional_variables_prefixes", ["BROTLI", ])
            deps.set_property("brotli", "cmake_extra_variables", {"BROTLI_FOUND": "1"})

        if self.options.with_zstd:
            deps.set_property("zstd", "cmake_file_name", "Zstd")
            deps.set_property("zstd", "cmake_target_name", "CURL::zstd")
            deps.set_property("zstd", "cmake_additional_variables_prefixes", ["ZSTD", ])
            deps.set_property("zstd", "cmake_extra_variables", {"ZSTD_FOUND": "1", "ZSTD_VERSION": str(self.dependencies["zstd"].version)})

        if self.options.with_c_ares:
            deps.set_property("c-ares", "cmake_file_name", "Cares")
            deps.set_property("c-ares", "cmake_target_name", "CURL::cares")

        if self.options.with_libidn:
            deps.set_property("libidn2", "cmake_file_name", "Libidn2")
            deps.set_property("libidn2", "cmake_target_name", "CURL::libidn2")
            deps.set_property("libidn2", "cmake_additional_variables_prefixes", ["LIBIDN2"])

        if self.options.with_libpsl:
            deps.set_property("libpsl", "cmake_target_name", "CURL::libpsl")

        if self.options.with_libssh2:
            deps.set_property("libssh2", "cmake_target_name", "CURL::libssh2")

        if self.options.with_nghttp2:
            deps.set_property("libnghttp2", "cmake_file_name", "NGHTTP2")
            deps.set_property("libnghttp2", "cmake_target_name", "CURL::nghttp2")

        if self.options.with_ssl == "wolfssl":
            deps.set_property("wolfssl", "cmake_target_name", "CURL::wolfssl")
        # Now the rest of the dependencies that don't use the imported target directly
        # (openssl, zlib)

        if self.options.with_ssl == "mbedtls":
            deps.set_property("mbedtls", "cmake_target_name", "CURL::mbedtls")

        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "cacert.pem", src=self.folders.source, dst=self.folders.package / "res")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "CURL")
        self.info.set_property("cmake_target_name", "CURL::libcurl")
        self.info.set_property("pkg_config_name", "libcurl")

        self.info.components["curl"].resdirs = ["res"]
        if is_msvc(self):
            self.info.components["curl"].libs = ["libcurl_imp"] if self.options.shared else ["libcurl"]
        else:
            self.info.components["curl"].libs = ["curl"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["curl"].system_libs = ["rt", "pthread"]
        elif self.settings.os == "Windows":
            # used on Windows for VS build, native and cross mingw build
            self.info.components["curl"].system_libs = ["ws2_32", "bcrypt", "iphlpapi"]
            if self.options.with_ldap:
                self.info.components["curl"].system_libs.append("wldap32")
            if self.options.with_ssl == "libressl":
                self.info.components["curl"].system_libs.append("crypt32")
            if self.options.with_ssl == "schannel":
                self.info.components["curl"].system_libs.extend(["crypt32", "secur32"])
        elif is_apple_os(self):
            self.info.components["curl"].frameworks.append("CoreFoundation")
            self.info.components["curl"].frameworks.append("CoreServices")
            self.info.components["curl"].frameworks.append("SystemConfiguration")
            if self.options.with_apple_sectrust:
                self.info.components["curl"].frameworks.append("Security")
            if self.options.with_ldap:
                self.info.components["curl"].system_libs.append("ldap")

        if self._is_mingw:
            # provide pthread for dependent packages
            self.info.components["curl"].cflags.append("-pthread")
            self.info.components["curl"].exelinkflags.append("-pthread")
            self.info.components["curl"].sharedlinkflags.append("-pthread")

        if not self.options.shared:
            self.info.components["curl"].defines.append("CURL_STATICLIB=1")

        if self.options.with_ssl == "openssl":
            self.info.components["curl"].requires.append("openssl::openssl")
        if self.options.with_ssl == "libressl":
            self.info.components["curl"].requires.append("libressl::libressl")
        if self.options.with_ssl == "wolfssl":
            self.info.components["curl"].requires.append("wolfssl::wolfssl")
        if self.options.with_ssl == "mbedtls":
            self.info.components["curl"].requires.append("mbedtls::mbedtls")
        if self.settings.os == "Linux" and self.options.with_ldap:
            self.info.components["curl"].requires.append("openldap::openldap")
        if self.options.with_nghttp2:
            self.info.components["curl"].requires.append("libnghttp2::libnghttp2")
        if self.options.with_libssh2:
            self.info.components["curl"].requires.append("libssh2::libssh2")
        if self.options.with_zlib:
            self.info.components["curl"].requires.append("zlib::zlib")
        if self.options.with_brotli:
            self.info.components["curl"].requires.append("brotli::brotli")
        if self.options.with_zstd:
            self.info.components["curl"].requires.append("zstd::zstd")
        if self.options.with_c_ares:
            self.info.components["curl"].requires.append("c-ares::c-ares")
        if self.options.with_libpsl:
            self.info.components["curl"].requires.append("libpsl::libpsl")
        if self.options.with_libidn:
            self.info.components["curl"].requires.append("libidn2::libidn2")

        self.info.components["curl"].set_property("cmake_target_name", "CURL::libcurl")
        self.info.components["curl"].set_property("pkg_config_name", "libcurl")

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _is_win_x_android(self):
        return self.settings.os == "Android" and self.settings_build.os == "Windows"

    @property
    def _is_using_cmake_build(self):
        # This recipe always builds with CMake (see generate()); upstream's autotools
        # build path was not ported, so the CMake branch always applies.
        return True

    def _patch_sources(self):
        if self.options.with_largemaxwritesize:
            replace_in_file(
                self,
                self.folders.source / "include" / "curl" / "curl.h",
                "define CURL_MAX_WRITE_SIZE 16384",
                "define CURL_MAX_WRITE_SIZE 10485760")
