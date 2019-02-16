import numpy as np
import numpy.matlib
import cmath

import scipy as sp
from scipy.linalg import block_diag, orth
import logging

from gymwipe.simtools import SimTimePrepender, SimMan

logger = SimTimePrepender(logging.getLogger(__name__))
PARAM_SEED = 42


class StateSpacePlant:
    def __init__(self, n, m, dt, marginally_stable=True):
        """
        Generate a random discrete time system.

        Parameters
        ----------
        n : int
            Order of the system model.
        m : int
            Number of inputs.
        marginally_stable : boolean
            Boolean variable that determines whether the system should be marginally stable.
        Returns
        -------
        a : nxn system dynamic matrix
        b : nxm input dynamic matrix
        """
        self.dim = n
        if marginally_stable:
            n_integrator = np.int((np.random.random_sample() < 0.1) + np.sum(np.random.random_sample((n-1,)) < 0.01))
            n_double = np.int(np.floor(np.sum(np.random.random_sample((n-n_integrator,)) < 0.05)/2))
            n_complex = np.int(np.floor(np.sum(np.random.random_sample((n - n_integrator - 2*n_double,)) < 0.5) / 2))
            n_real = n - n_integrator - 2*n_double - 2*n_complex

            rep = 2*np.random.random_sample((n_double,)) - 1
            real = 2*np.random.random_sample((n_real,)) - 1
            poles = []
            if n_complex != 0:
                for i in range(n_complex):
                    mag = np.random.random_sample()
                    comp = mag * cmath.exp(complex(0, np.pi * np.random.random_sample()))
                    re = comp.real
                    im = comp.imag
                    poles.append(np.array([[re, im], [-im, re]]))
            if n_integrator != 0:
                poles.append(np.eye(n_integrator))
            if n_double != 0:
                for pole in rep:
                    poles.append(np.eye(2)*pole)
            if n_real != 0:
                poles.append(np.diag(real))

            t = orth(np.random.random_sample((n, n)))
            self.a = np.linalg.lstsq(t, block_diag(*poles), rcond=None)[0] @ t

            self.b = np.random.random_sample((n, m))
            mask = np.random.random_sample((n, m)) < 0.75
            zero_col = np.all(np.logical_not(mask), axis=0, keepdims=True)
            self.b = self.b*(mask+np.matlib.repmat(zero_col, n, 1))
        else:
            n_unstable = np.int(1 + np.sum(np.random.random_sample((n - 1,)) < 0.1))
            n_double = np.int(np.floor(np.sum(np.random.random_sample((n - n_unstable,)) < 0.05) / 2))
            n_complex = np.int(np.floor(np.sum(np.random.random_sample((n - n_unstable - 2 * n_double,)) < 0.5) / 2))
            n_real = n - n_unstable - 2 * n_double - 2 * n_complex

            unstable = np.random.uniform(1.01, 2, n_unstable)
            for k in range(n_unstable):
                if np.random.random_sample() < 0.5:
                    unstable[k] *= -1

            rep = 2*np.random.random_sample((n_double,)) - 1
            real = 2*np.random.random_sample((n_real,)) - 1
            poles = []
            if n_complex != 0:
                for i in range(n_complex):
                    mag = 2*np.random.random_sample() - 1
                    comp = mag * cmath.exp(complex(0, np.pi * np.random.random_sample()))
                    re = comp.real
                    im = comp.imag
                    poles.append(np.array([[re, im], [-im, re]]))
            if n_unstable != 0:
                poles.append(np.diag(unstable))
            if n_double != 0:
                for pole in rep:
                    poles.append(np.eye(2) * pole)
            if n_real != 0:
                poles.append(np.diag(real))

            t = orth(np.random.random_sample((n, n)))
            self.a = np.linalg.lstsq(t, block_diag(*poles), rcond=None)[0] @ t

            self.b = np.random.random_sample((n, m))
            mask = np.random.random_sample((n, m)) < 0.75
            zero_col = np.all(np.logical_not(mask), axis=0, keepdims=True)
            self.b = self.b * (mask + np.matlib.repmat(zero_col, n, 1))
        self.x0_mean = np.zeros((n,))
        self.x0_cov = np.eye(n) * 6
        self.state = np.random.multivariate_normal(self.x0_mean, self.x0_cov)
        self.reset_state = self.state
        self.control = [0.0]
        self.dt = dt
        logger.debug("Plant initialized\n A: %s\nB: %s", self.a, self.b, sender="StateSpacePlant")
        SimMan.process(self.state_update())

    def reset(self):
        self.state = self.reset_state

    def generate_controller(self):
        q_subsystem = np.eye(np.shape(self.a)[0])
        r_subsystem = 0.1
        dare = sp.linalg.solve_discrete_are(self.a, self.b, q_subsystem, r_subsystem)
        controller = (-np.linalg.inv(self.b.transpose() @ dare @ self.b +
                                          r_subsystem) @ self.b.transpose() @ dare @ self.a)
        logger.debug("controller generated:\n%s", controller, sender="StateSpacePlant")
        return controller

    def state_update(self):
        while True:
            self.state = np.einsum('ij,j->i', self.a, self.state) + np.einsum('ij,j->i', self.b, self.control)
            logger.debug("state updated:\n%s", self.state, sender="StateSpacePlant")
            yield SimMan.timeout(self.dt)

    def get_state(self):
        """
        Gets the plant's current state
        :return: Noisy state
        """
        mean = np.zeros((self.dim,))
        cov = np.eye(self.dim)*0.1
        return self.state + np.random.multivariate_normal(mean, cov)

    """
    Sets the current control value
    """
    def set_control(self, control: float):
        self.control[0] = control


def partition(n, k, sing):
    # Credits to 'Snakes and Coffee' from stackoverflow.com
    # n is the integer to partition, k is the length of partitions, l is the min partition element size
    if k < 1:
        raise StopIteration
    if k == 1:
        if n >= sing:
            yield (n,)
        raise StopIteration
    for i in range(sing, n+1):
        for result in partition(n-i, k-1, i):
            yield (i,)+result
