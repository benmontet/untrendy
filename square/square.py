#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tools for fitting and removing trends from light curves using the ￭ algorithm.
The default settings are tuned to work well for Kepler light curves but the
same algorithm might be useful for other datasets.

"""

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)

__all__ = ["detrend", "fit_trend"]

import logging
import numpy as np

try:
    from scipy.interpolate import LSQUnivariateSpline
    LSQUnivariateSpline = LSQUnivariateSpline
except ImportError:
    LSQUnivariateSpline = None

from . import _square


def detrend(x, y, yerr=None, **kwargs):
    """
    Use iteratively re-weighted least squares to remove the out-of-transit
    trends in a light curve.

    :param x:
        The sampled times.

    :param y:
        The fluxes corresponding to the times in ``x``.

    :param yerr: (optional)
        The 1-sigma error bars on ``y``.

    :param **kwargs: (optional)
        Other arguments passed to the ``fit_trend`` function.

    :returns flux:
        The de-trended relative fluxes.

    :returns ferr:
        The de-trended uncertainties on ``flux``.

    """
    trend = fit_trend(x, y, yerr=yerr, **kwargs)
    factor = trend(x)
    return y / factor, yerr / factor


def fit_trend(x, y, yerr=None, Q=12, dt=4., tol=1.25e-3, maxiter=15,
              fill_times=None, maxditer=4, nfill=4):
    """
    Use iteratively re-weighted least squares to fit a spline to the
    out-of-transit trends in a time series.

    :param x:
        The sampled times.

    :param y:
        The fluxes corresponding to the times in ``x``.

    :param yerr: (optional)
        The 1-sigma error bars on ``y``.

    :param Q: (optional)
        The parameter controlling the severity of the re-weighting.

    :param dt: (optional)
        The initial spacing between time control points.

    :param tol: (optional)
        The convergence criterion.

    :param maxiter: (optional)
        The maximum number of re-weighting iterations to run.

    :param fill_times: (optional)
        If provided, this number sets the minimum time spacing between
        adjacent samples that is acceptable. If the spacing is larger,
        knots will be added to fill in the gap.

    :param maxditer: (optional)
        The maximum number of discontinuity search iterations to run.

    :param nfill: (optional)
        The number of knots to use to fill in the gaps.

    """
    if LSQUnivariateSpline is None:
        raise ImportError("scipy is required for spline de-trending.")

    if yerr is None:
        yerr = np.ones_like(y)

    x, y, yerr = np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(yerr)

    inds = np.argsort(x)
    x, y, yerr = x[inds], y[inds], yerr[inds]
    ivar = 1. / yerr / yerr
    w = np.array(ivar)

    # Build the list of knot locations.
    N = (x[-1] - x[0]) / dt + 2
    t = np.linspace(x[0], x[-1], N)[1:-1]

    # Refine knot locations around break points.
    if fill_times is not None:
        inds = x[1:] - x[:-1] > fill_times
        logging.info("Filling in {0} time gaps.".format(np.sum(inds)))
        for i in np.arange(len(x))[inds]:
            t = _add_knots(t, x[i], x[i + 1], N=nfill)

    for j in range(maxditer):
        s0 = None
        for i in range(maxiter):
            # Fit the spline.
            extra_t = np.append(t, [x[0], x[-1]])
            x0 = np.append(x, extra_t)
            inds = np.argsort(x0)
            y0 = np.append(y, np.ones_like(extra_t))[inds]
            w0 = np.append(w, np.ones_like(extra_t))[inds]
            p = LSQUnivariateSpline(x0[inds], y0, t, k=3, w=w0)

            # Compute chi_i ^2.
            chi = (y - p(x)) / yerr
            chi2 = chi * chi

            # Check for convergence.
            sigma = np.median(chi2)
            if s0 is not None and np.abs(s0 - sigma) < tol:
                logging.info("Converged after {0} re-weighting iterations."
                             .format(i))
                break
            s0 = sigma

            # Re compute weights.
            w = ivar * Q / (chi2 + Q)

        # Find any discontinuities.
        i = _square.discontinuities(x, chi, 0.5 * dt, Q, 1.0)
        if i < 0:
            return p

        logging.info("Discontinuity found at t={0}".format(x[i]))
        t = _add_knots(t, x[i], x[i + 1], N=np.max([nfill, 4]))

    return p


def _add_knots(t, t1, t2, N=3):
    """
    A hack for adding ``N`` samples in a given region and removing any other
    samples in that region.

    """
    return np.sort(np.append(t[(t < t1) + (t > t2)], np.linspace(t1, t2, N)))
