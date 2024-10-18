# standard
from dataclasses import asdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Optional

# PyQGIS
from qgis.core import QgsMessageLog
from qgis.PyQt.QtCore import QCoreApplication

# project
from menu_from_project.__about__ import __title__
from menu_from_project.datamodel.project import Project
from menu_from_project.datamodel.project_config import MenuProjectConfig


class CacheManager:
    """Manager to get information from cached data

    :param iface: QGIS iface
    :type iface: QgsInterface
    """

    DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"

    def __init__(self, iface) -> None:
        self.iface = iface

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("MenuFromProject", message)

    @staticmethod
    def log(message, application=__title__, indent=0):
        indent_chars = " .. " * indent
        QgsMessageLog.logMessage(
            f"{indent_chars}{message}", application, notifyUser=True
        )

    def check_if_cache_enabled(self, project: Project) -> bool:
        """Check if cache is enabled for project

        :param project: project
        :type project: Project
        :return: True if cache is enabled, False otherwise
        :rtype: bool
        """
        cache_config = project.cache_config
        if not cache_config.enable:
            self.log(self.tr(f"Cache disabled for project {project.name}"))
            return False

        # Check if a cache info is available
        cache_info = {}
        cache_path = self.get_project_cache_dir(project)
        cache_info_path = cache_path / "cache_info.json"
        if cache_info_path.exists():
            with open(cache_info_path, encoding="UTF-8") as f:
                cache_info = json.load(f)
        if "last_refresh" in cache_info and cache_config.refresh_days_period:
            cache_last_refresh = datetime.strptime(
                cache_info["last_refresh"], self.DATETIME_FORMAT
            )
            refresh_date = cache_last_refresh + timedelta(
                days=cache_config.refresh_days_period
            )
            if datetime.now() > refresh_date:
                self.log(
                    self.tr(
                        f"Cache is not up to date since {refresh_date} for project {project.name}."
                    )
                )
                return False
        return True

    def get_project_menu_config(self, project: Project) -> Optional[MenuProjectConfig]:
        """Get menu project configuration from cache for a project

        :param project: dict of information about the project
        :type project: Project
        :return: menu project configuration from cache, None if no cache available
        :rtype: Optional[MenuProjectConfig]
        """
        cache_path = self.get_project_cache_dir(project)
        if not self.check_if_cache_enabled(project):
            self.log(
                self.tr(f"Cache disabled for project {project.name}. Reloading data.")
            )
            return None

        json_cache_path = cache_path / "project_config.json"
        if json_cache_path.exists():
            with open(json_cache_path, "r", encoding="UTF-8") as f:
                data = json.load(f)
                return MenuProjectConfig.from_json(data)
        return None

    def save_project_menu_config(
        self, project: Project, project_config: MenuProjectConfig
    ) -> None:
        """Save menu project configuration in cache

        :param project: dict of information about the project
        :type project: Project
        :param project_config: menu project configuration
        :type project_config: MenuProjectConfig
        """
        cache_path = self.get_project_cache_dir(project)
        json_cache_path = cache_path / "project_config.json"
        with open(json_cache_path, "w", encoding="UTF-8") as f:
            json.dump(asdict(project_config), f, indent=4)

        cache_info_path = cache_path / "cache_info.json"
        with open(cache_info_path, "w", encoding="UTF-8") as f:
            json.dump(
                {"last_refresh": datetime.now().strftime(self.DATETIME_FORMAT)},
                f,
                indent=4,
            )

    def get_project_cache_dir(self, project: Project) -> Path:
        """Get local project cache directory

        :param project: dict of information about the project
        :type project: Project
        :return: path to project cache directory
        :rtype: Path
        """
        cache_path = Path(self.iface.userProfileManager().userProfile().folder())
        cache_path = cache_path / ".cache" / "menu-layer" / project.name
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path

    def get_project_download_dir(self, project: Project) -> Path:
        """Get local project cache download directory

        :param project: dict of information about the project
        :type project: Project
        :return: path to project cache directory
        :rtype: Path
        """
        cache_path = self.get_project_cache_dir(project)
        cache_path = cache_path / "downloads"
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path
