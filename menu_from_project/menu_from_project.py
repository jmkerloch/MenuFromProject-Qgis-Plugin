"""
/***************************************************************************
Name            : menu_from_project plugin
Description          : Build layers shortcut menu based on QGIS project
Date                 :  10/11/2011
copyright            : (C) 2011 by Agence de l'Eau Adour Garonne
email                : xavier.culos@eau-adour-garonne.fr
***************************************************************************/

/***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************/

"""

# Standard library
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

# PyQGIS
from menu_from_project.toolbelt.preferences import (
    SOURCE_MD_LAYER,
    SOURCE_MD_NOTE,
    SOURCE_MD_OGC,
    PlgOptionsManager,
)
from qgis.core import (
    QgsApplication,
    QgsMessageLog,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsSettings,
    QgsVectorLayer,
    QgsVectorTileLayer,
    QgsRelation,
)
from qgis.PyQt.QtCore import QCoreApplication, QFileInfo, Qt, QTranslator, QUuid
from qgis.PyQt.QtGui import QFont, QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QWidget
from qgis.PyQt.QtCore import QLocale, QUrl, QDir
from qgis.PyQt.QtGui import QDesktopServices
from qgis.utils import plugins

# project
from .__about__ import DIR_PLUGIN_ROOT, __title__, __title_clean__
from .logic.qgs_manager import (
    QgsDomManager,
    is_absolute,
    read_from_file,
    read_from_http,
)
from .logic.tools import (
    guess_type_from_uri,
    icon_per_layer_type,
)
from .ui.menu_conf_dlg import MenuConfDialog  # noqa: F4 I001
from menu_from_project.logic.project_read import (
    MenuGroupConfig,
    MenuLayerConfig,
    MenuProjectConfig,
    get_project_menu_config,
)
from menu_from_project.logic.xml_utils import getFirstChildByTagNameValue

# ############################################################################
# ########## Globals ###############
# ##################################

logger = logging.getLogger(__name__)

# ############################################################################
# ########## Functions #############
# ##################################


"""
    En attendant un correctif
"""


def showPluginHelp(packageName: str = None, filename: str = "index", section: str = ""):
    try:
        source = ""
        if packageName is None:
            import inspect

            source = inspect.currentframe().f_back.f_code.co_filename
        else:
            import sys

            source = sys.modules[packageName].__file__
    except:
        return
    path = os.path.dirname(source)
    locale = str(QLocale().name())
    helpfile = os.path.join(path, filename + "-" + locale + ".html")
    if not os.path.exists(helpfile):
        helpfile = os.path.join(path, filename + "-" + locale.split("_")[0] + ".html")
    if not os.path.exists(helpfile):
        helpfile = os.path.join(path, filename + "-en.html")
    if not os.path.exists(helpfile):
        helpfile = os.path.join(path, filename + "-en_US.html")
    if not os.path.exists(helpfile):
        helpfile = os.path.join(path, filename + ".html")
    if os.path.exists(helpfile):
        url = "file://" + QDir.fromNativeSeparators(helpfile)
        if section != "":
            url = url + "#" + section
        QDesktopServices.openUrl(QUrl(url, QUrl.TolerantMode))


def project_trusted(doc):
    """Return if the project is trusted.

    :param doc: The QGIS project as XML document. Default to None.
    :type doc: QDomDocument

    :return: True of False.
    :rtype: bool
    """
    tags = doc.elementsByTagName("qgis")
    if tags.count():
        node = tags.at(0)
        trust_node = node.namedItem("trust")
        return trust_node.toElement().attribute("active") == "1"

    return False


# ############################################################################
# ########## Classes ###############
# ##################################


