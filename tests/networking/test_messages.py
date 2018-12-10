import pytest

from gymwipe.networking.messages import Packet, Transmittable

def test_packets():
    header = Transmittable("header")
    payload = Transmittable("payload")
    p1 = Packet(header, payload)

    assert p1.header is header
    assert p1.payload is payload
    assert p1.byteSize == header.byteSize + payload.byteSize

    trailer = Transmittable("payload")
    p2 = Packet(header, payload, trailer)
    assert p2.trailer is trailer
    assert p2.byteSize == header.byteSize + payload.byteSize + trailer.byteSize
