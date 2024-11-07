# Standard library
from typing import List
import os.path

# PyQGIS
from qgis.core import (
    QgsDataItemProvider,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataProvider,
    QgsApplication,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QWidget

# project
from menu_from_project.logic.layer_load import LayerLoad
from menu_from_project.logic.project_read import (
    MenuGroupConfig,
    MenuLayerConfig,
    MenuProjectConfig,
)
from menu_from_project.__about__ import __title__
from menu_from_project.logic.tools import icon_per_layer_type
from menu_from_project.toolbelt.preferences import (
    PlgOptionsManager,
)


class MenuLayerProvider(QgsDataItemProvider):
    """Provider for plugin data item"""

    def __init__(self, project_configs: List[MenuProjectConfig]):
        """Constructor for provider

        :param project_configs: list of project configuration
        :type project_configs: List[MenuProjectConfig]
        """
        QgsDataItemProvider.__init__(self)
        self.project_configs = project_configs

    def name(self) -> str:
        """Human readable name

        :return: name of item
        :rtype: str
        """
        return "Layer from project"

    def capabilities(self) -> int:
        """Returns combination of flags from QgsDataProvider::DataCapabilities.

        :return: item data capabilities
        :rtype: int
        """
        return QgsDataProvider.Net

    def createDataItem(self, path: str, parentItem: QgsDataItem) -> QgsDataItem:
        """Create root collection for provider

        :param path: current path (unused)
        :type path: str
        :param parentItem: parent
        :type parentItem: QgsDataItem
        :return: RootCollection data item
        :rtype: QgsDataItem
        """
        return RootCollection(parent=parentItem, project_configs=self.project_configs)


class RootCollection(QgsDataCollectionItem):
    """QgsDataCollectionItem to add available project as children"""

    def __init__(self, parent: QgsDataItem, project_configs: List[MenuProjectConfig]):
        """_summary_

        :param parent: parent
        :type parent: QgsDataItem
        :param project_configs: list of project configuration
        :type project_configs: List[MenuProjectConfig]
        """
        QgsDataCollectionItem.__init__(self, parent, "MenuLayer", "/MenuLayer")
        # TODO : define icon
        self.project_configs = project_configs

    def createChildren(self) -> List[QgsDataItem]:
        """Create children for each project

        :return: QgsDataItem for each project
        :rtype: List[QgsDataItem]
        """
        children = []
        for pfc in [
            ProjectCollection(parent=self, project_menu_config=project_config)
            for project_config in self.project_configs
        ]:
            children.append(pfc)
        return children


class ProjectCollection(QgsDataCollectionItem):
    """QgsDataCollectionItem to add all group and layer available in a project"""

    def __init__(self, parent: QgsDataItem, project_menu_config: MenuProjectConfig):
        """Constructor for a project QgsDataCollectionItem

        :param parent: parent
        :type parent: QgsDataItem
        :param project_menu_config: project configuration
        :type project_menu_config: MenuProjectConfig
        """
        self.path = "/MenuLayer/" + project_menu_config.project_name.lower()
        self.parent = parent
        QgsDataCollectionItem.__init__(
            self, parent, project_menu_config.project_name, self.path
        )
        self.project_menu_config = project_menu_config
        self.setName(project_menu_config.project_name)
        self.setIcon(QIcon(QgsApplication.iconPath("mIconFolderProject.svg")))

    def createChildren(self) -> List[QgsDataItem]:
        """Create children for all group and layer available in project

        :return: QgsDataItem for each project
        :rtype: List[QgsDataItem]
        """
        children = []
        for child in self.project_menu_config.root_group.childs:
            if isinstance(child, MenuLayerConfig):
                children.append(
                    LayerItem(
                        parent=self,
                        layer_config=child,
                        group_name=self.project_menu_config.root_group.name,
                    )
                )
            elif isinstance(child, MenuGroupConfig):
                children.append(GroupItem(parent=self, group_config=child))
        return children


class GroupItem(QgsDataCollectionItem):
    """QgsDataCollectionItem to add all group and layer available in a group"""

    def __init__(self, parent: QgsDataItem, group_config: MenuGroupConfig):
        """Constructor for a group QgsDataCollectionItem

        :param parent: parent
        :type parent: QgsDataItem
        :param group_config: group configuration
        :type group_config: MenuGroupConfig
        """
        self.path = os.path.join(parent.path, group_config.name)
        self.group_config = group_config
        QgsDataCollectionItem.__init__(self, parent, group_config.name, self.path)
        self.setIcon(QIcon(QgsApplication.iconPath("mIconFolder.svg")))

    def createChildren(self) -> List[QgsDataItem]:
        """Create children for all group and layer available in a group

        :return: QgsDataItem for each project
        :rtype: List[QgsDataItem]
        """
        children = []
        for child in self.group_config.childs:
            if isinstance(child, MenuLayerConfig):
                children.insert(
                    0,
                    LayerItem(
                        parent=self,
                        layer_config=child,
                        group_name=self.group_config.name,
                    ),
                )
            elif isinstance(child, MenuGroupConfig):
                children.insert(0, GroupItem(parent=self, group_config=child))
        return children

    def actions(self, parent: QWidget) -> List[QAction]:
        """Return list of available actions for layer

        :param parent: parent
        :type parent: QWidget
        :return: list of available actions
        :rtype: List[QAction]
        """
        settings = PlgOptionsManager().get_plg_settings()

        if len(self._get_layer_inserted()) != 0 and settings.optionLoadAll:
            ac_show_layer = QAction(self.tr("Load all"), parent)
            ac_show_layer.triggered.connect(self._add_layer_inserted)
            return [ac_show_layer]
        return []

    def _add_layer_inserted(self) -> None:
        """Add inserted layers to current QGIS project"""
        LayerLoad().load_layer_list(self._get_layer_inserted(), self.group_config.name)

    def _get_layer_inserted(self) -> List[MenuLayerConfig]:
        """Get layer inserted for this group

        :return: list of inserted layer
        :rtype: List[MenuLayerConfig]
        """
        layer_inserted = []
        for child in self.group_config.childs:
            if isinstance(child, MenuLayerConfig):
                layer_inserted.append(child)
        return layer_inserted


class LayerItem(QgsDataItem):
    """QgsDataItem for layer"""

    def __init__(
        self, parent: QgsDataItem, layer_config: MenuLayerConfig, group_name: str
    ):
        """Constructor for a QgsDataItem to display layer configuration

        :param parent: parent
        :type parent: QgsDataItem
        :param layer_config: layer configuration
        :type layer_config: MenuLayerConfig
        :param group_name: group name
        :type group_name: str
        """
        self.layer_config = layer_config
        self.group_name = group_name
        self.path = os.path.join(parent.path, layer_config.name)
        QgsDataItem.__init__(
            self, QgsDataItem.Custom, parent, layer_config.name, self.path
        )
        self.setState(QgsDataItem.Populated)  # no children

        settings = PlgOptionsManager().get_plg_settings()

        if settings.optionTooltip:
            self.setToolTip(settings.tooltip_for_layer(layer_config))
        self.setIcon(
            icon_per_layer_type(
                is_spatial=self.layer_config.is_spatial,
                layer_type=self.layer_config.layer_type,
                geometry_type=self.layer_config.geometry_type,
            )
        )

    def handleDoubleClick(self) -> None:
        """Load layer at double click"""
        self.addLayer()
        return True

    def actions(self, parent: QWidget) -> List[QAction]:
        """Return list of available actions for layer

        :param parent: parent
        :type parent: QWidget
        :return: list of available actions
        :rtype: List[QAction]
        """
        ac_show_layer = QAction(self.tr("Display layer"), parent)
        ac_show_layer.triggered.connect(self.addLayer)
        settings = PlgOptionsManager().get_plg_settings()

        if settings.optionTooltip:
            ac_show_layer.setToolTip(settings.tooltip_for_layer(self.layer_config))

        return [ac_show_layer]

    def addLayer(self) -> None:
        """Add layer to current QGIS project"""
        LayerLoad().load_layer(self.layer_config, self.group_name)
