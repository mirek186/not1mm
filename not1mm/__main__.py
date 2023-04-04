#!/usr/bin/env python3
"""
NOT1MM Logger
"""
# pylint: disable=unused-import, c-extension-no-member, no-member, invalid-name

import importlib
import logging
import os
import pkgutil
import re
import socket
import subprocess

# import sqlite3
import sys
import threading
import uuid
from datetime import datetime
from json import dumps, loads
from pathlib import Path
from shutil import copyfile
from xmlrpc.client import Error, ServerProxy

import psutil
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import QPoint  # pylint: disable=no-name-in-module
from PyQt5.QtCore import QDir, QRect, QSize, Qt
from PyQt5.QtGui import QFontDatabase  # pylint: disable=no-name-in-module

from not1mm.lib.cat_interface import CAT
from not1mm.lib.cwinterface import CW
from not1mm.lib.database import DataBase
from not1mm.lib.edit_macro import EditMacro
from not1mm.lib.edit_opon import OpOn
from not1mm.lib.edit_station import EditStation
from not1mm.lib.select_contest import SelectContest
from not1mm.lib.ham_utility import (
    bearing,
    bearing_with_latlon,
    calculate_wpx_prefix,
    distance,
    distance_with_latlon,
    get_logged_band,
    getband,
    reciprocol,
)
from not1mm.lib.lookup import QRZlookup
from not1mm.lib.multicast import Multicast
from not1mm.lib.new_contest import NewContest
from not1mm.lib.n1mm import N1MM
from not1mm.lib.qrz_dialog import UseQRZ
from not1mm.lib.version import __version__

# os.environ["QT_QPA_PLATFORM"] = "wayland"
os.environ["QT_QPA_PLATFORMTHEME"] = "gnome"
# os.environ["QT_STYLE_OVERRIDE"] = "Fusion"

loader = pkgutil.get_loader("not1mm")
WORKING_PATH = os.path.dirname(loader.get_filename())

if "XDG_DATA_HOME" in os.environ:
    DATA_PATH = os.environ.get("XDG_DATA_HOME")
else:
    DATA_PATH = str(Path.home() / ".local" / "share")
DATA_PATH += "/not1mm"
try:
    os.mkdir(DATA_PATH)
except FileExistsError:
    ...

if "XDG_CONFIG_HOME" in os.environ:
    CONFIG_PATH = os.environ.get("XDG_CONFIG_HOME")
else:
    CONFIG_PATH = str(Path.home() / ".config")
CONFIG_PATH += "/not1mm"
try:
    os.mkdir(CONFIG_PATH)
except FileExistsError:
    ...

CTYFILE = {}

with open(WORKING_PATH + "/data/cty.json", "rt", encoding="utf-8") as fd:
    CTYFILE = loads(fd.read())

DARK_STYLESHEET = ""

with open(WORKING_PATH + "/data/Combinear.qss", encoding="utf-8") as stylefile:
    DARK_STYLESHEET = stylefile.read()


def check_process(name: str) -> bool:
    """checks to see if program of name is in the active process list"""
    for proc in psutil.process_iter():
        if len(proc.cmdline()) == 2:
            if name in proc.cmdline()[1]:
                return True
    return False


def cty_lookup(callsign: str):
    """Lookup callsign in cty.dat file"""
    callsign = callsign.upper()
    for count in reversed(range(len(callsign))):
        searchitem = callsign[: count + 1]
        result = {key: val for key, val in CTYFILE.items() if key == searchitem}
        if not result:
            continue
        if result.get(searchitem).get("exact_match"):
            if searchitem == callsign:
                return result
            continue
        return result


