"""
Module for simulation tools
"""
import itertools
import logging
from collections import defaultdict, deque
from numbers import Number
from typing import (Any, Callable, DefaultDict, Dict, Generator, Set, Tuple,
                    Union)

from simpy import Environment
from simpy.rt import RealtimeEnvironment
from simpy.events import Event, Process

from gymwipe.utility import ownerPrefix


class SimulationManager:
    """
    The :class:`SimulationManager` offers methods and properties for managing
    and accessing a SimPy simulation.

    Note:
        Do not create instances on your own. Reference the existing instance by
        :attr:`SimMan` instead.
    """
    
    def __init__(self):
        self._env = None
    
    def nextTimeSlot(self, timeSlotLength: float) -> Event:
        """
        Returns a SimPy timeout event that is scheduled for the beginning of the
        next time slot. A time slot starts whenever `now` % `timeSlotLength` is
        ``0``.

        Args:
            timeSlotLength: The time slot length in seconds
        """
        return self.timeout(timeSlotLength - (self.now % timeSlotLength))

    @property
    def now(self):
        """int: The current simulation time step"""
        return self.env.now
    
    @property
    def env(self):
        """
        simpy.core.Environment: The SimPy :class:`~simpy.core.Environment`
        object belonging to the current simulation
        """
        if self._env is None:
            self.initEnvironment()
        return self._env

    def process(self, process: Generator[Event, None, None]) -> Process:
        """
        Registers a SimPy process (generator yielding SimPy events) at the SimPy
        environment and returns it.

        Args:
            process: The generator function to be registered as a process
        """
        return self.env.process(process)

    def event(self):
        """
        Creates and returns a new :class:`~simpy.events.Event` object belonging to the
        current environment.
        """
        return Event(self.env)

    def runSimulation(self, until: Union[int, float, Event]) -> None:
        """
        Runs the simulation (or continues running it) until the amount of
        simulated time specified by `until` has passed (with `until` being a
        :class:`float`) or `until` is triggered (with `until` being an
        :class:`Event`).
        """
        logger.info("SimulationManager: Running simulation...")
        if not isinstance(until, Event):
            assert isinstance(until, Number)
            until = self.now + until
        self.env.run(until)
    
    def initEnvironment(self) -> None:
        """
        Creates a new :class:`~simpy.core.Environment`.
        """
        self.setEnvironment()
    
    def setEnvironment(self, environment: Environment = None):
        """
        Sets the wrapped SimPy environment. If no environment instance is
        provided, a new :class:`simpy.core.Environment` will be created.
        """
        if environment is None:
            self._env = Environment()
        else:
            self._env = environment
        logger.debug("SimulationManager: Environment was set")
    
    def timeout(self, duration: float, value: Any = None) -> Event:
        """
        Shorthand for env.timeout(duration, value)
        """
        return self.env.timeout(duration, value)
    
    def timeoutUntil(self, triggerTime: float, value: Any = None) -> Event:
        """
        Returns a SimPy :class:`~simpy.events.EventEvent` that succeeds at the simulated
        time specified by `triggerTime`.

        Args: triggerTime: When to trigger the :class:`~simpy.events.Event` value: The
            value to call :meth:`~simpy.events.Event.succeed` with
        """
        now = self.now
        if triggerTime > now:
            return self.timeout(triggerTime-now, value)
        else:
            return self.timeout(0, value)
    
    def triggerAfterTimeout(self, event: Event, timeout: float, value: Any = None) -> None:
        """
        Calls :meth:`~simpy.events.Event.succeed` on the `event` after the simulated
        time specified in `timeout` has passed. If the event has already been
        triggered by then, no action is taken.
        """
        def callback(caller):
            if not event.triggered:
                event.succeed(value)
        timeoutEvent = self.timeout(timeout)
        timeoutEvent.callbacks.append(callback)

SimMan = SimulationManager()
"""
A globally accessible :class:`SimulationManager` instance to be used whenever the
SimPy simulation is involved
"""

