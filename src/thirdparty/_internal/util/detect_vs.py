import os
from typing import Any

from thirdparty.errors import RecipeException


def vs_installation_path(version: Any):
    return _vs_installation_path(version)[0]


def vs_detect_update(version: Any):
    version = {"195": "18", "194": "17", "193": "17", "192": "16", "191": "15"}.get(str(version))
    full_version = _vs_installation_path(version)[1]
    components = full_version.split(".")
    if len(components) > 1:
        return components[1]


def _vs_installation_path(version: Any) -> tuple[Any, Any]:
    # TODO: Preference hardcoded, [conf] must be defined
    preference = ["Enterprise", "Professional", "Community", "BuildTools"]

    # Query the Visual Studio Setup Configuration COM API. Like vswhere's default
    # (no -all), we only consider complete installs; prereleases are kept in.
    try:
        from thirdparty._internal.util.setupconfiguration import vs_instances
        products = [p for p in vs_instances() if p.is_complete]
    except RecipeException:
        products = None

    if products:  # First matching
        for product_type in preference:
            for product in products:
                if product.installation_version.startswith(f"{version}."):
                    if product_type in (product.product_id or ""):
                        return product.installation_path, product.installation_version

    # If the COM API finds nothing or is not available, try with vs_comntools
    vs_path = os.getenv("vs%s0comntools" % version)
    if vs_path:
        sub_path_to_remove = os.path.join("", "Common7", "Tools", "")
        # Remove '\\Common7\\Tools\\' to get same output as vswhere
        if vs_path.endswith(sub_path_to_remove):
            vs_path = vs_path[:-(len(sub_path_to_remove) + 1)]

    return vs_path, None
