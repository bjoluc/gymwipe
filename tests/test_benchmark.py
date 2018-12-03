"""
Performance benchmark tests using the `pytest-benchmark` package.
"""
import random
from math import sqrt

import pytest

from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.devices import NetworkDevice
from gymwipe.networking.messages import (Packet, Message, SimpleMacHeader,
                                         StackMessages, Transmittable)
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.stack import SimplePhy
from gymwipe.simtools import SimMan

SEND_INTERVAL = 1e-6 # seconds
MOVE_INTERVAL = 1e-5 # seconds

class SendingDevice(NetworkDevice):
    """
    A device that sends packets to a non-existent mac address.
    """

    def __init__(self, id, xPos, yPos, frequencyBand, sendInterval, initialDelay):
        super(SendingDevice, self).__init__("Device" + str(id), xPos, yPos, frequencyBand)

        # initialize a physical layer only
        self._phy = SimplePhy("phy", self, frequencyBand)
        
        def sender():
            yield SimMan.timeout(initialDelay)
            while True:
                yield SimMan.timeout(sendInterval)

                packet = Packet(
                    SimpleMacHeader(
                        bytes([0 for _ in range(5)] + [id % 255]),
                        bytes([255 for _ in range(6)]),
                        flag=0
                    ),
                    Transmittable("A message to all my homies")
                )
                signal = Message(StackMessages.SEND, {"packet": packet, "power": 40.0, "bitrate": 1e6})
                self._phy.ports["mac"].send(signal)

        SimMan.process(sender())

deviceCounts = range(0, 101, 5)

@pytest.fixture(params=deviceCounts)
def device_block(request):
    """
    A parametrized device fixture that sets up SendingDevices in a block
    arrangement with 1 m distance between adjacent devices.
    Tests using this fixture will be run with every specified parameter.
    """
    n = request.param # number of devices to be created
    SimMan.initEnvironment()
    frequencyBand = FrequencyBand([FsplAttenuation])

    devices = []
    cols = int(sqrt(n))
    for i in range(n):
        initialDelay = random.uniform(0, SEND_INTERVAL)
        devices.append(SendingDevice(i, i / cols, i % cols, frequencyBand, SEND_INTERVAL, initialDelay))
    
    return devices

@pytest.fixture
def moving_device_block(device_block):
    def mover(d: NetworkDevice):
        yield SimMan.timeout(random.uniform(0, MOVE_INTERVAL))
        initialPos = d.position
        while True:
            xOffset = random.uniform(-.2, .2)
            yOffset = random.uniform(-.2, .2)
            d.position.set(initialPos.x + xOffset, initialPos.y + yOffset)
            yield SimMan.timeout(MOVE_INTERVAL)
    
    for device in device_block:
        SimMan.process(mover(device))

def benchmark_simulation_block(benchmark, device_block):
    benchmark(SimMan.runSimulation, SEND_INTERVAL * 100)

def benchmark_simulation_block_moving(benchmark, moving_device_block):
    benchmark(SimMan.runSimulation, SEND_INTERVAL * 100)
