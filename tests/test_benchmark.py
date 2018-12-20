"""
Performance benchmark tests using the `pytest-benchmark` package.
"""
import random
from math import sqrt

import pytest

from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.devices import NetworkDevice
from gymwipe.networking.messages import (Message, Packet, SimpleMacHeader,
                                         StackMessageTypes, Transmittable)
from gymwipe.networking.physical import BpskMcs, FrequencyBand
from gymwipe.networking.simple_stack import SimplePhy
from gymwipe.simtools import SimMan

SEND_INTERVAL = 1e-2 # seconds
MOVE_INTERVAL = 1e-3 # seconds

class SendingDevice(NetworkDevice):
    """
    A device that sends packets to a non-existent mac address.
    """

    def __init__(self, id, xPos, yPos, frequencyBand, sendInterval, initialDelay):
        super(SendingDevice, self).__init__("Device" + str(id), xPos, yPos, frequencyBand)
        
        # initialize a physical layer only
        self._phy = SimplePhy("phy", self, frequencyBand)

        mcs = BpskMcs(frequencyBand)
        
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

                signal = Message(StackMessageTypes.SEND, {"packet": packet, "power": 40.0, "mcs": mcs})
                self._phy.gates["macIn"].send(signal)

        SimMan.process(sender())

deviceCounts = range(0, 101, 5)
#deviceCounts = [20]

@pytest.fixture(params=deviceCounts)
def device_grid(request):
    """
    A parametrized device fixture that sets up SendingDevices in a block
    arrangement with 1 m distance between adjacent devices.
    Tests using this fixture will be run with every specified parameter.
    """
    n = request.param # number of devices to be created
    SimMan.init()
    frequencyBand = FrequencyBand([FsplAttenuation])

    devices = []
    cols = int(sqrt(n))
    for i in range(n):
        initialDelay = random.uniform(0, SEND_INTERVAL)
        devices.append(SendingDevice(i, i / cols, i % cols, frequencyBand, SEND_INTERVAL, initialDelay))
    
    return devices

@pytest.fixture
def mobile_device_grid(device_grid):
    def mover(d: NetworkDevice):
        yield SimMan.timeout(random.uniform(0, MOVE_INTERVAL))
        initialPos = d.position
        while True:
            xOffset = random.uniform(-.2, .2)
            yOffset = random.uniform(-.2, .2)
            d.position.set(initialPos.x + xOffset, initialPos.y + yOffset)
            yield SimMan.timeout(MOVE_INTERVAL)
    
    for device in device_grid:
        SimMan.process(mover(device))

# def benchmark_simulation_grid(benchmark, device_grid):
#     benchmark(SimMan.runSimulation, 1)

# from pympler import tracker
# tr = tracker.SummaryTracker()

# import objgraph
# import textwrap
# def extrinfo(x):
#     output = repr(x)[:1000]
#     return textwrap.fill(output,40)

def benchmark_simulation_mobile_grid(benchmark, mobile_device_grid):

    #tr.print_diff()

    benchmark(SimMan.runSimulation, 1)

    #SimMan.runSimulation(1)
    #objgraph.show_refs(SimMan.env)
    #objgraph.show_backrefs(random.choice(objgraph.by_type("Notifier")), extra_info=extrinfo)

    #tr.print_diff()

    #cb = refbrowser.ConsoleBrowser(SimMan.env, maxdepth=3, str_func=output_function)
    #cb.print_tree()
