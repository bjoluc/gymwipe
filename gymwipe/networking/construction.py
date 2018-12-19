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

    def __init__(self, name: str, owner = None):
        self.name = name
        self._owner = owner

        # Notifiers
        self.nReceives: Notifier = Notifier('Receives', self)
        self.nConnectsTo: Notifier = Notifier('Connects to', self)

    def __repr__(self):
        return "{}Gate('{}')".format(ownerPrefix(self._owner), self.name)
    
    # connecting Gates with each other

    def connectTo(self, gate: 'Gate'):
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
    methods: :meth:`biConnectWith` and :meth:`biConnectProxy`.

    Args:
        name(:class:`str`): The Port's name
        owner(Any): The object that the :class:`Port` belongs to (e.g. a
            :class:`Module`)

    Attributes:
        name(:class:`str`): The Port's name, as provided to the constructor
        input: The Port's input :class:`Gate`
        output: The Port's output :class:`Gate`
    """

    def __init__(self, name: str, owner: Any = None):
        self.name = name
        self._owner = owner
        self.input: Gate = Gate("in", owner=self)
        self.output: Gate = Gate("out", owner=self)

    def __repr__(self):
        return "{}Port('{}')".format(ownerPrefix(self._owner), self.name)

    # Connecting Ports
    
    def biConnectWith(self, port: 'Port'):
        """
        Shorthand for
        ::
        
            self.output.connectTo(port.input)
            port.output.connectTo(self.input)

        Creates a bidirectional connection between this port an the passed port.
        If :tikz:`\\node [draw,circle,inner sep=1.5pt,outer sep=1pt]{};`
        indicates input gates and
        :tikz:`\\node [draw,fill,circle,inner sep=1.5pt,outer sep=1pt]{};`
        indicates output gates, the resulting connection between two ports can
        be visualized like this:

        .. tikz::

            \\node (p1in) at (0,0)[draw,circle,inner sep=1.5pt]{};
            \\node (p1out) at (0,0.4)[draw,circle,fill,inner sep=1.5pt]{};
            \\node (p2out) at (2,0)[draw,circle,fill,inner sep=1.5pt]{};
            \\node (p2in) at (2,0.4)[draw,circle,inner sep=1.5pt]{};

            \\draw[draw=black] (-0.2,-0.2) rectangle ++(0.4,0.8);
            \\draw[draw=black] (1.8,-0.2) rectangle ++(0.4,0.8);

            \\draw[->] (p1out) -- (p2in);
            \\draw[->] (p2out) -- (p1in);

        Args:
            port: The :class:`Port` to establish the bidirectional connection to
        """
        self.output.connectTo(port.input)
        port.output.connectTo(self.input)
    
    def biConnectProxy(self, port: 'Port'):
        """
        Shorthand for
        ::
        
            self.output.connectTo(port.output)
            port.input.connectTo(self.input)
        
        If :tikz:`\\node [draw,circle,inner sep=1.5pt,outer sep=1pt]{};`
        indicates input gates and
        :tikz:`\\node [draw,fill,circle,inner sep=1.5pt,outer sep=1pt]{};`
        indicates output gates, the resulting connection between two ports can
        be visualized like this:

        .. tikz::

            \\node (p1in) at (0,0)[draw,circle,inner sep=1.5pt]{};
            \\node (p1out) at (0,0.4)[draw,circle,fill,inner sep=1.5pt]{};
            \\node (p2out) at (2,0.4)[draw,circle,fill,inner sep=1.5pt]{};
            \\node (p2in) at (2,0)[draw,circle,inner sep=1.5pt]{};

            \\draw[draw=black] (-0.2,-0.2) rectangle ++(0.4,0.8);
            \\draw[draw=black] (1.8,-0.2) rectangle ++(0.4,0.8);

            \\draw[->] (p1out) -- (p2out);
            \\draw[->] (p2in) -- (p1in);

        Args:
            port: The :class:`Port` to establish the bidirectional proxy connection to
        """
        self.output.connectTo(port.output)
        port.input.connectTo(self.input)

    # Notifiers
    
    @property
    def nReceives(self):
        """
        :class:`~gymwipe.simtools.Notifier`: The input gate's nReceives
        notifier, which is triggered when an object is received by the input
        :class:`Gate`
        """
        return self.input.nReceives

class GateListener:
    """
    A factory for decorators that allow to call a module's method (or process a
    SimPy generator method) whenever a specified gate of a :class:`Module`
    receives an object. The received object is provided to the decorated method
    as a parameter.

    Note:
        In order to make this work for a class' methods, you have to decorate that
        class' constructor with `@PortListener.setup`.

    Examples:
        A module's method using this decorator could look like this:

        ::

            @PortListener("myPortIn")
            def myPortListener(self, obj):
                # This  method is processed whenever self.gates["myPortIn"]
                # receives an object and all previously created instances
                # have been processed.
                yield SimMan.timeout(1)
    """

    def __init__(self, gateName: str, validTypes: Union[type, Tuple[type]]=None,
                    blocking: bool = True, queued: bool = False):
        """
        Args:
            gateName: The index of the module's :class:`Gate` to listen on
            validTypes: If this argument is provided, a :class:`TypeError` will
                be raised when an object received via the specified :class:`Gate` is
                not of the :class:`type` / one of the types specified.
            blocking: Set this to ``False`` if you decorate a SimPy generator method and
                want it to be processed for each received object, regardless of
                whether an instance of the generator is still being processed or
                not. By default, only one instance of the decorated generator method
                is run at a time (blocking is ``True``).
            queued: If you decorate a SimPy generator method, `blocking` is
                ``True``, and you set `queued` to ``True``, an object received while
                an instance of the generator is being processed will be queued.
                Sequentially, a new generator will then be processed for every
                queued object as soon as the current generator has been processed.
                Using `queued`, you can thus react to multiple objects that are
                received at the same simulated time, while still only having one
                generator instance processed at a time. Queued defaults to
                ``False``.
        """
        self._gateName = gateName
        self._validTypes = validTypes
        self._blocking = blocking
        self._queued = queued
    
    def __call__(self, method):
        typecheck = self._validTypes is not None
        isGenerator = inspect.isgeneratorfunction(method)

        # Define the initialization method to be returned
        def initializer(instance):

            def callAdapter(obj: Any):
                # Takes any object, performs a typecheck (if requested), and
                # calls the decorated method with the given object.
                if typecheck:
                    ensureType(obj, self._validTypes, instance)
                return method(instance, obj)

            nReceives = instance.gates[self._gateName].nReceives

            if isGenerator:
                nReceives.subscribeProcess(callAdapter, self._blocking, self._queued)
            else:
                if self._queued:
                    logger.warning("GateListener decorator for {}: The 'queued' "
                                    "flag only effects generator methods. "
                                    "Did you mean to make the decorated "
                                    "method a generator?".format(method))
                nReceives.subscribeCallback(callAdapter)
        
        # Set the docstring accordingly

        if isGenerator:
            initializer.__doc__ = """
            A SimPy process method which is decorated with the
            :class:`~gymwipe.networking.construction.GateListener` decorator.
            It is processed when the module's `{}`
            :class:`~gymwipe.networking.construction.Gate` receives an object.
            """
        else:
            initializer.__doc__ = """
            A method which is decorated with the
            :class:`~gymwipe.networking.construction.GateListener` decorator.
            It is processed when the module's `{}`
            :class:`~gymwipe.networking.construction.Gate` receives an object.
            """

        initializer.__doc__ = initializer.__doc__.format(self._gateName)

        # Set the callAtConstruction flag.
        # This will make the setup generator invoke the method.
        initializer.callAtConstruction = True

        return initializer

    @staticmethod
    def setup(function):
        """
        A decorator to be used for the constructors of :class:`Module` subclasses
        that make use of the :class:`GateListener` decorator.
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
    
