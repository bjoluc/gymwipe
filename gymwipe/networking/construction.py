"""
Contains classes for building network stack representations.
"""
import logging, inspect
from collections import deque
from typing import Callable, Any, Union, Tuple
from functools import wraps
from simpy.events import Event
from gymwipe.simtools import SimMan, SimTimePrepender, ensureType

logger = SimTimePrepender(logging.getLogger(__name__))

class Port:
    """
    Todo:
        * documentation

    """

    def __init__(self, name: str = None, buffered: bool = True):
        self._name = name
        self._onSendCallables = set()
        self._sendEvent = None
    
    def __str__(self):
        return "Port('{}')".format(self._name)

    def addCallback(self, callback: Callable[[Any], None]) -> None:
        """
        Args:
            callback: A callback function that will be called with a message
                object when send is called on the Port
        """
        self._onSendCallables.add(callback)
    
    # connecting Ports with each other

    def connectTo(self, port: 'Port') -> None:
        """
        Connects this :class:`Port` to the provided :class:`Port`.
        Thus, if :meth:`send` is called on this :class:`Port`, it will
        also be called on the provided :class:`Port`.

        Args:
            port: The :class:`Port` for the connection to be established to
        """
        self.addCallback(port.send)

    # sending messages

    def send(self, message: Any):
        """
        Sends the object provided as `message` to all connected ports
        and registered callback functions (if any).
        """
        logger.debug("%s received message %s", self, message)
        for send in self._onSendCallables:
            send(message)
        self._triggerSendEvent(message)
    
    # SimPy events

    @property
    def receivesMessage(self) -> Event:
        """
        simpy.Event: A SimPy :class:`~simpy.Event` that is triggered
            when :meth:`send` is called on this :class:`Port`.
        """
        logger.debug("sendEvent of %s was requested", self)
        if self._sendEvent is None or self._sendEvent.triggered:
            # the current _sendEvent has been processed by SimPy and is outdated now
            # creating a new one
            self._sendEvent = Event(SimMan.env)
        return self._sendEvent

    def _triggerSendEvent(self, message) -> None:
        if self._sendEvent is not None and not self._sendEvent.triggered:
            # Only triggering the send event if it was requested and has not been triggered yet.
            self._sendEvent.succeed(message)
            logger.debug("sendEvent of %s was triggered (value: %s)", self, message)

