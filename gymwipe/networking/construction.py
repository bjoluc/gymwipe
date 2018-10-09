"""
Contains classes for building network stack representations.
"""
import inspect
import logging
from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, Tuple, Union

from simpy.events import Event

from gymwipe.simtools import Notifier, SimMan, SimTimePrepender, ensureType

logger = SimTimePrepender(logging.getLogger(__name__))

class Port:
    """
    Todo:
        * documentation

    """

    def __init__(self, name: str = None, buffered: bool = True):
        self._name = name
        self._onSendCallables = set()

        # Notifiers
        self.nReceives: Notifier = Notifier('Receives', self)
        """
        :class:`~gymwipe.simtools.Notifier`: A notifier that is triggered when
        :meth:`send` is called, providing the value passed to :meth:`send`
        """

    def __str__(self):
        return "Port('{}')".format(self._name)

    def addCallback(self, callback: Callable[[Any], None]) -> None:
        """
        Args:
            callback: A callback function that will be invoked whenever
                :meth:`send` is called, providing the object passed to :meth:`send`
        """
        self._onSendCallables.add(callback)
    
    # connecting Ports with each other

    def connectTo(self, port: 'Port') -> None:
        """
        Connects this :class:`Port` to the provided :class:`Port`. Thus, if
        :meth:`send` is called on this :class:`Port`, it will also be called on
        the provided :class:`Port`.

        Args:
            port: The :class:`Port` for the connection to be established to
        """
        self.addCallback(port.send)

    # sending objects

    def send(self, object: Any):
        """
        Sends the object provided to all connected ports and registered callback
        functions (if any).
        """
        logger.debug("%s received message %s", self, object)
        for send in self._onSendCallables:
            send(object)
        self.nReceives.trigger(object)


class Gate:
    """   
    Todo:
        * documentation

    """

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None):
        """
        Args:
            inputCallback: A callback function that will be invoked when an object
                is sent to the :attr:`input` Port.
        """
        
        self._name = name
        self.input: Port = Port(name + ".input")
        if callable(inputCallback):
            self.input.addCallback(inputCallback)
        self.output: Port = Port(name + ".output")
    
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
            raise TypeError("Expected Port, got {}. Use .input or .output to "
                            "access a Gate's ports.".format(type(port)))
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
    
    def send(self, object: Any):
        """
        Calls the :meth:`~gymwipe.networking.construction.Port.send` method of
        the :attr:`input` port
        """
        self.input.send(object)

    # Notifiers
    
    @property
    def nReceives(self):
        """
        :class:`~gymwipe.simtools.Notifier`: A notifier that is triggered when
        the input :class:`Port` receives an object
        """
        return self.input.nReceives
    
class Module:
    """
    Attributes:
        gates(Dict[str, Gate]): The Module's outer Gates
        subModules(Dict[str, Module]): The Module's nested Modules
    """

    def __init__(self, name: str):
        self._name = name
        self.gates: Dict[str, Gate]  = {}
        self.subModules: Dict[str, Module] = {}
    
    def __str__(self):
        return "{} '{}'".format(self.__class__.__name__, self._name)
    
    def _addGate(self, name: str, gate: Gate = None) -> None:
        """
        Adds a new :class:`Gate` to the :attr:`gates` dictionary, indexed by the name
        passed.
        
        Args:
            name: The name for the :class:`Gate` to be accessed by
            gate: The :class:`Gate` object to be added. If not provided, a new
                :class:`Gate` will be instantiated using a combination of the
                Module's name property and `name` as its name.
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
    A decorator factory to call methods or process SimPy generators whenever a
    specified gate receives an object. The received object is provided to the
    decorated method as a parameter.

    Note:
        In order to make this work for an object's methods, you have to decorate
        that object's constructor with `@GateListener.setup`.

    Examples:
        A method using this decorator could look like this:

        ::

            @GateListener("myGate")
            def myGateListener(self, obj):
                # This SimPy generator is processed whenever
                # self.gates["myGate"] receives an object and all
                # previously created instances have been processed.
                yield SimMan.timeout(1)
    """

    def __init__(self, gateName: str, validTypes: Union[type, Tuple[type]]=None, blocking=True, queued=False):
        """
        Args:
            gateName: The index of the module's :class:`Gate` to listen on
            validTypes: If this argument is provided, a :class:`TypeError` will
                be raised when an object received via the specified :class:`Gate` is
                not of the :class:`type` / one of the types specified.
            blocking: Set this to false if you decorate a SimPy generator and
                want it to be processed for each received object, regardless of
                whether an instance of the generator is still being processed or
                not. By default, only one instance of the decorated generator method
                is run at a time (blocking is ``True``).
            queued: If you decorate a generator method, `blocking` is ``True``
                and you set `queued` to ``True``, an object received while an
                instance of the generator is being processed will be queued.
                Sequentially, a new generator will then be processed for every
                queued object as soon as the current generator is processed.
                Using `queued`, you can thus react to multiple objects that are
                received at the same simulated time, while still only having one
                generator processed at a time.
        """
        self._gateName = gateName
        self._validTypes = validTypes
        self._blocking = blocking
        self._queued = queued
    
    def __call__(self, method):
        typecheck = self._validTypes is not None
        isGenerator = inspect.isgeneratorfunction(method)

        # define the initialization method to be returned
        def initializer(instance):

            def callAdapter(obj: Any):
                # Takes any object, performs a typecheck (if requested), and
                # calls the decorated method with the given object.
                if typecheck:
                    ensureType(obj, self._validTypes, instance)
                return method(instance, obj)

            receiveNotifier = instance.gates[self._gateName].nReceives

            if isGenerator:
                receiveNotifier.subscribeProcess(callAdapter, self._blocking, self._queued)
            else:
                if self._queued:
                    logger.warning("GateListener decorator for {}: The 'queued' "
                                    "flag only effects generator methods. "
                                    "Did you mean to make the decorated "
                                    "method a generator?".format(method))
                receiveNotifier.subscribeCallback(callAdapter)
        
        # Set the docstring accordingly

        if isGenerator:
            initializer.__doc__ = """
            A SimPy generator which is decorated with the
            :class:`~gymwipe.networking.construction.GateListener` decorator,
            processing it when the module's `{}`
            :class:`~gymwipe.networking.construction.Gate` receives an object.
            """
        else:
            initializer.__doc__ = """
            A method which is decorated with the
            :class:`~gymwipe.networking.construction.GateListener` decorator,
            invoking it when the module's `{}` :class:`~gymwipe.networking.construction.Gate`
            receives an object.
            """

        initializer.__doc__ = initializer.__doc__.format(self._gateName)

        # Set the callAtConstruction flag.
        # This will make the setup generator invoke the method.
        initializer.callAtConstruction = True

        return initializer

    @staticmethod
    def setup(function):
        """
        A decorator to be used for the constructor of any :class:`Module` sublass
        that makes use of the :class:`GateListener` decorator.
        """

        @wraps(function)
        def wrapper(self, *args, **kwargs):
            retVal = function(self, *args, **kwargs) # keep return value (just in case)

            # Invoke methods with the callAtConstruction flag set to True
            for method in [getattr(self, a) for a in dir(self) if not a.startswith("__")]:
                if getattr(method, "callAtConstruction", False):
                    method()
            
            return retVal
        
        return wrapper
