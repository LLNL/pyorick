Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.  Pyorick provides a full interface to yorick,
plus a simpler interface.

Simplified interface
--------------------

You interact with yorick via two interface handles, returned by the
yorick() function:

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
prepended.  In the case of yo(), the yorick code executes, but returns
no value to python.  The oy() call returns an expression value.

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

There are two types of yorick reference objects: yo.varname returns a
subroutine-like reference, while oy.varname returns a function-like
reference.  The yorick reference objects have overloaded call,
getitem, and setitem methods.  You use the call methods to invoke
yorick functions:

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
Since python has no equivalent distinctions, you distinguish the two
cases by using the appropriate handle.

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
  or min:max:inc is interpreted according to yorick indexing semantics
  (1-origin, with max inclusive).  An Ellipsis index is translated
  to the yorick .. index.  However, if you need the numpy.newaxis,
  which translates to yorick's - index, you must pass the pyorick new_axis
  instead.  That is because numpy.newaxis is a synonym for None, which
  pyorick translates to yorick's nil [], which in turn means the full
  range of the index (equivalent to : in python).

``oy.yarray[index1, index2, ...] = expression``
  Set the specified slice of the yorick array "yarray".  Again, the
  indices are interpreted in a yorick-like manner.

Because a yorick array cannot have an associated exec yorick reference
object, ``yo.yarray[index1, index2, ...]`` is very different than
``oy.yarray[index1, index2, ...]``.  Python immediately retrieves the
entire yo.yarray value as a numpy array, so the indices will be
interpreted according to python semantics.  If you want python slicing
semantics, and you need to avoid transferring the whole array to
python before slicing, you can use the python-like reference objects
available in the full interface.

Full interface
--------------

The full interface may be conceptually simpler than the simplified
interface, but as a user you need to type slightly more.  The principal
object in the full interface is the yorick connection object:

yc = Yorick()

In the simplified interface, the underlying connection for the yo and oy
handles is the _yorick attribute, yo._yorick or oy._yorick.

Each instance of Yorick represents a different yorick process.  A
Yorick instance directly exposes all of the command and transfer
methods available:

``yc.kill()``
  Close the connection, and reap the child yorick process.

``yc("code")``
  Parse and execute the yorick code, returning None.

``yc("=expr")``
  Parse and execute the yorick expression, returning its value.

``yc.getvar(name)``
  Return value of yorick name variable.

``yc.setvar(name, value)``
  Set value of yorick name variable, returning None.

``yc.funcall(name, arg1, arg2, key1=karg1, ...)``
  Return value of yorick name as function with given arguments.

``yc.subcall(name, arg1, arg2, key1=karg1, ...)``
  Call yorick name as subroutine with given arguments, returning None.

``yc.getslice(name, reftype, index1, index2, key1=kindex1, ...)``
  Return value of slice of yorick name array.  With reftype=1, the
  index list is interpreted according to yorick semantics (fastest
  varying first, 1-origin, slice max inclusive); with reftype=2, the
  index list is interpreted according to python semantics.

``yc.setslice(name, reftype, index1, index2, key1=kindex1, ...)``
  Set value of slice of yorick name array, returning None.  The
  reftype determines whether the index list is interpreted according
  to yorick (1) or python (2) semantics, as for getslice.

``yc.getshape(name)``
  Return (type, shape) for yorick name variable without retrieving its value.
  The shape is a tuple matching the ndarray shape.  For strings, which become
  nested lists in python, type=1 and shape is the shape tuple it would have
  if converted to an ndarray.  For anything else, shape is None and type is
  a small integer: 2 func, 3 list, 4 dict, 5 slice, 6 None, 7 binary file,
  and 8 or 9 something else.

``yc.setdebug(on)``
  Turn debug mode on or off.  Debug mode generates lots of output.

``yc.setmode(interactive)``
  Turn interactive mode on or off.  By default, yorick starts in interactive
  mode.  Batch mode will probably confuse you; it's for experts.

These methods require typing quotes around the name argument for the
get/setvar, fun/subcall, get/setslice, or getshape functions.  To
avoid that, the yorick connection instance provides three attributes
that overload the getattr, setattr, and call methods:

``yc.v``
  The "by value" interface.  This is the yo object in the simple interface.

``yc.r``
  The "by reference" interface.  This is the oy object in the simple interface.

``yc.p``
  The "by reference, python indexing semantics" interface.

Hence, ``yc.v.varname`` is the same thing as ``yo.varname``, and
``yc.r.varname`` is the same thing as ``oy.varname``.  There is no
equivalent to ``yc.p.varname`` in the simplified interface.  However,
all reference objects have several methods of their own, and
``oy.varname.p()`` returns ``yc.p.varname``.  All of the variable
reference objects have the following methods:

``varref(arg1, arg2, key1=karg1, ...)``
  Calls the yorick variable with the given arguments.  The yc.v by value
  varref invokes the variable as a subroutine returning None.  The
  yc.r by reference varref invokes the variable as a function, returning
  its result.  Finally, the yc.p varref invokes the variable as a
  subroutine, returning None, the same as yc.v.  However, with yc.p,
  you avoid a round trip to yorick -- ``yc.v.varname`` gets the
  reference back from yorick before the call, while ``yc.p.varname``
  does not talk to yorick at all.

``varref[index1, index2, ...]``
  Returns the specified slice of the yorick variable.  With a yc.r varref,
  the index semantics are yorick's, for the other two, the index semantics
  are python's.

``varref[index1, index2, ...] = <expr>``
  Sets the specified slice of the yorick variable.  With a yc.r varref,
  the index semantics are yorick's, for the other two, the index semantics
  are python's.

``type, shape = varref.info()``
  Returns the type and shape information about the yorick variable, without
  transferring its value.  Same as ``yc.getshape(name)`` above.

``varref.p()``
  Returns a varref referring to the same variable, but of type yc.p.

``varref.y()``
  Returns a varref referring to the same variable, but of type yc.r.
  (The y means "yorick semntics".)

Note that these varref methods are all equally available in the
simplified interface.
