# standard
from dataclasses import asdict
import json
from pathlib import Path
from typing import Dict, Optional

# project
from menu_from_project.datamodel.project_config import MenuProjectConfig


class CacheManager:
    """Manager to get information from cached data

    :param iface: QGIS iface
    :type iface: QgsInterface
    """

    def __init__(self, iface) -> None:
        self.iface = iface

    def get_project_menu_config(
        self, project: Dict[str, str]
    ) -> Optional[MenuProjectConfig]:
        """Get menu project configuration from cache for a project

        :param project: dict of information about the project
        :type project: Dict[str, str]
        :return: menu project configuration from cache, None if no cache available
        :rtype: Optional[MenuProjectConfig]
        """
        cache_path = self.get_project_cache_dir(project)
        json_cache_path = cache_path / "project_config.json"
        if json_cache_path.exists():
            with open(json_cache_path, "r", encoding="UTF-8") as f:
                data = json.load(f)
                return MenuProjectConfig.from_json(data)
        return None

    def save_project_menu_config(
        self, project: Dict[str, str], project_config: MenuProjectConfig
    ) -> None:
        """Save menu project configuration in cache

        :param project: dict of information about the project
        :type project: Dict[str, str]
        :param project_config: menu project configuration
        :type project_config: MenuProjectConfig
        """
        cache_path = self.get_project_cache_dir(project)
        json_cache_path = cache_path / "project_config.json"

        with open(json_cache_path, "w", encoding="UTF-8") as f:
            json.dump(asdict(project_config), f, indent=4)

    def get_project_cache_dir(self, project: Dict[str, str]) -> Path:
        """Get local project cache directory

        :param project: dict of information about the project
        :type project: Dict[str, str]
        :return: path to project cache directory
        :rtype: Path
        """
        cache_path = Path(self.iface.userProfileManager().userProfile().folder())
        cache_path = cache_path / ".cache" / "menu-layer" / project["name"]
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path

    def get_project_download_dir(self, project: Dict[str, str]) -> Path:
        """Get local project cache download directory

        :param project: dict of information about the project
        :type project: Dict[str, str]
        :return: path to project cache directory
        :rtype: Path
        """
        cache_path = self.get_project_cache_dir(project)
        cache_path = cache_path / "downloads"
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path
