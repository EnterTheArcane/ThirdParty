from typing import Any

from thirdparty._internal.model.toolchain import find_toolchain
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase


def disable_flag(recipe: RecipeBase, flag: str) -> bool:
    disable_flags = recipe.conf.tools.gnu.disable_flags
    valid = [
        "arch", "arch_link", "libcxx", "build_type", "build_type_link", "threads", "cppstd", "cstd",
    ]
    for v in disable_flags:
        if v not in valid:
            raise RecipeException(f"conf.tools.gnu.disable_flags value '{v}', must be one of: {valid}")
    return flag in disable_flags


def architecture_flag(recipe: RecipeBase) -> str:
    """
    returns flags specific to the target architecture and compiler
    Used by CMakeToolchain and AutotoolsToolchain
    """
    if disable_flag(recipe, "arch"):
        return ""
    settings = recipe.settings
    from thirdparty.apple.utils import _to_apple_arch
    compiler = settings.compiler
    arch = settings.arch
    the_os = settings.os
    subsystem = settings.os_subsystem
    subsystem_ios_version = settings.os_subsystem_ios_version
    if not compiler or not arch:
        return ""

    if the_os == "Android":
        return ""

    if compiler == "clang" and the_os == "Windows":
        comp_exes = recipe.conf.tools.build.compiler_executables
        clangcl = "clang-cl" in str(comp_exes.get("c") or comp_exes.get("cpp", ""))
        if clangcl:
            return ""  # Do not add arch flags for clang-cl, can happen in cross-build runtime=None
        # LLVM/Clang and VS/Clang must define runtime. msys2 clang won't
        runtime = settings.compiler_runtime  # runtime is Windows only
        if runtime is not None:
            return ""
        # TODO: Maybe Clang-Mingw runtime does, but with C++ is impossible to test
        return {"X64": "-m64"}.get(arch, "")
    elif compiler in ["gcc", "apple-clang", "clang", "sun-cc"]:
        if the_os == "Mac" and subsystem == "catalyst":
            # FIXME: This might be conflicting with Autotools --target cli arg
            apple_arch = _to_apple_arch(arch)
            if apple_arch:
                # TODO: Could we define anything like `to_apple_target()`?
                #       Check https://github.com/rust-lang/rust/issues/48862
                return f"--target={apple_arch}-apple-ios{subsystem_ios_version}-macabi"
        elif arch in ["X64"]:
            return "-m64"
        elif arch in ["x86", "sparc"]:
            return "-m32"
        elif arch in ["s390"]:
            return "-m31"
        elif arch in ["tc131", "tc16", "tc161", "tc162", "tc18"]:
            return f"-m{arch}"
        elif the_os == "AIX":
            if arch in ["ppc32"]:
                return "-maix32"
            elif arch in ["ppc64"]:
                return "-maix64"
    elif compiler == "mcst-lcc":
        return {
            "e2k-v2": "-march=elbrus-v2", "e2k-v3": "-march=elbrus-v3", "e2k-v4": "-march=elbrus-v4", "e2k-v5": "-march=elbrus-v5", "e2k-v6": "-march=elbrus-v6", "e2k-v7": "-march=elbrus-v7",
        }.get(arch, "")
    elif compiler == "emcc":
        if arch == "wasm64":
            return "-sMEMORY64=1"
    return ""


def architecture_link_flag(recipe: RecipeBase) -> str:
    """
    returns exclusively linker flags specific to the target architecture and compiler
    """
    if disable_flag(recipe, "arch_link"):
        return ""
    compiler = recipe.settings.compiler
    arch = recipe.settings.arch
    if compiler == "emcc":
        # Emscripten default output is WASM since 1.37.x (long time ago)
        # Deactivate WASM output forcing asm.js output instead
        if arch == "asm.js":
            return "-sWASM=0"
    return ""


def libcxx_flags(recipe: RecipeBase) -> tuple[str | None, str | None]:
    libcxx = recipe.settings.compiler_libcxx
    if not libcxx:
        return None, None
    if disable_flag(recipe, "libcxx"):
        return None, None
    compiler = recipe.settings.compiler
    lib = stdlib11 = None
    if compiler == "apple-clang":
        # In apple-clang 2 only values atm are "libc++" and "libstdc++"
        lib = f"-stdlib={libcxx}"
    elif compiler in ("clang", "emcc"):
        if libcxx == "libc++":
            lib = "-stdlib=libc++"
        elif libcxx == "libstdc++" or libcxx == "libstdc++11":
            lib = "-stdlib=libstdc++"  # FIXME, something to do with the other values? Android c++_shared?
    elif compiler == "sun-cc":
        lib = {
            "libCstd": "-library=Cstd", "libstdcxx": "-library=stdcxx4", "libstlport": "-library=stlport4", "libstdc++": "-library=stdcpp",
        }.get(libcxx)
    elif compiler == "qcc":
        lib = f"-Y _{libcxx}"

    if compiler in ["clang", "apple-clang", "gcc", "emcc"]:
        if libcxx == "libstdc++":
            stdlib11 = "_GLIBCXX_USE_CXX11_ABI=0"
        elif libcxx == "libstdc++11" and recipe.conf.tools.gnu.define_libcxx11_abi:
            stdlib11 = "_GLIBCXX_USE_CXX11_ABI=1"
    return lib, stdlib11


