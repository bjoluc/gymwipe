"""
Core components for modelling physical devices
"""
import logging
from math import sqrt
from typing import Any, List, Tuple, Union

from simpy import Event

from gymwipe.simtools import Notifier, SimTimePrepender
from gymwipe.utility import ownerPrefix

logger = SimTimePrepender(logging.getLogger(__name__))

class Position:
    """
    A simple class for representing 2-dimensional positions, stored as two float values.
    """

    def __init__(self, x: Union[float, int], y: Union[float, int], owner: Any = None):
        """
        Args:
            x: The distance to a fixed origin in x direction, measured in meters
            y: The distance to a fixed origin in y direction, measured in meters
            owner: The object owning (having) the position.
        """
        self._x = float(x)
        self._y = float(y)
        self.owner = owner

        self.nChange: Notifier = Notifier("changes", self)
        """
        :class:`~gymwipe.simtools.Notifier`: A notifier that is triggered when one or both of :attr:`x`
            and :attr:`y` is changed, providing the triggering position object.
        """
    
    def __eq__(self, p):
        return p.x == self._x and p.y == self._y
    
    @property
    def x(self):
        """
        float: The distance to a fixed origin in x direction, measured in meters

        Note:
            When setting both :attr:`x` and :attr:`y`, please use
            the :meth:`set` method.
        """
        return self._x
    
    @x.setter
    def x(self, x):
        if x != self._x:
            logger.debug("%s: Changing x to %s", self, x)
            self._x = x
            self.nChange.trigger(self)
    
    @property
    def y(self):
        """
        float: The distance to a fixed origin in y direction, measured in meters

        Note:
            When setting both :attr:`x` and :attr:`y`, please use
            the :meth:`set` method.
        """
        return self._y
    
    @y.setter
    def y(self, y):
        if y != self._y:
            logger.debug("%s: Changing y to %s", self, y)
            self._y = y
            self.nChange.trigger(self)
    
    def set(self, x: float, y:float):
        """
        Sets both the x and the y value while triggering the
        :attr:`nChange` notifier only once.
        """
        if x != self._x or y != self._y:
            logger.debug("%s: Setting x, y = %s, %s", self, x, y)
            self._x = x
            self._y = y
            self.nChange.trigger(self)
    
    def distanceTo(self, p: 'Position') -> float:
        """
        Returns the euclidean distance of this :class:`Position` to `p`, measured in meters.

        Args:
            p: The :class:`Position` object to calculate the distance to
        """
        return sqrt((self.x - p.x)**2 + (self.y - p.y)**2)
    
    def __str__(self):
        return "{}Position({},{})".format(ownerPrefix(self.owner), self.x, self.y)

class Device:
    """
    Represents a physical device that has a name and a position.
    """

    def __init__(self, name: str, xPos: float, yPos: float):
        """
        Args:
            name: The device name
            xPos: The device's physical x position
            yPos: The device's physical y position
        """
        self._name: str = name
        self._position: Position = Position(xPos, yPos, self)
    
    def __str__(self):
        return "Device('{}')".format(self.name)
    
    @property
    def position(self):
        """:class:`Position`: The device's physical position"""
        return self._position
    
    @property
    def name(self) -> str:
        """str: The device name (for debugging and plotting)"""
        return self._name
