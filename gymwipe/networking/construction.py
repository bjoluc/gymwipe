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
from gymwipe.utility import ownerPrefix

logger = SimTimePrepender(logging.getLogger(__name__))

class Gate:
    """
    Todo:
        * documentation

    """

    def __init__(self, name: str = None, owner = None):
        self._name = name
        self._owner = owner

        # Notifiers
        self.nReceives: Notifier = Notifier('Receives', self)
        """
        :class:`~gymwipe.simtools.Notifier`: A notifier that is triggered when
        :meth:`send` is called, providing the value passed to :meth:`send`
        """

    def __repr__(self):
        return "{}Gate('{}')".format(ownerPrefix(self._owner), self._name)

    def addCallback(self, callback: Callable[[Any], None]) -> None:
        """
        Args:
            callback: A callback function that will be invoked whenever
                :meth:`send` is called, providing the object passed to :meth:`send`
        """
        self.nReceives.subscribeCallback(callback)
    
    # connecting Gates with each other

    def connectTo(self, gate: 'Gate') -> None:
        """
        Connects this :class:`Gate` to the provided :class:`Gate`. Thus, if
        :meth:`send` is called on this :class:`Gate`, it will also be called on
        the provided :class:`Gate`.

        Args:
            gate: The :class:`Gate` for the connection to be established to
        """
        self.addCallback(gate.send)

    # sending objects

    def send(self, object: Any):
        """
        Sends the object provided to all connected ports and registered callback
        functions (if any).
        """
        logger.debug("Received object: %s", object, sender=self)
        self.nReceives.trigger(object)


class Port:
    """   
    Todo:
        * documentation

    """

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None, owner = None):
        """
        Args:
            inputCallback: A callback function that will be invoked when an object
                is sent to the :attr:`input` Gate.
        """
        
        self._name = name
        self._owner = owner
        self.input: Gate = Gate("in", owner=self)
        if inputCallback is not None:
            self.input.addCallback(inputCallback)
        self.output: Gate = Gate("out", owner=self)

    def __repr__(self):
        return "{}Port('{}')".format(ownerPrefix(self._owner), self._name)

    # Connecting Ports

    def connectOutputTo(self, gate: Gate) -> None:
        """
        Connects this Port's output Gate to the provided Gate.

        Args:
            gate: The gate to connect this Port's output to
        """
        if not isinstance(gate, Gate):
            raise TypeError("Expected Gate, got {}. Use .input or .output to "
                            "access a Port's ports.".format(type(gate)))
        self.output.connectTo(gate)
    
    def connectInputTo(self, gate: Gate) -> None:
        """
        Connects this Port's input Gate to the provided Gate.

        Args:
            gate: The gate to connect this Port's input to
        """
        self.input.connectTo(gate)
    
    def biConnectWith(self, port: 'Port') -> None:
        """
        Shorthand for
        ::
        
            self.connectOutputTo(port.input)
            port.connectOutputTo(self.input)

        Args:
            port: The `Port` for the bidirectional connection to be established to
        """
        self.connectOutputTo(port.input)
        port.connectOutputTo(self.input)
    
    def biConnectProxy(self, port: 'Port') -> None:
        """
        Shorthand for
        ::
        
            self.connectOutputTo(port.output)
            port.connectInputTo(self.input)
        
        Note:
            The term `Proxy` is used for a port that passes its input
            to another port's input.

        Args:
            port: The :class:`Port` to be connected as a proxy
        """
        self.connectOutputTo(port.output)
        port.connectInputTo(self.input)
    
    def send(self, object: Any):
        """
        Calls the :meth:`~gymwipe.networking.construction.Gate.send` method of
        the :attr:`input` port
        """
        self.input.send(object)

    # Notifiers
    
    @property
    def nReceives(self):
        """
        :class:`~gymwipe.simtools.Notifier`: A notifier that is triggered when
        the input :class:`Gate` receives an object
        """
        return self.input.nReceives
    
class Module:
    """
    Attributes:
        gates(Dict[str, Port]): The Module's outer Ports
        subModules(Dict[str, Module]): The Module's nested Modules
    """

    def __init__(self, name: str, owner = None):
        self._name = name
        self._owner = owner
        self.ports: Dict[str, Port]  = {}
        self.subModules: Dict[str, Module] = {}
    
    def __repr__(self):
        return "{}{}('{}')".format(ownerPrefix(self._owner), self.__class__.__name__, self._name)
    
    def _addPort(self, name: str, port: Port = None) -> None:
        """
        Adds a new :class:`Port` to the :attr:`gates` dictionary, indexed by the name
        passed.
        
        Args:
            name: The name for the :class:`Port` to be accessed by
            po_rt: The :class:`Port` object to be added. If not provided, a new
                :class:`Port` will be instantiated using a combination of the
                Module's name property and `name` as its name.
        """
        if name in self.ports:
            raise ValueError("A port indexed by '{}' already exists.".format(name))
        if port is None:
            port = Port(name, owner=self)
        self.ports[name] = port
    
    def _addSubModule(self, name: str, module: 'Module') -> None:
        if name in self.subModules:
            raise ValueError("A sub module named '%s' already exists." % str)
        self.subModules[name] = module
    
    @property
    def name(self):
        """str: The Module's name"""
        return self._name

class PortListener:
    """
    A decorator factory to call methods or process SimPy generators whenever a
    specified port receives an object. The received object is provided to the
    decorated method as a parameter.

    Note:
        In order to make this work for an object's methods, you have to decorate
        that object's constructor with `@PortListener.setup`.

    Examples:
        A method using this decorator could look like this:

        ::

            @PortListener("myPort")
            def myPortListener(self, obj):
                # This SimPy generator is processed whenever
                # self.gates["myPort"] receives an object and all
                # previously created instances have been processed.
                yield SimMan.timeout(1)
    """

    def __init__(self, gateName: str, validTypes: Union[type, Tuple[type]]=None, blocking=True, queued=False):
        """
        Args:
            gateName: The index of the module's :class:`Port` to listen on
            validTypes: If this argument is provided, a :class:`TypeError` will
                be raised when an object received via the specified :class:`Port` is
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
        self._portName = gateName
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

            receiveNotifier = instance.ports[self._portName].nReceives

            if isGenerator:
                receiveNotifier.subscribeProcess(callAdapter, self._blocking, self._queued)
            else:
                if self._queued:
                    logger.warning("PortListener decorator for {}: The 'queued' "
                                    "flag only effects generator methods. "
                                    "Did you mean to make the decorated "
                                    "method a generator?".format(method))
                receiveNotifier.subscribeCallback(callAdapter)
        
        # Set the docstring accordingly

        if isGenerator:
            initializer.__doc__ = """
            A SimPy generator which is decorated with the
            :class:`~gymwipe.networking.construction.PortListener` decorator,
            processing it when the module's `{}`
            :class:`~gymwipe.networking.construction.Port` receives an object.
            """
        else:
            initializer.__doc__ = """
            A method which is decorated with the
            :class:`~gymwipe.networking.construction.PortListener` decorator,
            invoking it when the module's `{}` :class:`~gymwipe.networking.construction.Port`
            receives an object.
            """

        initializer.__doc__ = initializer.__doc__.format(self._portName)

        # Set the callAtConstruction flag.
        # This will make the setup generator invoke the method.
        initializer.callAtConstruction = True

        return initializer

    @staticmethod
    def setup(function):
        """
        A decorator to be used for the constructor of any :class:`Module` sublass
        that makes use of the :class:`PortListener` decorator.
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