class Module:
    """
    A module has a number of ports and gates that can be used to exchange
    data with it and connect it to other modules.
    Modules provide the methods :meth:`_addPort` and :meth:`_addGate` that
    allow to add ports and gates, which can be accessed via the
    :attr:`ports` and the :attr:`gates` dictionaries.

    Note:

        Modules may have both ports (for bidirectional connections) and individual
        gates (for unidirectional connections). When a port is added by
        :meth:`_addPort`, its two gates are also added to the :attr:`gates`
        dictionary.

    Attributes:
        name(str): The Module's name
        ports(Dict[str, Port]): The Module's outer Ports
        gates(Dict[str, Gate]): The Module's outer Gates

    .. automethod:: _addPort
    .. automethod:: _addGate
    """

    def __init__(self, name: str, owner = None):
        self.name = name
        self._owner = owner

        self.ports: Dict[str, Port] = {}
        self.gates: Dict[str, Gate] = {}
    
    def __repr__(self):
        return "{}{}('{}')".format(ownerPrefix(self._owner), self.__class__.__name__, self.name)
    
    def _addPort(self, name: str):
        """
        Adds a new :class:`Port` to the :attr:`ports` dictionary, indexed by the
        name passed. Since a :class:`Port` holds two :class:`Gate` objects, a
        call of this method also adds two entries to the :attr:`gates`
        dictionary, namely "<name>In" and "<name>Out".

        Args:
            name: The name for the :class:`Port` to be indexed with
        """
        if name in self.ports:
            raise ValueError("A port indexed by '{}' already exists.".format(name))
        port = Port(name, owner=self)
        self.ports[name] = port
        self.gates[name + "In"] = port.input
        self.gates[name + "Out"] = port.output
    
    def _addGate(self, name: str):
        """
        Adds a new :class:`Gate` to the :attr:`gates` dictionary, indexed by the
        name passed.

        Note:
            
            Plain :class:`Gate` objects are only needed for unidirectional
            connections. Bidirectional connections can profit from :class:`Port`
            objects.
        
        Args:
            name: The name for the :class:`Gate` to be indexed with
        """
        if name in self.gates:
            raise ValueError("A gate indexed by '{}' already exists.".format(name))
        self.gates[name] = Gate(name, owner=self)

class CompoundModule(Module):
    """
    A :class:`CompoundModule` is a :class:`Module` that contains an arbitrary
    number of submodules (:class:`Module` objects) which can be connected with
    each other and their parent module's gates and ports.
    Submodules are added using :meth:`_addSubmodule` and can be accessed via
    the :attr:`submodules` dictionary.
    
    Note:

        When subclassing CompoundModule, do not directly implement
        functionalities in your subclass, but wrap them in submodules
        to ensure modularity.
        Also, do not connect a CompoundModule's submodules to anything
        else than other submodules or the CompoundModule itself for
        the same reason.
    
    Attributes:
        submodules(Dict[str, Module]): The CompoundModule's nested :class:`Module`
            objects
    
    .. automethod:: _addSubmodule
    """

    def __init__(self, name: str, owner = None):
        super(CompoundModule, self).__init__(name, owner)
        self.submodules: Dict[str, Module] = {}

    def _addSubmodule(self, name: str, module: Module):
        """
        Adds a new :class:`Module` to the :attr:`submodules` dictionary, indexed
        by the name passed.

        Args:
            name: The name for the submodule to be indexed with
            module: The :class:`Module` object to be added as a submodule
        """
        if name in self.submodules:
            raise ValueError("A submodule named '{}' already exists.".format(name))
        self.submodules[name] = module
