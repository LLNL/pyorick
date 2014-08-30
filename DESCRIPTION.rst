Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.  You interact with yorick via two interface handles,
returned by the yorick() function:

  from pyorick import *
  yo, oy = yorick()

The yo and oy handles are class instances with overloaded call,
getattr, and setattr methods.  The handles do similar, but not
identical things.  For example, the simplest interactions with yorick
are from the call methods:

``yo("yorick code")``
  Send the "yorick code" string to yorick for parsing and execution.

``value = oy("yorick expression")``
  Send the "yorick execution" string to yorick for parsing and execution,
  returning the resulting value.

The yo() call expects a complete yorick statement that returns no
result; it may consist of multiple lines, but if you typed it to
yorick, it must not result in a "cont>" continuation prompt.  The oy()
call must be a complete yorick expression; again it may consist of
multiple lines, but it must be a legal yorick statement with "value="
prepended.  In the case of yo(), the yorick code executes, but no
value is returned to python; if you need an expression returned, you
use oy().

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
  nothing is sent to or returned from yorick.  Setting an attribute using
  the oy handle, oy.varname = expression, is the same as for the yo handle.

There are two types of yorick reference objects: yo.varname returns an
exec reference, while oy.varname returns an eval reference.  The
yorick reference objects have overloaded call, getitem, and setitem
methods.  You use the call methods to invoke yorick functions:

``yo.yfunction(arg1, arg2, key1=karg1, ...)``
  Call yorick function "yfunction" as a subroutine with the specified
  argument list.

``value = oy.yfunction(arg1, arg2, key1=karg1, ...)``
  Call yorick function "yfunction" as a function with the specified
  argument list, returning its result to python.

Once again, you use the yo handle if you want to discard (and not
transfer) any return value, while you use the oy handle to return a
function value.  Unlike python, yorick functions may be specifically
invoked as subroutines, and some functions (e.g.- save) behave
differently when called as subroutines than when called as functions.
Since python has no equivalent distinctions, pyorick uses its two
interface handles to make this distinction.

In either form, you may pass oy.varname as an argument to use that
yorick variable as the argument.  This is important for later
retrieving yorick output arguments.  It also avoids the round-trip
data passing you would incur by passing yo.varname as an argument.
Note that you may pass keyword arguments as well as positional
arguments.

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
interpreted according to python semantics.  For the time being, the
entire array is transferred, which may be wasteful.

Eventually, ``yo.yarray`` will also be a true reference object, but it
will retain the python indexing and slice semantics.  Hence, for array
slices, the distinction between yo and oy handles is that you use the
oy handle when you want to get yorick index order and slice semantics,
whereas you use the yo handle when you want python index order and
slice semantics.

