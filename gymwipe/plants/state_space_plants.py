import numpy as np
import numpy.matlib
import cmath

import scipy as sp
from scipy.linalg import block_diag, orth
import logging

from gymwipe.simtools import SimTimePrepender, SimMan

logger = SimTimePrepender(logging.getLogger(__name__))


class StateSpacePlant:
    def __init__(self, n, m, dt, marginally_stable=True, name: str = "State Space Plant"):
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
        self.name = name
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

            unstable = np.random.uniform(1.01, 1.1, n_unstable)
            for k in range(n_unstable):
                if np.random.random_sample() < 0.5:
                    unstable[k] *= -1

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
        self.poles = poles
        self.x0_mean = np.zeros((n,))
        self.x0_cov = np.eye(n) * 6
        self.state = np.random.multivariate_normal(self.x0_mean, self.x0_cov)
        self.reset_state = self.state
        self.control = np.array([0.0])
        self.dt = dt
        self.q_subsystem = np.eye(np.shape(self.a)[0])
        self.r_subsystem = 0.1
        self.state_mean = np.zeros((self.dim,))
        self.state_cov = np.eye(self.dim) * 0.1
        self.control_back_to_0 = False
        self.marginally_stable = marginally_stable
        logger.debug("Plant initialized\n A: %s\nB: %s\n control: %s", self.a, self.b, self.control, sender=self.name)
        SimMan.process(self.state_update())

    def reset(self):
        self.state = self.reset_state
        self.control = np.array([0.0])

    def generate_controller(self):
        dare = sp.linalg.solve_discrete_are(self.a, self.b, self.q_subsystem, self.r_subsystem)
        if self.marginally_stable:
            controller = (-np.linalg.inv(self.b.transpose() @ dare @ self.b +
                                              self.r_subsystem) @ self.b.transpose() @ dare @ self.a)
        else:
            controller = (-np.linalg.inv(self.b.transpose() @ dare @ self.b +
                                         self.r_subsystem) @ self.b.transpose() @ dare @ self.a)
        logger.debug("controller generated: %s", controller, sender=self.name)
        return controller

    def state_update(self):
        while True:
            yield SimMan.timeout(self.dt)
            if self.control_back_to_0:
                self.control = np.array([0.0])
            self.state = np.einsum('ij,j->i', self.a, self.state) + np.einsum('ij,j->i', self.b, self.control) \
                         + np.random.multivariate_normal(self.state_mean, self.state_cov)
            logger.debug("state updated: %s", self.state, sender=self.name)
            self.control_back_to_0 = True

    def get_state(self):
        """
        Gets the plant's current state
        :return: Noisy state
        """
        return self.state

    """
    Sets the current control value
    """
    def set_control(self, control: float):
        self.control = np.array([control])
        self.control_back_to_0 = False
        logger.debug("set control to %s", self.control.__str__(), sender=self.name)
