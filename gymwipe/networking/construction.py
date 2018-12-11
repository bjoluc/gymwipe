"""
Classes for building network stack representations
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
    Gates provide features for the transfer of arbitrary objects. They can be
    connected to each other and offer a :meth:`send` method that passes an
    object to all connected gates, as shown in the figure below, where
    connections are depicted as arrows.

    .. tikz::

        [thick, gate/.style args={#1}{draw, circle, inner sep=3, outer
        sep=0, label=above:{#1}}]
        
        % Gates
        \\node[gate=Gate1] (g1) at (0,1) {};
        \\node[gate=Gate2] (g2) at (3,1) {};
        \\node[gate=Gate3] (g3) at (6,1) {};

        % Connections
        \\draw[->] (g1) -- (g2) node[above,midway] {msg};
        \\draw[->] (g2) -- (g3) node[above,midway] {msg};

        % Commands
        \\node[below=0.5 of g1] (s1) {send(msg)};
        \\draw[dashed] (s1) -- (g1);

    Gates emulate the transmission of objects via connections by calling
    :meth:`send` on their connected gates as illustrated below.

    .. tikz::

        [thick, gate/.style args={#1}{draw, circle, inner sep=3, outer
        sep=0, label=above:{#1}}]
        
        % Gates
        \\node[gate=Gate1] (g1) at (0,1) {};
        \\node[gate=Gate2] (g2) at (3,1) {};
        \\node[gate=Gate3] (g3) at (6,1) {};

        % Commands
        \\node[below=0.5 of g1] (s1) {send(msg)};
        \\node[below=0.5 of g2] (s2) {send(msg)};
        \\node[below=0.5 of g3] (s3) {send(msg)};
        \\draw[dashed] (s1) -- (g1);
        \\draw[dashed] (s2) -- (g2);
        \\draw[dashed] (s3) -- (g3);

        \\draw[dashed,->] (s1) -- (s2);
        \\draw[dashed,->] (s2) -- (s3);

    Attributes:
        name(str): The Gate's name
        nReceives(gymwipe.simtools.Notifier): A notifier that is triggered when
            :meth:`send` is called, providing the value passed to :meth:`send`
        nConnectsTo(:class:`~gymwipe.simtools.Notifier`): A notifier that is
            triggered when :meth:`connectTo` is called, providing the gate passed to
            :meth:`connectTo`
    """

    def __init__(self, name: str = None, owner = None):
        self.name = name
        self._owner = owner

        # Notifiers
        self.nReceives: Notifier = Notifier('Receives', self)
        self.nConnectsTo: Notifier = Notifier('Connects to', self)

    def __repr__(self):
        return "{}Gate('{}')".format(ownerPrefix(self._owner), self.name)
    
    # connecting Gates with each other

    def connectTo(self, gate: 'Gate') -> None:
        """
        Connects this :class:`Gate` to the provided :class:`Gate`. Thus, if
        :meth:`send` is called on this :class:`Gate`, it will also be called on
        the provided :class:`Gate`.

        Args:
            gate: The :class:`Gate` for the connection to be established to
        """
        self.nReceives.subscribeCallback(gate.send)
        self.nConnectsTo.trigger(gate)

    # sending objects

    def send(self, object: Any):
        """
        Triggers :attr:`nReceives` with the provided object and sends it to all
        connected gates.
        """
        logger.debug("Received object: %s", object, sender=self)
        self.nReceives.trigger(object)


class Port:
    """   
    A :class:`Port` simplifies the setup of bidirectional connections by
    wrapping an input and an output :class:`Gate` and offering two connection
    methods: :meth:`biConnectTo` and :meth:`biConnectProxy`.

    Attributes:
        name(str): The Port's name, as provided to the constructor
    """

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None, owner: Any = None):
        """
        Args:
            name: The Port's name
            owner: The object that the :class:`Port` belongs to (e.g. a
                :class:`Module`)
        """
        
        self.name = name
        self._owner = owner
        self.input: Gate = Gate("in", owner=self)
        if inputCallback is not None:
            self.input.nReceives.subscribeCallback(inputCallback)
        self.output: Gate = Gate("out", owner=self)

    def __repr__(self):
        return "{}Port('{}')".format(ownerPrefix(self._owner), self.name)

    # Connecting Ports
    
    def biConnectWith(self, port: 'Port') -> None:
        """
        Shorthand for
        ::
        
            self.output.connectTo(port.input)
            port.output.connectTo(self.input)

        Args:
            port: The `Port` for the bidirectional connection to be established to
        """
        self.output.connectTo(port.input)
        port.output.connectTo(self.input)
    
    def biConnectProxy(self, port: 'Port') -> None:
        """
        Shorthand for
        ::
        
            self.output.connectTo(port.output)
            port.input.connectTo(self.input)
        
        Note:
            The term `Proxy` is used for a port that passes its input
            to another port's input.

        Args:
            port: The :class:`Port` to be connected as a proxy
        """
        self.output.connectTo(port.output)
        port.input.connectTo(self.input)

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
        name(str): The Module's name
        ports(Dict[str, Port]): The Module's outer Ports
        gates(Dict[str, Port]): The Module's outer Gates
        subModules(Dict[str, Module]): The Module's nested Modules
    """

    def __init__(self, name: str, owner = None):
        self.name = name
        self._owner = owner

        self.ports: Dict[str, Port]  = {}
        self.gates: Dict[str, Gate] = {}
        self.subModules: Dict[str, Module] = {}
    
    def __repr__(self):
        return "{}{}('{}')".format(ownerPrefix(self._owner), self.__class__.__name__, self.name)
    
    def _addPort(self, name: str) -> None:
        """
        Adds a new :class:`Port` to the :attr:`ports` dictionary, indexed by the
        name passed. Since a :class:`Port` holds two :class:`Gate` objects, a
        call of this method also adds two entries to the :attr:`gates`
        dictionary, namely "`name`In" and "`name`Out".

        Args:
            name: The name for the :class:`Port` to be indexed with
        """
        if name in self.ports:
            raise ValueError("A port indexed by '{}' already exists.".format(name))
        port = Port(name, owner=self)
        self.ports[name] = port
        self.gates[name + "In"] = port.input
        self.gates[name + "Out"] = port.output
    
    def _addGate(self, name: str) -> None:
        """
        Adds a new :class:`Gate` to the :attr:`gates` dictionary, indexed by the
        name passed.

        Note:
            
            Single :class:`Gate` objects are only needed for unidirectional
            connections. Bidirectional connections can rely on :class:`Port`
            objects.
        
        Args:
            name: The name for the :class:`Gate` to be indexed with
        """
        if name in self.gates:
            raise ValueError("A gate indexed by '{}' already exists.".format(name))
        self.gates[name] = Gate(name, owner=self)
    
    def _addSubModule(self, name: str, module: 'Module') -> None:
        if name in self.subModules:
            raise ValueError("A sub module named '{}' already exists.".format(name))
        self.subModules[name] = module

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

    def __init__(self, portName: str, validTypes: Union[type, Tuple[type]]=None, blocking=True, queued=False):
        """
        Args:
            portName: The index of the module's :class:`Port` to listen on
            validTypes: If this argument is provided, a :class:`TypeError` will
                be raised when an object received via the specified :class:`Port` is
                not of the :class:`type` / one of the types specified.
            blocking: Set this to false if you decorate a SimPy process and
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
        self._portName = portName
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
