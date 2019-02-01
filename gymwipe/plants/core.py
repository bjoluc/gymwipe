"""
Core components for plant implementations.
"""
import logging
import ode
from scipy import signal
from scipy.signal import dlti, StateSpace

from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class Plant:
    """
    Plants are supposed to hold the state of a simulated plant and make it
    accessible to simulated sensors and modifyable by simulated actuators.
    The :class:`Plant` class itself does not provide any features.
    """


class StateSpacePlant(Plant):
    def __init__(self, state_space: StateSpace, dt ):
        self._state_space_form = state_space
        self._sample_interval = dt
        self.input = 0
        logger.debug("Plant initialized. Sample interval: %f, State space form: %s", self._sample_interval,
                     self._state_space_form.__str__(), sender=self)

    def update_state(self):
        pass

    def get_output(self):
        pass

    def get_sample_interval(self):
        return self._sample_interval

    def set_input(self, u: float):
        self.input = u
        self.update_state()


class OdePlant(Plant):
    """
    A :class:`Plant` implementation that interacts with an ODE world object: It
    offers an :meth:`updateState` method that makes the ODE world simulate
    physics for the SimPy simulation time that has passed since the most recent
    :meth:`updateState` call.
    """

    def __init__(self, world: ode.World = None):
        """
        Args:
            world: A py3ode :class:`World` object. If not provided, a new one will be
                created with gravity ``(0,-9.81,0)``.
        """
        if world is None:
            world = ode.World()
            world.setGravity((0, -9.81, 0))
        self.world = world
        self.maxStepSize = 0.01
        self._lastUpdateSimTime = SimMan.now
        SimMan.process(self._stateUpdater())

    def updateState(self):
        """
        Performs an ODE time step to update the plant's state according to the
        current simulation time.
        """
        now = SimMan.now
        # Rounding difference to nanoseconds to prevent strange ODE behavior
        difference = round(now - self._lastUpdateSimTime, 9)
        
        if difference > 0:
            self.world.step(difference)
            self._lastUpdateSimTime = now
            logger.debug("State updated", sender=self)
    
    def _stateUpdater(self):
        """
        A SimPy process that regularly performs ODE time steps when no ODE time step
        was previously taken within maxStepSize
        """
        while True:
            yield SimMan.timeout(self.maxStepSize)
            if self._lastUpdateSimTime <= SimMan.now - self.maxStepSize:
                self.updateState()


