"""
The Stack package contains implementations of network stack layers. Layers are modeled by `Module` objects from the `gymwipe.networking.construction` module.
"""
import logging
from gymwipe.networking.construction import Module, Gate
from gymwipe.networking.core import Channel, Transmission, NetworkDevice
from gymwipe.networking.messages import Signal, Packet, PhySignals
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class StackLayer(Module):

    def __init__(self, name: str, device: NetworkDevice):
        super(StackLayer, self).__init__(name)
        self._device = device
    
    def __str__(self):
        return "{}.{}('{}')".format(self._device, self.__class__.__name__, self._name)

class SimplePhy(StackLayer):
    """
    A very basic physical layer implementation, mainly for demonstration purposes.
    It provides a single gate called `mac` to be connected to the mac layer.

    The `mac` gate reacts to `Signal` objects typed as one of the following `PhySignals`:

    RECEIVE
        `Signal` properties:

        :duration: The number of time steps to listen for

    SEND
        `Signal` properties:

        :packet: The `Packet` object representing the packet to be sent
        :power: The transmission power [dBm]
        :bitrate: The bitrate of the transmission [bits/time step]
    """

    def __init__(self, name: str, device: NetworkDevice, channel: Channel):
        super(SimplePhy, self).__init__(name, device)
        self._channel = channel
        self._addGate("mac")
        SimMan.registerProcess(self.macGateListener())
        logger.debug("Initialized %s", self)
    
    RECV_THRESHOLD = -80 # dBm (https://www.metageek.com/training/resources/wifi-signal-strength-basics.html)
    
    def macGateListener(self):
        while True:
            logger.debug("%s: macGateListener listening for messages", self)
            cmd = yield self.gates["mac"].receivesMessage
            if not isinstance(cmd, Signal):
                raise AttributeError("SimplePhy of NetworkDevice {} received object of invalid type {} via the mac gate. Expected type: Signal".format(self._device, type(cmd)) )
            p = cmd.properties

            if cmd.type is PhySignals.SEND:
                logger.debug("%s received Signal: PhySignals.SEND", self)
                # simulate sending
                t = self._channel.transmit(self._device, p["power"], p["bitrate"], p["bitrate"], p["packet"])
                # wait for the transmission to finish
                yield t.completes
            
            elif cmd.type is PhySignals.RECEIVE:
                logger.debug("%s received Signal: PhySignals.RECEIVE", self)
                # simulate channel sensing & receiving
                timeout = SimMan.timeout(p["duration"])
                transmissionStarted = self._channel.transmissionStarted
                yield timeout | transmissionStarted
                if timeout.processed and not transmissionStarted.processed:
                    logger.debug("%s: Receiving timed out, no transmissions were detected.", self)
                else:
                    logger.debug("%s: Sensed a transmission.", self)
                    # value of the transmissionStarted event is the transmission that started
                    t = transmissionStarted.value 
                    # wait until the transmission has finished
                    yield t.completes
                    # check for collisions
                    if len(self._channel.getTransmissions(t.startTime, t.stopTime)) > 1:
                        logger.debug("%s: Colliding transmission(s) were found, transmission could not be received.", self)
                        pass
                    else:
                        # no colliding transmissions, check attenuation
                        a = self._channel.attenuationProvider.getAttenuation(t.sender.position, self._device.position, t.startTime)
                        recvPower = t.power - a
                        if recvPower < self.RECV_THRESHOLD:
                            logger.debug("%s: Signal strength of %s dBm is insufficient (RECV_THRESHOLD is %s dBm), packet could not be received correctly.", self, recvPower, self.RECV_THRESHOLD)
                            pass
                        else:
                            logger.debug("%s: Packet successfully received (Signal power was %s dBm)!", self, recvPower)
                            packet = t.packet
                            # sending it via the mac gate
                            self.gates["mac"].output.send(packet)
