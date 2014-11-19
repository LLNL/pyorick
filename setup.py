#!/use/bin/env python

from distutils.core import setup

# This package requires the yorick startup file pyorick.i0 to be
# installed as an ordinary file in the same directory as pyorick.py.
# Even if you have no way to install python packages, you can
# make pyorick.py work by creating a directory, copying pyorick.py
# and pyorick.i0 to that directory, and adding the directory to
# your PYTHONPATH environment variable.  You can optionally copy
# test_pyorick.py to the same directory, cd there, and run nosetests
# or py.test or python -m unittest -v test_pyorick to test pyorick.

setup(name='pyorick',
      version='1.0',
      description='python connection to yorick',
      long_description='Execute yorick code, set and get yorick variables.',
      author='David Munro and John Field',
      author_email='dhmunro@users.sourceforge.net',
      url='https://github.com/dhmunro/pyorick',
      packages=['pyorick'],
      package_data={'pyorick': ['pyorick.i0']},
      requires=['numpy'],
      license='BSD 2-Clause',
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
      )
