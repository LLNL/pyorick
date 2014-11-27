# make this package act like a single module
# - it is a package in order to be easily grouped with pyorick.i0 in setup.py

"""Interface to a yorick process.

yo = Yorick()      start a yorick process
yo.kill()          kill a yorick process

yo('code')         execute code in yorick, return None
v = yo('=expr')    execute expr in yorick, return value

Three different handles to the yorick process provide a nicer interface:
  chandle = yo.call      call-semantics handle
  ehandle = yo.evaluate  eval-semantics handle
  vhandle = yo.value     value-semantics handle
  chandle, ehandle, vhandle = yo.handles(7)
For interactive use, you may abbreviate
yo.call as yo.c, yo.evaluate as yo.e, and yo.value as yo.v.

Attributes of any handle object represent yorick variables, for example:
  yo.v.var = <expr>   sets the yorick variable var to the python <expr>
  yo.v.var            in a python expression gets the yorick variable var
The three types of handles come into play when the yorick variable is a
function rather than data, or when you want to refer to data stored in a
yorick variable without moving the entire array from yorick to python.

Python has only one syntax for invoking functions, whereas yorick has two
-- one to invoke the function and return its value, the other to invoke
the function as a subroutine, discarding its value.  The eval-semantics
handle produces yorick function references which return a value, whereas
the call-semantics handle produces yorick functions which will be invoked
as subroutines:
  yo.e.atan(<expr>)   returns yorick atan(<expr>)
  yo.c.plg(y, x)      invokes yorick plg,y,x
You can pass both positional and keyword arguments to either type of
function reference:
  yo.c.plg(y, x, color='red')

Thus, you usually want to use yo.v to set or get array data in yorick
variables, yo.c to call yorick functions as subroutines (discarding any
result), yo.e to return a yorick function value, and yo('code') to
parse yorick code (for example, to define an interpreted function).
The exception is, when you want to set or get only a part of a yorick
array, because the whole array is very large and you don't want the
performance penalty of transmitting the whole thing to or from yorick.
To do that, use the evaluate instead of the value handle:
  yo.e.var[ndx1, ndx2, ...] = <expr>  # set a slice of yorick array var
  yo.e.var[ndx1, ndx2, ...]           # get a slice of yorick array var
Each ndxI expression can be a scalar value, a list of integers, or a
slice start:stop:step.  The index expressions have yorick semantics, not
numpy semantics, that is: (A) dimension order is fastest varying to
slowest varying, (B) index origin is 1, and (C) the stop value in a
slice is included as part of the slice.  If you want numpy index semantics,
you can use the call handle yo.c.var[ndxlist], and pyorick will swap the
index order and attempt to fix the index origin and slice stop values.

A few potential yorick variable names cannot be accessed using the
yo.<handle>.varname syntax (e.g.- __init__).  For these cases, all
three handles accept a dict-like key:
  yo.v['var']   same as   yo.v.var   (same for yo.c, yo.e handles)
This feature is useful if the name of the yorick variable is the value
of a python string variable as well.

The call and evaluate handle attributes return a reference to a yorick
variable, which doesn't actually communicate with yorick until you use
it.  That is, yo.e.var is just a reference to the yorick variable 'var'
with eval-sematics, while yo.c.var is a reference with call-semantics.
Variable reference objects implement methods to actually retrieve data
with yo.e.var(args) or yo.e.var[ndxs].  Note that yorick does not distinguish
between var(args) and var[ndxs], so they do the same thing in pyorick.
However, in python, yo.e.var(1:2) is a syntax error, while yo.e.var[1:2]
is not.  Similarly, python syntax does not permit keywords in index lists,
nor keywords preceding positional arguments in argument lists.

Yorick variable reference objects have several properties:
  yo.e.var.info     # returns datatype and shape information about var
  yo.e.var.value    # returns the value of var, like yo.v.var
  yo.e.var.v        # returns the value of var, like yo.v.var
In general, you can convert any variable handle sematics to another
semantics, so yor.e.var.c is a call-semantics reference for var,
yo.c.var.e is and eval-semantics references, and so on.  Info returns
a 1D array [typeid, rank, dim1, dim2, ..., dimN] for an array type,
where typeid is 1, 2, 3 for short, int, long integers, 8 for bytes
(char in yorick, uint8 in numpy), 5, 6 for float, double reals, 14
for complex, and 16 for string data.  The dimension lengths are in
yorick order, fastest to slowest varying in memory.  For non-array
data, info returns a single element array [typeid], -1 for a function,
-2 for a list-like anonymous object, -3 for a dict-like object, -4 for
a slice, -5 for nil, -6 for a file handle, and -7 or -8 for
other non-representable objects.

An value handle attribute representing a non-data yorick variable, such
as a function or a file handle, also returns a yorick variable reference
(after a brief exchange with yorick).  A reference returned by a value
handle in this way is treated like a call-semantics reference.  Thus,
yo.v.plg is essentially the same as yo.c.plg.

All yorick array types except pointer and struct instance are valid data.
A yorick string maps to a python str, but only str which do not contain
any '\0' characters are possible in yorick.  Going from python to yorick,
a str is silently truncated at its first '\0'.  A yorick array of strings
becomes a nested list of python str.  In general, nested lists of python
numbers will be converted to numpy arrays and sent to yorick.  A numpy
array of strings, in addition to a nested list of strings, can also be
sent to yorick.  A python list (or other sequence) of arbitrary
representable data objects maps to an anonymous oxy object in yorick.
A python dict with str keys maps to a yorick oxy object with named
members.

The following special objects are available for use in expressions used
to set variable values in yorick:
  ystring0     yorick string(0) is C NULL, different than ""
  ynewaxis     np.newaxis is None, which yorick interprets as :
The ystring0 value is also passed back to python to represent a string(0)
value in yorick.  It is derived from str and has value '' in python.  You
can check for it with "s is ystring0" if you need to distinguish.

Finally, pyorick can turn the python command line into a yorick terminal:
  yo()          enter yorick terminal mode, special yorick commands are:
    py            from yorick terminal mode returns to python
    py, "code"    from yorick terminal mode to exec code in python
    py("expr")    from yorick terminal mode to eval expr in python
"""

from .pyorick import *

# limit names exported by "from pyorick import *"
__all__ = ['Yorick', 'PYorickError', 'ynewaxis', 'ystring0']
