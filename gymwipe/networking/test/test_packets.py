import pytest

import gymwipe.networking.packets as packets

def test_packets():
    payload = packets.PayloadString("test")
    assert payload.content == "test"

    p1 = packets.Packet("HEADER1 CONTENT", payload)
    assert p1.payload.content == "test"
    assert p1.header == "HEADER1 CONTENT"

    assert str(p1) == "HEADER1 CONTENT\ntest"
    
    p2 = packets.Packet("HEADER2 CONTENT", p1)
    assert str(p2) == "HEADER2 CONTENT\nHEADER1 CONTENT\ntest"

    # test invalid payload (payload has to be a payload object)
    with pytest.raises(TypeError):
        packets.Packet("header", "invalid payload")
