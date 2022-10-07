#!/usr/bin/python3
#
#           SPO2 Viewer
#   Written by Kevin Williams - 2022
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import sys
import time
import numpy
import serial
import serial.tools.list_ports
import logging
import pyqtgraph as pg
from scipy.signal import savgol_filter
from PyQt5 import QtWidgets, QtCore, QtWidgets, QtGui
from webbrowser import Error as wb_error
from webbrowser import open as wb_open

# manual includes to fix occasional compile problem
from pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5 import *
from pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5 import *
from pyqtgraph.imageview.ImageViewTemplate_pyqt5 import *
from pyqtgraph.console.template_pyqt5 import *

# local includes
import log_system
import debug
from spo2 import SPO2
from resource_path import resource_path
from spo2_window import Ui_MainWindow
from license import Ui_license_window

VERSION = "0.0.5"
LOG_LEVEL = logging.DEBUG

# Same for license window
class LicenseWindow(QtWidgets.QDialog, Ui_license_window):
    """License dialog box window."""
    def __init__(self, *args, **kwargs):
        super(LicenseWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)
        self.setWindowIcon(QtGui.QIcon(':/icon/icon.png'))

class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)
        self.setWindowTitle(f"SPO2 Viewer - v{VERSION}")
        self.setWindowIcon(QtGui.QIcon(':/icon/icon.png'))
        self.license_window = LicenseWindow()

        # Create SPO2 object
        self._spo2 = SPO2('cal.json', 3500)

        # latest capture
        self.current_capture: tuple = (0, 0)

        # Running timer for captures
        self.capture_timer_qt = QtCore.QElapsedTimer()

        # Capture timer
        self.capture_timer = QtCore.QTimer()
        self.capture_timer.timeout.connect(self.do_update)
        self.capture_rate_ms = 0

        # graph timer
        self.graph_timer = QtCore.QTimer()
        self.graph_timer.timeout.connect(self.draw_graphs)
        self.graph_frame_rate = 30
        self.graph_timer_ms = int(1 / (self.graph_frame_rate / 1000))

        # serial object
        self.ser: serial.Serial = serial.Serial(baudrate = 115200, timeout = 1, write_timeout = 1)

        # connect buttons to methods
        self.button_refresh.clicked.connect(self.ser_com_refresh)
        self.button_connect.clicked.connect(self.connect_toggle)
        self.button_capture.clicked.connect(self.start_stop_toggle)
        self.button_update.clicked.connect(self.read_calb_table)
        self.button_reload.clicked.connect(self.update_calb)
        self.button_add_row.clicked.connect(self.add_row)
        self.actionLicense.triggered.connect(self.ui_show_license)  
        self.actionQuit.triggered.connect(sys.exit)
        self.actionGet_Source_Code.triggered.connect(self.open_source_code_webpage)

        # graph properties
        self.graph.disableAutoRange()
        self.graph.showGrid(True, True, alpha = 0.5)
        self.graph_padding_factor = 0.667
        self.green_pen = pg.mkPen('g', width = 2)
        self.red_pen = pg.mkPen('r', width = 2)

        # do initial comport refresh and graph clear
        self.button_capture.setDisabled(True)
        self.ser_com_refresh()
        self.graph_reset()
        self.update_calb()

    def do_update(self):
        period_end = False
        if self.ser_get_input():
            period_end = self._spo2.add_data(self.current_capture, self.capture_timer_qt.elapsed())
        if period_end:
            self.lcd_r.display(self._spo2.r_inst)
            self.lcd_r_avg.display(self._spo2.r_average)
            self.lcd_spo2.display(self._spo2.spo2)
            self.lcd_heart.display(self._spo2.heart_rate)
            self.ui_statusbar_message(f"Samples per second: {self._spo2.samples_per_second}")
            self.graph.enableAutoRange()
            self.graph.disableAutoRange()

    def graph_reset(self):
        self.draw_r_curve()
        self.graph.clear()
        self.curve_ir  = self.graph.plot(numpy.arange(self._spo2.max_readings), self._spo2.history_ir, pen = self.green_pen, skipFiniteCheck = True)
        self.curve_red = self.graph.plot(numpy.arange(self._spo2.max_readings), self._spo2.history_red, pen = self.red_pen, skipFiniteCheck = True)

    def draw_graphs(self):
        ir_dat = savgol_filter(
            self._spo2.history_ir,
            window_length = 199,
            polyorder = 5,
            mode = 'interp',
            )[25:self._spo2.max_readings - 25]
        red_dat = savgol_filter(
            self._spo2.history_red,
            window_length = 199,
            polyorder = 5,
            mode = 'interp',
            )[25:self._spo2.max_readings - 25]
        self.curve_ir.setData(numpy.arange(ir_dat.size), ir_dat, skipFiniteCheck = True)
        self.curve_red.setData(numpy.arange(red_dat.size), red_dat, skipFiniteCheck = True)

    def draw_r_curve(self):
        self.graph_2.clear()
        self.graph_2.plot(self._spo2.cal_table_r, self._spo2.cal_table_spo2)

    def start_stop_toggle(self):
        if not self.capture_timer.isActive():
            self.capture_timer.start(self.capture_rate_ms)
            self.graph_timer.start(self.graph_timer_ms)
            self.button_capture.setText("Stop Capture")
            logging.debug("CAPTURE START")
        else:
            self.capture_timer.stop()
            self.graph_timer.stop()
            self.button_capture.setText("Start Capture")
            logging.debug("CAPTURE STOP")

    def connect_toggle(self) -> None:
        """
        Connect/Disconnect from the serial device selected in the dropdown menu.\n
        This function should be called from the UI.
        """

        if not self.ser.isOpen():
            logging.debug("Starting connection to device.")
            if self.ser_com_connect():
                self.button_refresh.setDisabled(True)
                self.button_capture.setDisabled(False)
                self.button_connect.setText("Disconnect")
                self._spo2.reset()
        else:
            logging.debug("Disconnecting serial device.")
            if self.capture_timer.isActive():
                self.start_stop_toggle()
            try:
                self.ser.close()
            except OSError as err_msg:
                # On sudden disconnect, this may throw a OSError 
                # For now, delete and reinstantiate the serial object
                logging.error(err_msg)
                del self.ser
                self.ser = serial.Serial(baudrate = 115200, timeout = 1, write_timeout = 1)
            self.button_refresh.setDisabled(False)
            self.button_capture.setDisabled(True)
            self.button_connect.setText("Connect")
            self.ser_com_refresh()
            self.ui_statusbar_message("Disconnected.")

    def ser_get_input(self) -> tuple:

        # send character to Arduino to trigger the Arduino to begin a analogRead capture
        try:
            self.ser.write('\n'.encode())
        except Exception as e:
            logging.warn(f"Device write error: {e}")
            self.start_stop_toggle()
            self.connect_toggle()
            err_msg = f"Connection to Arduino lost. \nPlease check cable and click connect.\n\nError information:\n{e}"
            self.ui_display_error_message("Connection Error", err_msg)
            raise  
        
        # get response from Arduino, terminated by newline character
        buf = ''
        try:
            # read and discard incoming bytes until the start character is found
            while self.ser.inWaiting() > 0:
                chr = str(self.ser.read().decode())
                if chr == '$':
                    break

            # read characters until newline is detected, this is faster than serial's read_until
            while self.ser.inWaiting() > 0:
                chr = str(self.ser.read().decode())
                if chr == '\n':
                    break
                buf = buf + chr
        # disconnecting during inWaiting() may throw this
        except OSError as err_msg:
            logging.warn(err_msg)
            return False
        # this may occur during str conversion if the device is disconnected abrutply
        except UnicodeDecodeError as err_msg:
            logging.warn(err_msg)
            return False

        # we should expect 7 bytes of information in the format: NNN,NNN
        if len(buf) != 7:
            return False
        try:
            ir, red = buf.split(',')
            self.current_capture = (int(ir), int(red))
        except:
            return False
        return True

    # refresh available devices, store in dropdown menu storage
    def ser_com_refresh(self):
        """
        Refreshes the list of available serial devices.\n
        Results are stored in the dropdown menu.\n
        Uses addItem to store the device string.
        """

        self.port_combo_box.clear()
        available_ports = serial.tools.list_ports.comports()
        for device in available_ports:
            d_name = device.device + ": " + device.description
            self.port_combo_box.addItem(d_name, device.device)
            logging.info(f"Detected port: {d_name}")

    @debug.debug_timer
    def ser_com_connect(self) -> bool:
        """
        Connect/Disconnect from the serial device selected in the devices dropdown menu.\n
        Returns True if the connection was sucessful.\n
        False if the connection was unsucessful.
        """

        # fetch port name from dropdown menu
        try:
            current_index = self.port_combo_box.currentIndex()
            com_port = self.port_combo_box.itemData(current_index)
            if not com_port:
                raise ValueError
        except ValueError:
            self.ui_statusbar_message('No device selected!')
            return False
        except TypeError as e:
            self.ui_display_error_message("Invalid port type", e)
            logging.error(e)
            return False

        # connect to port
        try:
            self.ser.port = com_port
            self.ser.open()
        except serial.serialutil.SerialException as e:
            self.ui_display_error_message("Connection Failure", e)
            logging.warning(f"Connection Failure: {e}")
            return False

        # detect if device is responding properly
        if not self.ser_check_device():
            logging.info(f"Serial device check failed: {self.ser.port}")
            self.ui_display_error_message("Device Error", "Connected device is not responding.\n\nThis may be the incorrect device. Please choose a different device in the menu and try again.")
            self.ser.close()
            return False

        # device is connected and test has passed
        logging.info(f"Connection to {com_port} succesful.")
        self.ui_statusbar_message(f"Connected to {com_port}.")
        return True

    @debug.debug_timer
    def ser_check_device(self) -> bool:
        """
        Checks to see if the Arduino is responding the way we expect.\n
        Returns True if device is responding properly.\n
        Returns False if device is not responding or is giving improper responses.
        """

        self.ui_statusbar_message('Connecting...')
        max_attempts = 10
        device_ok = False
        while max_attempts > 0 and not device_ok:
            try:
                self.ser.write('\n'.encode())
                self.ser.flush()
                while self.ser.inWaiting() > 0:
                    c = str(self.ser.read().decode())
                    if c == '$':
                        device_ok = True
                        break
            except Exception as e:
                logging.debug(f"Retrying connection: {e}")
                time.sleep(1)
            max_attempts -= 1
            time.sleep(0.2)
        return device_ok

    # temporary callback for the UI slots
    def _callback_placeholder(self):
        raise NotImplementedError

    def ui_statusbar_message(self, msg: str) -> None:
        """Display a message in the status bar."""
        self.statusBar.showMessage(str(msg))

    def ui_display_error_message(self, title: str, msg: str) -> None:
        """Display a generic error message to the user."""
        error_message = QtWidgets.QMessageBox()
        error_message.setWindowTitle(title)
        error_message.setText(str(msg))
        error_message.exec_()

    def ui_show_license(self):
        """Shows the License dialog window"""
        self.license_window.show()

    def update_calb(self):
        
        # plot data: x, y values
        self.graph.showGrid(True, True)
        self.graph_2.showGrid(True, True)
        self.draw_r_curve()
        
        # populate table
        self.tableWidget.setRowCount(len(self._spo2.cal_table_r))
        for i, v in enumerate(self._spo2.cal_table_r):
            item = QtWidgets.QTableWidgetItem()
            item.setText(f"{v}")
            self.tableWidget.setItem(i, 0, item)
        for i, v in enumerate(self._spo2.cal_table_spo2):    
            item = QtWidgets.QTableWidgetItem()
            item.setText(f"{v}")
            self.tableWidget.setItem(i, 1, item)        

    def add_row(self):
        self.tableWidget.setRowCount(self.tableWidget.rowCount() + 1)
        self.tableWidget.setCurrentCell(self.tableWidget.rowCount() - 1, 0)
        self.tableWidget.scrollToBottom()

    def read_calb_table(self):
        self.tableWidget.sortItems(0)
        r_val = []
        spo2_val = []
        for i in range(self.tableWidget.rowCount()):
            try:
                r_val.append(float(self.tableWidget.item(i, 0).text()))
                spo2_val.append(int(self.tableWidget.item(i, 1).text()))
            except Exception as e:
                print("Empty row")
                print(e)
        print(r_val)
        print(spo2_val)
        self._spo2.cal_table_r = r_val
        self._spo2.cal_table_spo2 = spo2_val
        self.update_calb()
        self._spo2.save_cal()

    def open_source_code_webpage(self):
        """
        Opens a link to the project source code.
        """
        try:
            wb_open("https://github.com/HTM-Workshop/DIY-SPO2", autoraise = True)
        except wb_error as error:
            error_msg = "Could not open URL.\n\n" + error
            logging.warning(error_msg)
            self.ui_display_error_message("Open URL Error", error_msg)

def main():
    log_system.init_logging(LOG_LEVEL)
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()