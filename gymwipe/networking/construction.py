"""
Contains classes for building network stack representations.
"""
from typing import Callable, Any

class Gate:
    """
    Todo:
        * finish documentation
    """

    class Port:

        def __init__(self):
            self._onSendCallables = set()

        def _addDest(self, dest: Callable[[Any], None]) -> None:
            """
            Args:
                dest: A callback function that a message will be sent to when send is called on the Port
            """
            self._onSendCallables.add(dest)
        
        # connecting Ports with each other

        def connectTo(self, port: 'Gate.Port') -> None:
            """
            Connects this Port to the provided Port. Thus, if send is called on this Port, send will also be called on the provided Port.

            Args:
                port: The port for the connection to be established to
            """
            self._addDest(port.send)

        # sending messages

        def send(self, message: Any):
            for send in self._onSendCallables:
                send(message)
    

    def __init__(self, inputCallback: Callable[[Any], None] = None):
        """
        Args:
            inputCallback: The callback that will be used when a message is sent to the input Port.
        """
        
        self.input = self.Port()
        if callable(inputCallback):
            self.input._addDest(inputCallback)
        self._output = self.Port()

    # Connecting Gates

    def connectOutputTo(self, port: Port) -> None:
        """
        Connects this Gate's output Port to the provided Port.

        Args:
            port: The port to connect this Gate's output to
        """
        self._output.connectTo(port)
    
    def connectInputTo(self, port: Port) -> None:
        """
        Connects this Gate's input Port to the provided Port.

        Args:
            port: The port to connect this Gate's input to
        """
        self.input.connectTo(port)
    
    def biConnectWith(self, gate: 'Gate') -> None:
        """
        Shorthand for self.connectOutputTo(gate.input); gate.connectOutputTo(self._output)

        Args:
            gate: The Gate for the bidirectional connection to be established to
        """
        self.connectOutputTo(gate.input)
        gate.connectOutputTo(self.input)

class Module:
    """
    Attributes:
        gates(Dict[str, Gate]): The Module's outer Gates
        _innerModules(Dict[str, Module]): The Module's nested Modules
    """

    def __init__(self, name: str):
        """
        Args:
            name: The Module's name
        """
        self._name = name
        self.gates = {}
        self._subModules = {}
    
    def _addGate(self, name: str, gate: Gate) -> None:
        if name in self.gates:
            raise ValueError("A gate named '%s' already exists." % str)
        self.gates[name] = gate
    
    def _addSubModule(self, name: str, module: 'Module') -> None:
        if name in self._subModules:
            raise ValueError("A sub module named '%s' already exists." % str)
        self._subModules[name] = module
    
    def getName(self) -> str:
        return self._name
