"""
Module for simulation tools
"""
import logging
from typing import Generator, Any
from simpy import Environment
from simpy.events import Event

logger = logging.getLogger(__name__)

class SimulationManager:
    """
    The Simulation Manager offers methods and properties for managing and accessing a SimPy simulation.
    Note: Do not create instances on your own. Use the existing simtools.SimMan instance instead.
    """
    
    _env = None

    @property
    def now(self):
        """int: The current simulation time step"""
        return self.env.now
    
    @property
    def env(self):
        """simpy.Environment: The SimPy environment object belonging to the current simulation"""
        if self._env is None:
            self.initEnvironment()
        return self._env

    def registerProcess(self, process: Generator[Event, None, None]) -> None:
        """
        Registers a SimPy process (generator function yielding events) at the SimPy environment.

        Args:
            process: The generator function to be registered as a process
        """
        self.env.process(process)

    def runSimulation(self, timesteps: int) -> None:
        self.env.run(until=timesteps)
        logger.info("SimulationManager: Starting simulation...")
    
    def initEnvironment(self) -> None:
        """
        Destroys the existing SimPy environment (if there is one) and creates a new one.
        The next `runSimulation` call will start a new simulation.
        """
        self._env = Environment()
        logger.debug("SimulationManager: Initialized environment")
    
    def timeout(self, steps: int, value: Any = None) -> Event:
        """
        Shorthand for env.timeout(steps, value)
        """
        return self.env.timeout(steps, value)
    
    def timeoutUntil(self, triggerTime: int, value: Any = None) -> Event:
        """
        Returns a SimPy event that is triggerd at the time step specified by `triggerTime`.

        Args:
            triggerTime: When to trigger the event
        """
        now = self.now
        if triggerTime > now:
            return self.timeout(triggerTime-now, value)
        else:
            return self.timeout(0, value)

SimMan = SimulationManager()
"""A globally accessible SimulationManager instance to be used whenever a SimPy simulation is envolved"""

class SimTimePrepender(logging.LoggerAdapter):
    """
    A LoggerAdapter that prepends the current simulation time step
    (fetched by requesting SimMan.now) to any log message sent via `logger`.
    """
    def __init__(self, logger: logging.Logger):
        """
        Args:
            logger: The `Logger` to be wrapped by the SimTimePrepender LoggerAdapter
        """
        super(SimTimePrepender, self).__init__(logger, {})

    def process(self, msg, kwargs):
        return "[Time step: {}] {}".format(SimMan.now, msg), kwargs
