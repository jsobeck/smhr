#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" The stellar parameters tab in Spectroscopy Made Hard """

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)

__all__ = ["StellarParametersTab"]

import logging
import matplotlib.gridspec
import numpy as np
import sys
from PySide import QtCore, QtGui
from matplotlib.ticker import MaxNLocator
from time import time

import mpl, style_utils
from smh.photospheres import available as available_photospheres
from smh.spectral_models import (ProfileFittingModel, SpectralSynthesisModel)
from linelist_manager import TransitionsDialog

logger = logging.getLogger(__name__)

if sys.platform == "darwin":
        
    # See http://successfulsoftware.net/2013/10/23/fixing-qt-4-for-mac-os-x-10-9-mavericks/
    substitutes = [
        (".Lucida Grande UI", "Lucida Grande"),
        (".Helvetica Neue DeskInterface", "Helvetica Neue")
    ]
    for substitute in substitutes:
        QtGui.QFont.insertSubstitution(*substitute)


DOUBLE_CLICK_INTERVAL = 0.1 # MAGIC HACK
PICKER_TOLERANCE = 10 # MAGIC HACK


class StellarParametersTab(QtGui.QWidget):

    def __init__(self, parent):
        """
        Create a tab for the determination of stellar parameters by excitation
        and ionization equalibrium.

        :param parent:
            The parent widget.
        """

        super(StellarParametersTab, self).__init__(parent)
        self.parent = parent

        self.parent_layout = QtGui.QHBoxLayout(self)
        lhs_layout = QtGui.QVBoxLayout()
        grid_layout = QtGui.QGridLayout()

        # Effective temperature.
        label = QtGui.QLabel(self)
        label.setText("Effective temperature")
        grid_layout.addWidget(label, 0, 0, 1, 1)
        hbox = QtGui.QHBoxLayout()
        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Minimum))
        self.edit_teff = QtGui.QLineEdit(self)
        self.edit_teff.setMinimumSize(QtCore.QSize(40, 0))
        self.edit_teff.setMaximumSize(QtCore.QSize(50, 16777215))
        self.edit_teff.setValidator(
            QtGui.QDoubleValidator(3000, 8000, 0, self.edit_teff))

        hbox.addWidget(self.edit_teff)
        grid_layout.addLayout(hbox, 0, 1, 1, 1)
        
        # Surface gravity.
        label = QtGui.QLabel(self)
        label.setText("Surface gravity")
        grid_layout.addWidget(label, 1, 0, 1, 1)
        hbox = QtGui.QHBoxLayout()
        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Minimum))
        self.edit_logg = QtGui.QLineEdit(self)
        self.edit_logg.setMinimumSize(QtCore.QSize(40, 0))
        self.edit_logg.setMaximumSize(QtCore.QSize(50, 16777215))
        self.edit_logg.setValidator(
            QtGui.QDoubleValidator(-1, 6, 3, self.edit_logg))
        hbox.addWidget(self.edit_logg)
        grid_layout.addLayout(hbox, 1, 1, 1, 1)

        # Metallicity.
        label = QtGui.QLabel(self)
        label.setText("Metallicity")
        grid_layout.addWidget(label, 2, 0, 1, 1)
        hbox = QtGui.QHBoxLayout()
        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Minimum))
        self.edit_metallicity = QtGui.QLineEdit(self)
        self.edit_metallicity.setMinimumSize(QtCore.QSize(40, 0))
        self.edit_metallicity.setMaximumSize(QtCore.QSize(50, 16777215))
        self.edit_metallicity.setValidator(
            QtGui.QDoubleValidator(-5, 1, 3, self.edit_metallicity))
        hbox.addWidget(self.edit_metallicity)
        grid_layout.addLayout(hbox, 2, 1, 1, 1)


        # Microturbulence.
        label = QtGui.QLabel(self)
        label.setText("Microturbulence")
        grid_layout.addWidget(label, 3, 0, 1, 1)
        hbox = QtGui.QHBoxLayout()
        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Minimum))
        self.edit_xi = QtGui.QLineEdit(self)
        self.edit_xi.setMinimumSize(QtCore.QSize(40, 0))
        self.edit_xi.setMaximumSize(QtCore.QSize(50, 16777215))
        self.edit_xi.setValidator(QtGui.QDoubleValidator(0, 5, 3, self.edit_xi))
        hbox.addWidget(self.edit_xi)
        grid_layout.addLayout(hbox, 3, 1, 1, 1)

        # Optionally TODO: alpha-enhancement.

        lhs_layout.addLayout(grid_layout)

        # Buttons for solving/measuring.        
        hbox = QtGui.QHBoxLayout()
        self.btn_measure = QtGui.QPushButton(self)
        self.btn_measure.setAutoDefault(True)
        self.btn_measure.setDefault(True)
        self.btn_measure.setText("Measure")

        hbox.addWidget(self.btn_measure)

        self.btn_options = QtGui.QPushButton(self)
        self.btn_options.setText("Options..")
        hbox.addWidget(self.btn_options)

        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Minimum))

        self.btn_solve = QtGui.QPushButton(self)
        self.btn_solve.setText("Solve")
        hbox.addWidget(self.btn_solve)
        lhs_layout.addLayout(hbox)

        line = QtGui.QFrame(self)
        line.setFrameShape(QtGui.QFrame.HLine)
        line.setFrameShadow(QtGui.QFrame.Sunken)
        lhs_layout.addWidget(line)

        self.spectral_models = []
        self.table_view = SpectralModelsTableView(self)
        self.table_view.setModel(SpectralModelsTableModel(self))
        self.table_view.setSelectionBehavior(
            QtGui.QAbstractItemView.SelectRows)
        self.table_view.setSortingEnabled(True)
        self.table_view.resizeColumnsToContents()
        self.table_view.setColumnWidth(0, 30) # MAGIC
        self.table_view.horizontalHeader().setStretchLastSection(True)
        lhs_layout.addWidget(self.table_view)

        _ = self.table_view.selectionModel()
        _.selectionChanged.connect(self.selected_model_changed)


        hbox = QtGui.QHBoxLayout()
        self.btn_filter = QtGui.QPushButton(self)
        self.btn_filter.setText("Filter..")
        self.btn_quality_control = QtGui.QPushButton(self)
        self.btn_quality_control.setText("Quality control..")
        hbox.addItem(QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding,
            QtGui.QSizePolicy.Minimum))
        hbox.addWidget(self.btn_filter)
        hbox.addWidget(self.btn_quality_control)
        lhs_layout.addLayout(hbox)

        self.parent_layout.addLayout(lhs_layout)


        # Matplotlib figure.
        self.figure = mpl.MPLWidget(None, tight_layout=True, autofocus=True)
        self.figure.setMinimumSize(QtCore.QSize(800, 300))
        self.figure.figure.patch.set_facecolor([(_ - 10)/255. for _ in \
            self.palette().color(QtGui.QPalette.Window).getRgb()[:3]])

        gs_top = matplotlib.gridspec.GridSpec(4, 1)
        gs_bottom = matplotlib.gridspec.GridSpec(4, 1, 
            height_ratios=[2, 2, 1, 2])
        gs_bottom.update(hspace=0)

        self.ax_excitation = self.figure.figure.add_subplot(gs_top[0])
        self.ax_excitation.scatter([], [], 
            s=30, facecolor="#CCCCCC", edgecolor="k", picker=PICKER_TOLERANCE)
        self.ax_excitation.legend()

        self.ax_excitation.xaxis.get_major_formatter().set_useOffset(False)
        self.ax_excitation.yaxis.set_major_locator(MaxNLocator(5))
        self.ax_excitation.yaxis.set_major_locator(MaxNLocator(4))
        self.ax_excitation.set_xlabel("Excitation potential (eV)")
        self.ax_excitation.set_ylabel("[X/H]") #TODO: X/M

        self.ax_line_strength = self.figure.figure.add_subplot(gs_top[1])
        self.ax_line_strength.scatter([], [],
            s=30, facecolor="#CCCCCC", edgecolor="k", picker=PICKER_TOLERANCE)
        self.ax_line_strength.xaxis.get_major_formatter().set_useOffset(False)
        self.ax_line_strength.yaxis.set_major_locator(MaxNLocator(5))
        self.ax_line_strength.yaxis.set_major_locator(MaxNLocator(4))
        self.ax_line_strength.set_xlabel(r"$\log({\rm EW}/\lambda)$")
        self.ax_line_strength.set_ylabel("[X/H]") # TODO: X/M

        self.ax_residual = self.figure.figure.add_subplot(gs_bottom[2])
        self.ax_residual.axhline(0, c="#666666")
        self.ax_residual.xaxis.set_major_locator(MaxNLocator(5))
        self.ax_residual.yaxis.set_major_locator(MaxNLocator(2))
        self.ax_residual.set_xticklabels([])

        self.ax_spectrum = self.figure.figure.add_subplot(gs_bottom[3])
        self.ax_spectrum.xaxis.get_major_formatter().set_useOffset(False)
        self.ax_spectrum.xaxis.set_major_locator(MaxNLocator(5))
        self.ax_spectrum.set_xlabel(u"Wavelength (Å)")
        self.ax_spectrum.set_ylabel(r"Normalized flux")

        # Some empty figure objects that we will use later.
        self._lines = {
            "selected_point": [
                self.ax_excitation.scatter([], [],
                    edgecolor="b", facecolor="none", s=150, linewidth=3, zorder=2),
                self.ax_line_strength.scatter([], [],
                    edgecolor="b", facecolor="none", s=150, linewidth=3, zorder=2)
            ],
            "spectrum": None,
            "transitions_center_main": self.ax_spectrum.axvline(
                np.nan, c="#666666", linestyle=":"),
            "transitions_center_residual": self.ax_residual.axvline(
                np.nan, c="#666666", linestyle=":"),
            "model_masks": [],
            "nearby_lines": [],
            "model_fit": self.ax_spectrum.plot([], [], c="r")[0],
            "model_residual": self.ax_residual.plot([], [], c="k")[0],
            "interactive_mask": [
                self.ax_spectrum.axvspan(xmin=np.nan, xmax=np.nan, ymin=np.nan,
                    ymax=np.nan, facecolor="r", edgecolor="none", alpha=0.25,
                    zorder=-5),
                self.ax_residual.axvspan(xmin=np.nan, xmax=np.nan, ymin=np.nan,
                    ymax=np.nan, facecolor="r", edgecolor="none", alpha=0.25,
                    zorder=-5)
            ]
        }


        self.parent_layout.addWidget(self.figure)

        # Connect buttons.
        self.btn_measure.clicked.connect(self.measure_abundances)
        self.btn_options.clicked.connect(self.options)
        self.btn_solve.clicked.connect(self.solve_parameters)
        self.edit_teff.returnPressed.connect(self.btn_measure.clicked)
        self.edit_logg.returnPressed.connect(self.btn_measure.clicked)
        self.edit_metallicity.returnPressed.connect(self.btn_measure.clicked)
        self.edit_xi.returnPressed.connect(self.btn_measure.clicked)

        # Connect matplotlib.
        self.figure.mpl_connect("button_press_event", self.figure_mouse_press)
        self.figure.mpl_connect("button_release_event", self.figure_mouse_release)
        self.figure.figure.canvas.callbacks.connect(
            "pick_event", self.figure_mouse_pick)

        return None


    def populate_widgets(self):
        """ Update the stellar parameter edit boxes from the session. """

        if not hasattr(self.parent, "session") or self.parent.session is None:
            return None

        widget_info = [
            (self.edit_teff, "{0:.0f}", "effective_temperature"),
            (self.edit_logg, "{0:.2f}", "surface_gravity"),
            (self.edit_metallicity, "{0:+.2f}", "metallicity"),
            (self.edit_xi, "{0:.2f}", "microturbulence")
        ]
        metadata = self.parent.session.metadata["stellar_parameters"]

        for widget, format, key in widget_info:
            widget.setText(format.format(metadata[key]))

        return None


    def figure_mouse_pick(self, event):
        """
        Trigger for when the mouse is used to select an item in the figure.

        :param event:
            The matplotlib event.
        """

        # Select the row. That will trigger the rest.
        self.table_view.selectRow(self._spectral_model_indices[event.ind[0]])
        return None


    def figure_mouse_press(self, event):
        """
        Trigger for when the mouse button is pressed in the figure.

        :param event:
            The matplotlib event.
        """

        if event.inaxes in (self.ax_residual, self.ax_spectrum):
            self.spectrum_axis_mouse_press(event)
        return None


    def figure_mouse_release(self, event):
        """
        Trigger for when the mouse button is released in the figure.

        :param event:
            The matplotlib event.
        """

        if event.inaxes in (self.ax_residual, self.ax_spectrum):
            self.spectrum_axis_mouse_release(event)
        return None


    def spectrum_axis_mouse_press(self, event):
        """
        The mouse button was pressed in the spectrum axis.

        :param event:
            The matplotlib event.
        """

        if event.dblclick:

            # Double click.
            spectral_model, index = self._get_selected_model(True)
            for i, (s, e) in enumerate(spectral_model.metadata["mask"][::-1]):
                if e >= event.xdata >= s:

                    mask = spectral_model.metadata["mask"]
                    index = len(mask) - 1 - i
                    del mask[index]

                    # Re-fit the current spectral_model.
                    spectral_model.fit()

                    # Update the table view for this row.
                    table_model = self.table_view.model()
                    table_model.dataChanged.emit(
                        table_model.createIndex(index, 0),
                        table_model.createIndex(
                            index, table_model.columnCount(0)))

                    # Update the view of the current model.
                    self.update_spectrum_figure()
                    break

            else:
                # No match with a masked region. 

                # TODO: Add a point that will be used for the continuum?

                # For the moment just refit the model.
                spectral_model.fit()

                # Update the table view for this row.
                table_model = self.table_view.model()
                table_model.dataChanged.emit(
                    table_model.createIndex(index, 0),
                    table_model.createIndex(
                        index, table_model.columnCount(0)))

                # Update the view of the current model.
                self.update_spectrum_figure()
                return None

        else:
            # Single click.
            xmin, xmax, ymin, ymax = (event.xdata, np.nan, -1e8, +1e8)
            for patch in self._lines["interactive_mask"]:
                patch.set_xy([
                    [xmin, ymin],
                    [xmin, ymax],
                    [xmax, ymax],
                    [xmax, ymin],
                    [xmin, ymin]
                ])

            # Set the signal and the time.
            self._interactive_mask_region_signal = (
                time(),
                self.figure.mpl_connect(
                    "motion_notify_event", self.update_mask_region)
            )

        return None


    def update_mask_region(self, event):
        """
        Update the visible selected masked region for the selected spectral
        model. This function is linked to a callback for when the mouse position
        moves.

        :para event:
            The matplotlib motion event to show the current mouse position.
        """

        if event.xdata is None: return

        signal_time, signal_cid = self._interactive_mask_region_signal
        if time() - signal_time > DOUBLE_CLICK_INTERVAL:

            data = self._lines["interactive_mask"][0].get_xy()

            # Update xmax.
            data[2:4, 0] = event.xdata
            for patch in self._lines["interactive_mask"]:
                patch.set_xy(data)

            self.figure.draw()

        return None



    def spectrum_axis_mouse_release(self, event):
        """
        Mouse button was released from the spectrum axis.

        :param event:
            The matplotlib event.
        """

        try:
            signal_time, signal_cid = self._interactive_mask_region_signal

        except AttributeError:
            return None

        xy = self._lines["interactive_mask"][0].get_xy()

        if event.xdata is None:
            # Out of axis; exclude based on the closest axis limit
            xdata = xy[2, 0]
        else:
            xdata = event.xdata


        # If the two mouse events were within some time interval,
        # then we should not add a mask because those signals were probably
        # part of a double-click event.
        if  time() - signal_time > DOUBLE_CLICK_INTERVAL \
        and np.abs(xy[0,0] - xdata) > 0:
            
            # Get current spectral model.
            spectral_model, index = self._get_selected_model(True)

            # Add mask metadata.
            spectral_model.metadata["mask"].append([xy[0,0], xy[2, 0]])

            # Re-fit the spectral model.
            spectral_model.fit()

            # Update the table view for this row.
            table_model = self.table_view.model()
            table_model.dataChanged.emit(
                table_model.createIndex(index, 0),
                table_model.createIndex(
                    index, table_model.columnCount(0)))

            # Update the view of the spectral model.
            self.update_spectrum_figure()

        xy[:, 0] = np.nan
        for patch in self._lines["interactive_mask"]:
            patch.set_xy(xy)

        self.figure.mpl_disconnect(signal_cid)
        self.figure.draw()
        del self._interactive_mask_region_signal
        return None



    def update_stellar_parameters(self):
        """ Update the stellar parameters with the values in the GUI. """

        self.parent.session.metadata["stellar_parameters"].update({
            "effective_temperature": float(self.edit_teff.text()),
            "surface_gravity": float(self.edit_logg.text()),
            "metallicity": float(self.edit_metallicity.text()),
            "microturbulence": float(self.edit_xi.text())
        })
        return True


    def updated_spectral_models(self):
        """
        The spectral models in the underlying session have been updated.
        """
        self.spectral_models = []
        for model in self.parent.session.metadata["spectral_models"]:
            if model.use_for_stellar_parameter_inference:
                self.spectral_models.append(model)

        # Update the table view.
        self.table_view.model().reset()
        return None


    def _check_for_spectral_models(self):
        """
        Check the session for any valid spectral models that are associated with
        the determination of stellar parameters.
        """

        # Are there any spectral models to be used for the determination of
        # stellar parameters?
        for sm in self.parent.session.metadata.get("spectral_models", []):
            if sm.use_for_stellar_parameter_inference: break

        else:
            reply = QtGui.QMessageBox.information(self,
                "No spectral models found",
                "No spectral models are currently associated with the "
                "determination of stellar parameters.\n\n"
                "Click 'OK' to load the transitions manager.")

            if reply == QtGui.QMessageBox.Ok:
                # Load line list manager.
                dialog = TransitionsDialog(self.parent.session)
                dialog.exec_()

                # Do we even have any spectral models now?
                for sm in self.parent.session.metadata.get("spectral_models", []):
                    if sm.use_for_stellar_parameter_inference: break
                else:
                    return False
            else:
                return False

        return True


    def measure_abundances(self):
        """ The measure abundances button has been clicked. """

        if self.parent.session is None or not self._check_for_spectral_models():
            return None

        self.updated_spectral_models()

        # Collate the transitions from spectral models that are profiles.
        indices = []
        equivalent_widths = []
        models = []
        self._spectral_model_indices = []
        for i, model in enumerate(self.spectral_models):
            if not model.is_acceptable: continue

            # TODO THIS IS ALL BAD CODE.
            self._spectral_model_indices.append(i)
            indices.extend(model._transition_indices)
            models.append(model)
            equivalent_widths.append(
                1e3 * model.metadata["fitted_result"][2]["equivalent_width"][0])
        indices = np.array(indices)

        # For any spectral models to be used for SPs that are not profiles,
        # re-fit them.
        transitions = self.parent.session.metadata["line_list"][indices].copy()
        transitions["equivalent_width"] = np.array(equivalent_widths)

        # Update the session with the stellar parameters in the GUI.
        self.update_stellar_parameters()

        # Calculate abundances.
        abundances = self.parent.session.rt.abundance_cog(
            self.parent.session.stellar_photosphere, transitions)

        # Update figures.
        self.ax_excitation.collections[0].set_offsets(
            np.array([transitions["expot"], abundances]).T)

        rew = 1e-3 * transitions["equivalent_width"]/transitions["wavelength"]
        self.ax_line_strength.collections[0].set_offsets(
            np.array([np.log10(rew), abundances]).T)
        
        # Update limits on the excitation and line strength figures.
        style_utils.relim_axes(self.ax_excitation)
        style_utils.relim_axes(self.ax_line_strength)

        for model, abundance in zip(models, abundances):
            model.metadata["fitted_result"][-1]["abundances"] = [abundance]

        # Update selected entries.
        for collection in self._lines["selected_point"]:
            collection.set_offsets(np.array([np.nan, np.nan]).T)

        # Update table view model.
        self.table_view.model().reset()

        self.figure.draw()

        return None


    def _get_selected_model(self, full_output=False):
        index = self.table_view.selectionModel().selectedRows()[0].row()
        model = self.spectral_models[index]
        return (model, index) if full_output else model


    def selected_model_changed(self):
        """
        The selected model was changed.
        """

        # Show point on excitation/line strength plot.
        selected_model = self._get_selected_model()
        try:
            metadata = selected_model.metadata["fitted_result"][-1]
            abundances = metadata["abundances"]
            equivalent_width = metadata["equivalent_width"][0]

        except (IndexError, KeyError):
            abundances = [np.nan]

        assert len(abundances) == 1
        abundance = abundances[0]
        if not np.isfinite(abundance):
            excitation_potential, rew = (np.nan, np.nan)

        else:
            transitions = selected_model.transitions
            assert len(transitions) == 1

            excitation_potential = transitions["expot"][0]
            rew = np.log10(equivalent_width/transitions["wavelength"][0])


        point_excitation, point_strength = self._lines["selected_point"]
        point_excitation.set_offsets(np.array([excitation_potential,
            abundance]).T)
        point_strength.set_offsets(np.array([rew, abundance]).T)

        # Show spectrum.
        self.update_spectrum_figure()

        return None


    def update_spectrum_figure(self):
        """ Update the spectrum figure. """

        if self._lines["spectrum"] is None \
        and hasattr(self.parent, "session") \
        and hasattr(self.parent.session, "normalized_spectrum"):

            # Draw the spectrum.
            spectrum = self.parent.session.normalized_spectrum
            self._lines["spectrum"] = self.ax_spectrum.plot(spectrum.dispersion,
                spectrum.flux, c="k", drawstyle="steps-mid")

            sigma = 1.0/np.sqrt(spectrum.ivar)
            style_utils.fill_between_steps(self.ax_spectrum, spectrum.dispersion,
                spectrum.flux - sigma, spectrum.flux + sigma, 
                facecolor="#cccccc", edgecolor="#cccccc", alpha=1)

            style_utils.fill_between_steps(self.ax_residual, spectrum.dispersion,
                -sigma, +sigma, facecolor="#CCCCCC", edgecolor="none", alpha=1)

            self.ax_spectrum.set_xlim(
                spectrum.dispersion[0], spectrum.dispersion[-1])
            self.ax_residual.set_xlim(self.ax_spectrum.get_xlim())
            self.ax_spectrum.set_ylim(0, 1.2)
            self.ax_spectrum.set_yticks([0, 0.5, 1])
            self.ax_residual.set_ylim(-0.05, 0.05)

            self.figure.draw()


        selected_model = self._get_selected_model()
        transitions = selected_model.transitions
        window = selected_model.metadata["window"]
        limits = [
            transitions["wavelength"][0] - window,
            transitions["wavelength"][-1] + window,
        ]

        # Zoom to region.
        self.ax_spectrum.set_xlim(limits)
        self.ax_residual.set_xlim(limits)

        # If this is a profile fitting line, show where the centroid is.
        x = transitions["wavelength"][0] \
            if isinstance(selected_model, ProfileFittingModel) else np.nan
        self._lines["transitions_center_main"].set_data([x, x], [0, 1.2])
        self._lines["transitions_center_residual"].set_data([x, x], [0, 1.2])

        # Model masks specified by the user.
        # (These should be shown regardless of whether there is a fit or not.)
        for i, (start, end) in enumerate(selected_model.metadata["mask"]):
            try:
                patches = self._lines["model_masks"][i]

            except IndexError:
                self._lines["model_masks"].append([
                    self.ax_spectrum.axvspan(np.nan, np.nan,
                        facecolor="r", edgecolor="none", alpha=0.25),
                    self.ax_residual.axvspan(np.nan, np.nan,
                        facecolor="r", edgecolor="none", alpha=0.25)
                ])
                patches = self._lines["model_masks"][-1]

            for patch in patches:
                patch.set_xy([
                    [start, -1e8],
                    [start, +1e8],
                    [end,   +1e8],
                    [end,   -1e8],
                    [start, -1e8]
                ])
                patch.set_visible(True)

        # Hide unnecessary ones.
        N = len(selected_model.metadata["mask"])
        for unused_patches in self._lines["model_masks"][N:]:
            for unused_patch in unused_patches:
                unused_patch.set_visible(False)

        # Hide previous model_errs
        try:
            self._lines["model_yerr"].set_visible(False)
            del self._lines["model_yerr"]
            # TODO: This is wrong. It doesn't actually delete them so if
            #       you ran this forever then you would get a real bad 
            #       memory leak in Python. But for now, re-calculating
            #       the PolyCollection is in the too hard basket.

        except KeyError:
            None

        # Things to show if there is a fitted result.
        try:
            (named_p_opt, cov, meta) = selected_model.metadata["fitted_result"]

        except KeyError:
            meta = {}
            self._lines["model_fit"].set_data([], [])
            self._lines["model_residual"].set_data([], [])

        else:
            assert len(meta["model_x"]) == len(meta["model_y"])
            assert len(meta["model_x"]) == len(meta["residual"])
            assert len(meta["model_x"]) == len(meta["model_yerr"])

            self._lines["model_fit"].set_data(meta["model_x"], meta["model_y"])
            self._lines["model_residual"].set_data(meta["model_x"], 
                meta["residual"])

            # Model yerr.
            if np.any(np.isfinite(meta["model_yerr"])):
                self._lines["model_yerr"] = self.ax_spectrum.fill_between(
                    meta["model_x"],
                    meta["model_y"] + meta["model_yerr"],
                    meta["model_y"] - meta["model_yerr"],
                    facecolor="r", edgecolor="none", alpha=0.5)

            # Model masks due to nearby lines.
            if "nearby_lines" in meta:
                for i, (_, (start, end)) in enumerate(meta["nearby_lines"]):
                    try:
                        patches = self._lines["nearby_lines"][i]
                
                    except IndexError:
                        self._lines["nearby_lines"].append([
                            self.ax_spectrum.axvspan(np.nan, np.nan,
                                facecolor="b", edgecolor="none", alpha=0.25),
                            self.ax_residual.axvspan(np.nan, np.nan,
                                facecolor="b", edgecolor="none", alpha=0.25)
                        ])
                        patches = self._lines["nearby_lines"][-1]

                    for patch in patches:                            
                        patch.set_xy([
                            [start, -1e8],
                            [start, +1e8],
                            [end,   +1e8],
                            [end,   -1e8],
                            [start, -1e8]
                        ])
                        patch.set_visible(True)
                    

        # Hide any masked model regions due to nearby lines.
        N = len(meta.get("nearby_lines", []))
        for unused_patches in self._lines["nearby_lines"][N:]:
            for unused_patch in unused_patches:
                unused_patch.set_visible(False)

        self.figure.draw()

        return None



    def options(self):
        """ Open a GUI for the radiative transfer and solver options. """
        raise NotImplementedError


    def solve_parameters(self):
        """ Solve the stellar parameters. """
        raise NotImplementedError





