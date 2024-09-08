"""WSJTX General plugin"""

# pylint: disable=invalid-name, unused-argument, unused-variable, c-extension-no-member

import datetime
import logging

from pathlib import Path
from PyQt6 import QtWidgets

from not1mm.lib.ham_utility import get_logged_band
from not1mm.lib.plugin_common import gen_adif, get_points
from not1mm.lib.version import __version__

logger = logging.getLogger(__name__)

ALTEREGO = None

EXCHANGE_HINT = "1D ORG"

name = "WSJTX General"
mode = "BOTH"  # CW SSB BOTH RTTY
cabrillo_name = "WSJTX-General"

columns = [0, 1, 2, 3, 4, 16, 17]
columns = [
    "YYYY-MM-DD HH:MM:SS",
    "Call",
    "Freq",
    "Snt",
    "Rcv",
    "Name",
    "Comment",
]


advance_on_space = [True, True, True, True, True]

# 1 once per contest, 2 work each band, 3 each band/mode, 4 no dupe checking
dupe_type = 3

logger.debug("Inside plugin: {0}".format(name))

def init_contest(self):
    """setup plugin"""
    set_tab_next(self)
    set_tab_prev(self)
    interface(self)
    self.next_field = self.other_1


def interface(self):
    """Setup user interface"""
    self.field1.show()
    self.field2.show()
    self.field3.show()
    self.field4.show()
    self.snt_label.setText("SNT")
    self.field1.setAccessibleName("RST Sent")
    label = self.field3.findChild(QtWidgets.QLabel)
    label.setText("Name")
    self.field3.setAccessibleName("Name")
    label = self.field4.findChild(QtWidgets.QLabel)
    label.setText("Comment")
    self.field4.setAccessibleName("Comment")

#    """Setup user interface"""
#    self.field1.hide()
#    self.field2.hide()
#    self.field3.show()
#    self.field4.show()
#    label = self.field3.findChild(QtWidgets.QLabel)
#    label.setText("Class")
#    self.field3.setAccessibleName("Class")
#    label = self.field4.findChild(QtWidgets.QLabel)
#    label.setText("Section")
#    self.field4.setAccessibleName("Section")


def reset_label(self):
    """reset label after field cleared"""

def set_tab_next(self):
    """Set TAB Advances"""
    self.tab_next = {
        self.callsign: self.field1.findChild(QtWidgets.QLineEdit),
        self.field1.findChild(QtWidgets.QLineEdit): self.field2.findChild(
            QtWidgets.QLineEdit
        ),
        self.field2.findChild(QtWidgets.QLineEdit): self.field3.findChild(
            QtWidgets.QLineEdit
        ),
        self.field3.findChild(QtWidgets.QLineEdit): self.field4.findChild(
            QtWidgets.QLineEdit
        ),
        self.field4.findChild(QtWidgets.QLineEdit): self.callsign,
    }


def set_tab_prev(self):
    """Set TAB Advances"""
    self.tab_prev = {
        self.callsign: self.field4.findChild(QtWidgets.QLineEdit),
        self.field1.findChild(QtWidgets.QLineEdit): self.callsign,
        self.field2.findChild(QtWidgets.QLineEdit): self.field1.findChild(
            QtWidgets.QLineEdit
        ),
        self.field3.findChild(QtWidgets.QLineEdit): self.field2.findChild(
            QtWidgets.QLineEdit
        ),
        self.field4.findChild(QtWidgets.QLineEdit): self.field3.findChild(
            QtWidgets.QLineEdit
        ),
    }

#def set_tab_next(self):
#    """Set TAB Advances"""
#    self.tab_next = {
#        self.callsign: self.field3.findChild(QtWidgets.QLineEdit),
#        self.field1.findChild(QtWidgets.QLineEdit): self.field3.findChild(
#            QtWidgets.QLineEdit
#        ),
#        self.field2.findChild(QtWidgets.QLineEdit): self.field3.findChild(
#            QtWidgets.QLineEdit
#        ),
#        self.field3.findChild(QtWidgets.QLineEdit): self.field4.findChild(
#            QtWidgets.QLineEdit
#        ),
#        self.field4.findChild(QtWidgets.QLineEdit): self.callsign,
#    }
#
#
#def set_tab_prev(self):
#    """Set TAB Advances"""
#    self.tab_prev = {
#        self.callsign: self.field4.findChild(QtWidgets.QLineEdit),
#        self.field1.findChild(QtWidgets.QLineEdit): self.callsign,
#        self.field2.findChild(QtWidgets.QLineEdit): self.callsign,
#        self.field3.findChild(QtWidgets.QLineEdit): self.callsign,
#        self.field4.findChild(QtWidgets.QLineEdit): self.field3.findChild(
#            QtWidgets.QLineEdit
#        ),
#    }
#
def set_contact_vars(self):
    """Contest Specific"""
    self.contact["SNT"] = self.sent.text()
    self.contact["RCV"] = self.receive.text()
    self.contact["Name"] = self.other_1.text()
    self.contact["Comment"] = self.other_2.text()

