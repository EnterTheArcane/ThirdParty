import os
import platform
import re
import subprocess
import tempfile
import textwrap
from typing import Any

from thirdparty._internal.model.version import Version
from thirdparty._internal.output import Output
from thirdparty._internal.util.files import load
from thirdparty._internal.util.runners import check_output_runner, detect_runner
from thirdparty.errors import RecipeException


def detect_os() -> str:
    the_os = platform.system()
    if the_os == "Darwin":
        the_os = "Mac"
    return the_os


def detect_arch() -> str | None:
    machine = platform.machine().lower()
    if "arm64" in machine or "aarch64" in machine:
        return "ARM"
    if "86" in machine or "64" in machine:
        return "X64"
    return None


def _parse_gnu_libc(ldd_output: str):
    first_line = ldd_output.partition("\n")[0]
    if any(glibc_indicator in first_line for glibc_indicator in ["GNU libc", "GLIBC"]):
        return first_line.split()[-1].strip()
    return None


def _detect_gnu_libc(ldd: str = "/usr/bin/ldd"):
    if platform.system() != "Linux":
        Output(scope="detect_api").warning("detect_gnu_libc() only works on Linux")
        return None
    try:
        ldd_output = check_output_runner(f"{ldd} --version")
        version = _parse_gnu_libc(ldd_output)
        if version is None:
            first_line = ldd_output.partition("\n")[0]
            Output(scope="detect_api").warning(
                f"detect_gnu_libc() did not detect glibc in the first line of output from '{ldd} --version': '{first_line}'")
            return None
        return version
    except Exception as e:
        Output(scope="detect_api").debug(
            f"Couldn't determine the glibc version from the output of the '{ldd} --version' command {e}")
    return None


def _parse_musl_libc(ldd_output: str):
    lines = ldd_output.splitlines()
    if "musl libc" not in lines[0]:
        return None
    return lines[1].split()[-1].strip()


def _detect_musl_libc(ldd: str = "/usr/bin/ldd"):
    if platform.system() != "Linux":
        Output(scope="detect_api").warning(
            "detect_musl_libc() only works on Linux")
        return None

    d = tempfile.mkdtemp()
    tmp_file = os.path.join(d, "err")
    try:
        with open(tmp_file, "w") as stderr:
            check_output_runner(f"{ldd}", stderr=stderr, ignore_error=True)
        ldd_output = load(tmp_file)
        version = _parse_musl_libc(ldd_output)
        if version is None:
            first_line = ldd_output.partition("\n")[0]
            Output(scope="detect_api").warning(
                f"detect_musl_libc() did not detect musl libc in the first line of output from '{ldd}': '{first_line}'")
            return None
        return version
    except Exception as e:
        Output(scope="detect_api").debug(
            f"Couldn't determine the musl libc version from the output of the '{ldd}' command {e}")
    finally:
        try:
            os.unlink(tmp_file)
        except OSError:
            pass
    return None


def detect_libc(ldd: str = "/usr/bin/ldd"):
    if platform.system() != "Linux":
        Output(scope="detect_api").warning(
            f"detect_libc() is only supported on Linux currently")
        return None, None
    version = _detect_gnu_libc(ldd)
    if version is not None:
        return "gnu", version
    version = _detect_musl_libc(ldd)
    if version is not None:
        return "musl", version
    Output(scope="detect_api").warning(
        f"Couldn't detect the libc provider and version")
    return None, None


