import os
from setuptools import setup, find_packages

install_requires = []
with open('requirements.txt') as file:
    install_requires = file.read().splitlines()

setup(
    name='cytube-bot',
    version='1.0.0',
    packages=find_packages('cytubebot'),
    install_requires=install_requires
)
