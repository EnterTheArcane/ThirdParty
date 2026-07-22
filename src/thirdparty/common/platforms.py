from enum import StrEnum


class Arch(StrEnum):
    ARM = "ARM"
    X64 = "X64"


class BuildType(StrEnum):
    DEBUG = "Debug"
    PROFILE = "Profile"
    RELEASE = "Release"
