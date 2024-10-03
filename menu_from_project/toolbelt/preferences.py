#! python3  # noqa: E265

"""
    Plugin settings.
"""

# standard
from dataclasses import dataclass, field
from typing import List

# PyQGIS
from qgis.core import QgsSettings

# package
from menu_from_project.__about__ import __title__, __version__
from menu_from_project.datamodel.project import Project
from menu_from_project.logic.tools import guess_type_from_uri

# ############################################################################
# ########## Classes ###############
# ##################################

SOURCE_MD_OGC = "ogc"
SOURCE_MD_LAYER = "layer"
SOURCE_MD_NOTE = "note"


@dataclass
class PlgSettingsStructure:
    """Plugin settings structure and defaults values."""

    # global
    debug_mode: bool = False
    version: str = __version__

    # Projects
    projects: List[Project] = field(default_factory=lambda: [])

    # Menu option
    optionTooltip: bool = False
    optionCreateGroup: bool = False
    optionLoadAll: bool = False
    optionOpenLinks: bool = False
    optionSourceMD: List[str] = field(
        default_factory=lambda: [SOURCE_MD_OGC, SOURCE_MD_LAYER, SOURCE_MD_NOTE]
    )

    # Internal option
    is_setup_visible: bool = True


class PlgOptionsManager:
    @staticmethod
    def get_plg_settings() -> PlgSettingsStructure:
        """Load and return plugin settings as a dictionary. \
        Useful to get user preferences across plugin logic.

        :return: plugin settings
        :rtype: PlgSettingsStructure
        """
        # instanciate new settings object
        options = PlgSettingsStructure()

        s = QgsSettings()

        if s.value("menu_from_project/is_setup_visible") is None:
            # This setting does not exist. We add it by default.
            s.setValue("menu_from_project/is_setup_visible", True)

        # If we want to hide the dialog setup to users.
        options.is_setup_visible = s.value(
            "menu_from_project/is_setup_visible", True, bool
        )

        try:
            s.beginGroup("menu_from_project")
            try:
                options.optionTooltip = s.value("optionTooltip", True, type=bool)
                options.optionCreateGroup = s.value(
                    "optionCreateGroup", False, type=bool
                )
                options.optionLoadAll = s.value("optionLoadAll", False, type=bool)
                options.optionOpenLinks = s.value("optionOpenLinks", True, type=bool)
                defaultOptionSourceMD = "{},{},{}".format(
                    SOURCE_MD_OGC,
                    SOURCE_MD_LAYER,
                    SOURCE_MD_NOTE,
                )
                optionSourceMD = s.value(
                    "optionSourceMD",
                    defaultOptionSourceMD,
                    type=str,
                )
                options.optionSourceMD = optionSourceMD.split(",")
                # Retro comp
                if (
                    len(options.optionSourceMD) == 1
                    and options.optionSourceMD[0] == SOURCE_MD_OGC
                ):
                    options.optionSourceMD = [
                        SOURCE_MD_OGC,
                        SOURCE_MD_LAYER,
                        SOURCE_MD_NOTE,
                    ]
                if (
                    len(options.optionSourceMD) == 1
                    and options.optionSourceMD[0] == SOURCE_MD_LAYER
                ):
                    options.optionSourceMD = [
                        SOURCE_MD_LAYER,
                        SOURCE_MD_OGC,
                        SOURCE_MD_NOTE,
                    ]
                if (
                    len(options.optionSourceMD) == 1
                    and options.optionSourceMD[0] == SOURCE_MD_NOTE
                ):
                    options.optionSourceMD = [
                        SOURCE_MD_NOTE,
                        SOURCE_MD_LAYER,
                        SOURCE_MD_OGC,
                    ]

                size = s.beginReadArray("projects")
                try:
                    for i in range(size):
                        s.setArrayIndex(i)
                        file = s.value("file", "")
                        name = s.value("name", "")
                        location = s.value("location", "new")
                        type_storage = s.value(
                            "type_storage", guess_type_from_uri(file)
                        )
                        if file != "":
                            options.projects.append(
                                Project(
                                    file=file,
                                    name=name,
                                    location=location,
                                    type_storage=type_storage,
                                )
                            )
                finally:
                    s.endArray()

            finally:
                s.endGroup()

        except Exception:
            pass

        return options

    @classmethod
    def save_from_object(cls, plugin_settings_obj: PlgSettingsStructure):
        """Load and return plugin settings as a dictionary. \
        Useful to get user preferences across plugin logic.

        :return: plugin settings value matching key
        """
        s = QgsSettings()

        s.beginGroup("menu_from_project")
        try:
            s.setValue("optionTooltip", plugin_settings_obj.optionTooltip)
            s.setValue("optionCreateGroup", plugin_settings_obj.optionCreateGroup)
            s.setValue("optionLoadAll", plugin_settings_obj.optionLoadAll)
            s.setValue("optionOpenLinks", plugin_settings_obj.optionOpenLinks)
            s.setValue("optionSourceMD", ",".join(plugin_settings_obj.optionSourceMD))

            s.beginWriteArray("projects", len(plugin_settings_obj.projects))
            try:
                for i, project in enumerate(plugin_settings_obj.projects):
                    s.setArrayIndex(i)
                    s.setValue("file", project.file)
                    s.setValue("name", project.name)
                    s.setValue("location", project.location)
                    s.setValue("type_storage", guess_type_from_uri(project.file))
            finally:
                s.endArray()
        finally:
            s.endGroup()
