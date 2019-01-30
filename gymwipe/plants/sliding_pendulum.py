"""
A plant, sensor, and actuator implementation for an inverted pendulum.
"""
import logging
import pygame
from pygame import Surface

import ode
from gymwipe.networking.devices import SimpleNetworkDevice
from gymwipe.networking.messages import Packet, Transmittable
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.core import OdePlant
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class SlidingPendulum(OdePlant):
    """
    Simulates a pendulum, mounted on a motorized slider.
    """

    def __init__(self, world: ode.World = None, visualized=False):
        super(SlidingPendulum, self).__init__(world)

        # Bodies and joints
        # Create wagon
        wagon = ode.Body(self.world)
        M = ode.Mass()
        M.setSphere(2500, 0.05)
        wagon.setMass(M)
        wagon.setPosition((0, 1, 0))

        # Create pendulum
        pendulum = ode.Body(self.world)
        M = ode.Mass()
        M.setSphere(2500, 0.05)
        pendulum.setMass(M)
        pendulum.setPosition((0, 2, 0))

        # Connect wagon with the static environment using a slider joint
        slider = ode.SliderJoint(self.world)
        slider.attach(ode.environment, wagon)
        slider.setAxis((1, 0, 0))

        # Connect pendulum with wagon
        arm = ode.HingeJoint(self.world)
        arm.attach(wagon, pendulum)
        arm.setAnchor(wagon.getPosition())
        arm.setAxis((0, 0, 1))

        self._wagon = wagon
        self._pendulum = pendulum
        self._slider = slider
        self._arm = arm

        slider.setParam(ode.ParamVel, 0.1)
        slider.setParam(ode.ParamFMax, 22)  # used to be 22

        # visualization
        self._visualized = visualized
        if visualized:
            surface = pygame.display.set_mode((640, 480))
            SimMan.process(self._screenUpdater(surface))

        logger.debug("Pendulum initialized")
    
    # Methods for plant value access

    def getAngle(self) -> float:
        logger.debug("angle requested", sender=self)
        self.updateState()
        return self._arm.getAngle()
    
    def getAngleRate(self):
        self.updateState()
        return self._arm.getAngleRate()
    
    def getWagonPos(self) -> float:
        self.updateState()
        return self._wagon.getPosition()[0]
    
    def getWagonVelocity(self) -> float:
        self.updateState()
        return self._wagon.getLinearVel()[0]
    
    def setMotorVelocity(self, velocity: float):
        self.updateState()
        self._slider.setParam(ode.ParamVel, velocity)

    # Visualization-specific methods
    
    def _toPixelCoordinate(self, position):
        """Converts a world coordinate to a pixel coordinate."""
        x, y = position[:2]
        return int(320+170*x), int(400-170*y)
    
    def _drawOnSurface(self, surface: Surface):
        surface.fill((255, 255, 255))

        pendulumPos = self._toPixelCoordinate(self._pendulum.getPosition())
        wagonPos = self._toPixelCoordinate(self._wagon.getPosition())

        pygame.draw.circle(surface, (0, 0, 0), pendulumPos, 20, 0)
        pygame.draw.circle(surface, (0, 0, 0), wagonPos, 20, 0)
        pygame.draw.line(surface, (0, 0, 0), pendulumPos, wagonPos, 2)

        pygame.display.flip()

    def _screenUpdater(self, surface: Surface):
        """
        A SimPy process for regularly redrawing the visualization window.
        """
        fps = 50
        stepSize = 1.0/fps

        while True:
            self._drawOnSurface(surface)
            yield SimMan.timeout(stepSize)
            self.updateState()

class AngleSensor(SimpleNetworkDevice):
    """
    A networked angle sensor implementation for the :class:`SlidingPendulum`
    plant
    """

    def __init__(self, name: str, frequencyBand: FrequencyBand, plant: SlidingPendulum,
                    controllerAddr: bytes, sampleInterval: float):
        super(AngleSensor, self).__init__(name, plant.getWagonPos(), 0, frequencyBand)
        self.plant = plant
        self.controllerAddr = controllerAddr
        self.sampleInterval = sampleInterval

        SimMan.process(self._sensor())
    
    def _sensor(self):
        while True:
            self.position.x = self.plant.getWagonPos()
            self.send(Transmittable(2, self.plant.getAngle()), self.controllerAddr)
            yield SimMan.timeout(self.sampleInterval)

class WagonActuator(SimpleNetworkDevice):
    """
    A networked actuator implementation for moving the :class:`SlidingPendulum`
    plant's wagon
    """

    def __init__(self, name: str, frequencyBand: FrequencyBand, plant: SlidingPendulum):
        super(WagonActuator, self).__init__(name, plant.getWagonPos, 0, frequencyBand)
        self.plant = plant
        
        SimMan.process(self._positionUpdater())
    
    def _positionUpdater(self):
        while True:
            self.position.x = self.plant.getWagonPos()
            yield SimMan.timeout(1e-3) # 1 ms

    def onReceive(self, packet: Packet):
        self.plant.setMotorVelocity(packet.payload.value)
