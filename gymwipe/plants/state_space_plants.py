from gymwipe.plants.core import StateSpacePlant
import numpy as np
from math import sin, cos, pi
from numpy import matrix, array
from scipy import signal as sg
import logging
import math
from scipy.signal import StateSpace
import matplotlib.pyplot as plt
from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class RCL(StateSpacePlant):
    def __init__(self, c, r, l):
        a_cont = np.array([[0, 1/c],
                           [-1/l, -r/l]])
        b_cont = np.array([[0], [1/l]])
        c_cont = np.array([1, 0])
        d_cont = 0
        disc_state_space = sg.cont2discrete((a_cont, b_cont, c_cont, d_cont), dt=0.001)
        super(RCL, self).__init__(StateSpace(disc_state_space[0], disc_state_space[1], disc_state_space[2],
                                             disc_state_space[3], dt=disc_state_space[4]))


class LinearInvertedPendulum(StateSpacePlant):
    def __init__(self, m, M, g, l):
        a_cont = np.array([[0, 0, 1, 0],
                           [0, 0, 0, 1],
                           [0, (m*g)/M, 0, 0],
                           [0, (-(M+m)*g)/(l*m), 0, 0]])
        b_cont = np.array([[0], [0], [1/M], [(-1)/(l*M)]])
        c_cont = np.array([0, 1, 0, 0])
        d_cont = 0
        dt = 0.001
        disc_state_space = sg.cont2discrete((a_cont, b_cont, c_cont, d_cont), dt=dt)

        super(LinearInvertedPendulum, self).__init__(StateSpace(disc_state_space[0], disc_state_space[1],
                                                                disc_state_space[2], disc_state_space[3],
                                                                dt=disc_state_space[4]), dt)

    def get_impulse_response(self, n):
        imp_response = sg.dstep(self._state_space_form, [0, math.pi, 0, 0], n=n)
        angles = imp_response[1][0]
        logger.debug("angles: %s, len: %d", angles.__str__(), len(angles), sender=self)
        for i in range(len(angles)):
            imp_response[1][0][i] = math.degrees(imp_response[1][0][i])
        logger.debug(" impulse response is %s", imp_response.__str__(), sender=self)
        plt.close()
        plt.plot(imp_response[0], imp_response[1][0])
        plt.xlabel('time')
        plt.ylabel('pendulum angle')
        plt.show()
        return imp_response


class Pendulum(StateSpacePlant):

    def __init__(self, dt, init_conds= None):
        self.M = .6  # mass of cart+pendulum
        self.m = .3  # mass of pendulum
        self.Km = 2  # motor torque constant
        self.Kg = .01  # gear ratio
        self.R = 6  # armiture resistance
        self.r = .01  # drive radiu3
        self.K1 = self.Km * self.Kg / (self.R * self.r)
        self.K2 = self.Km ** 2 * self.Kg ** 2 / (self.R * self.r ** 2)
        self.l = .3  # length of pendulum to CG
        self.I = 0.006  # inertia of the pendulum
        self.L = (self.I + self.m * self.l ** 2) / (self.m * self.l)
        self.g = 9.81  # gravity
        self.Vsat = 20.  # saturation voltage

        self.A11 = -1 * self.Km ** 2 * self.Kg ** 2 / ((self.M - self.m * self.l / self.L) * self.R * self.r ** 2)
        self.A12 = -1 * self.g * self.m * self.l / (self.L * (self.M - self.m * self.l / self.L))
        self.A31 = self.Km ** 2 * self.Kg ** 2 / (self.M * (self.L - self.m * self.l / self.M) * self.R * self.r ** 2)
        self.A32 = self.g / (self.L - self.m * self.l / self.M)
        self.A = array([
            [0, 1, 0, 0],
            [0, self.A11, self.A12, 0],
            [0, 0, 0, 1],
            [0, self.A31, self.A32, 0]
        ])

        self.B1 = self.Km * self.Kg / ((self.M - self.m * self.l / self.L) * self.R * self.r)
        self.B2 = -1 * self.Km * self.Kg / (self.M * (self.L - self.m * self.l / self.M) * self.R * self.r)

        self.B = array([
            [0],
            [self.B1],
            [0],
            [self.B2]
        ])

        self.C = array([0, 0, 1, 0])
        self.d = 0
        self.dt = dt
        #self.x = init_conds[:]
        disc_state_space = sg.cont2discrete((self.A, self.B, self.C, self.d), dt=self.dt)
        super(Pendulum, self).__init__(StateSpace(disc_state_space[0], disc_state_space[1],
                                                  disc_state_space[2], disc_state_space[3],
                                                  dt=disc_state_space[4]))

    def get_impulse_response(self, n):
        imp_response = sg.dimpulse(self._state_space_form, x0=[0, 0, pi, 0], n=n)
        angles = imp_response[1][0]
        logger.debug("angles: %s, len: %d", angles.__str__(), len(angles), sender=self)
        for i in range(len(angles)):
            imp_response[1][0][i] = math.degrees(imp_response[1][0][i])
        logger.debug(" impulse response is %s", imp_response.__str__(), sender=self)
        plt.close()
        plt.plot(imp_response[0], imp_response[1][0])
        plt.xlabel('time')
        plt.ylabel('pendulum angle')
        plt.show()
        return imp_response


class ThirdPendulum(StateSpacePlant):
    def __init__(self, dt):
        M = 0.5
        m = 0.2
        b = 0.1
        I = 0.006
        g = 9.81
        l = 0.3

        p = I*(M + m)+M*m*(l**2)

        a1 = (-(I+m*(l**2))*b)/p
        a2 = ((m**2)*g*(l**2))/p
        a3 = -(m*l*b)/p
        a4 = m*g*l*(M+m)/p
        A = array([[0, 1, 0, 0],
                   [0, a1, a2, 0],
                   [0, 0, 0, 1],
                   [0, a3, a4, 0]])
        b1 = (I+m*(l**2))/p
        b2 = m*l/p
        B = array([
            [0],
            [b1],
            [0],
            [b2]
        ])
        c = array([0, 0, 1, 0])
        d = 0
        super(ThirdPendulum, self).__init__(StateSpace(A, B, c, d), dt)

    def get_impulse_response(self, until):
        t = np.arange(0, until, self._sample_interval)
        logger.debug("t is: %s", t.__str__(), sender=self)
        imp_response = sg.impulse(self._state_space_form, T=t)
        angles = imp_response[1]
        logger.debug("angles: %s, len: %d", angles.__str__(), len(angles), sender=self)
        for i in range(len(angles)):
            imp_response[1][i] = math.degrees(imp_response[1][i])
        logger.debug(" impulse response is %s", imp_response.__str__(), sender=self)
        plt.close()
        plt.plot(imp_response[0], imp_response[1])
        plt.xlabel('time')
        plt.ylabel('pendulum angle')
        plt.show()
        return imp_response
