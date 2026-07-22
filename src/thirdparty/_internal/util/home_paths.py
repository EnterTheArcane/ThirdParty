import os


class HomePaths:
    """ pure computing of paths in the home, not caching anything
    """

    def __init__(self, home_folder: str):
        self._home = home_folder

    @property
    def default_sources_backup_folder(self):
        return os.path.join(self._home, "sources")

    @property
    def settings_path(self):
        return os.path.join(self._home, "settings.yml")

    @property
    def settings_path_user(self):
        return os.path.join(self._home, "settings_user.yml")