class SourcePrepender(logging.LoggerAdapter):
    """
    A :class:`~logging.LoggerAdapter` that prepends the string representation of
    a provided object to log messages.

    Examples:
        The following command sets up a :class:`~logging.Logger` that
        prepends message sources:
        ::

            logger = SourcePrepender(logging.getLogger(__name__))

        Assuming `self` is the object that logs a message, it could prepend `str(self)`
        to a message like this:
        ::

            logger.info("Something happened", sender=self)
        
        If `str(self)` is ``myObject``, this example would result in the log message
        "myObject: Something happened".


    """
    def __init__(self, logger: logging.Logger):
        """
        Args:
            logger: The :class:`~logging.Logger` instance to be wrapped by the
                SourcePrepender :class:`~logging.LoggerAdapter`
        """
        super(SourcePrepender, self).__init__(logger, {})

    def process(self, msg, kwargs):
        """
        If a `sender` keyword argument is provided, prepends "`obj`: " to `msg`,
        with `obj` being the string representation of the `sender` keyword
        argument.
        """
        if "sender" in kwargs:
            sender = kwargs.pop("sender")
            msg = str(sender) + ": " + msg
        return msg, kwargs

class SimTimePrepender(SourcePrepender):
    """
    A :class:`~logging.LoggerAdapter` that prepends the current simulation time
    (fetched by requesting :attr:`SimMan.now`) to any log message sent.
    Additionally, the `sender` keyword argument can be used for logging calls,
    which also prepends a sender to messages like explained in
    :class:`SourcePrepender`.

    Examples:
        The following command sets up a :class:`~logging.Logger` that
        prepends simulation time:
        ::

            logger = SimTimePrepender(logging.getLogger(__name__))

    """
    def __init__(self, logger: logging.Logger):
        """
        Args:
            logger: The :class:`~logging.Logger` instance to be wrapped by the
                SimTimePrepender :class:`~logging.LoggerAdapter`
        """
        super(SimTimePrepender, self).__init__(logger)

    def process(self, msg, kwargs):
        """
        Prepends "[Time: `x`]" to `msg`, with `x` being the current
        simulation time. Additionally, if a `sender` argument is provided,
        str(`sender`) is also prepended to the simulation time.
        """
        msg, kwargs = super(SimTimePrepender, self).process(msg, kwargs)
        return "[Time: {:12f}] {}".format(SimMan.now, msg), kwargs

logger = SimTimePrepender(logging.getLogger(__name__))

def ensureType(input: Any, validTypes: Union[type, Tuple[type]], caller: Any) -> None:
    """
    Checks whether `input` is an instance of the type / one of the types
    provided as `validTypes`. If not, raises a :class:`TypeError` with a message
    containing the string representation of `caller`.

    Args:
        input: The object for which to check the type
        validTypes: The type / tuple of types to be allowed
        caller: The object that (on type mismatch) will be mentioned in the
            error message.
    
    Raises:
        TypeError: If the type of `input` mismatches the type(s) specified in
            `validClasses`
    """
    if not isinstance(input, validTypes):
        raise TypeError("{}: Got object of invalid type {}. Expected type(s): {}".format(caller, type(input), validTypes) )