class SpectralModelsTableView(QtGui.QTableView):

    def __init__(self, parent, *args):
        super(SpectralModelsTableView, self).__init__(parent, *args)
        self.parent = parent


    def contextMenuEvent(self, event):
        """
        Provide a context (right-click) menu for the line list table.

        :param event:
            The mouse event that triggered the menu.
        """

        N = len(self.selectionModel().selectedRows())
        
        menu = QtGui.QMenu(self)
        fit_models = menu.addAction("Fit model{}..".format(["", "s"][N != 1]))
        menu.addSeparator()
        option = menu.addAction("Option A")
        option.setEnabled(False)
        option = menu.addAction("Option B")
        option.setEnabled(False)
        option = menu.addAction("Option C")
        option.setEnabled(False)
        option = menu.addAction("Option D")
        option.setEnabled(False)
        menu.addSeparator()
        option = menu.addAction("Option E")
        option.setEnabled(False)

        if N == 0:
            fit_models.setEnabled(False)

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == fit_models:
            self.fit_selected_models()

        return None


    def fit_selected_models(self):
        """ Fit the selected spectral models. """

        for i, index in enumerate(self.selectionModel().selectedIndexes()):
            # Fit the model.
            self.parent.spectral_models[index.row()].fit()

            # Update the view if this is the first one.
            if i == 0:
                self.parent.update_spectrum_figure()

        # Update the data model.
        self.model().reset()

        return None





