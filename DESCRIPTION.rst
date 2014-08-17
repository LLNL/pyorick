Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.  The pyorick package defines only two objects:
The yorick() function starts yorick and returns two handles for
all subsequent interactions::

  from pyorick import *
  yo, oy = yorick()

The second object, PYorickError, is an exception class you can use to
identify exceptions thrown by pyorick.

The yo and oy handles are class instances with overloaded call, getattr,
and setattr methods.  The simplest interactions with yorick are from
the call methods:

``yo("yorick code")``
  Send the "yorick code" string to yorick for parsing and execution.

``value = oy("yorick expression")``
  Send the "yorick execution" string to yorick for parsing and execution,
  returning the resulting value.

The yo() call expects a complete yorick statement that returns no
result; it may consist of multiple lines, but if you typed it to
yorick, it must not result in a "cont>" continuation prompt.  The oy()
call must be a complete yorick expression; again it may consist of
multiple lines, but it must be a legal yorick statement when "value="
is prepended.

The getattr and setattr methods are the workhorses of the interface:

``yo.varname = expression``
  Set the yorick variable "varname" to the python expression.

``yo.varname``
  Return the value of the yorick variable "varname" to python.  If
  varname is any numeric, string, or oxy object data, the data is
  actually sent to python.  If varname is a function or a file handle
  or any other non-data object, returns a yorick reference object,
  discussed below.

``oy.varname``
  Return a yorick reference object, discussed below.  Unlike yo.varname,
  nothing is sent to or returned from yorick.

There are two types of yorick reference objects: yo.varname returns an
exec reference, while oy.varname returns an eval reference.  Note that
you can only get an exec reference for functions and other
non-representable objects.  The yorick reference objects have
overloaded call, getitem, and setitem methods.  You use the call
methods to invoke yorick functions:

``yo.yfunction(arg1, arg2, key1=karg1, ...)``
  Call yorick function "yfunction" as a subroutine with the specified
  argument list.

``value = oy.yfunction(arg1, arg2, key1=karg1, ...)``
  Call yorick function "yfunction" as a function with the specified
  argument list, returning its result to python.

In either form, you may pass oy.varname as an argument to use that
yorick variable as the argument.  This is important for later
retrieving yorick output arguments.  It also avoids the round-trip
data passing you would incur by passing yo.varname as an argument.

Finally, with the yorick reference object getitem and setitem methods,
you can retrieve or set slices of large arrays:

``oy.yarray[index1, index2, ...]``
  Return the specified slice of the yorick array "yarray".  Note that
  the indices are in yorick order (fastest varying first) rather than
  the default numpy order.  Also, any index which is a slice min:max
  or min:max:inc is interpreted according to yorick indexing rules
  (1-origin, with max inclusive).  An Ellipsis index is translated
  to the yorick .. index, but None translates to the yorick - index
  (numpy.newaxis).  Use the python : index to get a yorick nil index
  (indicating the entire axis).

``oy.yarray[index1, index2, ...] = expression``
  Set the specified slice of the yorick array "yarray".  Again, the
  indices are interpreted in a yorick-like manner.

Because a yorick array cannot have an associated exec yorick reference
object, ``yo.yarray[index1, index2, ...]`` is very different than
``oy.yarray[index1, index2, ...]``.  Python immediately retrieves the
entire yo.yarray value as a numpy array, so the indices will be
interpreted according to python semantics.  But more importantly, the
entire array is transferred, which may be wasteful.

There is only one yorick process active at any one time.  You can call
the yorick() function multiple times, but the handles it returns always
refer to the single yorick process.  Deleting the yo and oy handles
does not shut down the yorick process.  To do that, call::

  yorick(kill=1)
