import pytest

from gymwipe.networking.messages import Packet, Transmittable

def test_packets():
    p1 = Packet(Transmittable("HEADER1 CONTENT"), Transmittable("test"))
    assert str(p1.payload) == "test"
    assert str(p1.header) == "HEADER1 CONTENT"

    assert str(p1) == "HEADER1 CONTENT,test"
    
    p2 = Packet(Transmittable("HEADER2 CONTENT"), p1)
    assert str(p2) == "HEADER2 CONTENT,HEADER1 CONTENT,test"
