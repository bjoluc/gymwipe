"""
Package for simulation tools
"""
from typing import Generator
from simpy import Environment
from simpy.events import Event

class SimulationManager:
    """
    The Simulation Manager offers methods and properties for controlling and accessing the SimPy simulation.
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
            self.resetEnvironment()
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
    
    def resetEnvironment(self) -> None:
        """
        Destroys the existing SimPy environment (if there is one) and creates a new one.
        The next `runSimulation` call will start a new simulation.
        """
        self._env = Environment()

SimMan = SimulationManager()
