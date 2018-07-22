"""
Contains classes for building network stack representations.
"""
import logging
import inspect
from collections import deque
from typing import Callable, Any, Union, Tuple
from simpy.events import Event
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class Gate:
    """   
    Todo:
        * finish documentation

    """

    class Port:
        """

        """

        def __init__(self, name: str = None):
            self._name = name
            self._onSendCallables = set()
            self._sendEvent = None
            self._queue = deque()
            # a queue that catches objects sent at the same simulated time
            # and makes them accessible by repeatedly yielding the sendEvent
        
        def __str__(self):
            return "Port('{}')".format(self._name)

        def _addDest(self, dest: Callable[[Any], None]) -> None:
            """
            Args:
                dest: A callback function that will be called with a message object when send is called on the Port
            """
            self._onSendCallables.add(dest)
        
        # connecting Ports with each other

        def connectTo(self, port: 'Gate.Port') -> None:
            """
            Connects this :class:`~Gate.Port` to the provided :class:`~Gate.Port`. Thus, if :meth:`send` is called on this :class:`~Gate.Port`, it will also be called on the provided :class:`~Gate.Port`.

            Args:
                port: The :class:`~Gate.Port` for the connection to be established to
            """
            self._addDest(port.send)

        # sending messages

        def send(self, message: Any):
            """
            Sends the object provided as `message` to all connected ports and registered callback functions (if any).
            """
            logger.debug("%s received message %s", self, message)
            self._triggerSendEvent(message)
            for send in self._onSendCallables:
                send(message)
        
        # SimPy events

        @property
        def sendEvent(self) -> Event:
            """simpy.Event: A SimPy :class:`~simpy.Event` that is triggered when :meth:`send` is called on this :class:`~Gate.Port`."""
            if self._sendEvent is None or self._sendEvent.triggered:
                # the current _sendEvent has been processed by SimPy and is outdated now
                # creating a new one
                self._sendEvent = Event(SimMan.env)
                if len(self._queue) > 0:
                    # there is a queued message, immediately triggering the event again
                    self._triggerSendEvent(self._queue.popleft())
            return self._sendEvent

        def _triggerSendEvent(self, message) -> None:
            if self._sendEvent is not None:
                if self._sendEvent.triggered:
                    self._queue.append(message)
                else:
                    self._sendEvent.succeed(message)
                    logger.debug("sendEvent of %s was triggered (value: %s)", self, message)
    

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None):
        """
        Args:
            inputCallback: A callback function that will be used when a message is sent to the input Port.
        """
        
        self._name = name
        self.input = self.Port(name + ".input")
        if callable(inputCallback):
            self.input._addDest(inputCallback)
        self.output = self.Port(name + ".output")
    
    def __str__(self):
        return "Gate('{}')".format(self._name)

    # Connecting Gates

    def connectOutputTo(self, port: Port) -> None:
        """
        Connects this Gate's output Port to the provided Port.

        Args:
            port: The port to connect this Gate's output to
        """
        if not isinstance(port, Gate.Port):
            raise TypeError("Expected Port, got {}. Use .input or .output to access a Gate's ports.".format(type(port)))
        self.output.connectTo(port)
    
    def connectInputTo(self, port: Port) -> None:
        """
        Connects this Gate's input Port to the provided Port.

        Args:
            port: The port to connect this Gate's input to
        """
        self.input.connectTo(port)
    
    def biConnectWith(self, gate: 'Gate') -> None:
        """
        Shorthand for
        ::
        
            self.connectOutputTo(gate.input)
            gate.connectOutputTo(self.input)

        Args:
            gate: The `Gate` for the bidirectional connection to be established to
        """
        self.connectOutputTo(gate.input)
        gate.connectOutputTo(self.input)
    
    def biConnectProxy(self, gate: 'Gate') -> None:
        """
        Shorthand for
        ::
        
            self.connectOutputTo(gate.output)
            gate.connectInputTo(self.input)
        
        Note:
            The term `Proxy` is used for a gate that redirects its input
            to another gate's input.

        Args:
            gate: The `Gate` to be connected as a proxy
        """
        self.connectOutputTo(gate.output)
        gate.connectInputTo(self.input)
    
    # SimPy events vor message handling
    
    @property
    def receivesMessage(self):
        """Event: A SimPy :class:`~simpy.Event` that is triggered when the input :class:`~Gate.Port` receives a message"""
        return self.input.sendEvent
    
