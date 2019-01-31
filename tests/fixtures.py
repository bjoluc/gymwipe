import pytest

from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.simple_stack import SimplePhy
from gymwipe.simtools import SimMan

@pytest.fixture
def simman():
    SimMan.init()
    yield SimMan

class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

@pytest.fixture
def simple_phy(simman):
    # create a wireless frequency band with FSPL attenuation
    frequencyBand = FrequencyBand([FsplAttenuation])

    # create two network devices
    device1 = Device("1", 0, 0)
    device2 = Device("2", 1, 1)

    # create the SimplePhy network stack layers
    device1Phy = SimplePhy("Phy", device1, frequencyBand)
    device2Phy = SimplePhy("Phy", device2, frequencyBand)

    setup = dotdict()
    setup.frequencyBand = frequencyBand
    setup.device1 = device1
    setup.device2 = device2
    setup.device1Phy = device1Phy
    setup.device2Phy = device2Phy
    return setup