class Gate:
    """   
    Todo:
        * documentation

    """

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None):
        """
        Args:
            inputCallback: A callback function that will be used when a message is sent to the input Port.
        """
        
        self._name = name
        self.input = Port(name + ".input")
        if callable(inputCallback):
            self.input.addCallback(inputCallback)
        self.output = Port(name + ".output")
    
    def __str__(self):
        return "Gate('{}')".format(self._name)

    # Connecting Gates

    def connectOutputTo(self, port: Port) -> None:
        """
        Connects this Gate's output Port to the provided Port.

        Args:
            port: The port to connect this Gate's output to
        """
        if not isinstance(port, Port):
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
            The term `Proxy` is used for a gate that passes its input
            to another gate's input.

        Args:
            gate: The `Gate` to be connected as a proxy
        """
        self.connectOutputTo(gate.output)
        gate.connectInputTo(self.input)
    
    # SimPy events for message handling
    
    @property
    def receivesMessage(self):
        """
        Event: A SimPy :class:`~simpy.Event` that is triggered when
        the input :class:`Port` receives a message
        """
        return self.input.receivesMessage
    
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

class GateListener:
    """
    A decorator for both generator and non-generator methods.
    The resulting generator will be registered as a SimPy process
    that (during simulation) executes the decorated method whenever the input
    :class:`Port` of the provided :class:`Gate` receives an object.
    The received object is provided to the decorated method as a parameter.
    If the decorated method is a generator, it will be executed as a SimPy process.

    Note:
        SimPy process registration is done in the :class:`Module` constructor.
        Thus, when using :class:`GateListener` for methods that do not belong to
        a subclass of :class:`Module`, one has to call :code:`SimMan.process(decoratedMethod())`
        in the subclass constructor.

    Examples:
        A method using this decorator could look like this:

        ::

            @GateListener("myGate")
            def myGateListener(self, msg):
                # this is executed whenever self.gates["myGate"].input.receivesMessage
                # is triggered and this SimPy process is not running
                yield SimMan.timeout(1)
    
    Todo:
        * update documentation to reference GateListener.setup
        * Add an example for the buffered flag
    """

    def __init__(self, gateName: str, validTypes: Union[type, Tuple[type]]=None, buffered=False):
        """
        Args:
            gateName: The index of the module's :class:`Gate` to listen on
            validTypes: If this argument is provided, a :class:`TypeError` will
                be raised when an object received via the specified :class:`Gate`
                is not of the :class:`type` / one of the types specified.
            buffered: Only applies when decorating a generator function.
                If set to ``True``, the decorated SimPy process is running
                (due to an object received earlier in the program flow) and the specified :class:`Gate`
                receives one or more objects, they will be queued and the SimPy process
                will be executed with queued objects until the queue is empty again.
                Thus, the buffer flag also enables a decorated SimPy process to process
                multiple objects that are received at the same simulated time.
        """
        self._gateName = gateName
        self._validTypes = validTypes
        self._buffered = buffered
    
    def __call__(self, method):
        typecheck = self._validTypes is not None
        wrapper = None
        
        if inspect.isgeneratorfunction(method):
            # The decorated method is a generator (yielding SimPy events).
            # We will return a generator method (declared below).

            def processWrapper(instance):
                """
                A generator which is decorated with the
                :class:`~gymwipe.networking.construction.GateListener` decorator,
                running it as a SimPy process when the module's `{}`
                :class:`~gymwipe.networking.construction.Gate` receives an object.
                """

                gate = instance.gates[self._gateName]

                if self._buffered:
                    # buffering is enabled
                    
                    buffer = deque()

                    def bufferFiller(obj: Any):
                        if typecheck:
                            ensureType(obj, self._validTypes, instance)
                        buffer.append(obj)
                        logger.debug("{}: Buffered GateListener on Gate '{}': Received '{}', queued. "
                                        "Buffer usage: {:d}".format(instance, self._gateName, obj, len(buffer)))
                
                    # register callback function at the gate's input port
                    gate.input.addCallback(bufferFiller)

                    while True:
                        logger.debug("{}: Buffered GateListener on Gate '{}': Idling.".format(instance, self._gateName))
                        yield gate.receivesMessage
                        while len(buffer) > 0:
                            obj = buffer.popleft()
                            logger.debug("{}: Buffered GateListener on Gate '{}': Processing '{}'. "
                                            "Buffer usage: {:d}".format(instance, self._gateName, obj, len(buffer)))
                            yield SimMan.process(method(instance, obj))
                else:
                    # buffering is disabled
                    while True:
                        logger.debug("{}: GateListener on Gate '{}': Idling.".format(instance, self._gateName))
                        obj = yield gate.receivesMessage
                        logger.debug("{}: GateListener on Gate '{}': Received '{}', "
                                        "processing...".format(instance, self._gateName, obj))
                        if typecheck:
                            ensureType(obj, self._validTypes, instance)
                        yield SimMan.process(method(instance, obj))

            # Set the registerAsProcess flag.
            # This will make the setup decorator add it as a SimPy process.
            processWrapper.makeSimPyProcess = True
            
            wrapper = processWrapper
        
        else:
            # The decorated method is not a generator.
            # We will directly register it as a callback at the input port.

            if self._buffered:
                logger.warn("{}: The 'buffered' flag only "
                            "effects generator functions. Did you mean to make the decorated "
                            "method a generator?".format(method))

            def methodWrapper(instance):
                """
                A method which is decorated with the
                :class:`~gymwipe.networking.construction.GateListener` decorator,
                invoking it when the module's `{}` :class:`~gymwipe.networking.construction.Gate`
                receives an object.
                """

                # Making sure callback registration is done only once
                # per decorated method and instance.
                if (method, instance) in methodWrapper.executedFor:
                    logger.info("{}: GateListener on Gate '{}': Duplicate method call of {} of {}, ignored."
                                "Methods decorated with GateListener do not have to be invoked manually. "
                                "@GateListener.setup does this for you. "
                                .format(instance, self._gateName, method, instance))
                else:
                    def messageAdapter(obj: Any):
                        # Takes any object, performs a typecheck (if requested),
                        # and calls the decorated method with the given object.
                        logger.debug("{}: GateListener on Gate '{}': Received '{}', "
                                        "calling decorated method.".format(instance, self._gateName, obj))
                        if typecheck:
                            ensureType(obj, self._validTypes, instance)
                        method(instance, obj)
                    
                    instance.gates[self._gateName].input.addCallback(messageAdapter)

                    methodWrapper.executedFor.add((method, instance))
            
            methodWrapper.executedFor = set()
            
            # Set the callAtConstruction flag.
            # This will make the setup generator invoke it.
            methodWrapper.callAtConstruction = True

            wrapper = methodWrapper
        
        wrapper.__doc__ = wrapper.__doc__.format(self._gateName)
        return wrapper

    @staticmethod
    def setup(function):
        """
        A decorator to be used for the constructor of any :class:`Module` sublass
        that makes use of the :class:`GateListener` decorator.
        When applied, it will register decorated generator functions as SimPy processes
        and execute the setup code for non-generator functions.
        """

        @wraps(function)
        def wrapper(self, *args, **kwargs):
            retVal = function(self, *args, **kwargs) # keep return value (just in case)

            # Register SimPy processes (those methods with makeSimPyProcess set to true)
            # and invoke methods with the callAtConstruction flag.
            for method in [getattr(self, a) for a in dir(self) if not a.startswith("__")]:
                if getattr(method, "makeSimPyProcess", False):
                    SimMan.process(method())
                if getattr(method, "callAtConstruction", False):
                    method()
            
            return retVal
        
        return wrapper
