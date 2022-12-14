#!/usr/bin/env python

import sys
import yaml
import dotmap
import datetime
import zoneinfo
import numpy as np

from typing import Tuple, Type, Optional

from astropy import units as u
from astropy.coordinates import EarthLocation

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from matchers import StarMatcher, Fitter
from projections import Projection, EquidistantProjection, BorovickaProjection

from main_ui import Ui_MainWindow

from amos import AMOS, Station

mpl.use('Qt5Agg')

COUNT = 100




class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.param_widgets = [
            (self.dsb_x0, 'x0'), (self.dsb_y0, 'y0'), (self.dsb_a0, 'a0'), (self.dsb_A, 'A'), (self.dsb_F, 'F'),
            (self.dsb_V, 'V'), (self.dsb_S, 'S'), (self.dsb_D, 'D'), (self.dsb_P, 'P'), (self.dsb_Q, 'Q'),
            (self.dsb_eps, 'eps'), (self.dsb_E, 'E')
        ]

        self.settings = dotmap.DotMap(dict(
            resolution=dict(left=-1, bottom=-1, right=1, top=1)
        ))

        self.populateStations()

        self.setupSensorPlot()
        self.setupSkyPlot()
        self.setupErrorPlot()

        self.sensorScatter = self.sensorAxis.scatter([0], [0], s=[50], c='white', marker='o')
        self.skyScatter = self.skyAxis.scatter([0], [0], s=[50], c='red', marker='x')
        self.starsScatter = self.skyAxis.scatter([0], [0], s=[1], marker='o', c='white')
        self.errorScatter = self.errorAxis.scatter([0], [0], s=[1], marker='x', c='cyan')
