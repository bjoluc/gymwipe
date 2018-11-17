"""
A keras-rl DQN learning agent operating the
:class:`~gymwipe.envs.counter_traffic.CounterTrafficEnv` based on a `keras-rl example
<https://github.com/keras-rl/keras-rl/blob/master/examples/dqn_cartpole.py>`_
"""
import sys
import traceback

import gym
import numpy as np
from keras.layers import Activation, Dense, Flatten, Reshape
from keras.models import Sequential
from keras.optimizers import Adam
from rl.agents.dqn import DQNAgent
from rl.core import Processor
from rl.memory import SequentialMemory
from rl.policy import BoltzmannQPolicy

from gymwipe.envs.counter_traffic import CounterTrafficEnv

ENV_NAME = 'CounterTraffic-v0'

class CounterTrafficProcessor(Processor):

    def process_action(self, flat_action):
        # "reshape" the action to a dict in the action space
        assert flat_action is not None
        max_duration = CounterTrafficEnv.MAX_ASSIGN_DURATION
        device = int(flat_action / max_duration)
        duration = flat_action - (device*max_duration)
        reshaped_action = {"device": device, "duration": duration}
        #print(reshaped_action)
        return reshaped_action

def learn():
    # Get the environment and extract the number of actions.
    env = gym.make(ENV_NAME)
    np.random.seed(123)
    env.seed(123)

    # Action space details
    nb_devices = env.action_space.spaces["device"].n
    nb_durations = env.action_space.spaces["duration"].n
    nb_actions = nb_devices * nb_durations

    # Next, we build a very simple model.
    model = Sequential()
    model.add(Dense(16, input_shape=(1,)))
    model.add(Activation('relu'))
    model.add(Dense(16))
    model.add(Activation('relu'))
    model.add(Dense(16))
    model.add(Activation('relu'))
    model.add(Dense(nb_actions))
    model.add(Activation('linear'))
    print(model.summary())

    # Finally, we configure and compile our agent. You can use every built-in
    # Keras optimizer and even the metrics!
    memory = SequentialMemory(limit=50000, window_length=1)
    processor = CounterTrafficProcessor()
    policy = BoltzmannQPolicy()
    dqn = DQNAgent(model=model, processor=processor, nb_actions=nb_actions, memory=memory,
                nb_steps_warmup=1000, target_model_update=1e-2, policy=policy)
    dqn.compile(Adam(lr=1e-3), metrics=['mae'])

    # Okay, now it's time to learn something! We visualize the training here for
    # show, but this slows down training quite a lot. You can always safely
    # abort the training prematurely using Ctrl + C.
    dqn.fit(env, nb_steps=50000, visualize=False, verbose=1)

    # After training is done, we save the final weights.
    dqn.save_weights('dqn_{}_weights.h5f'.format(ENV_NAME), overwrite=True)
    #dqn.load_weights('dqn_{}_weights.h5f'.format(ENV_NAME))

    # Finally, evaluate our algorithm
    dqn.test(env, nb_episodes=5, visualize=True)


if __name__ == "__main__":
    try:
        learn()
    except Exception:
        print(traceback.format_exc())
