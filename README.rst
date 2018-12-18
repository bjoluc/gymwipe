Gym-WiPE – Gym Wireless Plant Environment
=========================================

|Documentation|

An `OpenAI Gym`_ environment for the application of reinforcement learning in the simulation of wireless networked
feedback control loops

Documentation lives at `Read the Docs`_.

.. _Read the Docs: https://gymwipe.readthedocs.io/en/latest/

.. |Documentation| image:: https://readthedocs.org/projects/gymwipe/badge/
   :alt: Documentation Status
   :target: https://gymwipe.readthedocs.io/

.. include-in-docs

Why Gym-WiPE?
-------------

Networked control systems often put high requirements on the underlying
networks. Off-the-shelf wireless network solutions, however, may not fulfill
their needs without further improvements. Reinforcement learning may help to
find appropriate policies for radio resource management in control systems for
which optimal static resource management algorithms can not easily be
determined. This is where Gym-WiPE comes in: It provides an `OpenAI Gym`_
reinforcement learning environment that simulates wireless networked feedback
control loops.

.. _OpenAI Gym: https://gym.openai.com/

What's included?
----------------

Gym-WiPE features an all-Python wireless network simulator based on
`SimPy`_. The `Open Dynamics Engine (ODE)`_, more specifically its
Python wrapper `Py3ODE`_ is integrated for plant simulation. Two Gym
environments have been implemented for frequency band assignments yet: A
simplistic network-only example and the control of an inverted pendulum.
The development of further environments may concern frequency band
assignments but is not limited to these as the entire simulation model
is accessible from within Python and may be used for arbitrary Gym
wireless networked control environments. Control
algorithm implementations may profit from the `python-control`_ project.

.. _SimPy: https://simpy.readthedocs.io/
.. _Open Dynamics Engine (ODE): https://www.ode.org/
.. _Py3ODE: https://github.com/filipeabperes/Py3ODE
.. _python-control: https://python-control.readthedocs.io/

Getting started
---------------

Environment Setup
~~~~~~~~~~~~~~~~~

Gym-WiPE uses `pipenv`_. To install it, run

::

   pip install pipenv

With pipenv installed, you may clone the repository like

::

   git clone https://github.com/bjoluc/gymwipe.git
   cd gymwipe

and invoke pipenv to set up a virtual environment and install the
dependencies into it:

::

   pipenv install

Optionally, the development dependencies may be installed via

::

   pipenv isntall --dev

If ODE is used for plant Simulation, it has to be `downloaded`_ and
built. After that, ``make ode`` will install Py3ODE and pygame for plant
visualizations.

.. _pipenv: https://pipenv.readthedocs.io/en/latest/
.. _downloaded: https://sourceforge.net/projects/opende/files/ODE/

Running the tests
~~~~~~~~~~~~~~~~~

The pytest testsuite can be executed via ``make test``.

Further steps
-------------

Yet, this project lacks usage examples and tutorials. For now, you
can have a look at the API documentation at
https://gymwipe.readthedocs.io/en/latest/api/index.html
