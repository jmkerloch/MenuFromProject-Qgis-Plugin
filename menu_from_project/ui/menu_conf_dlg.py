#! python3  # noqa: E265

"""
    Dialog for setting up the plugin.
"""

# Standard library
import logging
from functools import partial

# PyQGIS
from menu_from_project.datamodel.project import Project, ProjectCacheConfig
from menu_from_project.logic.qgs_manager import QgsDomManager
from menu_from_project.toolbelt.preferences import (
    SOURCE_MD_LAYER,
    SOURCE_MD_NOTE,
    SOURCE_MD_OGC,
    PlgOptionsManager,
)
from qgis.core import QgsApplication, Qgis, QgsMessageLog
from qgis.gui import QgsProviderGuiRegistry, QgsSpinBox
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QRect, Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QTableWidgetItem,
    QToolButton,
    QCheckBox,
)
from qgis.utils import iface

# project
from menu_from_project.__about__ import DIR_PLUGIN_ROOT, __title__, __version__
from menu_from_project.logic.custom_datatypes import TABLE_COLUMNS_ORDER
from menu_from_project.logic.tools import (
    guess_type_from_uri,
    icon_per_storage_type,
)

# ############################################################################
# ########## Globals ###############
# ##################################

logger = logging.getLogger(__name__)

# load ui
FORM_CLASS, _ = uic.loadUiType(DIR_PLUGIN_ROOT / "ui/conf_dialog.ui")

# ############################################################################
# ########## Classes ###############
# ##################################


