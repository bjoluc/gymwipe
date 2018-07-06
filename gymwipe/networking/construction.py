"""
Contains classes for building network stack representations.
"""
from typing import Callable, Any
from simpy.events import Event
from gymwipe.simtools import SimMan

class Gate:
    """   
    Todo:
        * finish documentation

    """

    class Port:
        """

        """

        def __init__(self):
            self._onSendCallables = set()
            self._sendEvent = None

        def _addDest(self, dest: Callable[[Any], None]) -> None:
            """
            Args:
                dest: A callback function that will be called with a message object when send is called on the Port
            """
            self._onSendCallables.add(dest)
        
        # connecting Ports with each other

        def connectTo(self, port: 'Gate.Port') -> None:
            """
            Connects this `Port` to the provided port. Thus, if `send` is called on this port, it will also be called on the provided port.

            Args:
                port: The port for the connection to be established to
            """
            self._addDest(port.send)

        # sending messages

        def send(self, message: Any):
            """
            Sends the object provided as `message` to all connected ports and registered callback functions (if any).
            """
            self._triggerSendEvent(message)
            for send in self._onSendCallables:
                send(message)
        
        # SimPy events

        @property
        def sendEvent(self) -> Event:
            """simpy.events.Event: A SimPy `Event` that is triggered when `send` is called on this port."""
            if self._sendEvent is None:
                self._sendEvent = Event(SimMan.env)
            return self._sendEvent

        def _triggerSendEvent(self, message) -> None:
            if self._sendEvent is not None:
                self._sendEvent.succeed(message)
                self._sendEvent = None
    

    def __init__(self, name: str, inputCallback: Callable[[Any], None] = None):
        """
        Args:
            inputCallback: A callback function that will be used when a message is sent to the input Port.
        """
        
        self.input = self.Port()
        if callable(inputCallback):
            self.input._addDest(inputCallback)
        self.output = self.Port()

    # Connecting Gates

    def connectOutputTo(self, port: Port) -> None:
        """
        Connects this Gate's output Port to the provided Port.

        Args:
            port: The port to connect this Gate's output to
        """
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
        Shorthand for `self.connectOutputTo(gate.input); gate.connectOutputTo(self._output)`

        Args:
            gate: The `Gate` for the bidirectional connection to be established to
        """
        self.connectOutputTo(gate.input)
        gate.connectOutputTo(self.input)
    
    # SimPy events vor message handling
    
    @property
    def receivesMessage(self):
        """Event: A SimPy `Event` that is triggered when the input port receives a message"""
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
    
    def _addGate(self, name: str, gate: Gate = None) -> None:
        """
        Adds a new `Gate` to the *gates* dictionary, indexed by the name passed.
        
        Args:
            name: The name for the gate to be accessed by
            gate: The `Gate` object to be added. If not provided, a new `Gate` will be
                instantiated using a concatenation of the Module's name property and *name* as its name.
        """
        if name in self.gates:
            raise ValueError("A gate named '%s' already exists." % str)
        if gate is None:
            gate = Gate(self.name + '.' + name)
        self.gates[name] = gate
    
    def _addSubModule(self, name: str, module: 'Module') -> None:
        if name in self.subModules:
            raise ValueError("A sub module named '%s' already exists." % str)
        self.subModules[name] = module
    
    @property
    def name(self):
        """str: The Module's name"""
        return self._name