def build_type_link_flags(settings: Any) -> list[str]:
    """
    returns link flags specific to the build type (Debug, Release, etc.)
    [-debug]
    """
    compiler = settings.compiler
    build_type = settings.build_type
    if not compiler or not build_type:
        return []

    # https://github.com/Kitware/CMake/blob/d7af8a34b67026feaee558433db3a835d6007e06/
    # Modules/Platform/Windows-MSVC.cmake
    if compiler == "msvc":
        if build_type in ("Debug", "RelWithDebInfo"):
            return ["-debug"]

    return []


def build_type_flags(recipe: RecipeBase) -> list[str]:
    """
    returns flags specific to the build type (Debug, Release, etc.)
    (-s, -g, /Zi, etc.)
    Used only by AutotoolsToolchain
    """
    if disable_flag(recipe, "build_type"):
        return []
    settings = recipe.settings
    compiler = settings.compiler
    build_type = settings.build_type
    vs_toolset = settings.compiler_toolset
    if not compiler or not build_type:
        return []

    comp_exes = recipe.conf.tools.build.compiler_executables
    clangcl = "clang-cl" in str(comp_exes.get("c") or comp_exes.get("cpp", ""))

    if compiler == "msvc" or clangcl:
        # https://github.com/Kitware/CMake/blob/d7af8a34b67026feaee558433db3a835d6007e06/
        # Modules/Platform/Windows-MSVC.cmake
        # FIXME: This condition seems legacy, as no more "clang" exists in Recipe toolsets
        if vs_toolset and "clang" in vs_toolset:
            flags = {
                "Debug": ["-gline-tables-only", "-fno-inline", "-O0"], "Release": ["-O2"], "RelWithDebInfo": ["-gline-tables-only", "-O2", "-fno-inline"], "MinSizeRel": [],
            }.get(build_type, ["-O2", "-Ob2"])
        else:
            flags = {
                "Debug": ["-Zi", "-Ob0", "-Od"], "Release": ["-O2", "-Ob2"], "RelWithDebInfo": ["-Zi", "-O2", "-Ob1"], "MinSizeRel": ["-O1", "-Ob1"],
            }.get(build_type, [])
        return flags
    else:
        # https://github.com/Kitware/CMake/blob/f3bbb37b253a1f4a26809d6f132b3996aa2e16fc/
        # Modules/Compiler/GNU.cmake
        # clang include the gnu (overriding some things, but not build type) and apple clang
        # overrides clang but it doesn't touch clang either
        if compiler in ["clang", "gcc", "apple-clang", "qcc", "mcst-lcc"]:
            flags = {
                "Debug": ["-g"], "Release": ["-O3"], "RelWithDebInfo": ["-O2", "-g"], "MinSizeRel": ["-Os"],
            }.get(build_type, [])
            return flags
        elif compiler == "sun-cc":
            # https://github.com/Kitware/CMake/blob/f3bbb37b253a1f4a26809d6f132b3996aa2e16fc/
            # Modules/Compiler/SunPro-CXX.cmake
            flags = {
                "Debug": ["-g"], "Release": ["-xO3"], "RelWithDebInfo": ["-xO2", "-g"], "MinSizeRel": ["-xO2", "-xspace"],
            }.get(build_type, [])
            return flags
    return []


def threads_flags(recipe: RecipeBase) -> list[str]:
    """
    returns flags specific to the threading model used by the compiler
    """
    if disable_flag(recipe, "threads"):
        return []
    compiler = recipe.settings.compiler
    threads = recipe.settings.compiler_threads
    if compiler == "emcc":
        if threads == "posix":
            return ["-pthread"]
        elif threads == "wasm_workers":
            return ["-sWASM_WORKERS=1"]
    return []


def llvm_clang_front(recipe: RecipeBase) -> str | None:
    # Only Windows clang with MSVC backend (LLVM/Clang, not MSYS2 clang)
    if (recipe.settings.os != "Windows" or recipe.settings.compiler != "clang" or not recipe.settings.compiler_runtime):
        return
    tc = find_toolchain(recipe)
    if tc is not None and tc.front_kind in ("clang-cl", "clang"):
        return tc.front_kind
    compilers = recipe.conf.tools.build.compiler_executables
    if "clang-cl" in str(compilers.get("c", "")) or "clang-cl" in str(compilers.get("cpp", "")):
        return "clang-cl"  # The MSVC-compatible front
    return "clang"  # The GNU-compatible front


