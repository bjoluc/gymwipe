from math import degrees, pi

from simpy.rt import RealtimeEnvironment

from gymwipe.networking.devices import SimpleNetworkDevice
from gymwipe.networking.messages import Packet
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.sliding_pendulum import SlidingPendulum
from gymwipe.simtools import SimMan

# You may want to use this for plant setup in an appropriate environment:
# SimMan.setEnvironment(RealtimeEnvironment())
# plant = SlidingPendulum(visualized=True)

class InvertedPendulumPidController(SimpleNetworkDevice):
    
    def __init__(self, name: str, xPos: float, yPos: float, frequencyBand: FrequencyBand):
        super(InvertedPendulumPidController, self).__init__(name, xPos, yPos, frequencyBand)
        
        self._angle = 0

        SimMan.process(self.control)
    
    def onReceive(self, packet: Packet):
        """
        TODO extract degree value from sensor
        """
        # degrees(plant.getAngle())

    def _sendVelocity(self, velocity: float):
        """
        TODO send velocity to actuator
        """
        # plant.setMotorVelocity(correction)

    def control(self):
        correction = 0
        kp = 1.0 # 57.0
        ki = 0.0 # 26.0
        kd = 0.0 # 12.0
        last_error = 0
        sp = 0

        def calcVelocity(error):
            nonlocal last_error
            PID = kp * error + ki * (error + last_error) + kd * (error - last_error)
            last_error = error
            return PID

        yield SimMan.timeout(1)

        while True:
            errorcw = abs(sp - self._angle)
            correction = calcVelocity(errorcw)
            if self._angle < sp:
                self._sendVelocity(correction)
            if self._angle > sp:
                self._sendVelocity(-correction)
            yield SimMan.timeout(0.01)
