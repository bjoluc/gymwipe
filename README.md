# Gym-WiPE – Gym Wireless Plant Environment

[![Documentation](https://readthedocs.org/projects/gymwipe/badge/)](https://gymwipe.readthedocs.io/)

An OpenAI Gym Environment for Channel Assignments in the Simulation of Wireless Networked Feedback Control Loops

## Why Gym-WiPE?

Networked control systems often put high requirements on the underlying networks.
Off-the-shelf wireless network solutions, however, may not fulfill these needs without further improvements.
Reinforcement learning may help to find appropriate policies for radio resource management in control systems for which optimal static resource management algorithms can not easily be determined.
This is where Gym-WiPE comes in:
It provides an [OpenAI Gym](https://gym.openai.com/) reinforcement learning environment that simulates wireless networked feedback control loops.

## What's included?

Gym-WiPE features an all-Python wireless network simulator based on [SimPy](https://simpy.readthedocs.io/).
The [Open Dynamics Engine (ODE)](https://www.ode.org/), more specifically its Python wrapper [Py3ODE](https://github.com/filipeabperes/Py3ODE) is integrated for plant simulation.
Two Gym environments have been implemented for frequency band assignments yet: A simplistic network-only example and the control of an inverted pendulum.
The development of further environments may concern frequency band assignments but is not limited to these as the entire simulation model is accessible from within Python and may be used for arbitrary Gym wireless networked control environments.
The implementation of control algorithms may profit from the [python-control](https://python-control.readthedocs.io/) project.

## Getting started

### Environment Setup

Gym-WiPE uses [pipenv](https://pipenv.readthedocs.io/en/latest/).
To install it, run
```
pip install pipenv
```
With pipenv installed, you may clone the repository like
```
git clone https://github.com/bjoluc/gymwipe.git
cd gymwipe
```
and invoke pipenv to set up a virtual environment and install the dependencies into it:
```
pipenv install
```
Optionally, the development dependencies may be installed via
```
pipenv isntall --dev
```

If ODE is used for plant Simulation, it has to be [downloaded](https://sourceforge.net/projects/opende/files/ODE/) and built.
After that, `make ode` will install Py3ODE and pygame for plant visualizations.

### Running the tests

The pytest testsuite can be executed via ```make test```.

### Further steps

Yet, this project is missing usage examples and tutorials.
For now, you can have a look at the API documentation at [](https://gymwipe.read-the-docs-io).

