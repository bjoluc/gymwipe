import pytest

from gymwipe.networking.packets import Packet

def test_packets():
    p1 = Packet("HEADER1 CONTENT", "test")
    assert p1.payload == "test"
    assert p1.header == "HEADER1 CONTENT"

    assert str(p1) == "HEADER1 CONTENT\ntest"
    
    p2 = Packet("HEADER2 CONTENT", p1)
    assert str(p2) == "HEADER2 CONTENT\nHEADER1 CONTENT\ntest"
