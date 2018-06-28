from abc import ABC, abstractmethod

class Payload(ABC):
    """
    Payload represents data that can be sent in a package.
    """

    @abstractmethod
    def __str__(self):
        """
        Returns the Payload as a string.
        """
        pass
    

class PayloadString(Payload):
    """
    PayloadString is a wrapper for strings to be used as the Payload of a package.
    """

    def __init__(self, content):
        """
        Constructor.
        Args:
            content (string): The string to be used
        """
        self.content = content
    
    def __str__(self):
        """Returns the """
        return self.content

class Packet(Payload):
    """
    The Packet class represents packets.
    A Packet consists of both a header and a payload, which are passed to the constructor.
    Packets can be nested by providing them as payloads to the packet constructor.
    """

    def __init__(self, header, payload):
        """
        Constructs a new Packet object.
        Args:
            header (str): The String to be used as the Packet's header
            payload (Payload): The Payload object to be used as the Packet's payload
        """
        if not isinstance(payload, Payload):
            raise TypeError("Expected Payload, got %s" % type(payload))
        self.header = header
        self.payload = payload

    def __str__(self):
        """
        Returns the string content of the packet.
        This includes both the header and the string content of the packet's payload, divided by a newline character.
        """
        return str(self.header) + '\n' + str(self.payload)

