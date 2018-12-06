from os import path

from setuptools import find_packages, setup

# Reading the contents of README.md
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='gymwipe',
    version='1.0',
    description='Gym Wireless Plant Environment',
    author='bjoluc',
    url='https://github.com/bjoluc/gymwipe',
    packages=find_packages(),
    long_description=long_description,
    long_description_content_type='text/markdown',
    extras_require={
    'ode': ['py3ode','pygame'],
    },
)
