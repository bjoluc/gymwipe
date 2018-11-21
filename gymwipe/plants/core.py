"""
Todo:
    Documentation
"""

import ode
from gymwipe.simtools import SimMan


class Plant:
    """

    """

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
            world.setGravity((0,-9.81,0))
        self.world = world
        self._lastUpdateSimTime = SimMan.now

    def updateState(self):
        now = SimMan.now
        # Rounding difference to nanoseconds to prevent strange ODE behavior
        difference = round(now - self._lastUpdateSimTime, 9)
        
        if difference > 0:
            self.world.step(difference)
            self._lastUpdateSimTime = now