class MenuConfDialog(QDialog, FORM_CLASS):
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.plg_settings = PlgOptionsManager()
        self.qgs_dom_manager = QgsDomManager()

        self.defaultcursor = self.cursor
        self.setWindowTitle(
            self.windowTitle() + " - {} v{}".format(__title__, __version__)
        )
        self.setWindowIcon(
            QIcon(str(DIR_PLUGIN_ROOT / "resources/gear.svg")),
        )

        # column order reference
        self.cols = TABLE_COLUMNS_ORDER(
            edit=0,
            name=1,
            type_menu_location=3,
            type_storage=2,
            uri=4,
            refresh_days=5,
            enable_cache=6,
        )

        # menu locations
        self.LOCATIONS = {
            "new": {
                "index": 0,
                "label": QgsApplication.translate("ConfDialog", "New menu", None),
            },
            "layer": {
                "index": 1,
                "label": QgsApplication.translate("ConfDialog", "Add layer menu", None),
            },
            "merge": {
                "index": 2,
                "label": QgsApplication.translate(
                    "ConfDialog", "Merge with previous", None
                ),
            },
        }

        settings = self.plg_settings.get_plg_settings()

        # -- Configured projects (table and related buttons)
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.tableWidget.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        self.tableWidget.setRowCount(len(settings.projects))
        self.buttonBox.accepted.connect(self.onAccepted)
        self.btnDelete.clicked.connect(self.onDelete)
        self.btnDelete.setText(None)
        self.btnDelete.setIcon(
            QIcon(QgsApplication.iconPath("mActionDeleteSelected.svg"))
        )
        self.btnUp.clicked.connect(self.onMoveUp)
        self.btnUp.setText(None)
        self.btnUp.setIcon(QIcon(QgsApplication.iconPath("mActionArrowUp.svg")))
        self.btnDown.clicked.connect(self.onMoveDown)
        self.btnDown.setText(None)
        self.btnDown.setIcon(QIcon(QgsApplication.iconPath("mActionArrowDown.svg")))

        # add button
        self.btnAdd.setIcon(QIcon(QgsApplication.iconPath("mActionAdd.svg")))
        self.addMenu = QMenu(self.btnAdd)
        add_option_file = QAction(
            QIcon(QgsApplication.iconPath("mIconFile.svg")),
            self.tr("Add from file"),
            self.addMenu,
        )
        add_option_pgdb = QAction(
            QIcon(QgsApplication.iconPath("mIconPostgis.svg")),
            self.tr("Add from PostgreSQL database"),
            self.addMenu,
        )
        add_option_http = QAction(
            QIcon(str(DIR_PLUGIN_ROOT / "resources/globe.svg")),
            self.tr("Add from URL"),
            self.addMenu,
        )
        add_option_file.triggered.connect(partial(self.onAdd, "file"))
        add_option_http.triggered.connect(partial(self.onAdd, "http"))
        add_option_pgdb.triggered.connect(partial(self.onAdd, "database"))
        self.addMenu.addAction(add_option_file)
        self.addMenu.addAction(add_option_pgdb)
        self.addMenu.addAction(add_option_http)
        self.btnAdd.setMenu(self.addMenu)

        for idx, project in enumerate(settings.projects):
            # edit project
            self.addEditButton(idx, guess_type_from_uri(project.file))

            # project name
            itemName = QTableWidgetItem(project.name)
            itemName.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.tableWidget.setItem(idx, self.cols.name, itemName)
            le = QLineEdit()
            le.setText(project.name)
            le.setPlaceholderText(self.tr("Use project title"))
            self.tableWidget.setCellWidget(idx, self.cols.name, le)

            # project storage type
            self.tableWidget.setCellWidget(
                idx,
                self.cols.type_storage,
                self.mk_prj_storage_icon(guess_type_from_uri(project.file)),
            )

            # project menu location
            location_combo = QComboBox()
            for pk in self.LOCATIONS:
                if not (pk == "merge" and idx == 0):
                    location_combo.addItem(self.LOCATIONS[pk]["label"], pk)

            try:
                location_combo.setCurrentIndex(
                    self.LOCATIONS[project.location]["index"]
                )
            except Exception:
                location_combo.setCurrentIndex(0)
            self.tableWidget.setCellWidget(
                idx, self.cols.type_menu_location, location_combo
            )

            # project path (guess type stored into data)
            itemFile = QTableWidgetItem(project.file)
            itemFile.setData(Qt.UserRole, guess_type_from_uri(project.file))
            itemFile.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.tableWidget.setItem(idx, self.cols.uri, itemFile)
            le = QLineEdit()
            le.setText(project.file)
            try:
                le.setStyleSheet(
                    "color: {};".format("black" if project.valid else "red")
                )
            except Exception:
                le.setStyleSheet("color: {};".format("black"))

            self.tableWidget.setCellWidget(idx, self.cols.uri, le)
            le.textChanged.connect(self.onTextChanged)

            # refresh day
            refresh_day_item = QTableWidgetItem()
            refresh_day_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.tableWidget.setItem(idx, self.cols.refresh_days, refresh_day_item)
            spinbox = QgsSpinBox()
            spinbox.setClearValue(-1, self.tr("None"))
            spinbox.setSuffix(self.tr(" days"))
            if project.cache_config.refresh_days_period:
                spinbox.setValue(project.cache_config.refresh_days_period)
            self.tableWidget.setCellWidget(idx, self.cols.refresh_days, spinbox)

            # Cache enable
            enable_cache_item = QTableWidgetItem()
            enable_cache_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.tableWidget.setItem(idx, self.cols.enable_cache, enable_cache_item)
            checkbox = QCheckBox()
            checkbox.setChecked(project.cache_config.enable)
            self.tableWidget.setCellWidget(idx, self.cols.enable_cache, checkbox)

        # -- Options
        self.cbxLoadAll.setChecked(settings.optionLoadAll)
        self.cbxLoadAll.setTristate(False)

        self.cbxCreateGroup.setCheckState(settings.optionCreateGroup)
        self.cbxCreateGroup.setTristate(False)

        self.cbxShowTooltip.setCheckState(settings.optionTooltip)
        self.cbxShowTooltip.setTristate(False)

        self.cbxOpenLinks.setCheckState(settings.optionOpenLinks)
        self.cbxOpenLinks.setTristate(False)

        self.sourcesMdText = {
            SOURCE_MD_OGC: self.tr("QGis Server metadata"),
            SOURCE_MD_LAYER: self.tr("Layer Metadata"),
            SOURCE_MD_NOTE: self.tr("Layer Notes"),
        }
        self.optionSourceMD = settings.optionSourceMD

        self.tableTunning()

    def setSourceMdText(self):
        self.mdSource1.setText(self.sourcesMdText[self.optionSourceMD[0]])
        self.mdSource2.setText(self.sourcesMdText[self.optionSourceMD[1]])
        self.mdSource3.setText(self.sourcesMdText[self.optionSourceMD[2]])

    def addEditButton(self, row, guess_type):
        """Add edit button, adapted to the type of resource

        :param row: row index.
        :type guess_type: resource type (database, file)

        """
        if guess_type == "file":
            edit_button = self.mk_prj_edit_button()
            self.tableWidget.setCellWidget(row, self.cols.edit, edit_button)
            edit_button.clicked.connect(
                lambda checked, idx=row: self.onFileSearchPressed(row)
            )

        if guess_type == "database":
            edit_button = self.mk_prj_edit_button()
            self.tableWidget.setCellWidget(row, self.cols.edit, edit_button)
            edit_button.clicked.connect(
                lambda checked, idx=row: self.onDbSearchPressed(row)
            )

        if guess_type == "http":
            edit_button = self.mk_prj_edit_button("help")
            self.tableWidget.setCellWidget(row, self.cols.edit, edit_button)
            edit_button.clicked.connect(
                lambda checked, idx=row: self.onHttpSearchPressed(row)
            )

    def onFileSearchPressed(self, row: int):
        """Open file browser to allow user pick a QGIS project file. \
        Trigered when edit button is pressed for a project with type_storage == file.

        :param row: row indice
        :type row: int
        """
        file_widget = self.tableWidget.cellWidget(row, self.cols.uri)

        filePath = QFileDialog.getOpenFileName(
            self,
            QgsApplication.translate(
                "menu_from_project", "Projects configuration", None
            ),
            file_widget.text(),
            QgsApplication.translate(
                "menu_from_project", "QGIS projects (*.qgs *.qgz)", None
            ),
        )

        try:
            if filePath[0]:
                file_widget.setText(filePath[0])

                name_widget = self.tableWidget.cellWidget(row, self.cols.name)
                name = name_widget.text()
                if not name:
                    try:
                        name = filePath[0].split("/")[-1]
                        name = name.split(".")[0]
                    except Exception:
                        name = ""

                    name_widget.setText(name)

        except Exception:
            pass

    def onHttpSearchPressed(self, row: int):
        """no HTTP browser, only help message.

        :param row: row indice
        :type row: int
        """
        iface.messageBar().pushMessage(
            "Message",
            self.tr(
                "No HTTP Browser, simply paste your URL into the 'project' column."
            ),
            level=Qgis.Info,
        )

    def onDbSearchPressed(self, row: int):
        """Open database browser to allow user pick a QGIS project file. \
        Trigered when edit button is pressed for a project with type_storage == database.

        :param row: row indice
        :type row: int
        """
        item = self.tableWidget.item(row, 1)

        pgr = QgsProviderGuiRegistry(QgsApplication.pluginPath())
        pl = pgr.providerList()
        if "postgres" in pgr.providerList():
            psgp = pgr.projectStorageGuiProviders("postgres")
            if len(psgp) > 0:
                uri = psgp[0].showLoadGui()
                try:
                    if uri:
                        file_widget = self.tableWidget.cellWidget(row, self.cols.uri)
                        file_widget.setText(uri)

                        name_widget = self.tableWidget.cellWidget(row, self.cols.name)
                        name = name_widget.text()
                        if not name:
                            try:
                                name = uri.split("project=")[-1]
                                name = name.split(".")[0]
                            except Exception:
                                name = ""

                            name_widget.setText(name)

                except Exception:
                    pass

    def onAccepted(self):
        settings = self.plg_settings.get_plg_settings()
        settings.projects = []
        # self.log("count : {}".format(self.tableWidget.rowCount()))
        for row in range(self.tableWidget.rowCount()):
            file_widget = self.tableWidget.cellWidget(row, self.cols.uri)
            # self.log("row : {}".format(row))
            if file_widget and file_widget.text():
                # self.log("row {} : {}".format(row, file_widget.text()))

                name_widget = self.tableWidget.cellWidget(row, self.cols.name)
                name = name_widget.text()
                filename = file_widget.text()

                location_widget = self.tableWidget.cellWidget(
                    row, self.cols.type_menu_location
                )
                location = location_widget.itemData(location_widget.currentIndex())

                cache_config = ProjectCacheConfig(
                    refresh_days_period=self.tableWidget.cellWidget(
                        row, self.cols.refresh_days
                    ).value(),
                    enable=self.tableWidget.cellWidget(
                        row, self.cols.enable_cache
                    ).isChecked(),
                )

                settings.projects.append(
                    Project(
                        file=filename,
                        name=name,
                        location=location,
                        valid=False,
                        type_storage=guess_type_from_uri(filename),
                        cache_config=cache_config,
                    )
                )

        settings.optionTooltip = self.cbxShowTooltip.isChecked()
        settings.optionLoadAll = self.cbxLoadAll.isChecked()
        settings.optionCreateGroup = self.cbxCreateGroup.isChecked()
        settings.optionOpenLinks = self.cbxOpenLinks.isChecked()

        settings.optionSourceMD = self.optionSourceMD

        PlgOptionsManager().save_from_object(settings)

    def onAdd(self, qgs_type_storage: str = "file"):
        """Add a new line to the table.

        :param qgs_type_storage: project storage type, defaults to "file"
        :type qgs_type_storage: str, optional
        """
        row = self.tableWidget.rowCount()
        self.tableWidget.setRowCount(row + 1)

        # edit button
        self.addEditButton(row, qgs_type_storage)

        # project name
        itemName = QTableWidgetItem()
        itemName.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.tableWidget.setItem(row, self.cols.name, itemName)
        name_lineedit = QLineEdit()
        name_lineedit.setPlaceholderText(self.tr("Use project title"))
        self.tableWidget.setCellWidget(row, self.cols.name, name_lineedit)

        # project storage type
        self.tableWidget.setCellWidget(
            row,
            self.cols.type_storage,
            self.mk_prj_storage_icon(qgs_type_storage),
        )

        # menu location
        location_combo = QComboBox()
        for pk in self.LOCATIONS:
            if not (pk == "merge" and row == 0):
                location_combo.addItem(self.LOCATIONS[pk]["label"], pk)

        location_combo.setCurrentIndex(0)
        self.tableWidget.setCellWidget(
            row, self.cols.type_menu_location, location_combo
        )

        # project file path
        itemFile = QTableWidgetItem()
        itemFile.setData(Qt.UserRole, qgs_type_storage)
        itemFile.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.tableWidget.setItem(row, self.cols.uri, itemFile)
        filepath_lineedit = QLineEdit()
        filepath_lineedit.textChanged.connect(self.onTextChanged)
        self.tableWidget.setCellWidget(row, self.cols.uri, filepath_lineedit)

        # refresh day
        refresh_day_item = QTableWidgetItem()
        refresh_day_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.tableWidget.setItem(row, self.cols.refresh_days, refresh_day_item)
        spinbox = QgsSpinBox()
        spinbox.setClearValue(-1, self.tr("None"))
        spinbox.setSuffix(self.tr(" days"))
        self.tableWidget.setCellWidget(row, self.cols.refresh_days, spinbox)

        # Cache enable
        enable_cache_item = QTableWidgetItem()
        enable_cache_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.tableWidget.setItem(row, self.cols.enable_cache, enable_cache_item)
        checkbox = QCheckBox()
        self.tableWidget.setCellWidget(row, self.cols.enable_cache, checkbox)

        # apply table styling
        self.tableTunning()

    @staticmethod
    def log(message, application=__title__, indent=0):
        indent_chars = " .. " * indent
        QgsMessageLog.logMessage(
            f"{indent_chars}{message}", application, notifyUser=True
        )

    def onDelete(self):
        """Remove selected lines from the table."""
        sr = self.tableWidget.selectedRanges()
        try:
            self.tableWidget.removeRow(sr[0].topRow())
        except Exception:
            pass

    def onMoveUp(self):
        """Move the selected lines upwards."""
        sr = self.tableWidget.selectedRanges()
        try:
            r = sr[0].topRow()
            if r > 0:
                typeA = self.tableWidget.item(r - 1, self.cols.uri).data(Qt.UserRole)
                typeB = self.tableWidget.item(r, self.cols.uri).data(Qt.UserRole)

                # project path
                fileA = self.tableWidget.cellWidget(r - 1, self.cols.uri).text()
                fileB = self.tableWidget.cellWidget(r, self.cols.uri).text()
                self.tableWidget.cellWidget(r - 1, self.cols.uri).setText(fileB)
                self.tableWidget.cellWidget(r, self.cols.uri).setText(fileA)
                self.tableWidget.item(r - 1, self.cols.uri).setData(Qt.UserRole, typeB)
                self.tableWidget.item(r, self.cols.uri).setData(Qt.UserRole, typeA)

                # project name
                nameA = self.tableWidget.cellWidget(r - 1, self.cols.name).text()
                nameB = self.tableWidget.cellWidget(r, self.cols.name).text()
                self.tableWidget.cellWidget(r - 1, self.cols.name).setText(nameB)
                self.tableWidget.cellWidget(r, self.cols.name).setText(nameA)

                # project type menu location
                locA = self.tableWidget.cellWidget(
                    r - 1, self.cols.type_menu_location
                ).currentIndex()
                locB = self.tableWidget.cellWidget(
                    r, self.cols.type_menu_location
                ).currentIndex()
                if locB == 2 and r == 1:
                    locB = 0
                self.tableWidget.cellWidget(
                    r - 1, self.cols.type_menu_location
                ).setCurrentIndex(locB)
                self.tableWidget.cellWidget(
                    r, self.cols.type_menu_location
                ).setCurrentIndex(locA)

                # project type storage
                self.tableWidget.setCellWidget(
                    r,
                    self.cols.type_storage,
                    self.mk_prj_storage_icon(typeA),
                )
                self.tableWidget.setCellWidget(
                    r - 1,
                    self.cols.type_storage,
                    self.mk_prj_storage_icon(typeB),
                )

                self.tableWidget.removeCellWidget(r, self.cols.edit)
                self.tableWidget.removeCellWidget(r - 1, self.cols.edit)
                self.addEditButton(r, typeA)
                self.addEditButton(r - 1, typeB)

                # selected row
                self.tableWidget.setCurrentCell(r - 1, 1)
        except Exception as err:
            self.log("Error moving up row {}. Trace: {}".format(r, err))

    def onMoveDown(self):
        sr = self.tableWidget.selectedRanges()
        nbRows = self.tableWidget.rowCount()
        try:
            r = sr[0].topRow()
            if r < nbRows - 1:
                typeA = self.tableWidget.item(r, self.cols.uri).data(Qt.UserRole)
                typeB = self.tableWidget.item(r + 1, self.cols.uri).data(Qt.UserRole)

                # project path
                fileA = self.tableWidget.cellWidget(r, self.cols.uri).text()
                fileB = self.tableWidget.cellWidget(r + 1, self.cols.uri).text()
                self.tableWidget.cellWidget(r, self.cols.uri).setText(fileB)
                self.tableWidget.cellWidget(r + 1, self.cols.uri).setText(fileA)
                self.tableWidget.item(r, self.cols.uri).setData(Qt.UserRole, typeB)
                self.tableWidget.item(r + 1, self.cols.uri).setData(Qt.UserRole, typeA)

                # project name
                nameA = self.tableWidget.cellWidget(r, self.cols.name).text()
                nameB = self.tableWidget.cellWidget(r + 1, self.cols.name).text()
                self.tableWidget.cellWidget(r, self.cols.name).setText(nameB)
                self.tableWidget.cellWidget(r + 1, self.cols.name).setText(nameA)

                # project type menu location
                locA = self.tableWidget.cellWidget(
                    r, self.cols.type_menu_location
                ).currentIndex()
                locB = self.tableWidget.cellWidget(
                    r + 1, self.cols.type_menu_location
                ).currentIndex()
                if locB == 2 and r == 0:
                    locB = 0
                self.tableWidget.cellWidget(
                    r, self.cols.type_menu_location
                ).setCurrentIndex(locB)
                self.tableWidget.cellWidget(
                    r + 1, self.cols.type_menu_location
                ).setCurrentIndex(locA)

                # project type storage
                self.tableWidget.setCellWidget(
                    r,
                    self.cols.type_storage,
                    self.mk_prj_storage_icon(typeB),
                )
                self.tableWidget.setCellWidget(
                    r + 1,
                    self.cols.type_storage,
                    self.mk_prj_storage_icon(typeA),
                )

                self.tableWidget.removeCellWidget(r, self.cols.edit)
                self.tableWidget.removeCellWidget(r + 1, self.cols.edit)
                self.addEditButton(r, typeB)
                self.addEditButton(r + 1, typeA)

                # selected row
                self.tableWidget.setCurrentCell(r + 1, 1)
        except Exception as err:
            self.log("Error moving down row {}. Trace: {}".format(r, err))

    def onTextChanged(self, text: str):
        """Read the project using the URI of the project that changed into the table.

        :param text: project path URI
        :type text: str
        """
        file_widget = self.sender()
        try:
            self.qgs_dom_manager.getQgsDoc(text)
            file_widget.setStyleSheet("color: {};".format("black"))
        except Exception as err:
            self.log("Error during project reading: {}".format(err))
            file_widget.setStyleSheet("color: {};".format("red"))

    def on_mdSource2_released(self):
        myorder = [1, 0, 2]
        self.optionSourceMD = [self.optionSourceMD[i] for i in myorder]
        self.setSourceMdText()

    def on_mdSource3_released(self):
        myorder = [2, 0, 1]
        self.optionSourceMD = [self.optionSourceMD[i] for i in myorder]
        self.setSourceMdText()

    def tableTunning(self):
        """Prettify table aspect"""
        # edit button
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            self.cols.edit, QHeaderView.Fixed
        )
        self.tableWidget.horizontalHeader().resizeSection(self.cols.edit, 20)

        # project name
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            self.cols.name, QHeaderView.Interactive
        )

        # project type
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            self.cols.type_storage, QHeaderView.Fixed
        )
        self.tableWidget.horizontalHeader().resizeSection(self.cols.type_storage, 10)

        # project menu location
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            self.cols.type_menu_location, QHeaderView.Interactive
        )

        # project path
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            self.cols.uri, QHeaderView.Interactive
        )

        # fit to content
        self.tableWidget.resizeColumnToContents(self.cols.name)
        self.tableWidget.resizeColumnToContents(self.cols.type_menu_location)
        self.tableWidget.resizeColumnToContents(self.cols.uri)

    # -- Widgets factory ---------------------------------------------------------------
    def mk_prj_edit_button(self, fileName="edit") -> QToolButton:
        """Returns a tool button for the project edition.

        :return: button
        :rtype: QToolButton
        """
        edit_button = QToolButton(self.tableWidget)
        edit_button.setGeometry(QRect(0, 0, 20, 20))
        edit_button.setIcon(
            QIcon(str(DIR_PLUGIN_ROOT / "resources/{}.svg".format(fileName)))
        )
        edit_button.setToolTip(self.tr("Edit this project"))

        return edit_button

    def mk_prj_storage_icon(self, qgs_type_storage: str) -> QLabel:
        """Returns a QLabel with the matching icon for the storage type.

        :param qgs_type_storage: storage type
        :type qgs_type_storage: str
        :return: QLabel to be set in a cellWidget
        :rtype: QLabel
        """
        lbl_location_type = QLabel(self.tableWidget)
        lbl_location_type.setPixmap(QPixmap(icon_per_storage_type(qgs_type_storage)))
        lbl_location_type.setScaledContents(True)
        lbl_location_type.setMaximumSize(20, 20)
        lbl_location_type.setAlignment(Qt.AlignCenter)
        lbl_location_type.setTextInteractionFlags(Qt.NoTextInteraction)
        lbl_location_type.setToolTip(self.tr(qgs_type_storage))

        return lbl_location_type