def lto_flags(recipe: RecipeBase) -> list[str]:
    """Link-time-optimization flags for the selected toolchain (compile AND link).

    Default policy: ThinLTO with FAT objects, on by default for the clang toolchain in
    optimized configs. Fat objects carry bitcode AND machine code, so the shipped static
    libs stay linkable by non-LLVM linkers (MSVC link.exe, plain ld) - which is why LTO
    is limited to ELF targets: -ffat-lto-objects is not supported for Mach-O, and COFF
    support is unverified for the packaged LLVM (plain ThinLTO there would make static
    libs bitcode-only and toolchain-locked). Opt out per recipe with
    conf.tools.build.lto = False.
    """
    if recipe.conf.tools.build.lto is False:
        return []
    settings = recipe.settings
    if settings.build_type not in ("Release", "RelWithDebInfo"):
        return []
    if settings.os != "Linux":
        return []
    tc = find_toolchain(recipe)
    if tc is None or tc.front_kind != "clang":
        if not (recipe.conf.tools.build.lto and settings.compiler == "gcc"):
            return []
        return ["-flto", "-ffat-lto-objects"]
    return ["-flto=thin", "-ffat-lto-objects"]



# The standards each front end accepts are fixed by the pinned toolchains (the packaged
# MSVC toolset, the packaged LLVM, Xcode's clang, the system gcc), so the flags below are
# plain name mappings rather than the version ladders they used to be.
_MSVC_CPPSTD = {"14": "c++14", "17": "c++17", "20": "c++20", "23": "c++latest"}
_MSVC_CSTD = {"11": "c11", "17": "c17"}
_GNU_CSTD = {"99": "c99", "11": "c11", "17": "c17", "23": "c23"}
_GNU_COMPILERS = ("gcc", "clang", "apple-clang")


def cppstd_flag(recipe: RecipeBase) -> str:
    """
    Returns flags specific to the C++ standard based on the ``recipe.settings.compiler``
    and ``recipe.settings.compiler_cxx_standard``.

    It also considers when using GNU extension in ``settings.compiler_cxx_standard``, reflecting it in the
    compiler flag. Currently, it supports GCC, Clang, AppleClang and MSVC.

    In case there is no ``settings.compiler`` or ``settings.compiler_cxx_standard`` in the profile,
    the result will be an **empty string**.

    :param recipe: The current recipe object. Always use ``self``.
    :return: ``str`` with the standard C++ flag used by the compiler. e.g. "-std=c++11", "/std:c++latest"
    """
    compiler = recipe.settings.compiler
    cppstd = recipe.settings.compiler_cxx_standard

    if not compiler or not cppstd:
        return ""

    if disable_flag(recipe, "cppstd"):
        return ""

    if compiler == "msvc":
        flag = cppstd_msvc_flag(str(cppstd))
        return f"/std:{flag}" if flag else ""

    if compiler not in _GNU_COMPILERS:
        return ""

    flag = f"-std={gnu_cppstd_flag(str(cppstd))}"
    if llvm_clang_front(recipe) == "clang-cl":
        flag = flag.replace("=", ":")
    return flag


def cppstd_msvc_flag(cppstd: str) -> str | None:
    """The ``/std:`` value for *cppstd*, or None when MSVC has no flag for it.

    https://docs.microsoft.com/en-us/cpp/build/reference/std-specify-language-standard-version
    C++23 is only reachable through ``c++latest``; anything newer has no flag at all.
    """
    return _MSVC_CPPSTD.get(cppstd)


def gnu_cppstd_flag(cppstd: str) -> str:
    """The ``-std=`` value for *cppstd* on the GNU-style front ends, e.g. ``gnu17`` -> ``gnu++17``."""
    return f"gnu++{cppstd[3:]}" if cppstd.startswith("gnu") else f"c++{cppstd}"


def cstd_flag(recipe: RecipeBase) -> str:
    """
    Returns flags specific to the C standard based on the ``recipe.settings.compiler``
    and ``recipe.settings.compiler_c_standard``.

    It also considers when using GNU extension in ``settings.compiler_c_standard``, reflecting it in the
    compiler flag. Currently, it supports GCC, Clang, AppleClang, MSVC.

    In case there is no ``settings.compiler`` or ``settings.compiler_c_standard`` in the profile,
    the result will be an **empty string**.

    :param recipe: The current recipe object. Always use ``self``.
    :return: ``str`` with the standard C flag used by the compiler.
    """
    compiler = recipe.settings.compiler
    cstd = recipe.settings.compiler_c_standard

    if not compiler or not cstd:
        return ""

    if disable_flag(recipe, "cstd"):
        return ""

    if compiler == "msvc":
        flag = cstd_msvc_flag(str(cstd))
        return f"/std:{flag}" if flag else ""

    if compiler not in ("gcc", "clang", "apple-clang"):
        return ""

    return f"-std={gnu_cstd_flag(str(cstd))}"


def cstd_msvc_flag(cstd: str) -> str | None:
    """The ``/std:`` value for *cstd*, or None when MSVC has no flag for it."""
    return _MSVC_CSTD.get(cstd)


def gnu_cstd_flag(cstd: str) -> str:
    """The ``-std=`` value for *cstd* on the GNU-style front ends, e.g. ``17`` -> ``c17``.

    GNU-extension values (``gnu17``) are already valid ``-std=`` values, so they pass through.
    """
    return _GNU_CSTD.get(cstd, cstd)
