#!/use/bin/env python

from distutils.core import setup

setup(name='pyorick',
      version='1.0',
      description='python connection to yorick',
      long_description='Execute yorick code, set and get yorick variables.',
      author='David Munro and John Field',
      author_email='dhmunro@users.sourceforge.net',
      url='https://github.com/dhmunro/pyorick',
      packages=['pyorick'],
      package_data={'pyorick': ['pyorick.i0']},
      license='BSD New',
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
