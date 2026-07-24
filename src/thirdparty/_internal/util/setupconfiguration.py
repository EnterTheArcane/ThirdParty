import platform
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class VsSetupInstance:
    instance_id: str
    installation_path: str
    installation_version: str
    product_id: str | None
    is_prerelease: bool
    is_complete: bool
    package_ids: frozenset[str]

    def has_component(self, component_id: str) -> bool:
        return component_id in self.package_ids

    def version_key(self) -> tuple[int, ...]:
        parts: list[int] = []
        for part in self.installation_version.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        return tuple(parts)


@lru_cache(maxsize=1)
def vs_instances() -> list[VsSetupInstance]:
    if platform.system() != "Windows":
        return []
    from thirdparty._internal.util import setupconfiguration_com
    return setupconfiguration_com.enumerate_instances()
