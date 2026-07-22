from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from thirdparty.errors import RecipeException


_ARCH_VALUES = ("ARM", "X64")
_REQUIRED_FIELDS = ("arch", "build_type", "os")


@dataclass
class Settings:
    arch: str
    build_type: str
    os: str

    compiler: str | None = None
    compiler_c_standard: str | None = None
    compiler_cxx_standard: str | None = None
    compiler_libcxx: str | None = None
    compiler_runtime_type: str | None = None
    compiler_runtime_version: str | None = None
    compiler_runtime: str | None = None
    compiler_threads: str | None = None
    compiler_toolset: str | None = None
    compiler_update: str | None = None
    compiler_version: str | None = None

    os_api_level: str | int | None = None
    os_sdk: str | None = None
    os_sdk_version: str | None = None
    os_subsystem: str | None = None
    os_subsystem_ios_version: str | None = None
    os_version: str | None = None

    def __setattr__(self, name: str, value: Any):
        if name in _REQUIRED_FIELDS and value is None:
            raise RecipeException(f"Setting '{name}' cannot be None")
        if name == "arch":
            if value not in _ARCH_VALUES:
                raise RecipeException(f"Invalid setting '{value}' is not a valid 'arch' value")
            return super().__setattr__(name, value)
        return super().__setattr__(name, value)