#        self.skyQuiver = self.skyAxis.quiver([0], [0], [0], [0])

        self.tab_sensor.layout().addWidget(self.sensorCanvas)
        self.tab_sky.layout().addWidget(self.skyCanvas)
        self.tab_errors.layout().addWidget(self.errorCanvas)

        self.updateProjection()

        self.loadYAML('data/20220531_055655.yaml')
        self.matcher.load_catalogue('catalogue/HYG30.tsv')
        self.importConstants('out.yaml')
        self.matcher.catalogue.filter(7)

        self.onParametersChanged()
        self.plotSensorData()
        self.plotCatalogueStars()

        self.connectSignalSlots()

    def populateStations(self):
        for name, station in AMOS.stations.items():
            self.cb_stations.addItem(station.name)

        self.cb_stations.currentIndexChanged.connect(self.selectStation)

    def selectStation(self, index):
        if index == 0:
            station = Station("custom", self.dsb_lat.value(), self.dsb_lon.value(), 0)
        else:
            station = list(AMOS.stations.values())[index - 1]
            self.dsb_lat.setValue(station.latitude)
            self.dsb_lon.setValue(station.longitude)

        self.updateMatcher()
        self.onLocationTimeChanged()

    def setupSensorPlot(self):
        plt.style.use('dark_background')
        self.sensorFigure = Figure(figsize=(6, 6))
        self.sensorCanvas = FigureCanvasQTAgg(self.sensorFigure)
        self.sensorAxis = self.sensorFigure.add_subplot()
        self.sensorFigure.tight_layout()

        self.sensorAxis.set_xlim([-1, 1])
        self.sensorAxis.set_ylim([-1, 1])
        self.sensorAxis.grid(color='white', alpha=0.3)
        self.sensorAxis.set_aspect('equal')

    def setupSkyPlot(self):
        self.skyFigure = Figure(figsize=(6, 6))
        self.skyCanvas = FigureCanvasQTAgg(self.skyFigure)
        self.skyAxis = self.skyFigure.add_subplot(projection='polar')
        self.skyFigure.tight_layout()

        self.skyAxis.set_xlim([0, 2 * np.pi])
        self.skyAxis.set_ylim([0, 90])
        self.skyAxis.set_rlabel_position(0)
        self.skyAxis.set_rticks([15, 30, 45, 60, 75])
        self.skyAxis.yaxis.set_major_formatter('{x}??')
        self.skyAxis.grid(color='white', alpha=0.3)
        self.skyAxis.set_theta_offset(3 * np.pi / 2)

    def setupErrorPlot(self):
        self.errorFigure = Figure(figsize=(8, 6))
        self.errorCanvas = FigureCanvasQTAgg(self.errorFigure)
        self.errorAxis = self.errorFigure.add_subplot()
        self.errorFigure.tight_layout()

        self.errorAxis.set_xlim([0, 90])
        self.errorAxis.set_ylim([0, None])

    def connectSignalSlots(self):
        self.ac_load.triggered.connect(self.loadYAMLFile)

        self.dsb_x0.valueChanged.connect(self.onParametersChanged)
        self.dsb_y0.valueChanged.connect(self.onParametersChanged)
        self.dsb_a0.valueChanged.connect(self.onParametersChanged)
        self.dsb_V.valueChanged.connect(self.onParametersChanged)
        self.dsb_S.valueChanged.connect(self.onParametersChanged)
        self.dsb_D.valueChanged.connect(self.onParametersChanged)
        self.dsb_P.valueChanged.connect(self.onParametersChanged)
        self.dsb_Q.valueChanged.connect(self.onParametersChanged)
        self.dsb_A.valueChanged.connect(self.onParametersChanged)
        self.dsb_F.valueChanged.connect(self.onParametersChanged)
        self.dsb_eps.valueChanged.connect(self.onParametersChanged)
        self.dsb_E.valueChanged.connect(self.onParametersChanged)

        self.dt_time.dateTimeChanged.connect(self.updateTime)
        self.dt_time.dateTimeChanged.connect(self.onTimeChanged)
        self.dsb_lat.valueChanged.connect(self.onLocationChanged)
        self.dsb_lon.valueChanged.connect(self.onLocationChanged)

        self.pb_optimize.clicked.connect(self.minimize)
        self.pb_pair.clicked.connect(self.pair)
        self.pb_export.clicked.connect(self.exportFile)
        self.pb_import.clicked.connect(self.importFile)

        self.pb_cull_unidentified.clicked.connect(self.cullSensor)
        self.pb_cull_distant.clicked.connect(self.cullCatalogue)
        self.dsb_error_limit.valueChanged.connect(self.onErrorLimitChanged)

    def onTimeChanged(self):
        self.updateTime()
        self.onLocationTimeChanged()

    def onLocationChanged(self):
        self.updateLocation()
        self.onLocationTimeChanged()

    def setLocation(self, lat, lon):
        self.dsb_lat.setValue(lat)
        self.dsb_lon.setValue(lon)

    def updateLocation(self):
        self.location = EarthLocation(self.dsb_lon.value() * u.deg, self.dsb_lat.value() * u.deg)

    def setTime(self, time):
        self.dt_time.setDateTime(time)

    def updateTime(self):
        self.time = self.dt_time.dateTime().toString('yyyy-MM-dd HH:mm:ss')

    def updateMatcher(self):
        self.matcher.update(self.location, self.time)

    def updateProjection(self):
        self.projection = BorovickaProjection(*self.get_constants_tuple())

    def onParametersChanged(self):
        self.updateProjection()

        errors = self.matcher.errors_dots(self.projection, True)
        self.plotObservedStars(errors)
        self.plotErrors(errors)

    def onLocationTimeChanged(self):
        self.updateMatcher()
        self.plotCatalogueStars()

        errors = self.matcher.errors_dots(self.projection, True)
        self.plotCatalogueStars()
        self.plotErrors(errors)

    def onErrorLimitChanged(self):
        errors = self.matcher.errors_dots(self.projection, True)
        self.plotErrors(errors)

    def exportFile(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export constants to file", ".", "YAML files (*.yaml)")
        self.exportConstants(filename)

    def exportConstants(self, filename):
        try:
            with open(filename, 'w+') as file:
                yaml.dump(dict(
                    proj='Borovicka',
                    params=dict(
                        x0=self.dsb_x0.value(),
                        y0=self.dsb_y0.value(),
                        a0=self.dsb_a0.value(),
                        A=self.dsb_A.value(),
                        F=self.dsb_F.value(),
                        V=self.dsb_V.value(),
                        S=self.dsb_S.value(),
                        D=self.dsb_D.value(),
                        P=self.dsb_P.value(),
                        Q=self.dsb_Q.value(),
                        eps=self.dsb_eps.value(),
                        E=self.dsb_E.value(),
                    )
                ), file)
        except FileNotFoundError as exc:
            print(f"Could not export constants: {exc}")

    def loadYAMLFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Kvant YAML file", "data", "YAML files (*.yml *.yaml)")
        if filename != '':
            self.loadYAML(filename)

        self.cb_stations.setCurrentIndex(0)
        self.onLocationTimeChanged()
        self.plotSensorData()

    def loadYAML(self, file):
        data = dotmap.DotMap(yaml.safe_load(open(file, 'r')))
        self.setLocation(data.Latitude, data.Longitude)
        self.updateLocation()
        self.setTime(datetime.datetime.strptime(data.EventStartTime, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=zoneinfo.ZoneInfo('UTC')))
        self.updateTime()

        self.matcher = StarMatcher(self.location, self.time)
        self.matcher.sensor_data.load(data)

    def importFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import constants from file", ".", "YAML files (*.yml *.yaml)")
        self.importConstants(filename)
        self.onParametersChanged()

    def importConstants(self, filename):
        try:
            with open(filename, 'r') as file:
                try:
                    data = dotmap.DotMap(yaml.safe_load(file))
                    for widget, param in self.param_widgets:
                        widget.blockSignals(True)
                        widget.setValue(data.params[param])
                        widget.blockSignals(False)
                    self.updateProjection()
                except yaml.YAMLError as exc:
                    print(f"Could not open file {filename}")
        except FileNotFoundError as exc:
            print(f"Could not import constants: {exc}")

    def get_constants_tuple(self):
        return (self.dsb_x0.value(),
            self.dsb_y0.value(),
            np.radians(self.dsb_a0.value()),
            self.dsb_A.value(),
            np.radians(self.dsb_F.value()),
            self.dsb_V.value(),
            self.dsb_S.value(),
            self.dsb_D.value(),
            self.dsb_P.value(),
            self.dsb_Q.value(),
            np.radians(self.dsb_eps.value()),
            np.radians(self.dsb_E.value()),
        )

    def minimize(self):
        self.w_input.setEnabled(False)
        self.w_input.repaint();

        result = self.matcher.minimize(
        #    location=self.location,
        #    time=self.time,
            x0=self.get_constants_tuple(),
            maxiter=self.sb_maxiter.value()
        )

        x0, y0, a0, A, F, V, S, D, P, Q, e, E = tuple(result.x)
        self.dsb_x0.setValue(x0)
        self.dsb_y0.setValue(y0)
        self.dsb_a0.setValue(np.degrees(a0))
        self.dsb_A.setValue(A)
        self.dsb_F.setValue(np.degrees(F))
        self.dsb_V.setValue(V)
        self.dsb_S.setValue(S)
        self.dsb_D.setValue(D)
        self.dsb_P.setValue(P)
        self.dsb_Q.setValue(Q)
        self.dsb_eps.setValue(np.degrees(e))
        self.dsb_E.setValue(np.degrees(E))

        self.w_input.setEnabled(True)
        self.w_input.repaint();
        self.onParametersChanged()

    def cullSensor(self):
        errors = self.matcher.errors_dots(self.projection, False)
        self.matcher.sensor_data.use = (errors < np.radians(self.dsb_error_limit.value()))
        self.matcher.update_sky()
        print(f"Culled the observed stars to {self.dsb_error_limit.value()}??: {self.matcher.sky.shape} stars are valid")
        self.onParametersChanged()

    def cullCatalogue(self):
        errors = self.matcher.errors_stars(self.projection, False)
        self.matcher.catalogue.stars.use = (errors < np.radians(self.dsb_distance_limit.value()))
        print(f"Culled the catalogue to {self.dsb_distance_limit.value()}??: {self.matcher.catalogue.valid_stars.shape} stars used")
        self.matcher.update_sky()
        self.plotCatalogueStars()
        self.onParametersChanged()

    def plotSensorData(self):
        print("Plotting sensor data")
        self.sensorAxis.set_xlim([self.matcher.sensor_data.rect.left, self.matcher.sensor_data.rect.right])
        self.sensorAxis.set_ylim([self.matcher.sensor_data.rect.top, self.matcher.sensor_data.rect.bottom])
        self.sensorScatter.set_offsets(self.matcher.sensor_data.points)
        self.sensorScatter.set_sizes(np.sqrt(self.matcher.sensor_data.intensities))
        self.sensorCanvas.draw()

    def plotObservedStars(self, errors):
        #print(f"Plotting projected stars for {self.projection}")
        z, a = self.matcher.sensor_data.project(self.projection, True)
        self.skyScatter.set_offsets(np.stack((a, np.degrees(z)), axis=1))

        cmap = mpl.cm.get_cmap('autumn_r')
        norm = mpl.colors.Normalize(vmin=0, vmax=np.radians(1))
        self.skyScatter.set_facecolors(cmap(norm(errors)))
        self.skyScatter.set_sizes(10 + 0.05 * self.matcher.sensor_data.m)
        self.skyCanvas.draw()

    def plotCatalogueStars(self):
        print(f"Plotting catalogue stars for {self.location} at {self.time}")
        z, a = self.matcher.catalogue.to_altaz(self.location, self.time, True)
        offsets = np.stack((np.radians(a), 90 - z), axis=1)
        sizes = 0.2 * np.exp(-0.666 * (self.matcher.catalogue.vmag - 5))

        self.starsScatter.set_offsets(offsets)
        self.starsScatter.set_sizes(sizes)
        self.skyCanvas.draw()

    def plotQuiver(self):
        return
        z, a = self.matcher.sensor_data.project(self.projection)
        offsets = np.stack((a, np.degrees(z)), axis=1)
        self.skyQuiver.set_offsets(offsets)

        zz, aa = self.matcher.catalogue_altaz
        aa = np.radians(aa)
        offsets = np.stack((aa, 90 - zz), axis=1)
        self.skyQuiver.set_UVC(zz - z, aa - a)

        self.skyCanvas.draw()

    def plotErrors(self, errors):
        pos = self.matcher.sensor_data.project(self.projection, True)
        alt = np.degrees(pos[0, :])
        az = np.degrees(pos[1, :])

        avg_error = self.matcher.avg_error(errors)
        max_error = self.matcher.max_error(errors)
        self.lb_avg_error.setText(f'{np.degrees(avg_error):.6f}??')
        self.lb_max_error.setText(f'{np.degrees(max_error):.6f}??')
        self.lb_total_stars.setText(f'{alt.size}')
        outside_limit = errors[errors > np.radians(self.dsb_error_limit.value())].size
        self.lb_outside_limit.setText(f'{outside_limit}')

        if max_error is not np.nan:
            self.errorAxis.set_ylim([0, np.degrees(max_error) * 1.05])
            self.errorScatter.set_offsets(np.stack((alt, np.degrees(errors)), axis=1))

            cmap = mpl.cm.get_cmap('autumn_r')
            norm = mpl.colors.Normalize(vmin=0, vmax=np.radians(0.5))
            self.errorScatter.set_facecolors(cmap(norm(errors)))
            self.errorScatter.set_sizes(0.05 * self.matcher.sensor_data.m)
        self.errorCanvas.draw()

    def pair(self):
        print(f"Trying to pair stars")
        self.fitter = Fitter(self.matcher.pair(self.projection), self.matcher.catalogue.valid_stars)

        self.plotCatalogueStars()
        self.plotErrors()
        self.plotQuiver()



app = QApplication(sys.argv)

window = MainWindow()
window.showMaximized()

app.exec()
