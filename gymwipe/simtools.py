"""
Module for simulation tools
"""
import logging
from collections import deque
from typing import Any, Callable, Generator, Tuple, Union

from simpy import Environment
from simpy.events import Event, Process


class SimulationManager:
    """
    The :class:`SimulationManager` offers methods and properties for managing and accessing a SimPy simulation.

    Note:
        Do not create instances on your own. Reference the existing instance by :`simtools.SimMan` instead.
    """
    
    def __init__(self):
        self._env = None
    
    stepsPerSecond = 1000
    """int: The number of SimPy time steps per simulated second"""

    clockFreq = 1000
    """int: The frequency of a network card's clock [1/time step]"""

    timeSlotSize = 1
    """int: The number of time steps for one time slot (slotted time)"""
    
    def clockTick(self):
        """
        Returns a SimPy timeout event with a duration of ``1/clockFreq``.
        """
        return self.timeout(1/self.clockFreq)
    
    def nextTimeSlot(self):
        """
        Returns a SimPy timeout event that is scheduled for the beginning of the next time slot.
        A time slot starts whenever ``now % timeSlotSize`` is ``0``.
        """
        return self.timeout(self.timeSlotSize - (self.now % self.timeSlotSize))

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
        Registers a SimPy process (generator yielding SimPy events) at the SimPy environment
        and returns it.

        Args:
            process: The generator function to be registered as a process
        """
        return self.env.process(process)

    def event(self):
        """
        Creates and returns a new :class:`~simpy.Event` object belonging to the current environment.
        """
        return Event(self.env)

    def runSimulation(self, timesteps: int) -> None:
        self.env.run(until=self.now + timesteps)
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
    
    def triggerAfterTimeout(self, event: Event, timeout: float, value: Any = None) -> None:
        """
        Calls ``succeed(value)`` on the `event` after the simulated time specified in `timeout` has passed.
        If the event has already been triggered by then, no action is taken.
        """
        def callback(caller):
            if not event.triggered:
                event.succeed(value)
        timeoutEvent = self.timeout(timeout)
        timeoutEvent.callbacks.append(callback)

SimMan = SimulationManager()
"""A globally accessible SimulationManager instance to be used whenever a SimPy simulation is involved"""

class SimTimePrepender(logging.LoggerAdapter):
    """
    A :class:`~logging.LoggerAdapter` that prepends the current simulation time
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
        """Prepends "[Time: x]"to `message`, with x being the current simulation time."""
        return "[Time: {}] {}".format(SimMan.now, msg), kwargs

logger = SimTimePrepender(logging.getLogger(__name__))

def ensureType(input: Any, validTypes: Union[type, Tuple[type]], caller: Any) -> None:
    """
    Checks whether `input` is an instance of the type / one of the types provided as `validTypes`.
    If not, raises a :class:`TypeError` with a message containing the string representation of `caller`.

    Args:
        input: The object for which to check the type
        validTypes: The type / tuple of types to be allowed
        caller: The object that (on type mismatch) will be mentioned in the error message.
    
    Raises:
        TypeError: If the type of `input` mismatches the type(s) specified in `validClasses`
    """
    if not isinstance(input, validTypes):
        raise TypeError("{}: Got object of invalid type {}. Expected type(s): {}".format(caller, type(input), validTypes) )

class Notifier:
    """
    A class implementing the observer pattern.
    A :class:`Notifier` can be triggered providing a value.
    Both callback functions and SimPy generators can be subscribed.
    Every time the :class:`Notifier` is triggered, it will run its
    callback methods and trigger the execution of the subscribed SimPy generators.
    Aditionally, SimPy generators can wait for a :class:`Notifier` to be
    triggered by yielding its :attr:`event`.
    """

    def __init__(self, name: str):
        self._name = name
        self._event = None
        self._callbacks = set()
        self._processExecutors = {}
    
    def subscribeCallback(self, callback: Callable[[Any], None]) -> None:
        """
        Adds the passed callable to the set of callback functions.
        Thus, when the notifier gets triggered, the callable will be invoked passing
        the value that the notifier was triggered with.
        """
        self._callbacks.add(callback)

    def unsubscribeCallback(self, callback: Callable[[Any], None]) -> None:
        """
        If the passed callable is contained in the set of callback functions,
        this method will remove it.
        """
        self._callbacks.remove(callback)
    
    def subscribeProcess(self, process: Generator[Event, Any, None], blocking=True, queued=False):
        """
        Makes the SimPy environment process the passed generator function when
        :attr:`trigger` is called. The value passed to :attr:`trigger` will also
        be passed to the generator function.

        Args:
            blocking: If set to ``False``, only one instance of the generator
                will be processed at a time. Thus, if :attr:`trigger` is called
                while the SimPy process started by an earlier call has not terminated,
                no action is taken.
            queued: If blocking is ``True`` and queued is ``False``, a :attr:`trigger` call
                while an instance of the generator is still active will not result in a new generator instance.
                If queued is set to ``True`` instead, the values of those :attr:`trigger` calls
                will be queued and as long as the queue is not empty, a new generator instance
                with a queued value will be created every time a previous instance has terminated.
        """

        if process in self._processExecutors:
            logger.warn("%s: Generator function %s was already subscribed! Ignoring the call.", self, process)
        else:
            # creating an executor function that will be called whenever trigger is called
            def executor(value: Any) -> None:
                if executor.running:
                    if blocking:
                        executor.queue.append(value)
                    else:
                        # start a new process
                        SimMan.process(process(value))
                else:
                    executor.running = True
                    event = SimMan.process(process(value))
                    if queued:
                        def executeNext(prevProcessReturnValue: Any) -> None:
                            # callback for running the next process from the queue
                            if len(executor.queue) > 0:
                                event = SimMan.process(process(executor.queue.popleft()))
                                event.callbacks.append(executeNext)
                            else:
                                executor.running = False
                        event.callbacks.append(executeNext)

            executor.running = False
            if blocking:
                executor.queue = deque()
            self._processExecutors[process] = executor
    
    def trigger(self, value: Any) -> None:
        """
        Triggers the :class:`Notifier`.
        This runs the callbacks, makes the :attr:`Notifier.event` succeed,
        and schedules the SimPy generators for processing.
        """
        for c in self._callbacks:
            c(value)
        for executor in self._processExecutors.values():
            executor(value)
        if self._event is not None:
            self._event.succeed(value)
            self._event = None
    
    @property
    def event(self):
        if self._event is None:
            self._event = SimMan.event()
        return self._event
    
    @property
    def name(self):
        """
        str: The notifier's name as it has been passed to the constructor
        """
        return self._name
    
    def __str__(self):
        return "Notifier('{}')".format(self.name)
