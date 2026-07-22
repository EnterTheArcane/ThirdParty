from thirdparty.errors import RecipeException

__all__ = ["_get_gnu_triplet"]


def _get_gnu_arch(os_: str, arch: str) -> str:
    # Calculate the arch
    machine = {
        "X64": "x86_64", "ARM": "aarch64",
    }.get(arch, None)

    if not machine:
        # https://wiki.debian.org/Multiarch/Tuples
        if os_ == "AIX":
            if "ppc32" in arch:
                machine = "rs6000"
            elif "ppc64" in arch:
                machine = "powerpc"
        elif "arm" in arch:
            machine = "arm"
        elif "ppc32be" in arch:
            machine = "powerpcbe"
        elif "ppc64le" in arch:
            machine = "powerpc64le"
        elif "ppc64" in arch:
            machine = "powerpc64"
        elif "ppc32" in arch:
            machine = "powerpc"
        elif "mips64" in arch:
            machine = "mips64"
        elif "mips" in arch:
            machine = "mips"
        elif "sparcv9" in arch:
            machine = "sparc64"
        elif "sparc" in arch:
            machine = "sparc"
        elif "s390x" in arch:
            machine = "s390x-ibm"
        elif "s390" in arch:
            machine = "s390-ibm"
        elif "sh4" in arch:
            machine = "sh4"
        elif "e2k" in arch:
            # https://lists.gnu.org/archive/html/config-patches/2015-03/msg00000.html
            machine = "e2k-unknown"
        elif "riscv64" in arch:
            machine = "riscv64"
        elif "riscv32" in arch:
            machine = "riscv32"

    if machine is None:
        raise RecipeException(
            "Unknown '%s' machine, Recipe doesn't know how to "
            "translate it to the GNU triplet, please report this "
            "to the ThirdParty maintainers" % arch)
    return machine


def _get_gnu_os(os_: str, arch: str, compiler: str | None = None) -> str:
    # Calculate the OS
    if compiler == "gcc":
        windows_op = "w64-mingw32"
    else:
        windows_op = "unknown-windows"

    op_system = {
        "Windows": windows_op, "Linux": "linux-gnu", "Darwin": "apple-darwin", "Android": "linux-android", "Mac": "apple-darwin", "iOS": "apple-ios", "tvOS": "apple-tvos", "visionOS": "apple-xros",
        # NOTE: it technically must be "asmjs-unknown-emscripten" or
        # "wasm32-unknown-emscripten", but it's not recognized by old config.sub versions
        "Emscripten": "local-emscripten", "AIX": "ibm-aix", "Neutrino": "nto-qnx",
    }.get(os_, os_.lower())

    return op_system


def _get_gnu_triplet(os_: str, arch: str, compiler: str | None = None) -> dict[str, str]:
    """
    Returns string with <machine>-<vendor>-<op_system> triplet (<vendor> can be omitted in practice)

    :param os_: os to be used to create the triplet
    :param arch: arch to be used to create the triplet
    :param compiler: compiler used to create the triplet (only needed fo windows)
    """
    if os_ == "Windows" and compiler is None:
        raise RecipeException(
            "'compiler' parameter for 'get_gnu_triplet()' is not specified and "
            "needed for os=Windows")
    machine = _get_gnu_arch(os_, arch)
    op_system = _get_gnu_os(os_, arch, compiler=compiler)
    return {
        "machine": machine, "system": op_system, "triplet": f"{machine}-{op_system}",
    }
