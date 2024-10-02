from typing import List
import os.path
import webbrowser

from menu_from_project.logic.tools import icon_per_layer_type
from menu_from_project.toolbelt.preferences import (
    SOURCE_MD_LAYER,
    SOURCE_MD_NOTE,
    SOURCE_MD_OGC,
    PlgOptionsManager,
)
from qgis.core import (
    QgsDataItemProvider,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataProvider,
    QgsMimeDataUtils,
    QgsApplication,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.utils import iface


from menu_from_project.logic.layer_load import LayerLoad
from menu_from_project.logic.project_read import (
    MenuGroupConfig,
    MenuLayerConfig,
    MenuProjectConfig,
)
from menu_from_project.__about__ import __title__


class MenuLayerProvider(QgsDataItemProvider):
    def __init__(self, iface=iface, project_configs=[]):
        self.iface = iface
        QgsDataItemProvider.__init__(self)
        self.project_configs = project_configs

    def name(self):
        return "Layer from project"

    def capabilities(self):
        return QgsDataProvider.Net

    def createDataItem(self, path, parentItem):
        print("createDataItem for provider")
        self.root = RootCollection(
            self.iface, parent=parentItem, project_configs=self.project_configs
        )
        return self.root


class RootCollection(QgsDataCollectionItem):
    def __init__(
        self, iface: QgisInterface, parent, project_configs: List[MenuProjectConfig]
    ):
        self.iface = iface
        QgsDataCollectionItem.__init__(self, parent, "MenuLayer", "/MenuLayer")
        # TODO : define icon
        self.project_configs = project_configs

    def actions(self, parent):
        actions = list()
        add_idg_action = QAction(QIcon(), self.tr("Settings..."), parent)
        add_idg_action.triggered.connect(
            lambda: self.iface.showOptionsDialog(
                currentPage="mOptionsPage{}".format(__title__)
            )
        )
        actions.append(add_idg_action)
        return actions

    def menus(self, parent):
        # TODO : lister les projets dans le menu
        menu = QMenu(title=self.tr("Plateforms"), parent=parent)
        menu.setEnabled(False)  # dev
        for pf, checked in zip(
            ["DataGrandEst", "GeoBretagne", "Geo2France", "Indigeo"],
            [True, False, True, False],
        ):  # pour maquette TODO boucler sur une variable de conf
            action = QAction(pf, menu, checkable=True)
            action.setChecked(checked)
            menu.addAction(
                action
            )  # TODO l'action permet d'activer/désactiver une plateforme. La désactivation supprime le DataCollectionItem et désactive le download du fichier de conf
        menu.addSeparator()
        menu.addAction(
            QAction(
                self.tr("Add URL"),
                menu,
            )
        )  # TODO Liens vers le panneau Options de QGIS
        return [menu]

    def createChildren(self):
        children = []
        for pfc in [
            ProjectCollection(project_menu_config=project_config, parent=self)
            for project_config in self.project_configs
        ]:
            children.append(pfc)
        return children


class ProjectCollection(QgsDataCollectionItem):
    def __init__(self, project_menu_config: MenuProjectConfig, parent):
        self.path = "/MenuLayer/" + project_menu_config.project_name.lower()
        self.parent = parent
        QgsDataCollectionItem.__init__(
            self, parent, project_menu_config.project_name, self.path
        )
        self.project_menu_config = project_menu_config
        self.setName(project_menu_config.project_name)
        self.setIcon(QIcon(QgsApplication.iconPath("mIconFolderProject.svg")))

    def createChildren(self):
        children = []
        for child in self.project_menu_config.root_group.childs:
            if isinstance(child, MenuLayerConfig):
                children.append(LayerItem(parent=self, layer_config=child))
            elif isinstance(child, MenuGroupConfig):
                children.append(GroupItem(parent=self, group_config=child))
        return children

    def actions(self, parent):
        # parent.setToolTipsVisible(True)
        def set_action_url(link):
            a = QAction(link.name, parent)
            a.triggered.connect(lambda: webbrowser.open_new_tab(link.url))
            # a.setToolTip(link.description)
            return a

        def hide_plateform(pf):
            pf.hide()
            self.parent.removeChildItem(self)

        actions = []
        for link in self.project.metadata().links():
            if link.name.lower() != "icon":
                actions.append(set_action_url(link))
        separator = QAction(QIcon(), "", parent)
        separator.setSeparator(True)
        actions.append(separator)
        hide_action = QAction(self.tr("Hide"), parent)
        hide_action.triggered.connect(lambda: hide_plateform(self.plateform))
        actions.append(hide_action)
        return actions


class GroupItem(QgsDataCollectionItem):
    def __init__(self, parent, group_config: MenuGroupConfig):
        self.path = os.path.join(parent.path, group_config.name)
        self.group_config = group_config
        QgsDataCollectionItem.__init__(self, parent, group_config.name, self.path)
        self.setIcon(QIcon(QgsApplication.iconPath("mIconFolder.svg")))

    def createChildren(self):
        children = []
        for child in self.group_config.childs:
            if isinstance(child, MenuLayerConfig):
                children.insert(0, LayerItem(parent=self, layer_config=child))
            elif isinstance(child, MenuGroupConfig):
                children.insert(0, GroupItem(parent=self, group_config=child))
        return children


class LayerItem(QgsDataItem):
    def __init__(self, parent, layer_config: MenuLayerConfig):
        self.layer_config = layer_config
        self.path = os.path.join(parent.path, layer_config.name)
        QgsDataItem.__init__(
            self, QgsDataItem.Custom, parent, layer_config.name, self.path
        )
        self.setState(QgsDataItem.Populated)  # no children

        settings = PlgOptionsManager().get_plg_settings()

        if settings.optionSourceMD == SOURCE_MD_OGC:
            abstract = self.layer_config.abstract or self.layer_config.metadata_abstract
            title = self.layer_config.title or self.layer_config.metadata_title
        else:
            abstract = self.layer_config.metadata_abstract or self.layer_config.abstract
            title = self.layer_config.metadata_title or self.layer_config.title

        abstract = ""
        title = ""
        for oSource in settings.optionSourceMD:
            if oSource == SOURCE_MD_OGC:
                abstract = (
                    self.layer_config.metadata_abstract if abstract == "" else abstract
                )
                title = title or self.layer_config.metadata_title

            if oSource == SOURCE_MD_LAYER:
                abstract = self.layer_config.abstract if abstract == "" else abstract
                title = title or self.layer_config.title

            if oSource == SOURCE_MD_NOTE:
                abstract = self.layer_config.layer_notes if abstract == "" else abstract

        if (abstract != "") and (title == ""):
            self.setToolTip("<p>{}</p>".format(abstract))
        else:
            if abstract != "" or title != "":
                self.setToolTip("<b>{}</b><br/>{}".format(title, abstract))
            else:
                self.setToolTip("")
        self.setIcon(
            icon_per_layer_type(
                is_spatial=self.layer_config.is_spatial,
                layer_type=self.layer_config.layer_type,
                geometry_type=self.layer_config.geometry_type,
            )
        )

    def mimeUri(self):
        # Définir le mime est nécessaire pour le drag&drop
        return QgsMimeDataUtils.Uri(self.layer)

    def mimeUris(self):
        return [QgsMimeDataUtils.Uri(self.layer)]

    def hasDragEnabled(self):
        # TODO ajouter une couche via le drag fait perdre le style, car ouvre directement la couche sans passer par le projet
        return False

    def handleDoubleClick(self):
        self.addLayer()
        return True

    def hasChildren(self):
        return False

    def openUrl(self):
        webbrowser.open_new_tab(self.catalog_url)

    def addLayer(self):
        LayerLoad().loadLayer(
            self.layer_config.filename,
            self.layer_config.filename,
            self.layer_config.layer_id,
            None,
            self.layer_config.visible,
            self.layer_config.expanded,
        )

    def actions(self, parent):
        ac_open_meta = QAction(self.tr("Show metadata"), parent)
        if self.catalog_url is not None:
            ac_open_meta.triggered.connect(self.openUrl)
        else:
            ac_open_meta.setEnabled(False)

        ac_show_layer = QAction(self.tr("Display layer"), parent)
        ac_show_layer.triggered.connect(self.addLayer)

        actions = [
            ac_show_layer,
            ac_open_meta,
        ]
        return actions
