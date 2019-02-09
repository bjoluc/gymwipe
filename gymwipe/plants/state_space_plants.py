from gymwipe.plants.core import Plant
import numpy as np
import math
import logging
from gymwipe.simtools import SimTimePrepender, SimMan
import matlab.engine

logger = SimTimePrepender(logging.getLogger(__name__))


class MatlabPendulum(Plant):
    def __init__(self, m, M, l, g, dt):
        self.engine = matlab.engine.start_matlab()
        self.m = m
        self.M = M
        self.l = l
        self.g = g
        self.dt = dt
        self.u = 0
        self.state = [0, math.pi, 0, 0]

        self._lastUpdateSimTime = 0
        # linearisiert um obere Ruhelage
        self.engine.workspace['M'] = self.M
        self.engine.workspace['m'] = self.m
        self.engine.workspace['l'] = self.l
        self.engine.workspace['g'] = self.g
        self.engine.eval('A = [0,0,1,0;0,0,0,1;0,m*g/M,0,0;0,(M+m)*g/(l*M),0,0];', nargout=0)
        self.engine.eval('b = [0;0;1/M;1/(l*M)];', nargout=0)
        self.engine.eval('C=eye(4);', nargout=0)
        self.engine.eval('d=zeros(4,1);', nargout=0)
        self.engine.eval('sys=ss(A,b,C,d);', nargout=0)
        self.engine.eval('sysd = c2d(sys, ' + self.dt.__str__() + ');', nargout=0)
        A = self.engine.workspace['A']
        logger.debug("System created, A: %s", A.__str__(), sender=self)

    def impulse(self):
        self.engine.eval('hold on\nfigure(1)\nstep(sysd,\'--\', sys, \'-\', 10)', nargout=0)

    def system_reaction(self):
        self.engine.eval('dt = 0.01', nargout=0)
        self.engine.workspace['t'] = '0:dt:6;'
        self.engine.eval('u=zeros(1,length(t));', nargout=0)
        self.engine.eval('XLin=lsim(sys,u,t)\';', nargout=0)
        self.engine.eval('figure(1)'
                         'hold on'
                         'plot(t,XLin(1,:),\'b--\')'
                         'plot(t,XLin(2,:),\'r--\')'
                         'plot(t,XLin(3,:),\'g--\')'
                         'plot(t,XLin(4,:),\'k--\')', nargout=0)

    def get_angle(self) -> float:
        logger.debug("angle requested", sender=self)
        self.update_state()
        return self.state[1]

    def get_angle_rate(self):
        self.update_state()
        return self.state[3]

    def get_wagon_pos(self) -> float:
        self.update_state()
        return self.state[0]

    def get_wagon_velocity(self) -> float:
        self.update_state()
        return self.state[2]

    def set_motor_velocity(self, velocity: float):
        self.update_state()
        self.u = velocity

    def update_state(self):
        """
        Updates the plant's state according to the
        current simulation time.
        """
        now = round(SimMan.now, 9)
        difference = now - self._lastUpdateSimTime
        if difference > self.dt:
            self.engine.workspace['t'] = '0:dt:' + difference.__str__()
            self.engine.eval('lsim(')
            self._lastUpdateSimTime = now
            logger.debug("State updated", sender=self)

    def _state_updater(self):
        """
        A SimPy process that regularly performs ODE time steps when no ODE time step
        was previously taken within maxStepSize
        """
        while True:
            yield SimMan.timeout(self.dt)
            self.updateState()