class SpectralModelsTableModel(QtCore.QAbstractTableModel):

    header = ["", u"λ\n(Å)", "Element\n", u"E. W.\n(mÅ)",
        "log ε\n(dex)"]
    attrs = ("is_acceptable", "_repr_wavelength", "_repr_element", 
        "equivalent_width", "abundance")

    def __init__(self, parent, *args):
        """
        An abstract table model for spectral models.

        :param parent:
            The parent widget.
        """

        super(SpectralModelsTableModel, self).__init__(parent, *args)
        self.parent = parent
        return None


    def rowCount(self, parent):
        """ Return the number of rows in the table. """
        return len(self.parent.spectral_models)


    def columnCount(self, parent):
        """ Return the number of columns in the table. """
        return len(self.header)


    def data(self, index, role):
        """
        Display the data.

        :param index:
            The table index.

        :param role:
            The display role.
        """

        if not index.isValid():
            return None

        column = index.column()
        if  column == 0 \
        and role in (QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole):
            value = self.parent.spectral_models[index.row()].is_acceptable
            if role == QtCore.Qt.CheckStateRole:
                return QtCore.Qt.Checked if value else QtCore.Qt.Unchecked
            else:
                return None

        elif column == 1:
            value = self.parent.spectral_models[index.row()]._repr_wavelength

        elif column == 2:
            value = self.parent.spectral_models[index.row()]._repr_element

        elif column == 3:
            try:
                spectral_model = self.parent.spectral_models[index.row()]
                result = spectral_model.metadata["fitted_result"][2]
                equivalent_width = result["equivalent_width"][0]
            except:
                equivalent_width = np.nan

            value = "{0:.1f}".format(1000 * equivalent_width) \
                if np.isfinite(equivalent_width) else ""

        elif column == 4:
            try:
                spectral_model = self.parent.spectral_models[index.row()]
                abundances \
                    = spectral_model.metadata["fitted_result"][2]["abundances"]

            except (IndexError, KeyError):
                value = ""

            else:
                # How many elements were measured?
                value = "; ".join(["{0:.2f}".format(abundance) \
                    for abundance in abundances])

        return value if role == QtCore.Qt.DisplayRole else None


    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal \
        and role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None


    def setData(self, index, value, role=QtCore.Qt.DisplayRole):
        if index.column() != 0 or value:
            return False

        model = self.parent.spectral_models[index.row()]
        model.metadata["is_acceptable"] = value

        # Emit data change for this row.
        self.dataChanged.emit(
            self.createIndex(index.row(), 0),
            self.createIndex(index.row(), self.columnCount(0)))

        # Refresh the view.
        try:
            del model.metadata["fitted_result"]

        except KeyError:
            None

        self.parent.update_spectrum_figure()

        return value


    def sort(self, column, order):
    
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))

        def get_equivalent_width(model):
            try:
                return model.metadata["fitted_result"][-1]["equivalent_width"][0]
            except (IndexError, KeyError):
                return np.nan

        def get_abundance(model):
            try:
                return model.metadata["fitted_result"][-1]["abundances"][0]
            except (IndexError, KeyError):
                return np.nan

        sorter = {
            0: lambda model: model.is_acceptable,
            1: lambda model: model._repr_wavelength,
            2: lambda model: model._repr_element,
            3: get_equivalent_width,
            4: get_abundance,
        }

        self.parent.spectral_models \
            = sorted(self.parent.spectral_models, key=sorter[column])
        
        if order == QtCore.Qt.DescendingOrder:
            self.parent.spectral_models.reverse()

        self.dataChanged.emit(self.createIndex(0, 0),
            self.createIndex(self.rowCount(0), self.columnCount(0)))
        self.emit(QtCore.SIGNAL("layoutChanged()"))
        return None


    def flags(self, index):
        if not index.isValid(): return
        return  QtCore.Qt.ItemIsSelectable|\
                QtCore.Qt.ItemIsEnabled|\
                QtCore.Qt.ItemIsUserCheckable