def detect_libcxx(compiler: str, version: Any, compiler_exe: str | None = None):
    assert isinstance(version, Version)

    def _detect_gcc_libcxx(version_: Any, executable: str) -> str:
        output = Output(scope="detect_api")
        # Assumes a working g++ executable
        if executable == "g++":  # we can rule out old gcc versions
            new_abi_available = version_ >= "5.1"
            if not new_abi_available:
                return "libstdc++"

        main = textwrap.dedent(
            """
            #include <string>

            static_assert(sizeof(std::string) != sizeof(void*), "using libstdc++");
            int main(){}
            """)
        # -fsyntax-only to omit the output and stop early (but enough for our static_assert).
        # -xc++ and - to tell the compiler to compile code from stdin and treat it as C++.
        completed_process = subprocess.run(
            [executable, "-std=c++11", "-fsyntax-only", "-xc++", "-"], input=main, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        error, out_str = completed_process.returncode, completed_process.stdout
        if error:
            if "using libstdc++" in out_str:
                output.info("gcc C++ standard library: libstdc++")
                return "libstdc++"
            # Other error, but can't know, lets keep libstdc++11
            output.warning("compiler.libcxx check error: %s" % out_str)
            output.warning("Couldn't deduce compiler.libcxx for gcc>=5.1, assuming libstdc++11")
        else:
            output.info("gcc C++ standard library: libstdc++11")
        return "libstdc++11"

        # This is not really a detection in most cases  # Get compiler C++ stdlib

    if compiler == "apple-clang":
        return "libc++"
    elif compiler == "gcc":
        libcxx = _detect_gcc_libcxx(version, compiler_exe or "g++")
        return libcxx
    elif compiler == "cc":
        if platform.system() == "SunOS":
            return "libstdcxx4"
    elif compiler == "clang":
        if platform.system() == "FreeBSD":
            return "libc++"
        elif platform.system() == "Darwin":
            return "libc++"
        elif platform.system() == "Windows":
            return  # by default windows will assume LLVM/Clang with VS backend
        else:  # Linux
            libcxx = _detect_gcc_libcxx(version, compiler_exe or "clang++")
            return libcxx
    elif compiler == "sun-cc":
        return "libCstd"
    elif compiler == "mcst-lcc":
        return "libstdc++"


def default_msvc_runtime(compiler: str):
    if platform.system() != "Windows":
        return None, None
    if compiler == "clang":
        # It could be LLVM/Clang with VS runtime or Msys2 with libcxx
        Output(scope="detect_api").warning("Assuming LLVM/Clang in Windows with VS 17 2022")
        Output(scope="detect_api").warning(
            "If Msys2/Clang need to remove compiler.runtime* "
            "and define compiler.libcxx")
        return "dynamic", "v143"
    elif compiler == "msvc":
        # Add default mandatory fields for MSVC compiler
        return "dynamic", None
    return None, None


def detect_msvc_update(version: Any):
    from thirdparty._internal.util.detect_vs import vs_detect_update
    return vs_detect_update(version)


def default_cppstd(compiler: str, compiler_version: Any):
    """ returns the default cppstd for the compiler-version. This is not detected, just the default
    """

    def _clang_cppstd_default(version: Any) -> str:
        if version >= "16":
            return "gnu17"
        # Official docs are wrong, in 6.0 the default is gnu14 to follow gcc's choice
        return "gnu98" if version < "6" else "gnu14"

    def _gcc_cppstd_default(version: Any) -> str:
        if version >= "16":
            return "gnu20"
        if version >= "11":
            return "gnu17"
        return "gnu98" if version < "6" else "gnu14"

    def _visual_cppstd_default(version: Any) -> str | None:
        if version >= "190":  # VS 2015 update 3 only
            return "14"
        return None

    def _mcst_lcc_cppstd_default(version: Any) -> str:
        return "gnu14" if version >= "1.24" else "gnu98"

    def _apple_clang_cppstd_default(version: Any) -> str:
        return "gnu98" if version < "17" else "gnu14"

    default = {
        "gcc": _gcc_cppstd_default(compiler_version),
        "clang": _clang_cppstd_default(compiler_version),
        "apple-clang": _apple_clang_cppstd_default(compiler_version),
        "msvc": _visual_cppstd_default(compiler_version),
        "mcst-lcc": _mcst_lcc_cppstd_default(compiler_version),
    }.get(str(compiler), None)
    return default


def detect_cppstd(compiler: str, compiler_version: Any):
    cppstd = default_cppstd(compiler, compiler_version)
    if compiler == "apple-clang" and compiler_version >= "11":
        # Recipe does not detect the default cppstd for apple-clang,
        # because it's still 98/14 for the compiler (even though xcode uses newer in projects)
        # and having it be so old would be annoying for users
        cppstd = "gnu17"
    return cppstd


def default_cstd(compiler: str, compiler_version: Any):
    """returns the default cstd for the compiler-version. This is not detected, just the default"""

    def _clang_cstd_default(version: Any) -> str:
        if version >= "11":
            return "gnu17"  # https://releases.llvm.org/11.0.0/tools/clang/docs/ReleaseNotes.html#c-language-changes-in-clang
        elif version >= "4":  # 3.5 actually
            return "gnu11"
        else:
            return "gnu99"  # It was gnu89 actually

    def _gcc_cstd_default(version: Any) -> str:
        if version >= "15":  # https://www.gnu.org/software/gcc/gcc-15/changes.html#c
            return "gnu23"
        elif version >= "8":
            return "gnu17"  # https://www.gnu.org/software/gcc/gcc-8/changes.html#c
        elif version >= "5":
            return "gnu11"  # https://www.gnu.org/software/gcc/gcc-5/changes.html#c
        else:
            return "gnu99"  # It was gnu89 actually

    def _visual_cstd_default(version: Any) -> None:
        return None

    def _apple_clang_cstd_default(version: Any) -> str:
        # Based on which LLVM/Clang versions these are based on
        if version >= "12":
            return "gnu17"
        if version >= "10":
            return "gnu11"
        return "gnu99"

    def _mcst_lcc_cstd_default(version: Any) -> None:
        return None

    default = {
        "gcc": _gcc_cstd_default(compiler_version),
        "clang": _clang_cstd_default(compiler_version),
        "apple-clang": _apple_clang_cstd_default(compiler_version),
        "msvc": _visual_cstd_default(compiler_version),
        "mcst-lcc": _mcst_lcc_cstd_default(compiler_version),
    }.get(str(compiler), None)
    return default


def detect_default_compiler() -> tuple[Any, Any, Any] | None:
    """
        find the default compiler on the build machine
        search order and priority:
        1. CC and CXX environment variables are always top priority
        2. Visual Studio detection (Windows only) via vswhere or registry or environment variables
        3. Apple Clang (Mac only)
        4. cc executable
        5. gcc executable
        6. clang executable
        """
    output = Output(scope="detect_api")
    cc = os.environ.get("CC", "")
    cxx = os.environ.get("CXX", "")
    if cc or cxx:  # Env defined, use them
        output.info("CC and CXX: %s, %s " % (cc or "None", cxx or "None"))
        command = cc or cxx
        if "/usr/bin/cc" == command or "/usr/bin/c++" == command:  # Symlinks of linux "alternatives"
            return _cc_compiler(command)
        if "clang" in command.lower():
            return detect_clang_compiler(command)
        if "gnu-cc" in command or "gcc" in command or "g++" in command or "c++" in command:
            gcc, gcc_version, compiler_exe = detect_gcc_compiler(command)
            if platform.system() == "Darwin" and gcc is None:
                output.error(
                    "%s detected as a frontend using apple-clang. "
                    "Compiler not supported" % command)
            return gcc, gcc_version, compiler_exe
        if platform.system() == "SunOS" and command.lower() == "cc":
            return detect_suncc_compiler(command)
        if (platform.system() == "Windows" and command.rstrip('"').endswith(("cl", "cl.exe")) and "clang" not in command):
            return detect_cl_compiler(command)

        # I am not able to find its version
        output.error("Not able to automatically detect '%s' version" % command)
        return None, None, None

    if platform.system() == "Windows":
        compiler, version, compiler_exe = detect_msvc_compiler()
        if compiler:
            return compiler, version, compiler_exe

    if platform.system() == "SunOS":
        sun_cc, sun_cc_version, compiler_exe = detect_suncc_compiler()
        if sun_cc:
            return sun_cc, sun_cc_version, compiler_exe

    if platform.system() in ["Darwin", "FreeBSD"]:
        clang, clang_version, compiler_exe = detect_clang_compiler()  # prioritize clang
        if clang:
            return clang, clang_version, compiler_exe
        return None, None, None
    else:  # linux like system
        compiler, compiler_version, compiler_exe = _cc_compiler()
        if compiler:
            return compiler, compiler_version, compiler_exe
        gcc, gcc_version, compiler_exe = detect_gcc_compiler()
        if gcc:
            return gcc, gcc_version, compiler_exe
        return detect_clang_compiler()


def default_msvc_ide_version(version: Any):
    version = {"195": "18", "194": "17", "193": "17", "192": "16", "191": "15"}.get(str(version))
    if version:
        return Version(version)


def _detect_vs_ide_version():
    from thirdparty._internal.util.detect_vs import vs_installation_path
    msvc_versions = "18", "17", "16", "15"
    for version in msvc_versions:
        vs_path = os.getenv("vs%s0comntools" % version)
        path = vs_path or vs_installation_path(version)
        if path:
            Output(scope="detect_api").info("Found msvc %s" % version)
            return Version(version)
    return None


def _cc_compiler(compiler_exe: str = "cc") -> tuple[Any, Any, Any]:
    # Try to detect the "cc" linux system "alternative". It could point to gcc or clang
    try:
        ret, out = detect_runner(f'"{compiler_exe}" --version')
        if ret != 0:
            return None, None, None
        compiler = "clang" if "clang" in out else "gcc"
        # clang and gcc have version after a space, first try to find that to skip extra numbers
        # that might appear in the first line of the output before the version
        # There might also be a leading parenthesis that contains build information,
        # so we try to skip it
        installed_version = re.search(r"(?:\(.*\))? ([0-9]+(\.[0-9]+)*)", out)
        # Fallback to the first number we find optionally followed by other version fields
        installed_version = installed_version or re.search(r"([0-9]+(\.[0-9]+)*)", out)
        if installed_version and installed_version.group(1):
            installed_version = installed_version.group(1)
            Output(scope="detect_api").info("Found cc=%s-%s" % (compiler, installed_version))
            return compiler, Version(installed_version), compiler_exe
    except (Exception,):  # to disable broad-except
        return None, None, None
    return None, None, None


def detect_gcc_compiler(compiler_exe: str = "gcc") -> tuple[Any, Any, Any]:
    try:
        if platform.system() == "Darwin":
            # In Mac OS X check if gcc is a fronted using apple-clang
            _, out = detect_runner(f'"{compiler_exe}" --version')
            out = out.lower()
            if "clang" in out:
                return None, None, None

        ret, out = detect_runner(f'"{compiler_exe}" -dumpversion')
        if ret != 0:
            return None, None, None
        compiler = "gcc"
        installed_version = re.search(r"([0-9]+(\.[0-9]+)?)", out).group()  # pyright: ignore[reportOptionalMemberAccess]  # no-match raises -> caught by broad except
        if installed_version:
            Output(scope="detect_api").info("Found %s %s" % (compiler, installed_version))
            return compiler, Version(installed_version), compiler_exe
    except (Exception,):  # to disable broad-except
        return None, None, None
    return None, None, None


def detect_suncc_compiler(compiler_exe: str = "cc") -> tuple[Any, Any, Any]:
    try:
        _, out = detect_runner(f'"{compiler_exe}" -V')
        compiler = "sun-cc"
        installed_version = re.search(r"Sun C.*([0-9]+\.[0-9]+)", out)
        if installed_version:
            installed_version = installed_version.group(1)
        else:
            installed_version = re.search(r"([0-9]+\.[0-9]+)", out).group()  # pyright: ignore[reportOptionalMemberAccess]  # no-match raises -> caught by broad except
        if installed_version:
            Output(scope="detect_api").info("Found %s %s" % (compiler, installed_version))
            return compiler, Version(installed_version), compiler_exe
    except (Exception,):  # to disable broad-except
        return None, None, None
    return None, None, None


def detect_clang_compiler(compiler_exe: str = "clang") -> tuple[Any, Any, Any]:
    try:
        ret, out = detect_runner(f'"{compiler_exe}" --version')
        if ret != 0:
            return None, None, None
        if "Apple" in out:
            compiler = "apple-clang"
        elif "clang version" in out:
            compiler = "clang"
        else:
            return None, None, None
        installed_version = re.search(r"([0-9]+\.[0-9])", out).group()  # pyright: ignore[reportOptionalMemberAccess]  # no-match raises -> caught by broad except
        if installed_version:
            Output(scope="detect_api").info("Found %s %s" % (compiler, installed_version))
            return compiler, Version(installed_version), compiler_exe
    except (Exception,):  # to disable broad-except
        return None, None, None
    return None, None, None


def detect_msvc_compiler() -> tuple[Any, Any, Any]:
    ide_version = _detect_vs_ide_version()
    # Map to compiler
    version = {"18": "195", "17": "193", "16": "192", "15": "191"}.get(str(ide_version))
    if ide_version == "17":
        update = detect_msvc_update(version)  # FIXME weird passing here the 193 compiler version
        if update and int(update) >= 10:
            version = "194"
    if version:
        return "msvc", Version(version), None
    return None, None, None


def detect_cl_compiler(compiler_exe: str = "cl") -> tuple[Any, Any, Any] | None:
    """ only if CC/CXX env-vars are defined pointing to cl.exe, and the VS environment must
    be active to have them in the path
    """
    try:
        compiler_exe = compiler_exe.strip('"')
        ret, out = detect_runner(f'"{compiler_exe}" /?')
        if ret != 0:
            return None, None, None
        first_line = out.splitlines()[0]
        if "Microsoft" not in first_line:
            return None, None, None
        compiler = "msvc"
        version_regex = re.search(
            r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.([0-9]+)\.?([0-9]+)?", first_line)
        if not version_regex:
            return None, None, None
        # 19.36.32535 -> 193
        version = f"{version_regex.group("major")}{version_regex.group("minor")[0]}"
        return compiler, Version(version), compiler_exe
    except (Exception,):  # to disable broad-except
        return None, None, None


def detect_emcc_compiler(compiler_exe: str = "emcc") -> tuple[Any, Any, Any]:
    ret, out = detect_runner(f'"{compiler_exe}" --version')
    if ret != 0:
        return None, None, None
    if "Emscripten" not in out:
        return None, None, None
    compiler = "emcc"
    version_match = re.search(r"[0-9]+\.[0-9]+\.[0-9]+", out)
    if not version_match:
        return None, None, None
    version = version_match.group()
    Output(scope="detect_api").info("Found %s %s" % (compiler, version))
    return compiler, Version(version), compiler_exe


def default_compiler_version(compiler: str, version: Any):
    """ returns the default version that Recipe uses in profiles, typically dropping some
    of the minor or patch digits, that do not affect binary compatibility
    """
    output = Output(scope="detect_api")
    if not version:
        raise RecipeException(
            f"No version provided to 'detect_api.default_compiler_version()' for {compiler} compiler")
    tokens = version.main
    major = tokens[0]
    minor = tokens[1] if len(tokens) > 1 else 0
    if compiler == "clang" and major >= 8:
        output.info("clang>=8, using the major as version")
        return major
    elif compiler == "gcc":
        if major >= 5:
            output.info("gcc>=5, using the major as version")
            return major
        else:
            output.info("gcc<5, using the major.minor as version")
            return Version(f"{major}.{minor}")
    elif compiler == "apple-clang" and major >= 13:
        output.info("apple-clang>=13, using the major as version")
        return major
    elif compiler == "intel" and (major < 19 or (major == 19 and minor == 0)):
        return major
    elif compiler == "msvc":
        return major
    return version


def detect_sdk_version(sdk: Any):
    if platform.system() != "Darwin":
        return
    cmd = f"xcrun -sdk {sdk} --show-sdk-version"
    _, result = detect_runner(cmd)
    result = result.strip()
    return result
