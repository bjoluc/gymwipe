"""
A collection of :class:`~gymwipe.networking.physical.AttenuationModel`
implementations. Currently contains:

.. autosummary::

    ~gymwipe.networking.attenuation_models.FSPLAttenuation
"""

import logging
from math import log10, sqrt

from gymwipe.devices import Device
from gymwipe.networking.physical import BaseAttenuationModel, ChannelSpec
from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class FSPLAttenuation(BaseAttenuationModel):
    """
    Free-space path loss (FSPL) :class:`AttenuationModel` implementation
    """

    def __init__(self, channelSpec: ChannelSpec, deviceA: Device, deviceB: Device):
        super(FSPLAttenuation, self).__init__(channelSpec, deviceA, deviceB)
        self._update()

    def _update(self):
        # https://en.wikipedia.org/wiki/Free-space_path_loss#Free-space_path_loss_in_decibels
        a = self.devices[0].position
        b = self.devices[1].position
        if a == b:
            logger.info("FSPLAttenuation: Source and destination position are equivalent.")
            return 0
        return 20*log10(a.distanceTo(b)) + 20*log10(self.channelSpec.frequency) - 147.55
    
    def _positionChanged(self, device: Device):
        self._update()
