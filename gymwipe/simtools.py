"""
Module for simulation tools
"""
import logging
from typing import Generator, Any
from simpy import Environment
from simpy.events import Event, Process

logger = logging.getLogger(__name__)

class SimulationManager:
    """
    The :class:`SimulationManager` offers methods and properties for managing and accessing a SimPy simulation.

    Note:
        Do not create instances on your own. Reference the existing instance by :`simtools.SimMan` instead.
    """
    
    def __init__(self):
        self._env = None
        self.stepsPerSecond = 1000
        """int: The number of SimPy time steps per second (defaults to 1000)"""
        
    @property
    def now(self):
        """int: The current simulation time step"""
        return self.env.now
    
    @property
    def env(self):
        """simpy.Environment: The SimPy :class:`~simpy.Environment` object belonging to the current simulation"""
        if self._env is None:
            self.initEnvironment()
        return self._env

    def process(self, process: Generator[Event, None, None]) -> Process:
        """
        Registers a SimPy process (generator function yielding SimPy events) at the SimPy environment
        and returns it.

        Args:
            process: The generator function to be registered as a process
        """
        return self.env.process(process)

    def runSimulation(self, timesteps: int) -> None:
        self.env.run(until=timesteps)
        logger.info("SimulationManager: Starting simulation...")
    
    def initEnvironment(self) -> None:
        """
        Destroys the existing SimPy :class:`~simpy.Environment` (if there is one) and creates a new one.
        The next :meth:`runSimulation` call will start a new simulation.
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
        Returns a SimPy :class:`~simpy.Event` that is triggered at the time step specified by `triggerTime`.

        Args:
            triggerTime: When to trigger the :class:`~simpy.Event`
        """
        now = self.now
        if triggerTime > now:
            return self.timeout(triggerTime-now, value)
        else:
            return self.timeout(0, value)

SimMan = SimulationManager()
"""A globally accessible SimulationManager instance to be used whenever a SimPy simulation is involved"""

class SimTimePrepender(logging.LoggerAdapter):
    """
    A :class:`~logging.LoggerAdapter` that prepends the current simulation time step
    (fetched by requesting :attr:`SimMan.now`) to any log message sent.

    Examples:
        The following command sets up a :class:`~logging.Logger` that prepends simulation time:
        ::

            logger = SimTimePrepender(logging.getLogger(__name__))
        
    """
    def __init__(self, logger: logging.Logger):
        """
        Args:
            logger: The :class:`~logging.Logger` to be wrapped by the SimTimePrepender LoggerAdapter
        """
        super(SimTimePrepender, self).__init__(logger, {})

    def process(self, msg, kwargs):
        """Prepends "[Time step: x]"to `message`, with x being the current time step."""
        return "[Time step: {}] {}".format(SimMan.now, msg), kwargs
