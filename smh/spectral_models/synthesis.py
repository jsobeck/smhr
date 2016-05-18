
#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Model for fitting synthetic spectra to spectral data. """

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)

__all__ = ["SpectralSynthesisModel"]

import logging
import itertools
import numpy as np
import scipy.optimize as op
import scipy.interpolate
from collections import OrderedDict
from six import string_types
from scipy.ndimage import gaussian_filter

from .base import BaseSpectralModel
from smh import utils
from smh.photospheres.abundances import asplund_2009 as solar_composition
# HACK TODO REVISIT SOLAR SCALE: Read from session defaults?


logger = logging.getLogger(__name__)


def approximate_spectral_synthesis(model, centroids, bounds):

    # Generate spectra at +/- the initial bounds. For all elements.
    species \
        = [utils.element_to_species(e) for e in model.metadata["elements"]]
    N = len(species)
    try:
        centroids[0]
    except IndexError:
        centroids = centroids * np.ones(N)

    calculated_abundances = np.array(list(
        itertools.product(*[[c-bounds, c, c+bounds] for c in centroids])))

    # Group syntheses into 5 where possible.
    M, K = 5, calculated_abundances.shape[0]
    fluxes = None
    for i in range(1 + int(K / M)):
        abundances = {}
        for j, specie in enumerate(species):
            abundances[specie] = calculated_abundances[M*i:M*(i + 1), j]
        
        spectra = model.session.rt.synthesize(
            model.session.stellar_photosphere, 
            model.transitions, abundances=abundances) # TODO other kwargs?

        dispersion = spectra[0][0]
        if fluxes is None:
            fluxes = np.nan * np.ones((K, dispersion.size))

        for j, spectrum in enumerate(spectra):
            fluxes[M*i + j, :] = spectrum[1]

    def call(*parameters):
        N = len(model.metadata["elements"])
        if len(parameters) < N:
            raise ValueError("missing parameters")

        flux = scipy.interpolate.griddata(calculated_abundances, fluxes, 
            np.array(parameters[:N]).reshape(-1, N)).flatten()
        return (dispersion, flux)

    # Make sure the function works, otherwise fail early so we can debug.
    assert np.isfinite(call(*centroids)[1]).all()

    return call


