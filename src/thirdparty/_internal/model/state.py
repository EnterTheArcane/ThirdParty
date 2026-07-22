from dataclasses import dataclass

from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.settings import Settings


@dataclass
class RecipeState:
    dependencies: RecipeDependencies
    build_context: bool
    
    settings: Settings
    settings_build: Settings

    conf: Conf
    info: Info
