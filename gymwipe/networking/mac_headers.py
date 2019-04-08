import logging

from gymwipe.baSimulation.constants import ProtocolType
from gymwipe.networking.messages import Transmittable
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class NCSMacHeader(Transmittable):
    """
    A MAC header for packets within an NCS
    """
    def __init__(self, protocol: ProtocolType, type: bytes, sourceMAC: bytes, destMAC: bytes = None, more: bytes = None):
        """
        The bytesize of the header is computed according to the specified Protocoll, since sourceMACs are used within
        TDMA MAC layers, even though they are not needed.
        :param protocol: The MAC Protocol for which this header is generated
        :param type: the message type. could be sensordata, a schedule, a control message or an acknowledgement
        :param sourceMAC: The sending device's MAC address
        :param destMAC: The receiving device's MAC address
        :param more: Are more packages following?
        """
        if len(sourceMAC) != 6:
            raise ValueError("sourceMAC: Expected 6 bytes, got {:d}.".format(len(sourceMAC)))
        if destMAC != None:
            if len(destMAC) != 6:
                raise ValueError("destMAC: Expected 6 bytes, got {:d}.".format(len(destMAC)))
        if len(type) != 1:
            raise ValueError("type: Expected 1 byte, got {:d}.".format(len(type)))
        if more != None:
            if len(more) != 1:
                raise ValueError("more: Expected 1 or 0 bytes, got {:d}.".format(len(more)))
        self.sourceMAC = sourceMAC
        self.destMAC = destMAC
        self.type = type
        self.more = more
        bytesize = 0
        if protocol == ProtocolType.TDMA:
            bytesize = 1
        if protocol == ProtocolType.CSMA:
            if type[0] == 0:
                bytesize = 1
            else:
                bytesize = 7

        super(NCSMacHeader, self).__init__((type, sourceMAC, destMAC, more), bytesize)
        logger.debug("Header created, bytesize %d: ", bytesize, sender=self)
