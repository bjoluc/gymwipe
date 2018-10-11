from typing import Any

from gym.envs.registration import register


def ownerPrefix(ownerObject: Any):
    """
    Calls :meth:`__str__` on the `ownerObject` (if it is not ``None``) and
    returns the result concatenated with '.'.
    If the object is ``None``, an empty string will be returned.
    """
    if ownerObject is None:
        return ''
    return str(ownerObject) + '.'

# Register gym environments
register(
    id='gymwipe-simple-test-v0',
    entry_point='gymwipe.envs:SimpleTestEnv'
)