#def set_contact_vars(self):
#    """Contest Specific"""
#    self.contact["SNT"] = self.sent.text()
#    self.contact["RCV"] = self.receive.text()
#    self.contact["Exchange1"] = self.other_1.text().upper()
#    self.contact["Sect"] = self.other_2.text().upper()
#

def predupe(self):
    """called after callsign entered"""


def prefill(self):
    """Fill SentNR"""


def points(self):
    """Calc point"""
    _mode = self.contact.get("Mode", "")
    if _mode in "SSB, USB, LSB, FM, AM":
        return 1
    if _mode in "CW, RTTY, FT8":
        return 2
    return 0


def show_mults(self):
    """Return display string for mults"""
    result = self.database.get_unique_band_and_mode()
    if result:
        return int(result.get("mult", 0))
    return 0


def show_qso(self):
    """Return qso count"""
    result = self.database.fetch_qso_count()
    if result:
        return int(result.get("qsos", 0))
    return 0


def calc_score(self):
    """Return calculated score"""
    _points = get_points(self)
    _mults = show_mults(self)
    return _points * _mults


def adif(self):
    """Call the generate ADIF function"""
    gen_adif(self, cabrillo_name, "ARRL-FIELD-DAY")


def cabrillo(self):
    """Generates Cabrillo file. Maybe."""
    # https://www.cqwpx.com/cabrillo.htm

def recalculate_mults(self):
    """Recalculates multipliers after change in logged qso."""


def set_self(the_outie):
    """..."""
    globals()["ALTEREGO"] = the_outie


def ft8_handler(the_packet: dict):
    """Process FT8 QSO packets
    FT8
    {
        'CALL': 'KE0OG',
        'GRIDSQUARE': 'DM10AT',
        'MODE': 'FT8',
        'RST_SENT': '',
        'RST_RCVD': '',
        'QSO_DATE': '20210329',
        'TIME_ON': '183213',
        'QSO_DATE_OFF': '20210329',
        'TIME_OFF': '183213',
        'BAND': '20M',
        'FREQ': '14.074754',
        'STATION_CALLSIGN': 'K6GTE',
        'MY_GRIDSQUARE': 'DM13AT',
        'CONTEST_ID': 'ARRL-FIELD-DAY',
        'SRX_STRING': '1D UT',
        'CLASS': '1D',
        'ARRL_SECT': 'UT'
    }
    FlDigi
    {
            'FREQ': '7.029500',
            'CALL': 'DL2DSL',
            'MODE': 'RTTY',
            'NAME': 'BOB',
            'QSO_DATE': '20240904',
            'QSO_DATE_OFF': '20240904',
            'TIME_OFF': '212825',
            'TIME_ON': '212800',
            'RST_RCVD': '599',
            'RST_SENT': '599',
            'BAND': '40M',
            'COUNTRY': 'FED. REP. OF GERMANY',
            'CQZ': '14',
            'STX': '000',
            'STX_STRING': '1D ORG',
            'CLASS': '1D',
            'ARRL_SECT': 'DX',
            'TX_PWR': '0',
            'OPERATOR': 'K6GTE',
            'STATION_CALLSIGN': 'K6GTE',
            'MY_GRIDSQUARE': 'DM13AT',
            'MY_CITY': 'ANAHEIM, CA',
            'MY_STATE': 'CA'
        }

    """
    logger.debug("INSIDE THE HANDLER WITH PARSED PACKET: {0}".format(the_packet))

    if ALTEREGO is not None:
        ALTEREGO.callsign.setText(the_packet.get("CALL"))
        ALTEREGO.contact["Call"] = the_packet.get("CALL", "")
        ALTEREGO.contact["SNT"] = the_packet.get("RST_SENT", "")
        ALTEREGO.contact["RCV"] = the_packet.get("RST_RCVD", "")
        ALTEREGO.contact["Name"] = the_packet.get("NAME", "MISSING")
        ALTEREGO.contact["Comment"] = the_packet.get("EMAIL", "MISSING")
        ALTEREGO.contact["Mode"] = the_packet.get("MODE", "ERR")
        ALTEREGO.contact["Freq"] = round(float(the_packet.get("FREQ", "0.0")) * 1000, 2)
        ALTEREGO.contact["QSXFreq"] = round(
            float(the_packet.get("FREQ", "0.0")) * 1000, 2
        )
        ALTEREGO.contact["Band"] = get_logged_band(
            str(int(float(the_packet.get("FREQ", "0.0")) * 1000000))
        )
        ALTEREGO.other_1.setText(the_packet.get("NAME", "MISSING 2"))
        ALTEREGO.other_2.setText(the_packet.get("EMAIL", "MISSING 2"))
        ALTEREGO.save_contact()
