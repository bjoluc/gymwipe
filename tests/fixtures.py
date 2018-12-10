import pytest
from gymwipe.simtools import SimMan

@pytest.fixture
def simman():
    SimMan.init()
    yield SimMan