class Module:
    """
    Attributes:
        gates(Dict[str, Gate]): The Module's outer Gates
        subModules(Dict[str, Module]): The Module's nested Modules
    """

    def __init__(self, name: str):
        self._name = name
        self.gates = {}
        self.subModules = {}

        # register gate listeners as SimPy processes
        # gate listeners are those methods with isGateListener set to true
        for listener in [getattr(self, a) for a in dir(self) if not a.startswith("__")
                            and getattr(getattr(self, a), "isGateListener", False)]:
            SimMan.process(listener())
    
    def __str__(self):
        return "{} '{}'".format(self.__class__.__name__, self._name)
    
    def _addGate(self, name: str, gate: Gate = None) -> None:
        """
        Adds a new :class:`Gate` to the *gates* dictionary, indexed by the name passed.
        
        Args:
            name: The name for the :class:`Gate` to be accessed by
            gate: The :class:`Gate` object to be added. If not provided, a new :class:`Gate` will be
                instantiated using a combination of the Module's name property and `name` as its name.
        """
        if name in self.gates:
            raise ValueError("A gate indexed by '{}' already exists.".format(name))
        if gate is None:
            gate = Gate("({}).{}".format(self, name))
        self.gates[name] = gate
    
    def _addSubModule(self, name: str, module: 'Module') -> None:
        if name in self.subModules:
            raise ValueError("A sub module named '%s' already exists." % str)
        self.subModules[name] = module
    
    @property
    def name(self):
        """str: The Module's name"""
        return self._name

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

class GateListener():
    """
    A decorator for both generator and non-generator methods.
    The resulting generator will be registered as a SimPy process
    that (during simulation) executes the decorated method whenever the input
    :class:`~Gate.Port` of the provided :class:`Gate` receives an object.
    The received object is provided to the decorated method as a parameter.
    If the decorated method is a generator, it will be executed as a SimPy process.

    Note:
        SimPy process registration is done in the :class:`Module` constructor.
        Thus, when using :class:`GateListener` for methods that do not belong to
        a subclass of :class:`Module`, one has to call :code:`SimMan.process(decoratedMethod())`
        at construction.

    Examples:
        A method using this decorator could look like this:

        ::

            @GateListener("myGate")
            def myGateListener(self, msg):
                # this is executed whenever self.gates["myGate"].input.receivesMessage
                # is triggered and this SimPy process is not running
                yield SimMan.timeout(1)
    
    Todo:
        * Write a unit test for this
    """

    def __init__(self, gateName: str, validTypes: Union[type, Tuple[type]]=None):
        """
        Args:
            gateName: The index of the module's :class:`Gate` to listen on
            validTypes: If not ``None``, a :class:`TypeError` will be raised when an object
                received via the specified :class:`Gate`
                is not of the :class:`type` / one of the types specified.
        """
        self.gateName = gateName
        self.validTypes = validTypes
    
    def __call__(self, method):
        isGenerator = inspect.isgeneratorfunction(method)

        def wrapper(instance):
            """
            A method which is decorated with the :class:`~gymwipe.networking.construction.GateListener`
            decorator, calling it when a specified :class:`~gymwipe.networking.construction.Gate`
            receives an object.
            If the decorated method is a generator function, it will be run as a SimPy process.
            """
            while True:
                obj = yield instance.gates[self.gateName].receivesMessage
                if self.validTypes is not None:
                    ensureType(obj, self.validTypes, instance)
                if isGenerator:
                    yield SimMan.process(method(instance, obj))
                else:
                    method(instance, obj)

        # set the isGateListener flag
        # this will make the Module constructor add it as a SimPy process
        wrapper.isGateListener = True
        
        return wrapper
