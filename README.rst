Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.

Features:

- exec or eval arbitrary yorick code strings
- get or set yorick variables
- call yorick functions or subroutines with python arguments
- get or set slices of large yorick arrays
- terminal mode to interact with yorick by keyboard through python

Most of the data is exchanged via binary pipes between the two
interpreters.  Yorick runs in a request-reply mode.  Python prints
anything yorick sends to stdout or stderr except prompts.

See `DESCRIPTION.rst <https://github.com/dhmunro/pyorick/blob/master/DESCRIPTION.rst>`_
for a complete description of the interface.  You can clone or fork
`https://github.com/dhmunro/pyorick`_ to contriute to pyorick.

