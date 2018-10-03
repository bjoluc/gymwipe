"""
A collection of :class:`~gymwipe.networking.physical.AttenuationModel`
implementations. Currently contains:

.. autosummary::

    ~gymwipe.networking.attenuation_models.FSPLAttenuation
"""

import logging
from math import log10, sqrt

from gymwipe.networking.core import NetworkDevice, Position
from gymwipe.networking.physical import BaseAttenuationModel
from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class FSPLAttenuation(BaseAttenuationModel):
    """
    Free-space path loss (FSPL) :class:`AttenuationModel` implementation
    """

    f: float = 2.4e9 # 2.4 GHz
    """float: The transmission frequency in Hertz"""

    def __init__(self, deviceA: NetworkDevice, deviceB: NetworkDevice):
        super(FSPLAttenuation, self).__init__(deviceA, deviceB)
        self._update()

    def _update(self):
        # https://en.wikipedia.org/wiki/Free-space_path_loss#Free-space_path_loss_in_decibels
        a = self.devices[0].position
        b = self.devices[1].position
        if a == b:
            logger.info("FSPLAttenuation: Source and destination position are equivalent.")
            return 0
        return 20*log10(a.distanceTo(b)) + 20*log10(self.f) - 147.55
    
    def _positionChanged(self, device: NetworkDevice):
        self._update()