class SpectralSynthesisModel(BaseSpectralModel):

    def __init__(self, transitions, session, elements, *args, **kwargs):
        """
        A class to fit spectral data by synthesis, given a photospheric
        structure.
    
        :param transitions:
            Row(s) from a line list of transitions to associate with this model.

        :param session:
            The parent session that this model will be associated with.

        :param elements:
            The element(s) to be measured from the data.
        """
        
        super(SpectralSynthesisModel, self).__init__(
            transitions, session, **kwargs)

        # Initialize metadata with default fitting values.
        self.metadata.update({
            "mask": [],
            "window": 1, 
            "continuum_order": 1,
            "velocity_tolerance": 5,
            "smoothing_kernel": True,
            "initial_abundance_bounds": 1,
            "elements": self._verify_elements(elements)
        })

        # Set the model parameter names based on the current metadata.
        self._update_parameter_names()
        self._verify_transitions()

        return None

    def _verify_elements(self, elements):
        """
        Verify that the atomic or molecular transitions associated with this
        class are valid.

        :param elements:
            The element(s) (string or list-type of strings) that will be
            measured in this model.
        """

        # Format the elements and then check that all are real.
        if isinstance(elements, string_types):
            elements = [elements]

        elements = [str(element).title() for element in elements]
        for element in elements:
            # Is the element real?
            if element not in utils.periodic_table:
                raise ValueError("element '{}' is not valid".format(element))

            # Is it in the transition list?
            if  element not in self.transitions["elem1"] \
            and element not in self.transitions["elem2"]:
                raise ValueError(
                    "element '{0}' does not appear in the transition list"\
                        .format(element))

        return elements


    def _initial_guess(self, spectrum, **kwargs):
        """
        Return an initial guess about the model parameters.

        :param spectrum:
            The observed spectrum.
        """

        # Potential parameters:
        # elemental abundances, continuum coefficients, smoothing kernel,
        # velocity offset

        # The elemental abundances are in log_epsilon format.
        # We will assume a scaled-solar initial value based on the stellar [M/H]
        defaults = {
            "sigma_smooth": 0.1,
            "vrad": 0
        }
        p0 = []
        for parameter in self.parameter_names:
            default = defaults.get(parameter, None)
            if default is not None:
                p0.append(default)

            elif parameter.startswith("log_eps"):
                # Elemental abundance.
                element = parameter.split("(")[1].rstrip(")")

                # Assume scaled-solar composition.
                p0.append(solar_composition(element) + \
                    self.session.metadata["stellar_parameters"]["metallicity"])
                
            elif parameter.startswith("c"):
                # Continuum coefficient.
                p0.append((0, 1)[parameter == "c0"])

            else:
                raise ParallelUniverse("this should never happen")

        return np.array(p0)


    def _update_parameter_names(self):
        """
        Update the model parameter names based on the current metadata.
        """

        bounds = {}
        parameter_names = []

        # Abundances of different elements to fit simultaneously.
        parameter_names.extend(
            ["log_eps({0})".format(e) for e in self.metadata["elements"]])

        # Radial velocity?
        vt = abs(self.metadata["velocity_tolerance"] or 0)
        if vt > 0:
            parameter_names.append("vrad")
            bounds["vrad"] = [-vt, +vt]

        # Continuum coefficients?
        parameter_names += ["c{0}".format(i) \
            for i in range(self.metadata["continuum_order"] + 1)]

        # Gaussian smoothing kernel?
        if self.metadata["smoothing_kernel"]:
            # TODO: Better init of this
            bounds["sigma_smooth"] = (-5, 5)
            parameter_names.append("sigma_smooth")

        self._parameter_bounds = bounds
        self._parameter_names = parameter_names
        return True


    def fit(self, spectrum=None, **kwargs):
        """
        Fit a synthesised model spectrum to the observed spectrum.

        :param spectrum: [optional]
            The observed spectrum to fit the synthesis spectral model. If None
            is given, this will default to the normalized rest-frame spectrum in
            the parent session.
        """

        # Check the observed spectrum for validity.
        spectrum = self._verify_spectrum(spectrum)

        # Update internal metadata with any input parameters.
        # Ignore additional parameters because other BaseSpectralModels will
        # have different input arguments.
        for key in set(self.metadata).intersection(kwargs):
            self.metadata[key] = kwargs.pop(key)

        # Update the parameter names in case they have been updated due to the
        # input kwargs.
        self._update_parameter_names()
        
        # Build a mask based on the window fitting range, and prepare the data.
        mask = self.mask(spectrum)
        x, y = spectrum.dispersion[mask], spectrum.flux[mask]
        yerr, absolute_sigma = ((1.0/spectrum.ivar[mask])**0.5, True)
        if not np.all(np.isfinite(yerr)):
            yerr, absolute_sigma = (np.ones_like(x), False)

        # Get a bad initial guess.
        p0 = self._initial_guess(spectrum, **kwargs)

        cov, bounds = None, self.metadata["initial_abundance_bounds"]

        # We allow the user to specify their own function to decide if the
        # approximation is good.
        tolerance_metric = kwargs.pop("tolerance_metric",
            lambda t, a, y, yerr, abs_sigma: np.nansum(np.abs(t - a)) < 0.05)

        # Here we set a hard bound limit where linear interpolation must be OK.
        while bounds > 0.01: # dex
            central = p0[:len(self.metadata["elements"])]
            approximater = approximate_spectral_synthesis(self, central, bounds)

            def objective_function(x, *parameters):
                synth_dispersion, intensities = approximater(*parameters)
                return self._nuisance_methods(
                    x, synth_dispersion, intensities, *parameters)
                
            p_opt, p_cov = op.curve_fit(objective_function, xdata=x, ydata=y,
                    sigma=yerr, p0=p0, absolute_sigma=absolute_sigma)

            # At small bounds it can be difficult to estimate the Jacobian.
            # So if it is correctly approximated once then we keep that in case
            # things screw up later, since it provides a conservative estimate.
            if cov is None or np.isfinite(p_cov).any():
                cov = p_cov.copy()

            # Is the approximation good enough?
            model_y = self(x, *p_opt)
            close_enough = tolerance_metric(
                model_y,                        # Synthesised
                objective_function(x, *p_opt),  # Approxsised
                y, yerr, absolute_sigma)

            if close_enough: break
            else:
                bounds /= 2.0
                p0 = p_opt.copy()

                logger.debug("Dropping bounds to {} because approximation was "
                             "not good enough".format(bounds))

        # Use (p_opt, cov) not (p_opt, p_cov)

        # Make many draws from the covariance matrix.
        draws = kwargs.pop("covariance_draws", 100)
        percentiles = kwargs.pop("percentiles", (2.5, 97.5))
        if np.all(np.isfinite(cov)):
            p_alt = np.random.multivariate_normal(p_opt, cov, size=draws)
            model_yerr = model_y - np.percentile(
                [objective_function(x, *_) for _ in p_alt], percentiles, axis=0)
        else:
            p_alt = np.nan * np.ones((draws, p_opt.size))
            model_yerr = np.nan * np.ones((2, x.size))
        
        # Calculate chi-square for the points that we modelled.
        ivar = spectrum.ivar[mask]
        if not np.any(np.isfinite(ivar)): ivar = 1
        chi_sq = (y - model_y)**2 * ivar

        dof = np.isfinite(chi_sq).sum() - len(p_opt) - 1
        chi_sq = np.nansum(chi_sq)

        x, model_y, model_yerr = self._fill_masked_arrays(
            spectrum, x, model_y, model_yerr)

        fitting_metadata = {
            "model_x": x,
            "model_y": model_y,
            "model_yerr": model_yerr,
            "chi_sq": chi_sq,
            "dof": dof
        }

        # Convert result to ordered dict.
        named_p_opt = OrderedDict(zip(self.parameter_names, p_opt))
        self._result = (named_p_opt, cov, fitting_metadata)
        self.metadata["is_acceptable"] = True
        
        return self._result


    def __call__(self, dispersion, *parameters):
        """
        Generate data at the dispersion points, given the parameters.

        :param dispersion:
            An array of dispersion points to calculate the data for.

        :param *parameters:
            Keyword arguments of the model parameters and their values.
        """

        # Parse the elemental abundances, because they need to be passed to
        # the synthesis routine.
        abundances = {}
        names =  self.parameter_names
        for name, parameter in zip(names, parameters):
            if name.startswith("log_eps"):
                element = name.split("(")[1].rstrip(")")
                abundances[utils.element_to_species(element)] = parameter
            else: break # The log_eps abundances are always first.

        # Produce a synthetic spectrum.
        synth_dispersion, intensities, meta = self.session.rt.synthesize(
            self.session.stellar_photosphere, self.transitions,
            abundances=abundances, 
            isotopes=self.session.metadata["isotopes"])[0] # TODO: Other RT kwargs......

        return self._nuisance_methods(
            dispersion, synth_dispersion, intensities, *parameters)


    def _nuisance_methods(self, dispersion, synth_dispersion, intensities,
        *parameters):
        """
        Apply nuisance operations (convolution, continuum, radial velocity, etc)
        to a model spectrum.

        :param dispersion:
            The dispersion points to evaluate the model at.

        :param synth_dispersion:
            The model dispersion points.

        :param intensities:
            The intensities at the model dispersion points.

        :param *parameters:
            The model parameter values.

        :returns:
            A convolved, redshifted model with multiplicatively-entered
            continuum.
        """

        # Continuum.
        names = self.parameter_names
        O = self.metadata["continuum_order"]
        if 0 > O:
            continuum = 1
        else:
            continuum = np.polyval([parameters[names.index("c{}".format(i))] \
                for i in range(O + 1)][::-1], synth_dispersion)

        model = intensities * continuum

        # Smoothing.
        try:
            index = names.index("sigma_smooth")
        except IndexError:
            None
        else:
            # Scale value by pixel diff.
            kernel = abs(parameters[index])/np.mean(np.diff(synth_dispersion))
            if kernel > 0:
                model = gaussian_filter(model, kernel)

        try:
            v = parameters[names.index("vrad")]
        except ValueError:
            v = 0

        # Interpolate the model spectrum onto the requested dispersion points.
        return np.interp(dispersion, synth_dispersion * (1 + v/299792458e-3), 
            model, left=1, right=1)


    def abundances(self):
        """
        Calculate the abundances (model parameters) given the current stellar
        parameters in the parent session.
        """

        #_ self.fit(self.session.normalized_spectrum)

        # Parse the abundances into the right format.
        raise NotImplementedError("nope")

        