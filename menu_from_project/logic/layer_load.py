# Standard library
import re
import os


# PyQGIS
from menu_from_project.toolbelt.preferences import PlgOptionsManager
from qgis.core import (
    QgsApplication,
    QgsMessageLog,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsVectorLayer,
    QgsVectorTileLayer,
    QgsRelation,
)
from qgis.PyQt.QtCore import QCoreApplication, QFileInfo, Qt, QUuid
from qgis.utils import plugins, iface
from qgis.PyQt.QtWidgets import QMenu, QWidget

# project
from menu_from_project.__about__ import __title__
from menu_from_project.logic.qgs_manager import (
    QgsDomManager,
    is_absolute,
    project_trusted,
)
from menu_from_project.logic.xml_utils import getFirstChildByTagNameValue


class LayerLoad:

    def __init__(self) -> None:
        self.canvas = iface.mapCanvas()
        self.plg_settings = PlgOptionsManager()
        self.qgs_dom_manager = QgsDomManager()
        self.mapLayerIds = {}

    @staticmethod
    def log(message, application=__title__, indent=0):
        indent_chars = " .. " * indent
        QgsMessageLog.logMessage(
            f"{indent_chars}{message}", application, notifyUser=True
        )

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("MenuFromProject", message)

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
                menu
                and isinstance(menu.parentWidget(), (QMenu, QWidget))
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
