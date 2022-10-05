#!/usr/bin/python
from PyQt5 import QtWidgets, uic, QtCore, QtWidgets
from pyqtgraph import PlotWidget
import pyqtgraph as pg
import statistics as stat
import sys, os, math, serial, time, numpy
import serial.tools.list_ports
from spo2 import *

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        #Load the UI Page
        uic.loadUi('spo2_window.ui', self)

        # capture timer
        self.capture_timer = QtCore.QTimer()
        self.capture_timer.timeout.connect(self.get_input)

        # heart rate timer
        self.hr_timer = QtCore.QTimer()
        self.hr_timer.timeout.connect(self.update_hr)
        self.capture_rate_ms = 40

        # SPO2 timer
        self.spo2_timer = QtCore.QTimer()
        self.spo2_timer.timeout.connect(self.update_spo2)

        # connect buttons to methods
        self.button_refresh.clicked.connect(self.com_refresh)
        self.button_connect.clicked.connect(self.com_connect)
        self.button_capture.clicked.connect(self.start_stop_toggle)
        self.button_update.clicked.connect(self.read_calb_table)
        self.button_reload.clicked.connect(self.update_calb)
        self.button_add_row.clicked.connect(self.add_row)
        self.button_save.clicked.connect(self.save_calb)
        
        
        # SPO2 singleton
        self.SPO2 = SPO2()
        self.is_running = False

        # connection status
        self.ser = None
        self.com_port = ''

        # perform initial com port check
        self.button_capture.setDisabled(True)
        self.com_refresh()
        self.statusBar.showMessage('No device connected')

        # update calibration display
        self.update_calb()
        self.button_update.setEnabled(True)
        self.button_save.setEnabled(False)
            
    def com_refresh(self):
        self.port_combo_box.clear()
        self.available_ports = serial.tools.list_ports.comports()
        for i in self.available_ports:
            self.port_combo_box.addItem(i.device)  
        com_count = self.port_combo_box.count()
    def com_connect(self):
        if(self.ser == None):
            try:
                self.com_port = self.port_combo_box.currentText()
                if(self.com_port == ''):
                    self.statusBar.showMessage('No device selected!')
                    return
                self.ser = serial.Serial(self.com_port, 115200)
                self.button_refresh.setDisabled(True)
                self.button_capture.setDisabled(False)
                self.button_connect.setText("Disconnect")
                self.statusBar.showMessage("Connected to " + self.com_port)
                time.sleep(3)
                self.ser.flushInput()
        # re-add the try and uncomment below later
            except Exception as e:
                error_message = QtWidgets.QMessageBox()
                error_message.setWindowTitle("Connection Error")
                error_message.setText(str(e))
                error_message.exec_()
                print(e)
        else:
            self.capture_timer.stop()
            self.ser.close()
            self.ser = None
            self.button_refresh.setDisabled(False)
            self.button_connect.setText("Connect")
            self.statusBar.showMessage('No device connected')
            self.button_capture.setDisabled(True)

    # Send a value to the Arduino to trigger it to do a measurement
    def get_input(self):
        self.ser.write('\n'.encode())
        buf = ''
        while(self.ser.inWaiting() > 0):
            buf = buf + str(self.ser.read().decode())
        try:
            buf = buf.strip('\n').strip('\r')
            buf = buf.split(',')
            self.SPO2.add_reading([float(buf[0]), float(buf[1])])
        except:
            pass    # if there's a false reading, just ignore it
        if(len(self.SPO2.raw_red) and len(self.SPO2.raw_ir)):
            self.draw_graphs()
    def draw_graphs(self):
        red_pen = pg.mkPen('r')
        ir_pen = pg.mkPen('g')
        self.SPO2.calc_r()
        self.lcd_r.display(self.SPO2.r_value)
        self.lcd_r_avg.display(self.SPO2.calc_r_avg())
        self.graph.clear()
        self.graph.plot([*range(len(self.SPO2.raw_red))], self.SPO2.raw_red, pen = red_pen)
        self.graph.plot([*range(len(self.SPO2.raw_ir))], self.SPO2.raw_ir, pen = ir_pen)
    def draw_r_curve(self):
        self.graph_2.clear()
        self.graph_2.plot(self.SPO2.calb_r, self.SPO2.calb_spo2)
    def start_stop_toggle(self):
        if(self.is_running == False):
            self.capture_timer.start(self.capture_rate_ms)
            self.hr_timer.start(1000)
            self.spo2_timer.start(1000)
            self.is_running = True
            self.button_capture.setText("Stop Capture")
        else:
            self.capture_timer.stop()
            self.hr_timer.stop()
            self.spo2_timer.stop()
            self.ser.flushInput()
            self.is_running = False
            self.button_capture.setText("Capture")
            self.SPO2.dump_all()
    def update_hr(self):
        self.SPO2.detect_heart_rate(self.capture_rate_ms)
        if(self.SPO2.heart_rate < 300):
            self.lcd_heart.display(self.SPO2.heart_rate)
    def update_spo2(self):
        self.lcd_spo2.display(self.SPO2.calc_spo2())
    def update_calb(self):
        
        # plot data: x, y values
        self.graph.showGrid(True, True)
        self.graph_2.showGrid(True, True)
        self.draw_r_curve()
        
        # populate table
        self.tableWidget.setRowCount(len(self.SPO2.calb_r))
        for i, v in enumerate(self.SPO2.calb_r):
            item = QtWidgets.QTableWidgetItem()
            item.setText(str(v))
            self.tableWidget.setItem(i, 0, item)
        for i, v in enumerate(self.SPO2.calb_spo2):    
            item = QtWidgets.QTableWidgetItem()
            item.setText(str(v))
            self.tableWidget.setItem(i, 1, item)        
        self.button_save.setEnabled(True)
    def read_calb_table(self):
        self.tableWidget.sortItems(0)
        count = self.tableWidget.rowCount()
        r_val = list()
        spo2_val = list()
        print(count)
        for i in range(count):
            try:
                r_val.append(float(self.tableWidget.item(i, 0).text()))
                spo2_val.append(int(self.tableWidget.item(i, 1).text()))
            except Exception as e:
                print("Empty row")
                print(e)
        print(r_val)
        print(spo2_val)
        self.SPO2.calb_r = r_val
        self.SPO2.calb_spo2 = spo2_val
        self.update_calb()
    def add_row(self):
        self.tableWidget.setRowCount(self.tableWidget.rowCount() + 1)
    def save_calb(self):
        self.SPO2.save_file()
        self.message_window('''Calibration table saved. To restore default values
delete the r_curve.pkl file in this program's directory.''')
        self.button_save.setEnabled(False)
    def message_window(self, string):
        message = QtWidgets.QMessageBox()
        message.setWindowTitle('Message')
        message.setText(string)
        message.exec_()

def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()






