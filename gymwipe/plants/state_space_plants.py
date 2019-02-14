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
        self.u = 0.0
        # obere Ruhelage

        self._lastUpdateSimTime = 0
        # linearisiert um obere Ruhelage
        self.engine.workspace['M'] = self.M
        self.engine.workspace['m'] = self.m
        self.engine.workspace['l'] = self.l
        self.engine.workspace['g'] = self.g
        self.engine.workspace['dt'] = self.dt
        self.engine.eval('A = [0,0,1,0;0,0,0,1;0,m*g/M,0,0;0,-(M+m)*g/(l*M),0,0];', nargout=0)
        self.engine.eval('b = [0;0;1/M;-1/(l*M)];', nargout=0)
        self.engine.eval('C=eye(4);', nargout=0)
        self.engine.eval('d=zeros(4,1);', nargout=0)
        self.engine.eval('sys=ss(A,b,C,d);', nargout=0)
        self.engine.eval('sysd = c2d(sys, dt);', nargout=0)
        self.engine.eval('x0 = zeros(4,1);\n x0(1)= 0;\nx0(2)=pi;\nx0(3)=0;\nx0(4)=0;', nargout=0)

        A = self.engine.workspace['A']
        b = self.engine.workspace['b']
        c = self.engine.workspace['C']
        d = self.engine.workspace['d']
        self.state = self.engine.workspace['x0']
        logger.debug("System created \nA: %s \nB: %s\nC: %s\nd: %s\nx0: %s",
                     A.__str__(), b.__str__(), c.__str__(), d.__str__(), self.state.__str__(), sender=self)

    def impulse(self):
        self.engine.eval('hold on\nfigure(1)\nstep(sysd,\'--\', sys, \'-\', 10)', nargout=0)

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

    def set_motor_velocity(self, velocity: float, time: float):
        self.update_state(time)
        self.u = float(velocity)
        logger.debug("motor velocity set to %s", self.u.__str__(), sender=self)

    def update_state(self, time):
        """
        Updates the plant's state according to the current simulation time.
        """
        now = time
        logger.debug("Function called at time %f", now, sender=self)
        difference = now - self._lastUpdateSimTime
        if difference > self.dt:
            self.engine.eval('ta = 0:dt:' + difference.__str__() + ';', nargout=0)
            ta = self.engine.workspace['ta']
            logger.debug("ta init done: \n%s", ta.__str__(), sender=self)
            self.engine.workspace['uakt'] = self.u
            erg = self.engine.workspace['uakt']
            logger.debug("uakt set to %s", erg.__str__(), sender=self)
            self.engine.eval('U=ones(length(ta), 1)* uakt;', nargout=0)
            U = self.engine.workspace['U']
            logger.debug("U creation done: \n%s", U.__str__(), sender=self)
            self.engine.eval('[y,t,x] = lsim(sysd,U,[],x0);', nargout=0)
            self.engine.eval('hold on\nfigure(1)\nlsim(sysd,U,[],x0);', nargout=0)
            logger.debug("lsim done", sender=self)
            y = self.engine.workspace['y']
            t = self.engine.workspace['t']
            x = self.engine.workspace['x']
            logger.debug("computed results: \ny: %s \n t: %s \n x: %s",
                         y.__str__(), t.__str__(), x.__str__(), sender=self)
            self._lastUpdateSimTime = now
            logger.debug("State updated", sender=self)

