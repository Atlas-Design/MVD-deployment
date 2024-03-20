from setuptools import setup, find_packages
from src.version import __version__

setup(
    name='sd_cli',
    version=__version__,
    install_requires=[
        'click>=8.1.7',
        'requests>=2.31.0'
    ],
    python_requires='>=3.7',
    entry_points={
        'console_scripts': [
            'sd_cli = cli:cli',
        ],
    },
)