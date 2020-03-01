import atexit
import math
import sys
import time

import threading

import PyQt5
from PyQt5 import QtCore, QtGui, uic, QtWidgets
import os

from PyQt5.QtCore import pyqtSignal
import matplotlib.pyplot as plt
from scipy.misc import imresize

from matplotlib.offsetbox import OffsetImage, AnnotationBbox

import SerialThread
import MapBox
import RocketData
from RocketData import RocketData as RD
import mplwidget  # DO NOT REMOVE pyinstller needs this

if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    PyQt5.QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    PyQt5.QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

if getattr(sys, 'frozen', False):
    local = os.path.dirname(sys.executable)
elif __file__:
    local = os.path.dirname(__file__)

qtCreatorFile = os.path.join(local, "main.ui")

Ui_MainWindow, QtBaseClass = uic.loadUiType(qtCreatorFile)

TILES = 14


class MainApp(QtWidgets.QMainWindow, Ui_MainWindow):
    sig_send = pyqtSignal(str)

    def __init__(self, connection):
        self.data = RD()
        atexit.register(self.exit_handler)

        self.zoom = 20
        self.radius = 0.1

        self.lock = threading.Lock()
        self.lastgps = time.time()
        self.lastMapUpdate = time.time()
        self.latitude = None
        self.longitude = None
        self.lastLatitude = None
        self.lastLongitude = None
        self.x = None
        self.y = None

        QtWidgets.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        self.sendButton.clicked.connect(self.sendButtonPressed)
        self.commandEdit.returnPressed.connect(self.sendButtonPressed)
        self.actionSave.triggered.connect(self.data.save)

        self.StatusButton.clicked.connect(lambda _: self.sendCommand("status"))
        self.ArmButton.clicked.connect(lambda _: self.sendCommand("arm"))
        self.HaloButton.clicked.connect(lambda _: self.sendCommand("halo"))

        markerpath = os.path.join(local, "marker.png")
        # TODO: imresize removed in latest scipy since it's a duplicate from "Pillow". Update and replace.
        self.marker = imresize(plt.imread(markerpath), (12, 12))
        # self.plotMap(51.852667, -111.646972, self.radius, self.zoom)
        # self.plotMap(49.266430, -123.252162, self.radius, self.zoom)

        idSet = set(RocketData.chartoname.keys())
        self.printToConsole("Starting Connection")
        self.SThread = SerialThread.SThread(connection, idSet)
        self.SThread.sig_received.connect(self.receiveData)
        self.sig_send.connect(self.SThread.queueMessage)
        self.SThread.sig_print.connect(self.printToConsole)
        self.SThread.start()

        thread = threading.Thread(target=self.threadLoop, daemon=True)
        thread.start()

    def receiveData(self, bytes):  # TODO: ARE WE SURE THIS IS THREAD SAFE? USE QUEUE OR PUT IN SERIAL THREAD
        self.data.addpoint(bytes)

        latitude = self.data.lastvalue("Latitude")
        longitude = self.data.lastvalue("Longitude")

        nonezero = lambda x: 0 if x is None else x
        accel = math.sqrt(nonezero(self.data.lastvalue("Acceleration X")) ** 2 +
                          nonezero(self.data.lastvalue("Acceleration Y")) ** 2 +
                          nonezero(self.data.lastvalue("Acceleration Z")) ** 2)

        self.AltitudeLabel.setText(str(self.data.lastvalue("Calculated Altitude")))
        self.MaxAltitudeLabel.setText(str(self.data.highest_altitude))
        self.GpsLabel.setText(str(latitude) + ", " + str(longitude))
        self.StateLabel.setText(str(self.data.lastvalue("State")))
        self.PressureLabel.setText(str(self.data.lastvalue("Pressure")))
        self.AccelerationLabel.setText(str(accel))

        self.latitude = latitude
        self.longitude = longitude

        # if time.time() - self.lastMapUpdate > 5:
        #     self.plotMap(latitude, longitude)  # Uncomment to make map recenter
        #     self.lastMapUpdate = time.time()
        #     self.lastLatitude = latitude
        #     self.lastLongitude = longitude
        # # self.plotMap(latitude, longitude) #Uncomment to make map recenter
        #
        # newtime = time.time()
        # if newtime - self.lastgps >= 3:
        #     self.updateMark(latitude, longitude)
        # self.lastgps = newtime

    def sendButtonPressed(self):
        word = self.commandEdit.text()
        self.sendCommand(word)
        self.commandEdit.setText("")

    def printToConsole(self, text):
        self.consoleText.setPlainText(self.consoleText.toPlainText() + text + "\n")
        self.consoleText.moveCursor(QtGui.QTextCursor.End)

    def sendCommand(self, command):
        self.printToConsole(command)
        self.sig_send.emit(command)

    def plotMap(self, latitude, longitude):
        p = MapBox.MapPoint(latitude, longitude)

        with self.lock:
            if longitude is None or latitude is None or p.x == self.x and p.y == self.y:
                return

        lat1 = latitude + self.radius / 110.574
        lon1 = longitude - self.radius / 111.320 / math.cos(lat1 * math.pi / 180.0)
        p1 = MapBox.MapPoint(lat1, lon1)

        lat2 = latitude - self.radius / 110.574
        lon2 = longitude + self.radius / 111.320 / math.cos(lat2 * math.pi / 180.0)
        p2 = MapBox.MapPoint(lat2, lon2)

        # Create MapPoints that correspond to corners of a square area (of side length 2*radius) surrounding the
        # inputted latitude and longitude.

        location = MapBox.TileGrid(p1, p2, self.zoom)
        location.downloadArrayImages()

        img = location.genStichedMap()

        self.plotWidget.canvas.ax.set_axis_off()
        self.plotWidget.canvas.ax.set_ylim(location.height * MapBox.TILE_SIZE, 0)
        self.plotWidget.canvas.ax.set_xlim(0, location.width * MapBox.TILE_SIZE)

        self.plotWidget.canvas.fig.tight_layout(pad=0, w_pad=0, h_pad=0)
        self.plotWidget.canvas.ax.imshow(img)

        self.plotWidget.canvas.draw()

        with self.lock:
            self.x = p.x
            self.y = p.y

    def updateMark(self, latitude, longitude):
        if longitude is None or latitude is None:
            return

        children = self.plotWidget.canvas.ax.get_children()
        for c in children:
            if isinstance(c, AnnotationBbox):
                c.remove()

        p = MapBox.MapPoint(latitude, longitude)

        lat1 = latitude + self.radius / 110.574
        lon1 = longitude - self.radius / 111.320 / math.cos(lat1 * math.pi / 180.0)
        p1 = MapBox.MapPoint(lat1, lon1)

        lat2 = latitude - self.radius / 110.574
        lon2 = longitude + self.radius / 111.320 / math.cos(lat2 * math.pi / 180.0)
        p2 = MapBox.MapPoint(lat2, lon2)

        location = MapBox.TileGrid(p1, p2, self.zoom)

        x = (p.x - location.xMin)/(location.xMax - location.xMin)
        y = (p.y - location.yMin)/(location.yMax - location.yMin)

        mark = (x * MapBox.TILE_SIZE * len(location.ta[0]), y * MapBox.TILE_SIZE * len(location.ta))

        ab = AnnotationBbox(OffsetImage(self.marker), mark, frameon=False)

        self.plotWidget.canvas.ax.add_artist(ab)
        self.plotWidget.canvas.draw()

    def threadLoop(self):
        while True:
            with self.lock:
                lat = self.latitude
                lon = self.longitude
                lastLat = self.lastLatitude
                lastLon = self.lastLongitude
                lmu = self.lastMapUpdate

            if (time.time() - lmu > 5) and not (lat is None or lon is None):
                if lastLat is None or lastLon is None:
                    self.plotMap(lat, lon)
                    lastLat = lat
                    lastLon = lon
                    lmu = time.time()
                else:
                    if (abs(lat - lastLat) >= self.radius / 110.574) or (abs(lon - lastLon) >= self.radius / 111.320 / math.cos(lat * math.pi / 180.0)):
                        self.plotMap(lat, lon)
                        lastLat = lat
                        lastLon = lon
                        lmu = time.time()

            with self.lock:
                self.lastLatitude = lastLat
                self.lastLongitude = lastLon
                self.lastMapUpdate = lmu
                lgps = self.lastgps

            if time.time() - lgps >= 1:
                self.updateMark(self.latitude, self.longitude)
                lgps = time.time()

            with self.lock:
                self.lastgps = lgps


    def exit_handler(self):
        print("Saving...")
        self.data.save()
        print("Saved!")