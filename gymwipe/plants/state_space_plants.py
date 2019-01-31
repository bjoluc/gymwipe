from gymwipe.plants.core import DiscreteStateSpacePlant
import numpy as np
from scipy import signal as sg
import logging
import math
from scipy.signal import StateSpace

import matplotlib.pyplot as plt
from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class RCL(DiscreteStateSpacePlant):
    def __init__(self, c, r, l):
        a_cont = np.array([[0, 1/c],
                           [-1/l, -r/l]])
        b_cont = np.array([[0], [1/l]])
        c_cont = np.array([1, 0])
        d_cont = 0
        disc_state_space = sg.cont2discrete((a_cont, b_cont, c_cont, d_cont), dt=0.001)
        super(RCL, self).__init__(StateSpace(disc_state_space[0], disc_state_space[1], disc_state_space[2],
                                             disc_state_space[3], dt=disc_state_space[4]))


class LinearInvertedPendulum(DiscreteStateSpacePlant):
    def __init__(self, m, M, g, l):
        a_cont = np.array([[0, 0, 1, 0],
                           [0, 0, 0, 1],
                           [0, (m*g)/M, 0, 0],
                           [0, (-(M+m)*g)/(l*m), 0, 0]])
        b_cont = np.array([[0], [0], [1/M], [(-1)/(l*M)]])
        c_cont = np.array([0, 1, 0, 0])
        d_cont = 0

        disc_state_space = sg.cont2discrete((a_cont, b_cont, c_cont, d_cont), dt=0.0001)

        super(LinearInvertedPendulum, self).__init__(StateSpace(disc_state_space[0], disc_state_space[1],
                                                                disc_state_space[2], disc_state_space[3],
                                                                dt=disc_state_space[4]))

    def get_impulse_response(self, n):
        imp_response = sg.dimpulse(self._state_space_form, [0, math.pi, 0, 0], n=n)
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