class Notifier:
    """
    A class implementing the observer pattern. A :class:`Notifier` can be
    triggered providing a value. Both callback functions and SimPy generators
    can be subscribed. Every time the :class:`Notifier` is triggered, it will
    run its callback methods and trigger the execution of the subscribed SimPy
    generators. Aditionally, SimPy generators can wait for a :class:`Notifier`
    to be triggered by yielding its :attr:`event`.
    """

    def __init__(self, name: str = "", owner: Any = None):
        """
        Args:
            name: A string to identify the :class:`Notifier` instance (e.g.
                among all other :class:`Notifier` instances of the owner object)
            owner: The object that provides the :class:`Notifier` instance
        """
        self._name = name
        self.owner = owner
        self._event = None

        # Callbacks
        # A priority -> Set[Callable] defaultdict for callbacks:
        self._priorityToCallbacksDict: DefaultDict[int, Set[Callable[[Any], None]]] = defaultdict(set)
        self._callbackToPriorityDict: Dict[Callable[[Any], None], int] = {}
        self._sortedCallbacks = [] # List of callbacks sorted by their priority

        # SimPy generators
        self._processExecutors = {}
    
    def subscribeCallback(self, callback: Callable[[Any], None], priority: int = 0) -> None:
        """
        Adds the passed callable to the set of callback functions. Thus, when
        the :class:`Notifier` gets triggered, the callable will be invoked
        passing the value that the :class:`Notifier` was triggered with.

        Note:
            A callable can only be added once, regardless of its priority.

        Args:
            callback: The callable to be subscribed
            priority: If set, the callable is guaranteed to be invoked only
                after every callback with a higher priority value has been executed.
                Callbacks added without a priority value are assumed to have
                priority `0`.
        """
        # Every callback is only allowed to be added once
        assert callback not in self._callbackToPriorityDict

        self._callbackToPriorityDict[callback] = priority

        # Add the callback to the set belonging to its priority
        priorityCallbacks = self._priorityToCallbacksDict[priority]
        priorityCallbacks.add(callback)

        self._updateSortedCallbacks()
    
    def unsubscribeCallback(self, callback: Callable[[Any], None]):
        """
        Removes the passed callable from the set of callback functions. It is
        thus not triggered anymore by this :class:`Notifier`.

        Args:
            callback: The callable to be removed
        """
        if callback in self._callbackToPriorityDict:
            priority = self._callbackToPriorityDict.pop(callback)
            self._priorityToCallbacksDict[priority].remove(callback)
        self._updateSortedCallbacks()
    
    def _updateSortedCallbacks(self):
        """
        Rebuilds the sortedCallbacks list
        """
        sortedPriorities = sorted(self._priorityToCallbacksDict.keys(), reverse=True)
        self._sortedCallbacks = list(
            itertools.chain(
                *[self._priorityToCallbacksDict[p] for p in sortedPriorities]
            )
        )

    def subscribeProcess(self, process: Generator[Event, Any, None], blocking=True, queued=False):
        """
        Makes the SimPy environment process the passed generator function when
        :meth:`trigger` is called. The value passed to :meth:`trigger` will also
        be passed to the generator function.

        Args:
            blocking: If set to ``False``, only one instance of the generator
                will be processed at a time. Thus, if :meth:`trigger` is called
                while the SimPy process started by an earlier call has not
                terminated, no action is taken.
            queued: If blocking is ``True`` and queued is ``False``, a
                :meth:`trigger` call while an instance of the generator is still
                active will not result in a new generator instance. If queued is set
                to ``True`` instead, the values of those :meth:`trigger` calls will
                be queued and as long as the queue is not empty, a new generator
                instance with a queued value will be created every time a previous
                instance has terminated.
        """

        if process in self._processExecutors:
            logger.warn("Generator function %s was already subscribed! Ignoring the call.", process, sender=self)
        else:
            # creating an executor function that will be called whenever trigger is called
            def executor(value: Any) -> None:
                if not blocking:
                    # start a new process
                    SimMan.process(process(value))
                else:
                    if executor.running:
                        if not queued:
                            logger.debug("Notification with object '%s' did not lead "
                                            "to the processing of %s, since a previous SimPy "
                                            "process is still active, 'blocking' is 'True', and "
                                            "'queued' is 'False'.", value, process, sender=self)
                        else:
                            if len(executor.queue) == 10000:
                                    logger.critical("Queue of subscribed SimPy generator %s reached a "
                                                    "size of 10000. Is this intended?", process, sender=self)
                            executor.queue.append(value)
                            logger.debug("Object '%s' was appended to queue for SimPy generator %s, "
                                        "since a previous SimPy process is still active. "
                                        "Queue length: %d", value, process, len(executor.queue), sender=self)
                    else:
                        executor.running = True
                        processedEvent = SimMan.process(process(value))
                        if queued:
                            def executeNext(prevProcessReturnValue: Any) -> None:
                                # callback for running the next process from the queue
                                if len(executor.queue) > 0:
                                    nextObject = executor.queue.popleft()
                                    logger.debug("Processing generator %s "
                                                "with queued object %s.", process, nextObject, sender=self)
                                    event = SimMan.process(process(nextObject))
                                    event.callbacks.append(executeNext)
                                else:
                                    executor.running = False
                                    logger.debug("All queued jobs for generator %s were executed.", process, sender=self)
                            processedEvent.callbacks.append(executeNext)
                        else:
                            # We have to set executor.running back to False,
                            # once the generator has been processed.
                            def setRunningFlagToFalse(prevProcessReturnValue: Any):
                                executor.running = False
                            processedEvent.callbacks.append(setRunningFlagToFalse)


            executor.running = False
            if blocking:
                executor.queue = deque()
            self._processExecutors[process] = executor
    
    def trigger(self, value: Any) -> None:
        """
        Triggers the :class:`Notifier`. This runs the callbacks, makes the
        :attr:`event` succeed, and triggers the processing of subscribed SimPy
        generators.
        """
        logger.debug("Triggered with value %s", value, sender=self)
        for c in self._sortedCallbacks:
            c(value)
        for executor in self._processExecutors.values():
            executor(value)
        if self._event is not None:
            self._event.succeed(value)
            self._event = None
    
    @property
    def event(self):
        """
        :class:`~simpy.events.Event`: A SimPy event that succeeds when the
        :class:`Notifier` is triggered
        """
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
        return "{}Notifier('{}')".format(ownerPrefix(self.owner), self.name)
