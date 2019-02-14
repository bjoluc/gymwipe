import random
import itertools
import logging
import numpy as np
from scipy import linalg as LA
from scipy import signal as sg
import control.matlab

from gymwipe.simtools import SimTimePrepender, SimMan

SEED = 42
logger = SimTimePrepender(logging.getLogger(__name__))


class RandomPlant:
    def __init__(self, x, y, num):
        self.variables = {}
        np.random.seed(SEED)
        P_inf = np.matrix(np.diag([1000, 1000]))
        while np.trace(P_inf) > 15:  # don't use parameters giving too high error covariances compared to other systems
            D = np.matrix(np.diag(np.random.uniform(0.0, 1.3, x)))  # eigenvalues of A
            X = np.matrix(np.random.rand(x, x))
            self.variables['A' + str(num)] = X * D * LA.inv(X)
            self.variables['C' + str(num)] = np.matrix(np.random.uniform(0, 1.0, [y, x]))
            X = np.matrix(LA.orth(np.random.randn(x, x)))
            D = np.matrix(np.diag(np.random.uniform(0.2, 1.0, x)))
            self.variables['W' + str(num)] = X * D * X.T
            X = np.matrix(LA.orth(np.random.randn(y, y)))
            D = np.matrix(np.diag(np.random.uniform(0.2, 1.0, y)))
            self.variables['V' + str(num)] = X * D * X.T
            P_inf = LA.solve_discrete_are(self.variables['A' + num].T,
                                          self.variables['C' + num].T,
                                          self.variables['W' + num], self.variables['V' + num],
                                          e=None, s=None, balanced=True)


class RandomPlant2:
    def __init__(self, inputs, states, outputs, dt):
        cont_sys = control.matlab.rss(states, outputs, inputs)
        discrete_sys = control.sample_system(cont_sys, Ts=dt)
        zeros = control.zero(discrete_sys)
        logger.debug("init done, dt is %f\nzeros are %s", discrete_sys.dt, zeros, sender=self)