class MenuFromProject:

    def on_initializationCompleted(self):
        # build menu
        self.initMenus()

    def __init__(self, iface):
        self.path = QFileInfo(os.path.realpath(__file__)).path()

        # default lang
        settings = QgsSettings()
        locale = settings.value("locale/userLocale")
        self.myLocale = locale[0:2]
        # dictionary
        localePath = self.path + "/i18n/" + self.myLocale + ".qm"
        # translator
        if QFileInfo(localePath).exists():
            self.translator = QTranslator()
            self.translator.load(localePath)
            QCoreApplication.installTranslator(self.translator)

        self.iface = iface
        self.toolBar = None

        self.qgs_dom_manager = QgsDomManager()
        self.menubarActions = []
        self.layerMenubarActions = []
        self.canvas = self.iface.mapCanvas()

        self.mapLayerIds = {}

        self.plg_settings = PlgOptionsManager()

        self.action_project_configuration = None
        self.action_menu_help = None

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("MenuFromProject", message)

    @staticmethod
    def log(message, application=__title__, indent=0):
        indent_chars = " .. " * indent
        QgsMessageLog.logMessage(
            f"{indent_chars}{message}", application, notifyUser=True
        )

    def initMenus(self):
        menuBar = self.iface.editMenu().parentWidget()
        for action in self.menubarActions:
            menuBar.removeAction(action)
            del action

        self.menubarActions = []

        menuBar = self.iface.addLayerMenu()
        for action in self.layerMenubarActions:
            menuBar.removeAction(action)
            del action

        self.layerMenubarActions = []

        QgsApplication.setOverrideCursor(Qt.WaitCursor)
        settings = self.plg_settings.get_plg_settings()
        previous = None
        for project in settings.projects:
            uri = project["file"]
            try:
                project["valid"] = True
                previous = self.load_and_add_project_config(project, previous)
            except Exception as e:
                project["valid"] = False
                self.log("Menu from layer: Invalid {}".format(uri))
                for m in e.args:
                    self.log(m)

        QgsApplication.restoreOverrideCursor()

    def load_and_add_project_config(
        self, project: Dict[str, str], previous: Optional[QMenu]
    ) -> QMenu:
        """Load project menu configuration from project and add it to menus

        :param project: dict of information about the project
        :type project: Dict[str, str]
        :param previous: previous created menu
        :type previous: Optional[QMenu]
        :return: created menu
        :rtype: QMenu
        """

        # Create project menu configuration from QgsProject
        project_config = get_project_menu_config(project, self.qgs_dom_manager)

        # Add to QGIS instance
        previous = self.add_project_config(project, project_config, previous)

        return previous

    def add_project_config(
        self,
        project: Dict[str, str],
        project_config: MenuProjectConfig,
        previous: Optional[QMenu],
    ) -> QMenu:
        """Add a project menu configuration to current QGIS instance

        :param menu_name: Name of the menu to create
        :type menu_name: str
        :param project: dict of information about the project
        :type project: Dict[str, str]
        :param project_config: project menu configuration
        :type project_config: MenuProjectConfig
        :param previous: previous created menu
        :type previous: Optional[QMenu]
        :return: created menu
        :rtype: QMenu
        """
        project_menu = self.create_project_menu(
            menu_name=project_config.project_name, project=project, previous=previous
        )
        self.add_group_childs(project_config.root_group, project_menu)

        return project_menu

    def create_project_menu(
        self, menu_name: str, project: Dict[str, str], previous: Optional[QMenu]
    ) -> QMenu:
        """Create project menu and add it to QGIS instance

        :param menu_name: Name of the menu to create
        :type menu_name: str
        :param project: dict of information about the project
        :type project: Dict[str, str]
        :param previous: previous created menu
        :type previous: Optional[QMenu]
        :return: created menu
        :rtype: QMenu
        """
        location = project["location"]
        if location == "merge" and previous:
            project_menu = previous
            project_menu.addSeparator()
        else:
            if location == "layer":
                menu_bar = self.iface.addLayerMenu()
            if location == "new":
                menu_bar = self.iface.editMenu().parentWidget()

            project_menu = QMenu("&" + menu_name, menu_bar)
            project_menu.setToolTipsVisible(
                self.plg_settings.get_plg_settings().optionTooltip
            )
            project_action = menu_bar.addMenu(project_menu)

            if location == "layer":
                self.layerMenubarActions.append(project_action)
            if location == "new":
                self.menubarActions.append(project_action)
        return project_menu

    def add_group_childs(self, group: MenuGroupConfig, grp_menu: QMenu) -> bool:
        """Add all childs of a group config

        :param uri: initial uri of project (can be from local file / http / postgres)
        :type uri: str
        :param group: group menu configuration
        :type group: MenuGroupConfig
        :param grp_menu: menu for group
        :type grp_menu: QMenu
        :return: True if a layer was inserted, False otherwise
        :rtype: bool
        """
        layer_inserted = False
        for child in group.childs:
            if isinstance(child, MenuGroupConfig):
                self.add_group(child, grp_menu)
            elif isinstance(child, MenuLayerConfig):
                layer_inserted = True
                self.add_layer(child, grp_menu)
        return layer_inserted

    def add_group(self, group: MenuGroupConfig, menu: QMenu) -> None:
        """Add group menu configuration to a menu

        :param uri: initial uri of project (can be from local file / http / postgres)
        :type uri: str
        :param group: group menu configuration
        :type group: MenuGroupConfig
        :param menu: input menu
        :type menu: QMenu
        """

        name = group.name

        settings = self.plg_settings.get_plg_settings()

        # Special cases for separator and title
        # "-" => insert a separator
        if name == "-":
            menu.addSeparator()
        # "-*" => insert a title
        elif name.startswith("-"):
            action = QAction(name[1:], self.iface.mainWindow())
            font = QFont()
            font.setBold(True)
            action.setFont(font)
            menu.addAction(action)
        # regular group
        else:
            grp_menu = menu.addMenu("&" + name)
            grp_menu.setToolTipsVisible(settings.optionTooltip)

            layer_inserted = self.add_group_childs(group=group, grp_menu=grp_menu)

            if layer_inserted and settings.optionLoadAll:
                action = QAction(self.tr("Load all"), self.iface.mainWindow())
                font = QFont()
                font.setBold(True)
                action.setFont(font)
                grp_menu.addAction(action)
                action.triggered.connect(
                    lambda checked, f=None, w=None, m=grp_menu: self.loadLayer(
                        None, f, w, m
                    )
                )

    def add_layer(self, layer: MenuLayerConfig, menu: QMenu) -> None:
        """Add layer menu configuration to a menu

        :param uri: initial uri of project (can be from local file / http / postgres)
        :type uri: str
        :param layer: layer menu configuration
        :type layer: MenuLayerConfig
        :param menu: input menu
        :type menu: QMenu
        """
        settings = self.plg_settings.get_plg_settings()
        action = QAction(layer.name, self.iface.mainWindow())

        # add menu item
        action.triggered.connect(
            lambda checked, uri=layer.filename, f=layer.filename, lid=layer.layer_id, m=menu, v=layer.visible, x=layer.expanded: self.loadLayer(
                uri, f, lid, m, v, x
            )
        )
        action.setIcon(
            icon_per_layer_type(layer.is_spatial, layer.layer_type, layer.geometry_type)
        )
        if settings.optionTooltip:
            if settings.optionSourceMD == SOURCE_MD_OGC:
                abstract = layer.abstract or layer.metadata_abstract
                title = layer.title or layer.metadata_title
            else:
                abstract = layer.metadata_abstract or layer.abstract
                title = layer.metadata_title or layer.title

            abstract = ""
            title = ""
            for oSource in settings.optionSourceMD:
                if oSource == SOURCE_MD_OGC:
                    abstract = layer.metadata_abstract if abstract == "" else abstract
                    title = title or layer.metadata_title

                if oSource == SOURCE_MD_LAYER:
                    abstract = layer.abstract if abstract == "" else abstract
                    title = title or layer.title

                if oSource == SOURCE_MD_NOTE:
                    abstract = layer.layer_notes if abstract == "" else abstract

            if (abstract != "") and (title == ""):
                action.setToolTip("<p>{}</p>".format(abstract))
            else:
                if abstract != "" or title != "":
                    action.setToolTip("<b>{}</b><br/>{}".format(title, abstract))
                else:
                    action.setToolTip("")

        menu.addAction(action)

    def initGui(self):
        settings = self.plg_settings.get_plg_settings()
        if settings.is_setup_visible:
            # menu item - Main
            self.action_project_configuration = QAction(
                QIcon(str(DIR_PLUGIN_ROOT / "resources/menu_from_project.png")),
                self.tr("Projects configuration"),
                self.iface.mainWindow(),
            )

            self.iface.addPluginToMenu(
                "&" + __title__, self.action_project_configuration
            )
            # Add actions to the toolbar
            self.action_project_configuration.triggered.connect(
                self.open_projects_config
            )

            # menu item - Documentation
            self.action_menu_help = QAction(
                QIcon(QgsApplication.iconPath("mActionHelpContents.svg")),
                self.tr("Help"),
                self.iface.mainWindow(),
            )

            self.iface.addPluginToMenu("&" + __title__, self.action_menu_help)
            self.action_menu_help.triggered.connect(
                lambda: showPluginHelp(filename="doc/index")
            )

        self.iface.initializationCompleted.connect(self.on_initializationCompleted)

    def unload(self):
        menuBar = self.iface.editMenu().parentWidget()
        for action in self.menubarActions:
            menuBar.removeAction(action)
            del action

        menuBar = self.iface.addLayerMenu()
        for action in self.layerMenubarActions:
            menuBar.removeAction(action)
            del action

        self.menubarActions = []
        self.layerMenubarActions = []

        settings = self.plg_settings.get_plg_settings()
        if settings.is_setup_visible:
            self.iface.removePluginMenu(
                "&" + __title__, self.action_project_configuration
            )
            self.iface.removePluginMenu("&" + __title__, self.action_menu_help)
            self.action_project_configuration.triggered.disconnect(
                self.open_projects_config
            )

        self.iface.initializationCompleted.disconnect(self.on_initializationCompleted)

    def open_projects_config(self):
        dlg = MenuConfDialog(self.iface.mainWindow())
        dlg.setModal(True)

        dlg.show()
        result = dlg.exec_()
        del dlg

        if result != 0:
            # clear web projects cache
            try:
                read_from_http.cache_clear()
                read_from_file.cache_clear()
            except Exception:
                pass

            # build menus
            self.initMenus()

    def addLayer(
        self,
        uri,
        doc,
        layerId,
        group=None,
        visible=False,
        expanded=False,
        parentsLoop: dict = {},
        loop=0,
    ):
        theLayer = None
        settings = self.plg_settings.get_plg_settings()

        # is project in relative path ?
        absolute = is_absolute(doc)
        trusted = project_trusted(doc)

        node = getFirstChildByTagNameValue(
            doc.documentElement(), "maplayer", "id", layerId
        )
        node = node.cloneNode()
        if node:
            idNode = node.namedItem("id")
            layerType = node.toElement().attribute("type", "vector")
            # give it a new id (for multiple import)
            newLayerId = "L%s" % re.sub("[{}-]", "", QUuid.createUuid().toString())
            self.mapLayerIds[newLayerId] = layerId

            try:
                idNode.firstChild().toText().setData(newLayerId)
            except Exception:
                pass

            # if relative path, adapt datasource
            if not absolute:
                try:
                    datasourceNode = node.namedItem("datasource")
                    ds = datasourceNode.firstChild().toText().data()
                    providerNode = node.namedItem("provider")
                    provider = providerNode.firstChild().toText().data()

                    if provider in ["ogr", "gdal"] and (ds.find(".") == 0):
                        projectpath = QFileInfo(uri).path()
                        newlayerpath = projectpath + "/" + ds
                        datasourceNode.firstChild().toText().setData(newlayerpath)
                except Exception:
                    pass

            # is relations exists ?
            relationsToBuild = []
            if settings.optionOpenLinks:
                relationsToBuild = self.buildRelations(
                    uri, doc, layerId, newLayerId, group, parentsLoop, loop
                )

            # read modified layer node
            newLayer = None
            if settings.optionCreateGroup and group is not None:
                if layerType == "raster":
                    theLayer = QgsRasterLayer()
                elif layerType == "vector-tile":
                    theLayer = QgsVectorTileLayer()
                else:
                    theLayer = QgsVectorLayer()
                    theLayer.setReadExtentFromXml(trusted)

                theLayer.readLayerXml(node.toElement(), QgsReadWriteContext())

                # Special process if the plugin "DB Style Manager" is installed
                flag = "use_db_style_manager_in_custom_menu" in os.environ
                if flag and "db-style-manager" in plugins:
                    try:
                        plugins["db-style-manager"].load_style_from_database(theLayer)
                    except Exception:
                        self.log(
                            "DB-Style-Manager failed to load the style.",
                            indent=loop,
                        )

                # needed
                newLayer = QgsProject.instance().addMapLayer(theLayer, False)
                if newLayer is not None:
                    # add to group
                    treeNode = group.insertLayer(0, newLayer)
                    treeNode.setExpanded(expanded)
                    treeNode.setItemVisibilityChecked(visible)
            else:
                # create layer
                ok = QgsProject.instance().readLayer(node)
                if ok:
                    newLayer = QgsProject.instance().mapLayer(newLayerId)

            return newLayer, relationsToBuild

        else:
            self.log("{} not found".format(layerId), indent=loop)

        return None, None

    def getRelations(self, doc):
        """
        Charger la définition des relations (niveau projet), pour les rétablir éventuellement après chargement des couches

        <relations>
            <relation strength="Association" referencedLayer="layerid" id="refid" name="fk_region" referencingLayer="layerid">
                <fieldRef referencedField="insee_region" referencingField="insee_region"/>
            </relation>
        </relations>
        """
        relations = []
        try:
            nodes = doc.elementsByTagName("relations")
            relsNode = nodes.at(0)

            relNodes = relsNode.toElement().elementsByTagName("relation")
            for relNode in (relNodes.at(i) for i in range(relNodes.size())):
                fieldNodes = relNode.toElement().elementsByTagName("fieldRef")
                fieldNode = fieldNodes.at(0)

                if fieldNode:
                    relation = {}
                    for attr in [
                        "strength",
                        "referencedLayer",
                        "id",
                        "name",
                        "referencingLayer",
                    ]:
                        relation[attr] = relNode.toElement().attribute(attr)

                    for attr in [
                        "referencedField",
                        "referencingField",
                    ]:
                        relation[attr] = fieldNode.toElement().attribute(attr)

                    if relation["referencedLayer"] != "":
                        relations.append(relation)
        except Exception as e:
            for m in e.args:
                self.log(m)

        return relations

    def getRelationsForLayer(self, relations, source=None, target=None):
        """Retourne le dico de la relation selon si 'source'=referencedLayer ou 'target'=referencingLayer"""

        r = []
        try:
            for relation in relations:
                if source is not None and source == relation["referencedLayer"]:
                    r.append(relation)

                if target is not None and target == relation["referencingLayer"]:
                    r.append(relation)
        except Exception as e:
            for m in e.args:
                self.log(m)

        return r

    def fixForm(self, doc, newLayerId: str, oldRelationId, newRelationId):
        """rebuilds the form when relations are defined in it

        Principle: reading the source XML document, updating identifiers, updating editFormConfig
        """
        theLayer = QgsProject.instance().mapLayer(newLayerId)
        oldLayerId = self.mapLayerIds[newLayerId]

        layerNode = getFirstChildByTagNameValue(
            doc.documentElement(), "maplayer", "id", oldLayerId
        )

        nodes = layerNode.toElement().elementsByTagName("attributeEditorForm")
        if nodes.count() == 0:
            return
        aefNode = nodes.at(0)

        nodes = aefNode.toElement().elementsByTagName("attributeEditorRelation")
        for nodeIdx in range(nodes.length()):
            aerNode = nodes.at(nodeIdx)
            rid = aerNode.toElement().attribute("relation")
            if rid == oldRelationId:
                aerNode.toElement().setAttribute("relation", newRelationId)

                nodes = aefNode.toElement().elementsByTagName("widgets")
                widgets = nodes.at(0)
                widgets.toElement().setAttribute("name", newRelationId)

                editFormConfig = theLayer.editFormConfig()
                rootContainer = editFormConfig.invisibleRootContainer()
                rootContainer.clear()
                editFormConfig.clearTabs()
                editFormConfig.readXml(layerNode, QgsReadWriteContext())
                theLayer.setEditFormConfig(editFormConfig)

    def buildProjectRelation(self, doc, relDict):
        try:
            """builds one relation, add it to the project"""
            REL_STRENGTH = {
                "Association": QgsRelation.Association,
                "Composition": QgsRelation.Composition,
            }
            relMan = QgsProject.instance().relationManager()

            rel = QgsRelation()
            rel.addFieldPair(relDict["referencingField"], relDict["referencedField"])
            oldRelationId = relDict["id"]
            newRelationId = "R%s" % re.sub("[{}-]", "", QUuid.createUuid().toString())
            rel.setId(newRelationId)
            rel.setName(relDict["name"])
            rel.setReferencedLayer(relDict["referencedLayer"])
            rel.setReferencingLayer(relDict["referencingLayer"])
            rel.setStrength(REL_STRENGTH[relDict["strength"]])
            rel.updateRelationStatus()

            if rel.isValid():
                relMan.addRelation(rel)

                # Adapter le formulaire de la couche referencedLayer
                try:
                    self.fixForm(
                        doc,
                        relDict["referencedLayer"],
                        oldRelationId,
                        newRelationId,
                    )
                except Exception:
                    self.log(
                        "Form not fixed for layer {}".format(relDict["referencedLayer"])
                    )

            else:
                self.log(
                    "Invalid relation {} : {}".format(rel.id(), rel.validationError())
                )
        except Exception as e:
            for m in e.args:
                self.log(m)

    def buildRelations(
        self, uri, doc, oldLayerId, newLayerId, group, parentsLoop, loop
    ):
        """identify the relations to be created (later, after source layer creation)

        Based on those of the source project, adapted to the new identifiers of the layers
        """
        relationsToBuild, targetRelations = [], []

        relations = self.getRelations(doc)
        relsTarget = self.getRelationsForLayer(relations, source=oldLayerId)
        # relsSource = self.getRelationsForLayer(relations, target=oldLayerId)

        if len(relsTarget) > 0:
            for relDict in relsTarget:
                if relDict["referencingLayer"] in parentsLoop:
                    # La couche cible a déjà été ajoutée (boucle infinie)
                    # on se contente de référencer celle-ci
                    relDict["referencedLayer"] = newLayerId
                    relDict["referencingLayer"] = parentsLoop[
                        relDict["referencingLayer"]
                    ]
                    relationsToBuild.append(relDict)
                else:
                    # la couche cible n'a pas été ajoutée
                    parentsLoop.update({oldLayerId: newLayerId})

                    targetLayer, targetRelations = self.addLayer(
                        uri,
                        doc,
                        relDict["referencingLayer"],
                        group,
                        False,
                        False,
                        parentsLoop,
                        loop + 1,
                    )
                    if targetLayer is not None:
                        relDict["referencedLayer"] = newLayerId
                        relDict["referencingLayer"] = targetLayer.id()
                        relationsToBuild.append(relDict)

        return targetRelations + relationsToBuild

    def loadLayer(self, uri, fileName, layerId, menu=None, visible=None, expanded=None):
        """Load the chosen layer(s)

        :param uri: The layer URI (file path or PG URI)
        :type uri: basestring

        :param layerId: The layer ID to look for in the project.
        :type layerId: basestring

        """
        self.canvas.freeze(True)
        self.canvas.setRenderFlag(False)
        group = None
        QgsApplication.setOverrideCursor(Qt.WaitCursor)
        self.mapLayerIds = {}

        settings = self.plg_settings.get_plg_settings()

        try:
            if (
                isinstance(menu.parentWidget(), (QMenu, QWidget))
                and settings.optionCreateGroup
            ):
                groupName = menu.title().replace("&", "")
                group = QgsProject.instance().layerTreeRoot().findGroup(groupName)
                if group is None:
                    group = (
                        QgsProject.instance().layerTreeRoot().insertGroup(0, groupName)
                    )

            # load all layers
            if fileName is None and layerId is None and settings.optionLoadAll:
                for action in menu.actions()[::-1]:
                    if (
                        action.text() != self.tr("Load all")
                        and action.text() != "Load all"
                    ):
                        action.trigger()
            else:
                doc, _ = self.qgs_dom_manager.getQgsDoc(fileName)

                # Loading layer
                layer, relationsToBuild = self.addLayer(
                    uri, doc, layerId, group, visible, expanded, {}, 0
                )
                for relDict in relationsToBuild:
                    self.buildProjectRelation(doc, relDict)

                # is joined layers exists ?
                if settings.optionOpenLinks and layer and type(layer) == QgsVectorLayer:
                    for j in layer.vectorJoins():
                        try:
                            joinLayer, joinRelations = self.addLayer(
                                uri, doc, j.joinLayerId(), group
                            )
                            for relDict in joinRelations:
                                self.buildProjectRelation(doc, relDict)

                            if joinLayer:
                                j.setJoinLayerId(joinLayer.id())
                                j.setJoinLayer(joinLayer)
                                layer.addJoin(j)
                        except Exception as e:
                            self.log(
                                "Joined layer {} not added.".format(j.joinLayerId())
                            )
                            pass

        except Exception as e:
            # fixme fileName is not defined
            # self.log(
            #     'Menu from layer: Invalid ' + (fileName if fileName is not None else ""))
            for m in e.args:
                self.log(m)

        finally:
            self.canvas.freeze(False)
            self.canvas.setRenderFlag(True)
            self.canvas.refresh()
            QgsApplication.restoreOverrideCursor()