class MainWindow(QtWidgets.QMainWindow):
    """
    The main window
    """

    pref_ref = {
        "useqrz": False,
        "lookupusername": "username",
        "lookuppassword": "password",
        "run_state": True,
        "dark_mode": False,
        "command_buttons": False,
        "cw_macros": True,
        "bands_modes": True,
        "window_height": 200,
        "window_width": 600,
        "window_x": 120,
        "window_y": 120,
        "current_database": "ham.db",
        "contest": "",
        "multicast_group": "224.1.1.1",
        "multicast_port": 2239,
        "interface_ip": "0.0.0.0",
        "send_n1mm_packets": False,
        "n1mm_station_name": "20M CW Tent",
        "n1mm_operator": "Bernie",
        "n1mm_ip": "127.0.0.1",
        "n1mm_radioport": 12060,
        "n1mm_contactport": 12061,
        "n1mm_lookupport": 12060,
        "n1mm_scoreport": 12062,
    }
    appstarted = False
    contest = None
    contest_settings = {}
    pref = None
    station = {}
    current_op = ""
    current_mode = ""
    current_band = ""
    look_up = None
    run_state = False
    fkeys = {}
    qrz_dialog = None
    settings_dialog = None
    edit_macro_dialog = None
    contest_dialog = None
    opon_dialog = None
    dbname = DATA_PATH + "/ham.db"
    radio_state = {}
    server_udp = None
    multicast_group = None
    multicast_port = None
    interface_ip = None
    rig_control = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("MainWindow: __init__")

        data_path = WORKING_PATH + "/data/main.ui"
        uic.loadUi(data_path, self)
        self.n1mm = N1MM()
        self.next_field = self.other_2
        self.dupe_indicator.hide()
        self.cw_speed.valueChanged.connect(self.cwspeed_spinbox_changed)

        self.actionCW_Macros.triggered.connect(self.cw_macros_state_changed)
        self.actionCommand_Buttons.triggered.connect(self.command_buttons_state_change)
        self.actionDark_Mode.triggered.connect(self.dark_mode_state_change)
        self.actionLog_Window.triggered.connect(self.launch_log_window)
        self.actionRecalculate_Mults.triggered.connect(self.recalculate_mults)

        self.actionGenerate_Cabrillo.triggered.connect(self.generate_cabrillo)
        self.actionGenerate_ADIF.triggered.connect(self.generate_adif)

        self.actionStationSettings.triggered.connect(self.edit_station_settings)
        self.actionQRZ_Settings.triggered.connect(self.qrz_preference_selected)

        self.actionNew_Contest.triggered.connect(self.new_contest_dialog)
        self.actionOpen_Contest.triggered.connect(self.open_contest)
        self.actionNew_Database.triggered.connect(self.new_database)
        self.actionOpen_Database.triggered.connect(self.open_database)

        self.radioButton_run.clicked.connect(self.run_sp_buttons_clicked)
        self.radioButton_sp.clicked.connect(self.run_sp_buttons_clicked)
        self.score.setText("0")
        self.callsign.textEdited.connect(self.callsign_changed)
        self.callsign.returnPressed.connect(self.save_contact)
        self.sent.returnPressed.connect(self.save_contact)
        self.receive.returnPressed.connect(self.save_contact)
        self.other_1.returnPressed.connect(self.save_contact)
        self.other_2.returnPressed.connect(self.save_contact)
        self.sent.setText("59")
        self.receive.setText("59")
        icon_path = WORKING_PATH + "/data/"
        self.greendot = QtGui.QPixmap(icon_path + "greendot.png")
        self.reddot = QtGui.QPixmap(icon_path + "reddot.png")
        self.leftdot.setPixmap(self.greendot)
        self.rightdot.setPixmap(self.reddot)

        self.F1.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F1.customContextMenuRequested.connect(self.edit_F1)
        self.F1.clicked.connect(self.sendf1)
        self.F2.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F2.customContextMenuRequested.connect(self.edit_F2)
        self.F2.clicked.connect(self.sendf2)
        self.F3.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F3.customContextMenuRequested.connect(self.edit_F3)
        self.F3.clicked.connect(self.sendf3)
        self.F4.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F4.customContextMenuRequested.connect(self.edit_F4)
        self.F4.clicked.connect(self.sendf4)
        self.F5.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F5.customContextMenuRequested.connect(self.edit_F5)
        self.F5.clicked.connect(self.sendf5)
        self.F6.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F6.customContextMenuRequested.connect(self.edit_F6)
        self.F6.clicked.connect(self.sendf6)
        self.F7.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F7.customContextMenuRequested.connect(self.edit_F7)
        self.F7.clicked.connect(self.sendf7)
        self.F8.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F8.customContextMenuRequested.connect(self.edit_F8)
        self.F8.clicked.connect(self.sendf8)
        self.F9.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F9.customContextMenuRequested.connect(self.edit_F9)
        self.F9.clicked.connect(self.sendf9)
        self.F10.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F10.customContextMenuRequested.connect(self.edit_F10)
        self.F10.clicked.connect(self.sendf10)
        self.F11.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F11.customContextMenuRequested.connect(self.edit_F11)
        self.F11.clicked.connect(self.sendf11)
        self.F12.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F12.customContextMenuRequested.connect(self.edit_F12)
        self.F12.clicked.connect(self.sendf12)

        self.readpreferences()
        self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
        self.database = DataBase(self.dbname, WORKING_PATH)
        self.station = self.database.fetch_station()
        if self.station is None:
            self.station = {}
            self.edit_station_settings()
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
        self.contact = self.database.empty_contact
        self.current_op = self.station.get("Call", "")
        if self.pref.get("contest"):
            self.load_contest()

        self.cw = CW(1, "127.0.0.1", 6789)
        # self.cw = CW(2, "127.0.0.1", 8000)

        self.read_cw_macros()
        self.clearinputs()
        # self.launch_log_window()

        self.rig_control = None
        local_flrig = self.check_process("flrig")
        local_rigctld = self.check_process("rigctld")
        if local_flrig:
            logger.debug("Found flrig")
            address, port = "localhost", "12345"
            self.rig_control = CAT("flrig", address, int(port))
        if local_rigctld:
            logger.debug("Found rigctld")
            address, port = "localhost", "4532"
            self.rig_control = CAT("rigctld", address, int(port))

        self.band_indicators_cw = {
            "160": self.cw_band_160,
            "80": self.cw_band_80,
            "40": self.cw_band_40,
            "20": self.cw_band_20,
            "15": self.cw_band_15,
            "10": self.cw_band_10,
        }

        self.band_indicators_ssb = {
            "160": self.ssb_band_160,
            "80": self.ssb_band_80,
            "40": self.ssb_band_40,
            "20": self.ssb_band_20,
            "15": self.ssb_band_15,
            "10": self.ssb_band_10,
        }

        self.band_indicators_rtty = {
            "160": self.rtty_band_160,
            "80": self.rtty_band_80,
            "40": self.rtty_band_40,
            "20": self.rtty_band_20,
            "15": self.rtty_band_15,
            "10": self.rtty_band_10,
        }

        self.all_mode_indicators = {
            "CW": self.band_indicators_cw,
            "SSB": self.band_indicators_ssb,
            "RTTY": self.band_indicators_rtty,
        }

    @staticmethod
    def check_process(name: str) -> bool:
        """checks to see if program of name is in the active process list"""
        for proc in psutil.process_iter():
            if bool(re.match(name, proc.name().lower())):
                return True
        return False

    def new_database(self):
        """Create new database."""
        filename = self.filepicker("new")
        if filename:
            if filename[-3:] != ".db":
                filename += ".db"
            self.pref["current_database"] = filename.split("/")[-1:][0]
            self.write_preference()
            self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
            self.database = DataBase(self.dbname, WORKING_PATH)
            self.contact = self.database.empty_contact
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
            self.current_op = self.station.get("Call", "")
            cmd = {}
            cmd["cmd"] = "NEWDB"
            self.multicast_interface.send_as_json(cmd)
            self.clearinputs()
            self.edit_station_settings()

    def open_database(self):
        """Open existing database."""
        filename = self.filepicker("open")
        if filename:
            self.pref["current_database"] = filename.split("/")[-1:][0]
            self.write_preference()
            self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
            self.database = DataBase(self.dbname, WORKING_PATH)
            self.contact = self.database.empty_contact
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
            if self.station.get("Call", "") == "":
                self.edit_station_settings()
            self.current_op = self.station.get("Call", "")
            cmd = {}
            cmd["cmd"] = "NEWDB"
            self.multicast_interface.send_as_json(cmd)
            self.clearinputs()

    def new_contest(self):
        """Create new contest in existing database."""

    def open_contest(self):
        """Switch to a different existing contest in existing database."""
        logger.debug("Open Contest selected")
        contests = self.database.fetch_all_contests()
        logger.debug("%s", f"{contests}")

        if contests:
            self.contest_dialog = SelectContest(WORKING_PATH)
            self.contest_dialog.contest_list.setRowCount(0)
            self.contest_dialog.contest_list.setColumnCount(4)
            self.contest_dialog.contest_list.verticalHeader().setVisible(False)
            self.contest_dialog.contest_list.setColumnWidth(1, 200)
            self.contest_dialog.contest_list.setColumnWidth(2, 200)
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                0, QtWidgets.QTableWidgetItem("Contest Nr")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                1, QtWidgets.QTableWidgetItem("Contest Name")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                2, QtWidgets.QTableWidgetItem("Contest Start")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                3, QtWidgets.QTableWidgetItem("Not UIsed")
            )
            self.contest_dialog.contest_list.setColumnHidden(0, True)
            self.contest_dialog.contest_list.setColumnHidden(3, True)
            self.contest_dialog.accepted.connect(self.open_contest_return)
            for contest in contests:
                number_of_rows = self.contest_dialog.contest_list.rowCount()
                self.contest_dialog.contest_list.insertRow(number_of_rows)
                contest_id = str(contest.get("ContestID", 1))
                contest_name = contest.get("ContestName", 1)
                start_date = contest.get("StartDate", 1)
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 0, QtWidgets.QTableWidgetItem(contest_id)
                )
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 1, QtWidgets.QTableWidgetItem(contest_name)
                )
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 2, QtWidgets.QTableWidgetItem(start_date)
                )
        self.contest_dialog.show()

    def open_contest_return(self):
        """Called by open_contest"""
        selected_row = self.contest_dialog.contest_list.currentRow()
        contest = self.contest_dialog.contest_list.item(selected_row, 0).text()
        self.pref["contest"] = contest
        logger.debug("Selected contest: %s", f"{contest}")
        self.load_contest()

    def load_contest(self):
        """load a contest"""
        if self.pref.get("contest"):
            self.contest_settings = self.database.fetch_contest_by_id(
                self.pref.get("contest")
            )
            self.database.current_contest = self.pref.get("contest")
            if self.contest_settings.get("ContestName"):
                self.contest = doimp(self.contest_settings.get("ContestName"))
                logger.debug("Loaded Contest Name = %s", self.contest.name)
                self.contest.init_contest(self)

    def filepicker(self, action: str) -> str:
        """
        Get a filename
        action: "new" or "open"
        """
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.DontConfirmOverwrite
        # picker = QFileDialog(self)
        if action == "new":
            file, _ = QFileDialog.getSaveFileName(
                self,
                "Choose a Database",
                DATA_PATH,
                "Database (*.db)",
                options=options,
            )
        if action == "open":
            file, _ = QFileDialog.getOpenFileName(
                self,
                "Choose a Database",
                DATA_PATH,
                "Database (*.db)",
                options=options,
            )
        return file

    def recalculate_mults(self):
        """Recalculate Multipliers"""
        self.contest.recalculate_mults(self)

    def launch_log_window(self):
        """launch the Log Window"""
        if not check_process("logwindow.py"):
            _ = subprocess.Popen([sys.executable, WORKING_PATH + "/logwindow.py"])

    def clear_band_indicators(self):
        """Clear the indicators"""
        for _, indicators in self.all_mode_indicators.items():
            for _, indicator in indicators.items():
                indicator.setFrameShape(QtWidgets.QFrame.NoFrame)

    def set_band_indicator(self, band: str) -> None:
        """Set the band indicator"""
        logger.debug("%s", f"band:{band} mode: {self.current_mode}")
        if band and self.current_mode:
            self.clear_band_indicators()
            indicator = self.all_mode_indicators[self.current_mode].get(band, None)
            if indicator:
                indicator.setFrameShape(QtWidgets.QFrame.Box)

    def closeEvent(self, _event):
        """
        Write window size and position to config file
        """
        self.pref["window_width"] = self.size().width()
        self.pref["window_height"] = self.size().height()
        self.pref["window_x"] = self.pos().x()
        self.pref["window_y"] = self.pos().y()
        self.write_preference()

    def cty_lookup(self, callsign: str):
        """Lookup callsign in cty.dat file"""
        callsign = callsign.upper()
        for count in reversed(range(len(callsign))):
            searchitem = callsign[: count + 1]
            result = {key: val for key, val in CTYFILE.items() if key == searchitem}
            if not result:
                continue
            if result.get(searchitem).get("exact_match"):
                if searchitem == callsign:
                    return result
                continue
            return result

    def cwspeed_spinbox_changed(self):
        """triggered when value of CW speed in the spinbox changes."""
        if self.cw.servertype == 1:
            self.cw.speed = self.cw_speed.value()
            self.cw.sendcw(f"\x1b2{self.cw.speed}")

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        """This overrides Qt key event."""
        modifier = event.modifiers()
        if event.key() == Qt.Key.Key_Escape:  # pylint: disable=no-member
            self.clearinputs()
        if self.cw is not None and modifier == Qt.ControlModifier:
            if self.cw.servertype == 1:
                self.cw.sendcw("\x1b4")
        if event.key() == Qt.Key.Key_PageUp:
            if self.cw is not None:
                if self.cw.servertype == 1:
                    self.cw.speed += 1
                    self.cw_speed.setValue(self.cw.speed)
                    self.cw.sendcw(f"\x1b2{self.cw.speed}")
        if event.key() == Qt.Key.Key_PageDown:
            if self.cw is not None:
                if self.cw.servertype == 1:
                    self.cw.speed -= 1
                    self.cw_speed.setValue(self.cw.speed)
                    self.cw.sendcw(f"\x1b2{self.cw.speed}")
        # if event.key() == Qt.Key.Key_Enter:
        #     self.save_contact()
        if event.key() == Qt.Key.Key_Tab or event.key() == Qt.Key.Key_Backtab:
            if self.sent.hasFocus():
                logger.debug("From sent")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.sent)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.sent)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.receive.hasFocus():
                logger.debug("From receive")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.receive)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.receive)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.other_1.hasFocus():
                logger.debug("From other_1")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.other_1)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.other_1)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.other_2.hasFocus():
                logger.debug("From other_2")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.other_2)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.other_2)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.callsign.hasFocus():
                logger.debug("From callsign")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.callsign)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    text = self.callsign.text()
                    text = text.upper()
                    _thethread = threading.Thread(
                        target=self.check_callsign2,
                        args=(text,),
                        daemon=True,
                    )
                    _thethread.start()
                    next_tab = self.tab_next.get(self.callsign)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
        if event.key() == Qt.Key_F1:
            self.sendf1()
        if event.key() == Qt.Key_F2:
            self.sendf2()
        if event.key() == Qt.Key_F3:
            self.sendf3()
        if event.key() == Qt.Key_F4:
            self.sendf4()
        if event.key() == Qt.Key_F5:
            self.sendf5()
        if event.key() == Qt.Key_F6:
            self.sendf6()
        if event.key() == Qt.Key_F7:
            self.sendf7()
        if event.key() == Qt.Key_F8:
            self.sendf8()
        if event.key() == Qt.Key_F9:
            self.sendf9()
        if event.key() == Qt.Key_F10:
            self.sendf10()
        if event.key() == Qt.Key_F11:
            self.sendf11()
        if event.key() == Qt.Key_F12:
            self.sendf12()

    def set_window_title(self):
        """Set window title"""
        vfoa = self.radio_state.get("vfoa", "")
        if vfoa:
            vfoa = int(vfoa) / 1000
        else:
            vfoa = 0.0
        contest_name = ""
        if self.contest:
            contest_name = self.contest.name
        self.setWindowTitle(
            f"{round(vfoa,2)} "
            f"{self.radio_state.get('mode', '')} "
            f"OP:{self.current_op} {contest_name} "
            f"- Not1MM v{__version__}"
        )

    def clearinputs(self):
        """Clears the text input fields and sets focus to callsign field."""
        self.dupe_indicator.hide()
        self.contact = self.database.empty_contact
        self.heading_distance.setText("No Heading")
        self.dx_entity.setText("dxentity")
        if self.contest:
            mults = self.contest.show_mults(self)
            qsos = self.contest.show_qso(self)
            multstring = f"{qsos}/{mults}"
            self.mults.setText(multstring)
            score = self.contest.calc_score(self)
            self.score.setText(str(score))
        self.callsign.clear()
        if self.current_mode == "CW":
            self.sent.setText("599")
            self.receive.setText("599")
        else:
            self.sent.setText("59")
            self.receive.setText("59")
        self.other_1.clear()
        self.other_2.clear()
        self.callsign.setFocus()
        cmd = {}
        cmd["cmd"] = "CALLCHANGED"
        cmd["call"] = ""
        self.multicast_interface.send_as_json(cmd)

    def save_contact(self):
        """Save to db"""
        logger.debug("saving")
        if len(self.callsign.text()) < 3:
            return
        if not any(char.isdigit() for char in self.callsign.text()):
            return
        if not any(char.isalpha() for char in self.callsign.text()):
            return

        self.contact["TS"] = datetime.utcnow().isoformat(" ")[:19]
        self.contact["Call"] = self.callsign.text()
        self.contact["Freq"] = round(float(self.radio_state.get("vfoa", 0.0)) / 1000, 2)
        self.contact["QSXFreq"] = round(
            float(self.radio_state.get("vfoa", 0.0)) / 1000, 2
        )
        self.contact["Mode"] = self.radio_state.get("mode", "")
        self.contact["ContestName"] = self.contest.cabrillo_name
        self.contact["ContestNR"] = self.pref.get("contest", "0")
        self.contact["StationPrefix"] = self.station.get("Call", "")
        self.contact["WPXPrefix"] = calculate_wpx_prefix(self.callsign.text())
        self.contact["IsRunQSO"] = self.radioButton_run.isChecked()
        self.contact["Operator"] = self.current_op
        self.contact["NetBiosName"] = socket.gethostname()
        self.contact["IsOriginal"] = 1
        self.contact["ID"] = uuid.uuid4().hex
        self.contest.set_contact_vars(self)
        self.contact["Points"] = self.contest.points(self)
        debug_output = f"{self.contact}"
        logger.debug(debug_output)
        self.database.log_contact(self.contact)
        self.n1mm.send_contact_info()
        self.clearinputs()
        cmd = {}
        cmd["cmd"] = "UPDATELOG"
        self.multicast_interface.send_as_json(cmd)
        # self.contact["ContestName"] = self.contest.name
        # self.contact["SNT"] = self.sent.text()
        # self.contact["RCV"] = self.receive.text()
        # self.contact["CountryPrefix"]
        # self.contact["StationPrefix"] = self.pref.get("callsign", "")
        # self.contact["QTH"]
        # self.contact["Name"] = self.other_1.text()
        # self.contact["Comment"] = self.other_2.text()
        # self.contact["NR"]
        # self.contact["Sect"]
        # self.contact["Prec"]
        # self.contact["CK"]
        # self.contact["ZN"]
        # self.contact["SentNr"]
        # self.contact["Points"]
        # self.contact["IsMultiplier1"]
        # self.contact["IsMultiplier2"]
        # self.contact["Power"]
        # self.contact["Band"]
        # self.contact["WPXPrefix"] = calculate_wpx_prefix(self.callsign.text())
        # self.contact["Exchange1"]
        # self.contact["RadioNR"]
        # self.contact["isMultiplier3"]
        # self.contact["MiscText"]
        # self.contact["ContactType"]
        # self.contact["Run1Run2"]
        # self.contact["GridSquare"]
        # self.contact["Continent"]
        # self.contact["RoverLocation"]
        # self.contact["RadioInterfaced"]
        # self.contact["NetworkedCompNr"]
        # self.contact["CLAIMEDQSO"]

    def qrz_preference_selected(self):
        """Show QRZ settings dialog"""
        logger.debug("QRZ preference selected")
        self.qrz_dialog = UseQRZ(WORKING_PATH)
        self.qrz_dialog.accepted.connect(self.save_qrz_settings)
        if self.pref.get("dark_mode"):
            self.qrz_dialog.setStyleSheet(DARK_STYLESHEET)
        self.qrz_dialog.useqrz.setChecked(self.pref.get("useqrz", False))
        self.qrz_dialog.username.setText(self.pref.get("lookupusername", ""))
        self.qrz_dialog.password.setText(self.pref.get("lookuppassword", ""))
        self.qrz_dialog.open()

    def save_qrz_settings(self):
        """Save QRZ settings"""
        self.pref["useqrz"] = self.qrz_dialog.useqrz.isChecked()
        self.pref["lookupusername"] = self.qrz_dialog.username.text()
        self.pref["lookuppassword"] = self.qrz_dialog.password.text()
        self.qrz_dialog.close()
        self.write_preference()
        self.readpreferences()

    def new_contest_dialog(self):
        """Show new contest dialog"""
        logger.debug("New contest Dialog")
        self.contest_dialog = NewContest(WORKING_PATH)
        self.contest_dialog.accepted.connect(self.save_contest)
        if self.pref.get("dark_mode"):
            self.contest_dialog.setStyleSheet(DARK_STYLESHEET)
        self.contest_dialog.dateTimeEdit.setDate(QtCore.QDate.currentDate())
        self.contest_dialog.dateTimeEdit.setCalendarPopup(True)
        self.contest_dialog.dateTimeEdit.setTime(QtCore.QTime(0, 0))
        self.contest_dialog.power.setCurrentText("LOW")
        self.contest_dialog.station.setCurrentText("FIXED")
        self.contest_dialog.open()

    def save_contest(self):
        """Save Contest"""
        next_number = self.database.get_next_contest_nr()
        contest = {}
        contest["ContestName"] = (
            self.contest_dialog.contest.currentText().lower().replace(" ", "_")
        )
        contest["StartDate"] = self.contest_dialog.dateTimeEdit.dateTime().toString(
            "yyyy-MM-dd hh:mm:ss"
        )
        contest["OperatorCategory"] = self.contest_dialog.operator_class.currentText()
        contest["BandCategory"] = self.contest_dialog.band.currentText()
        contest["PowerCategory"] = self.contest_dialog.power.currentText()
        contest["ModeCategory"] = self.contest_dialog.mode.currentText()
        contest["OverlayCategory"] = self.contest_dialog.overlay.currentText()
        # contest['ClaimedScore'] = self.contest_dialog.
        contest["Operators"] = self.contest_dialog.operators.text()
        contest["Soapbox"] = self.contest_dialog.soapbox.toPlainText()
        contest["SentExchange"] = self.contest_dialog.exchange.text()
        contest["ContestNR"] = next_number.get("count", 1)
        self.pref["contest"] = next_number.get("count", 1)
        # contest['SubType'] = self.contest_dialog.
        contest["StationCategory"] = self.contest_dialog.station.currentText()
        contest["AssistedCategory"] = self.contest_dialog.assisted.currentText()
        contest["TransmitterCategory"] = self.contest_dialog.transmitter.currentText()
        # contest['TimeCategory'] = self.contest_dialog.
        logger.debug("%s", f"{contest}")
        self.database.add_contest(contest)
        self.write_preference()
        self.load_contest()

    def edit_station_settings(self):
        """Show settings dialog"""
        logger.debug("Station Settings selected")
        self.settings_dialog = EditStation(WORKING_PATH)
        self.settings_dialog.accepted.connect(self.save_settings)
        # if self.pref.get("dark_mode"):
        #     self.settings_dialog.setStyleSheet(DARK_STYLESHEET)

        self.settings_dialog.Call.setText(self.station.get("Call", ""))
        self.settings_dialog.Name.setText(self.station.get("Name", ""))
        self.settings_dialog.Address1.setText(self.station.get("Street1", ""))
        self.settings_dialog.Address2.setText(self.station.get("Street2", ""))
        self.settings_dialog.City.setText(self.station.get("City", ""))
        self.settings_dialog.State.setText(self.station.get("State", ""))
        self.settings_dialog.Zip.setText(self.station.get("Zip", ""))
        self.settings_dialog.Country.setText(self.station.get("Country", ""))
        self.settings_dialog.GridSquare.setText(self.station.get("GridSquare", ""))
        self.settings_dialog.CQZone.setText(str(self.station.get("CQZone", "")))
        self.settings_dialog.ITUZone.setText(str(self.station.get("IARUZone", "")))
        self.settings_dialog.License.setText(self.station.get("LicenseClass", ""))
        self.settings_dialog.Latitude.setText(str(self.station.get("Latitude", "")))
        self.settings_dialog.Longitude.setText(str(self.station.get("Longitude", "")))
        self.settings_dialog.StationTXRX.setText(self.station.get("stationtxrx", ""))
        self.settings_dialog.Power.setText(self.station.get("SPowe", ""))
        self.settings_dialog.Antenna.setText(self.station.get("SAnte", ""))
        self.settings_dialog.AntHeight.setText(self.station.get("SAntH1", ""))
        self.settings_dialog.ASL.setText(self.station.get("SAntH2", ""))
        self.settings_dialog.ARRLSection.setText(self.station.get("ARRLSection", ""))
        self.settings_dialog.RoverQTH.setText(self.station.get("RoverQTH", ""))
        self.settings_dialog.Club.setText(self.station.get("Club", ""))
        self.settings_dialog.Email.setText(self.station.get("Email", ""))
        self.settings_dialog.open()

    def save_settings(self):
        """Save settings"""
        cs = self.settings_dialog.Call.text()
        self.station = {}
        self.station["Call"] = cs.upper()
        self.station["Name"] = self.settings_dialog.Name.text().title()
        self.station["Street1"] = self.settings_dialog.Address1.text().title()
        self.station["Street2"] = self.settings_dialog.Address2.text().title()
        self.station["City"] = self.settings_dialog.City.text().title()
        self.station["State"] = self.settings_dialog.State.text().upper()
        self.station["Zip"] = self.settings_dialog.Zip.text()
        self.station["Country"] = self.settings_dialog.Country.text().title()
        self.station["GridSquare"] = self.settings_dialog.GridSquare.text()
        self.station["CQZone"] = self.settings_dialog.CQZone.text()
        self.station["IARUZone"] = self.settings_dialog.ITUZone.text()
        self.station["LicenseClass"] = self.settings_dialog.License.text().title()
        self.station["Latitude"] = self.settings_dialog.Latitude.text()
        self.station["Longitude"] = self.settings_dialog.Longitude.text()
        self.station["STXeq"] = self.settings_dialog.StationTXRX.text()
        self.station["SPowe"] = self.settings_dialog.Power.text()
        self.station["SAnte"] = self.settings_dialog.Antenna.text()
        self.station["SAntH1"] = self.settings_dialog.AntHeight.text()
        self.station["SAntH2"] = self.settings_dialog.ASL.text()
        self.station["ARRLSection"] = self.settings_dialog.ARRLSection.text().upper()
        self.station["RoverQTH"] = self.settings_dialog.RoverQTH.text()
        self.station["Club"] = self.settings_dialog.Club.text().title()
        self.station["Email"] = self.settings_dialog.Email.text()
        self.database.add_station(self.station)
        self.settings_dialog.close()
        if self.current_op == "":
            self.current_op = self.station.get("Call", "")
        contest_count = self.database.fetch_all_contests()
        if len(contest_count) == 0:
            self.new_contest_dialog()

    def edit_macro(self, function_key):
        """Show edit macro dialog"""
        self.edit_macro_dialog = EditMacro(function_key, WORKING_PATH)
        self.edit_macro_dialog.accepted.connect(self.edited_macro)
        if self.pref.get("dark_mode"):
            self.edit_macro_dialog.setStyleSheet(DARK_STYLESHEET)
        self.edit_macro_dialog.open()

    def edited_macro(self):
        """Save edited macro"""
        self.edit_macro_dialog.function_key.setText(
            self.edit_macro_dialog.macro_label.text()
        )
        self.edit_macro_dialog.function_key.setToolTip(
            self.edit_macro_dialog.the_macro.text()
        )
        self.edit_macro_dialog.close()
        # logger.debug(f"{self.current_op}")

    def edit_F1(self):
        """stub"""
        logger.debug("F1 Right Clicked.")
        self.edit_macro(self.F1)

    def edit_F2(self):
        """stub"""
        logger.debug("F2 Right Clicked.")
        self.edit_macro(self.F2)

    def edit_F3(self):
        """stub"""
        logger.debug("F3 Right Clicked.")
        self.edit_macro(self.F3)

    def edit_F4(self):
        """stub"""
        logger.debug("F4 Right Clicked.")
        self.edit_macro(self.F4)

    def edit_F5(self):
        """stub"""
        logger.debug("F5 Right Clicked.")
        self.edit_macro(self.F5)

    def edit_F6(self):
        """stub"""
        logger.debug("F6 Right Clicked.")
        self.edit_macro(self.F6)

    def edit_F7(self):
        """stub"""
        logger.debug("F7 Right Clicked.")
        self.edit_macro(self.F7)

    def edit_F8(self):
        """stub"""
        logger.debug("F8 Right Clicked.")
        self.edit_macro(self.F8)

    def edit_F9(self):
        """stub"""
        logger.debug("F9 Right Clicked.")
        self.edit_macro(self.F9)

    def edit_F10(self):
        """stub"""
        logger.debug("F10 Right Clicked.")
        self.edit_macro(self.F10)

    def edit_F11(self):
        """stub"""
        logger.debug("F11 Right Clicked.")
        self.edit_macro(self.F11)

    def edit_F12(self):
        """stub"""
        logger.debug("F12 Right Clicked.")
        self.edit_macro(self.F12)

    def process_macro(self, macro: str) -> str:
        """Process CW macro substitutions"""
        macro = macro.upper()
        macro = macro.replace("{MYCALL}", self.station.get("Call"))
        macro = macro.replace("{HISCALL}", self.callsign.text())
        return macro

    def sendf1(self):
        """stub"""
        logger.debug("F1 Clicked")
        if self.cw:
            # if self.preference.get("send_n1mm_packets"):
            #     self.n1mm.radio_info["FunctionKeyCaption"] = self.F1.text()
            self.cw.sendcw(self.process_macro(self.F1.toolTip()))

    def sendf2(self):
        """stub"""
        logger.debug("F2 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F2.toolTip()))

    def sendf3(self):
        """stub"""
        logger.debug("F3 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F3.toolTip()))

    def sendf4(self):
        """stub"""
        logger.debug("F4 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F4.toolTip()))

    def sendf5(self):
        """stub"""
        logger.debug("F5 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F5.toolTip()))

    def sendf6(self):
        """stub"""
        logger.debug("F6 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F6.toolTip()))

    def sendf7(self):
        """stub"""
        logger.debug("F7 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F7.toolTip()))

    def sendf8(self):
        """stub"""
        logger.debug("F8 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F8.toolTip()))

    def sendf9(self):
        """stub"""
        logger.debug("F9 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F9.toolTip()))

    def sendf10(self):
        """stub"""
        logger.debug("F10 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F10.toolTip()))

    def sendf11(self):
        """stub"""
        logger.debug("F11 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F11.toolTip()))

    def sendf12(self):
        """stub"""
        logger.debug("F12 Clicked")
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F12.toolTip()))

    def run_sp_buttons_clicked(self):
        """Handle run/s&p mode"""
        self.pref["run_state"] = self.radioButton_run.isChecked()
        self.write_preference()
        self.read_cw_macros()

    def write_preference(self):
        """
        Write preferences to json file.
        """
        try:
            with open(
                CONFIG_PATH + "/not1mm.json", "wt", encoding="utf-8"
            ) as file_descriptor:
                file_descriptor.write(dumps(self.pref, indent=4))
                logger.info("writing: %s", self.pref)
        except IOError as exception:
            logger.critical("writepreferences: %s", exception)

    def readpreferences(self):
        """
        Restore preferences if they exist, otherwise create some sane defaults.
        """
        try:
            if os.path.exists(CONFIG_PATH + "/not1mm.json"):
                with open(
                    CONFIG_PATH + "/not1mm.json", "rt", encoding="utf-8"
                ) as file_descriptor:
                    self.pref = loads(file_descriptor.read())
                    logger.info("%s", self.pref)
            else:
                logger.info("No preference file. Writing preference.")
                with open(
                    CONFIG_PATH + "/not1mm.json", "wt", encoding="utf-8"
                ) as file_descriptor:
                    self.pref = self.pref_ref.copy()
                    file_descriptor.write(dumps(self.pref, indent=4))
                    logger.info("%s", self.pref)
        except IOError as exception:
            logger.critical("Error: %s", exception)
        if self.pref.get("useqrz"):
            self.look_up = QRZlookup(
                self.pref.get("lookupusername"),
                self.pref.get("lookuppassword"),
            )
        else:
            self.look_up = None
        if self.pref.get("run_state"):
            self.radioButton_run.setChecked(True)
        else:
            self.radioButton_sp.setChecked(True)

        if self.pref.get("dark_mode"):
            self.actionDark_Mode.setChecked(True)
        else:
            self.actionDark_Mode.setChecked(False)

        if self.pref.get("command_buttons"):
            self.actionCommand_Buttons.setChecked(True)
        else:
            self.actionCommand_Buttons.setChecked(False)

        if self.pref.get("cw_macros"):
            self.actionCW_Macros.setChecked(True)
        else:
            self.actionCW_Macros.setChecked(False)

        if self.pref.get("bands_modes"):
            self.actionMode_and_Bands.setChecked(True)
        else:
            self.actionMode_and_Bands.setChecked(False)

        multicast_group = self.pref.get("multicast_group", "224.1.1.1")
        multicast_port = self.pref.get("multicast_port", 2239)
        interface_ip = self.pref.get("interface_ip", "0.0.0.0")
        self.multicast_interface = Multicast(
            multicast_group, multicast_port, interface_ip
        )

        self.dark_mode()
        self.show_command_buttons()
        self.show_CW_macros()
        # self.show_band_mode()

    def dark_mode_state_change(self):
        """darkmode dropdown checkmark changed"""
        self.pref["dark_mode"] = self.actionDark_Mode.isChecked()
        self.write_preference()
        self.dark_mode()

    def dark_mode(self):
        """change display mode"""
        if self.pref.get("dark_mode"):
            self.setStyleSheet(DARK_STYLESHEET)
        else:
            self.setStyleSheet("")

    def cw_macros_state_changed(self):
        """Menu item to show/hide macro buttons"""
        self.pref["cw_macros"] = self.actionCW_Macros.isChecked()
        self.write_preference()
        self.show_CW_macros()

    def show_CW_macros(self):
        """macro button state change"""
        if self.pref.get("cw_macros"):
            self.Button_Row1.show()
            self.Button_Row2.show()
        else:
            self.Button_Row1.hide()
            self.Button_Row2.hide()

    def command_buttons_state_change(self):
        """Menu item to show/hide command buttons"""
        self.pref["command_buttons"] = self.actionCommand_Buttons.isChecked()
        self.write_preference()
        self.show_command_buttons()

    def show_command_buttons(self):
        """command button state change"""
        if self.pref.get("command_buttons"):
            self.Command_Buttons.show()
        else:
            self.Command_Buttons.hide()

    # def show_band_mode_state_change(self):
    #     """Called when the mode and bads menu item changes"""
    #     self.pref["bands_modes"] = self.actionMode_and_Bands.isChecked()
    #     self.write_preference()
    #     self.show_band_mode()

    # def show_band_mode(self):
    #     """Hide or show band/mode indicator"""
    #     if self.actionMode_and_Bands.isChecked():
    #         self.Band_Mode_Frame.show()
    #     else:
    #         self.Band_Mode_Frame.hide()

    def is_floatable(self, item: str) -> bool:
        """check to see if string can be a float"""
        if item.isnumeric():
            return True
        try:
            _test = float(item)
        except ValueError:
            return False
        return True

    def callsign_changed(self):
        """Called when text in the callsign field has changed"""
        text = self.callsign.text()
        text = text.upper()
        position = self.callsign.cursorPosition()
        stripped_text = text.strip().replace(" ", "")
        self.callsign.setText(stripped_text)
        self.callsign.setCursorPosition(position)

        if " " in text:
            if stripped_text == "CW":
                self.setmode("CW")
                self.radio_state["mode"] = "CW"
                if self.rig_control:
                    if self.rig_control.online:
                        self.rig_control.set_mode("CW")
                self.set_window_title()
                self.clearinputs()
                return
            if stripped_text == "RTTY":
                self.setmode("RTTY")
                if self.rig_control:
                    if self.rig_control.online:
                        self.rig_control.set_mode("RTTY")
                    else:
                        self.radio_state["mode"] = "RTTY"
                self.set_window_title()
                self.clearinputs()
                return
            if stripped_text == "SSB":
                self.setmode("SSB")
                if int(self.radio_state.get("vfoa", 0)) > 10000000:
                    self.radio_state["mode"] = "USB"
                else:
                    self.radio_state["mode"] = "LSB"
                self.set_window_title()
                if self.rig_control:
                    self.rig_control.set_mode(self.radio_state.get("mode"))
                self.clearinputs()
                return
            if stripped_text == "OPON":
                self.get_opon()
                self.clearinputs()
                return
            if self.is_floatable(stripped_text):
                vfo = float(stripped_text)
                vfo = int(vfo * 1000)
                band = getband(str(vfo))
                self.set_band_indicator(band)
                # self.contact["Band"] = get_logged_band(str(self.radio_state.get("vfoa", 0.0)))
                self.radio_state["vfoa"] = vfo
                self.set_window_title()
                self.clearinputs()
                if self.rig_control:
                    self.rig_control.set_vfo(vfo)
                return

            self.check_callsign(stripped_text)
            if self.check_dupe(stripped_text):
                self.dupe_indicator.show()
            else:
                self.dupe_indicator.hide()
            _thethread = threading.Thread(
                target=self.check_callsign2,
                args=(text,),
                daemon=True,
            )
            _thethread.start()
            self.next_field.setFocus()
            return
        cmd = {}
        cmd["cmd"] = "CALLCHANGED"
        cmd["call"] = stripped_text
        self.multicast_interface.send_as_json(cmd)
        self.check_callsign(stripped_text)

    def check_callsign(self, callsign):
        """Check call as entered"""
        result = cty_lookup(callsign)
        debug_result = f"{result}"
        logger.debug("%s", debug_result)
        if result:
            for a in result.items():
                entity = a[1].get("entity", "")
                cq = a[1].get("cq", "")
                itu = a[1].get("itu", "")
                continent = a[1].get("continent")
                lat = float(a[1].get("lat", "0.0"))
                lon = float(a[1].get("long", "0.0"))
                lon = lon * -1  # cty.dat file inverts longitudes
                primary_pfx = a[1].get("primary_pfx", "")
                heading = bearing_with_latlon(self.station.get("GridSquare"), lat, lon)
                kilometers = distance_with_latlon(
                    self.station.get("GridSquare"), lat, lon
                )
                self.heading_distance.setText(
                    f"Regional Hdg {heading}° LP {reciprocol(heading)}° / "
                    f"distance {int(kilometers*0.621371)}mi {kilometers}km"
                )
                self.contact["CountryPrefix"] = primary_pfx
                self.contact["ZN"] = int(cq)
                self.contact["Continent"] = continent
                self.dx_entity.setText(
                    f"{primary_pfx}: {continent}/{entity} cq:{cq} itu:{itu}"
                )
                if len(callsign) > 2:
                    self.contest.prefill(self)

    def check_callsign2(self, callsign):
        """Check call once entered"""
        callsign = callsign.strip()
        debug_lookup = f"{self.look_up}"
        logger.debug("%s, %s", callsign, debug_lookup)
        if hasattr(self.look_up, "session"):
            if self.look_up.session:
                response = self.look_up.lookup(callsign)
                debug_response = f"{response}"
                logger.debug("The Response: %s\n", debug_response)
                if response:
                    theirgrid = response.get("grid")
                    self.contact["GridSquare"] = theirgrid
                    _theircountry = response.get("country")
                    if self.station.get("GridSquare", ""):
                        heading = bearing(self.station.get("GridSquare", ""), theirgrid)
                        kilometers = distance(self.station.get("GridSquare"), theirgrid)
                        self.heading_distance.setText(
                            f"{theirgrid} Hdg {heading}° LP {reciprocol(heading)}° / "
                            f"distance {int(kilometers*0.621371)}mi {kilometers}km"
                        )
                    # self.dx_entity.setText(f"{theircountry}")
                # else:
                # self.heading_distance.setText("Lookup failed.")

    def check_dupe(self, call: str) -> bool:
        """Checks if a callsign is a dupe on current band/mode."""
        band = float(get_logged_band(str(self.radio_state.get("vfoa", 0.0))))
        mode = self.radio_state.get("mode", "")
        debugline = (
            f"Call: {call} Band: {band} Mode: {mode} Dupetype: {self.contest.dupe_type}"
        )
        logger.debug("%s", debugline)
        if self.contest.dupe_type == 1:
            result = self.database.check_dupe(call)
        if self.contest.dupe_type == 2:
            result = self.database.check_dupe_on_band(call, band)
        if self.contest.dupe_type == 3:
            result = self.database.check_dupe_on_band_mode(call, band, mode)
        if self.contest.dupe_type == 4:
            result = {"isdupe": False}
        debugline = f"{result}"
        logger.debug("%s", debugline)
        return result.get("isdupe", False)

    def setmode(self, mode: str) -> None:
        """stub for when the mode changes."""
        if mode == "CW":
            self.current_mode = "CW"
            # self.mode.setText("CW")
            self.sent.setText("599")
            self.receive.setText("599")
            return
        if mode == "SSB":
            self.current_mode = "SSB"
            # self.mode.setText("SSB")
            self.sent.setText("59")
            self.receive.setText("59")
        if mode == "RTTY":
            self.current_mode = "RTTY"
            # self.mode.setText("RTTY")
            self.sent.setText("59")
            self.receive.setText("59")

    def get_opon(self):
        """Ctrl+O or OPON dialog"""
        self.opon_dialog = OpOn(WORKING_PATH)
        self.opon_dialog.accepted.connect(self.new_op)
        self.opon_dialog.open()

    def new_op(self):
        """Save new OP"""
        if self.opon_dialog.NewOperator.text():
            self.current_op = self.opon_dialog.NewOperator.text().upper()

        self.opon_dialog.close()
        logger.debug("New Op: %s", self.current_op)

    def poll_radio(self):
        """stub"""
        if self.rig_control:
            if self.rig_control.online:
                vfo = self.rig_control.get_vfo()
                mode = self.rig_control.get_mode()
                if mode == "CW":
                    self.setmode(mode)
                if mode == "LSB" or mode == "USB":
                    self.setmode("SSB")
                if mode == "RTTY":
                    self.setmode("RTTY")
                self.radio_state["vfoa"] = vfo
                band = getband(str(vfo))
                self.contact["Band"] = get_logged_band(str(vfo))
                self.set_band_indicator(band)
                self.radio_state["mode"] = mode
                # logger.debug("VFO: %s  MODE: %s", vfo, mode)
                self.set_window_title()

    def read_cw_macros(self) -> None:
        """
        Reads in the CW macros, firsts it checks to see if the file exists. If it does not,
        and this has been packaged with pyinstaller it will copy the default file from the
        temp directory this is running from... In theory.
        """

        if not Path(DATA_PATH + "/cwmacros.txt").exists():
            logger.debug("read_cw_macros: copying default macro file.")
            copyfile(WORKING_PATH + "/data/cwmacros.txt", DATA_PATH + "/cwmacros.txt")
        with open(
            DATA_PATH + "/cwmacros.txt", "r", encoding="utf-8"
        ) as file_descriptor:
            for line in file_descriptor:
                try:
                    mode, fkey, buttonname, cwtext = line.split("|")
                    if mode.strip().upper() == "R" and self.pref.get("run_state"):
                        self.fkeys[fkey.strip()] = (buttonname.strip(), cwtext.strip())
                    if mode.strip().upper() != "R" and not self.pref.get("run_state"):
                        self.fkeys[fkey.strip()] = (buttonname.strip(), cwtext.strip())
                except ValueError as err:
                    logger.info("read_cw_macros: %s", err)
        keys = self.fkeys.keys()
        if "F1" in keys:
            self.F1.setText(f"F1: {self.fkeys['F1'][0]}")
            self.F1.setToolTip(self.fkeys["F1"][1])
        if "F2" in keys:
            self.F2.setText(f"F2: {self.fkeys['F2'][0]}")
            self.F2.setToolTip(self.fkeys["F2"][1])
        if "F3" in keys:
            self.F3.setText(f"F3: {self.fkeys['F3'][0]}")
            self.F3.setToolTip(self.fkeys["F3"][1])
        if "F4" in keys:
            self.F4.setText(f"F4: {self.fkeys['F4'][0]}")
            self.F4.setToolTip(self.fkeys["F4"][1])
        if "F5" in keys:
            self.F5.setText(f"F5: {self.fkeys['F5'][0]}")
            self.F5.setToolTip(self.fkeys["F5"][1])
        if "F6" in keys:
            self.F6.setText(f"F6: {self.fkeys['F6'][0]}")
            self.F6.setToolTip(self.fkeys["F6"][1])
        if "F7" in keys:
            self.F7.setText(f"F7: {self.fkeys['F7'][0]}")
            self.F7.setToolTip(self.fkeys["F7"][1])
        if "F8" in keys:
            self.F8.setText(f"F8: {self.fkeys['F8'][0]}")
            self.F8.setToolTip(self.fkeys["F8"][1])
        if "F9" in keys:
            self.F9.setText(f"F9: {self.fkeys['F9'][0]}")
            self.F9.setToolTip(self.fkeys["F9"][1])
        if "F10" in keys:
            self.F10.setText(f"F10: {self.fkeys['F10'][0]}")
            self.F10.setToolTip(self.fkeys["F10"][1])
        if "F11" in keys:
            self.F11.setText(f"F11: {self.fkeys['F11'][0]}")
            self.F11.setToolTip(self.fkeys["F11"][1])
        if "F12" in keys:
            self.F12.setText(f"F12: {self.fkeys['F12'][0]}")
            self.F12.setToolTip(self.fkeys["F12"][1])

    def generate_adif(self):
        """Generate ADIF"""
        logger.debug("******ADIF*****")
        self.contest.adif(self)

    def generate_cabrillo(self):
        """Generates Cabrillo file. Maybe."""
        # https://www.cqwpx.com/cabrillo.htm
        logger.debug("******Cabrillo*****")
        self.contest.cabrillo(self)


def load_fonts_from_dir(directory: str) -> set:
    """
    Well it loads fonts from a directory...
    """
    font_families = set()
    for _fi in QDir(directory).entryInfoList(["*.ttf", "*.woff", "*.woff2"]):
        _id = QFontDatabase.addApplicationFont(_fi.absoluteFilePath())
        font_families |= set(QFontDatabase.applicationFontFamilies(_id))
    return font_families


def install_icons():
    """Install icons"""
    os.system(
        "xdg-icon-resource install --size 32 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-32.png k6gte-not1mm"
    )
    os.system(
        "xdg-icon-resource install --size 64 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-64.png k6gte-not1mm"
    )
    os.system(
        "xdg-icon-resource install --size 128 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-128.png k6gte-not1mm"
    )
    os.system(f"xdg-desktop-menu install {WORKING_PATH}/data/k6gte-not1mm.desktop")


def doimp(modname):
    """return module path"""
    return importlib.import_module(f"not1mm.plugins.{modname}")


def run():
    """
    Main Entry
    """

    install_icons()
    timer.start(1000)

    sys.exit(app.exec())


logger = logging.getLogger("__main__")
handler = logging.StreamHandler()
formatter = logging.Formatter(
    datefmt="%H:%M:%S",
    fmt="[%(asctime)s] %(levelname)s %(module)s - %(funcName)s Line %(lineno)d:\n%(message)s",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

if Path("./debug").exists():
    logger.setLevel(logging.DEBUG)
    logger.debug("debugging on")
else:
    logger.setLevel(logging.WARNING)
    logger.warning("debugging off")

app = QtWidgets.QApplication(sys.argv)
font_path = WORKING_PATH + "/data"
families = load_fonts_from_dir(os.fspath(font_path))
logger.info(families)
window = MainWindow()
height = window.pref.get("window_height", 300)
width = window.pref.get("window_width", 700)
x = window.pref.get("window_x", -1)
y = window.pref.get("window_y", -1)
window.setGeometry(x, y, width, height)
window.setWindowTitle(f"Not1MM v{__version__}")
window.callsign.setFocus()
window.show()
timer = QtCore.QTimer()
timer.timeout.connect(window.poll_radio)


if __name__ == "__main__":
    run()
