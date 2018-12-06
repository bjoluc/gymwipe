import pygame
from pygame import Surface

import ode
from gymwipe.plants.core import OdePlant
from gymwipe.simtools import SimMan


class SlidingPendulum(OdePlant):
    """
    Simulates a pendulum, mounted on a motorized slider.
    """

    def __init__(self, world: ode.World = None, visualized = False):
        super(SlidingPendulum, self).__init__(world)

        # Bodies and joints
        # Create wagon
        wagon = ode.Body(self.world)
        M = ode.Mass()
        M.setSphere(2500, 0.05)
        wagon.setMass(M)
        wagon.setPosition((0,1,0))

        # Create pendulum
        pendulum = ode.Body(self.world)
        M = ode.Mass()
        M.setSphere(2500, 0.05)
        pendulum.setMass(M)
        pendulum.setPosition((0,2,0))

        # Connect wagon with the static environment using a slider joint
        slider = ode.SliderJoint(self.world)
        slider.attach(ode.environment, wagon)
        slider.setAxis((1,0,0))

        # Connect pendulum with wagon
        arm = ode.HingeJoint(self.world)
        arm.attach(wagon, pendulum)
        arm.setAnchor(wagon.getPosition())
        arm.setAxis((0,0,1))

        self._wagon = wagon
        self._pendulum = pendulum
        self._slider = slider
        self._arm = arm

        slider.setParam(ode.ParamVel, 0.1)
        slider.setParam(ode.ParamFMax, 22) # used to be 22

        # visualization
        self._visualized = visualized
        if visualized:
            surface = pygame.display.set_mode((640,480))
            SimMan.process(self._screenUpdater(surface))
    
    # Methods for plant value access

    def getAngle(self) -> float:
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
        surface.fill((255,255,255))

        pendulumPos = self._toPixelCoordinate(self._pendulum.getPosition())
        wagonPos = self._toPixelCoordinate(self._wagon.getPosition())

        pygame.draw.circle(surface, (0,0,0), pendulumPos, 20, 0)
        pygame.draw.circle(surface, (0,0,0), wagonPos, 20, 0)
        pygame.draw.line(surface, (0,0,0), pendulumPos, wagonPos, 2)

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
