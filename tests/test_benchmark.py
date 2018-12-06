"""
Performance benchmark tests using the `pytest-benchmark` package.
"""
import random
from math import sqrt

import pytest

from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.devices import NetworkDevice
from gymwipe.networking.messages import (Packet, Signal, SimpleMacHeader,
                                         StackSignals, Transmittable)
from gymwipe.networking.physical import Channel
from gymwipe.networking.stack import SimplePhy
from gymwipe.simtools import SimMan

SEND_INTERVAL = 1e-3 # seconds
MOVE_INTERVAL = 1e-3 # seconds

class SendingDevice(NetworkDevice):
    """
    A device that sends packets to a non-existent mac address.
    """

    def __init__(self, id, xPos, yPos, channel, sendInterval, initialDelay):
        super(SendingDevice, self).__init__("Device" + str(id), xPos, yPos, channel)

        # initialize a physical layer only
        self._phy = SimplePhy("phy", self, channel)
        
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
                signal = Signal(StackSignals.SEND, {"packet": packet, "power": 40.0, "bitrate": 1e6})
                self._phy.gates["mac"].send(signal)

        SimMan.process(sender())

deviceCounts = range(0, 101, 5)
#deviceCounts = [20]

@pytest.fixture(params=deviceCounts)
def device_block(request):
    """
    A parametrized device fixture that sets up SendingDevices in a block
    arrangement with 1 m distance between adjacent devices.
    Tests using this fixture will be run with every specified parameter.
    """
    n = request.param # number of devices to be created
    SimMan.initEnvironment()
    channel = Channel([FsplAttenuation])

    devices = []
    cols = int(sqrt(n))
    for i in range(n):
        initialDelay = random.uniform(0, SEND_INTERVAL)
        devices.append(SendingDevice(i, i / cols, i % cols, channel, SEND_INTERVAL, initialDelay))
    
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

#def benchmark_simulation_block(benchmark, device_block):
#    benchmark(SimMan.runSimulation, 1)


# from pympler import tracker
# tr = tracker.SummaryTracker()

# import objgraph
# import textwrap
# def extrinfo(x):
#     output = repr(x)[:1000]
#     return textwrap.fill(output,40)

def benchmark_simulation_block_moving(benchmark, moving_device_block):

    #tr.print_diff()

    benchmark(SimMan.runSimulation, 1)
    #SimMan.runSimulation(1)
    #objgraph.show_refs(SimMan.env)
    #objgraph.show_backrefs(random.choice(objgraph.by_type("Notifier")), extra_info=extrinfo)

    #tr.print_diff()

    #cb = refbrowser.ConsoleBrowser(SimMan.env, maxdepth=3, str_func=output_function)
    #cb.print_tree()
