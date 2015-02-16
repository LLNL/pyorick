#!/usr/bin/env python

# to upload to pypi:
# <switch to setuptools branch, merge with master>
# git clean -fdx
#   first time: python setup.py register
# python setup.py sdist bdist_wheel upload

from __future__ import print_function
from setuptools import setup, Command

class TestCommand(Command):
  description = "PYorick test/check command"
  user_options = []
  def get_command_name(self):
      return "test"
  def initialize_options(self):
      pass
  def finalize_options(self):
      pass
  def run(self):
    try:
      import pyorick.test_pyorick as testmod
      import unittest
      for c in [testmod.TestProcess, testmod.TestCodec]:
        print("Testing", str(c))
        suite = unittest.TestLoader().loadTestsFromTestCase(c)
        unittest.TextTestRunner(verbosity=2).run(suite)
    except Exception as e :
      raiseNameError("setup.py test: error in test\nException: {0}".format(e))
    return

# This package requires the yorick startup file pyorick.i0 to be
# installed as an ordinary file in the same directory as pyorick.py.
# Even if you have no way to install python packages, you can
# make pyorick.py work by creating a directory, copying pyorick.py
# and pyorick.i0 to that directory, and adding the directory to
# your PYTHONPATH environment variable.  You can optionally copy
# test_pyorick.py to the same directory, cd there, and run nosetests
# or py.test or python -m unittest -v test_pyorick to test pyorick.

setup(name='pyorick',
      version='1.4',
      description='python connection to yorick',
      long_description=open('README.rst').read(),
      author='David Munro and John Field',
      author_email='dhmunro@users.sourceforge.net',
      url='https://github.com/dhmunro/pyorick',
      packages=['pyorick'],
      package_data={'pyorick': ['pyorick.i0']},
      requires=['numpy'],
      license='http://opensource.org/licenses/BSD-2-Clause',
      platforms=['Linux', 'MacOS X', 'Unix'],
      classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Unix',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Interpreters',
        ],
      cmdclass = {'test': TestCommand},
      )
