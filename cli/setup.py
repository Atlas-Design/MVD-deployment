from setuptools import setup, find_packages
from sd_cli.version import __version__

setup(
    name='sd_cli',
    version=__version__,
    install_requires=[
        'requests>=2.31.0'
    ],
    packages=find_packages(include=["*"]),
    include_package_data=True,
    python_requires='>=3.7',
    entry_points={
        'console_scripts': [
            'sd_cli = sd_cli.cli:cli',
        ],
    },
)