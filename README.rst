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

Most of the data is exchanged via binary pipes between the two
interpreters.  Yorick runs in a request-reply mode.  Python prints
anything yorick sends to stdout or stderr except prompts.
