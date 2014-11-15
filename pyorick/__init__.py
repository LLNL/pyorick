# make this package act like a single module
# - it is a package in order to be easily grouped with pyorick.i0 in setup.py
from .pyorick import *

# limit names exported by "from pyorick import *"
__all__ = ['Yorick', 'PYorickError', 'ynewaxis', 'ystring0']
