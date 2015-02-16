# make this package act like a single module
# - it is a package in order to be easily grouped with pyorick.i0 in setup.py

"""Interface to a yorick process.

See the DESCRIPTION.rst file in the pyorick source distribution for
more detailed explanations.

yo = Yorick()      start a yorick process
yo('code')         execute code in yorick, return None
v = yo('=expr')    execute expr in yorick, return value

yo.v  or  yo.value      value-semantics handle
yo.e  or  yo.evaluate   evaluate-semantics handle
yo.c  or  yo.call       call-semantics handle
  yo.v[''] or yo.e[''] or yo.c[''] return a copy of the parent yo object

yo.c('code')      same as yo('code'), parses and executes code
yo.e('expr')      same as yo('=expr'), returns expr value
  yo(string, a, b, ...)   or   yo.e(string, a, b, ...)
  -shorthand for string.format(a,b,...) passed to yo or yo.e (or yo.c)
yo.v.var          returns value of yorick variable var
yo.v.var = expr   sets value of yorick variable var to expr
  yo.e.var=expr  or  yo.c.var=expr   same as yo.v.var=expr
yo.e.fun(arglist)   returns value of yorick expression fun(arglist)
yo.c.fun(arglist)   calls yorick function as subroutine fun,arglist
yo.e.ary[ndxlist]   returns value of yorick expression ary(ndxlist)
yo.c.ary[ndxlist]     same, but numpy ndxlist semantics
yo.e.ary[ndxlist] = expr   sets yorick array slice ary(ndxlist)=expr
yo.c.ary[ndxlist] = expr     same, but numpy ndxlist semantics

An arglist may include both positional and keyword arguments.  Note
that python syntax requires all keyword arguments to follow all
positional arguments (although yorick syntax does not).

An ndxlist is not distinguishable from an arglist in yorick, but in
python there are syntactic differences: Index ranges start:stop:step
are allowed in an ndxlist, but not in an arglist.  A python arglist
may be empty, but a python ndxlist may not be empty.  The yo.e
evaluate handle passes the index list as-is to yorick, where array
indices begin at 1, the upper limit of an index range is inclusive,
and the index order is fastest-to-slowest varying in memory.  The yo.c
call handle makes a crude attempt to translate ndxlist from numpy to
yorick semantics by swapping the order of ndxlist and attempting to
adjust the numpy 0-origin indexing and range stop semantics.  This
almost certainly does not work in all cases, so you are better off
using the yo.e handle for array indexing.

An ndxlist element may have a string value to extract a member from
a yorick object:
  yo.e.ary['mem']     ary.mem or get_member(ary,"mem") in yorick
  yo.e.ary[1,'mem1',2:3,'mem2']    ary(1).mem1(2:3).mem2 in yorick

Not all objects can be passed through the pipes connecting python and
yorick.  The expr, arglist, and ndxlist elements must be numpy arrays
or array-like nested lists of elements of a common data type
(convertable to numpy arrays with the numpy.array constructor).  Only
numeric or string arrays are permitted.  Yorick strings are iso_8859_1
encoded and '\0'-terminated, so any python strings containing '\0'
characters will be silently truncated at the first '\0' when
transmitted to yorick, and any string which cannot be iso_8859_1
encoded will raise an exception.  In addition to string or numeric
arrays, a slice object or the value None can be encoded, translating
as an index range or [], respectively, in yorick.  Finally, a list or
a string-keyed dict whose members are also encodable (including other
such list or dict objects recursively).  In yorick, these become oxy
objects whose members are all anonymous (for a list) or all named (for
a dict).

yo.c.quit()    quit yorick (by invoking yorick quit function)
yo.kill()      try yo.c.quit(), then SIGKILL if that doesn't work
bool(yo), bool(yo.e), bool(yo.v), bool(yo.e.var), etc.
  True if yorick process is alive, False if it has quit or been killed

yo.v['var']  or  yo.e['var']  or  yo.c['var']
  same as yo.v.var, yo.e.var, or yo.c.var, respectively
  -work for otherwise reserved python attribute names (e.g.- __init__)
  -useful when yorick variable name is stored in python variable

Given yo.e.var or yo.c.var, you can switch to any other handle type,
for example:
var = yo.c.var
var.v  or  var.value   same as yo.v.var, immediately returns value
var.e(arglist)         returns yorick var function value  var(arglist)
var = yo.e.var
var.v  or  var.value   same as yo.v.var, immediately returns value
var.c(arglist)         calls yorick var as subroutine  var,arglist

var = yo.e.var   (or = yo.c.var)
var.info     return [typeid,rank,shape]
var.shape    return numpy.ndarray shape tuple, or None if not array
  Tests for encodable objects:
var.is_string  var.is_number
var.is_bytes  var.is_integer  var.is_real  var.is_complex
var.is_range  var.is_nil  var.is_list  var.is_dict
  Tests for non-encodable objects:
var.is_func
var.is_obj   yorick oxy object with both anonymous and named members
var.is_file  yorick file handle, 0 = not file, 1 = binary, 2 = text

When a yorick variable has an unencodable value, yo.v.var produces the
same python object as yo.c.var.  The call or evaluate semantic
variable objects are simply references to the yorick variable var.  If
that variable is changing in yorick, yo.e.var or yo.c.var always
refers to the value of var at the time python does something using the
object.  You may also pass yo.e.var or yo.c.var as an element of an
arglist or an ndxlist to have yorick place var in the list, without
transmitting its value to python and back (as would happen if you
placed yo.v.var in an arglist or ndxlist).

When a yorick function returns a non-encodable object, pyorick holds
a use (in yorick) of that object, and returns a reference to that use
to python.  For example:
  f = yo.e.createb('myfile.pdb')
returns a reference f to a use of the yorick file handle returned by
the yorick create function.  The python object f is similar to the
reference object yo.e.f, but in this case, there is no yorick variable
corresponding to the object.  You can pass the python f to a yorick
function, for example
  yo.c.save(f, item=[1,2,3])    save [1,2,3] as item in myfile.pdb
  f['item']                     return value of item in myfile.pdb
When the python object f is destroyed, its destructor removes the
(only) use of the corresponding yorick object.  In the case of yorick
file handles, this closes the file:
  del f
Held-reference objects like f are evaluate-semantics variable handles.

You can also hold a use of an encodable yorick object, if you do not
want to pass its value back to python, and you do not want to create
a yorick variable to hold its value:
  yo.e('@expr')    do not transmit value, hold&return use of result
    -passes additional arguments format method of first, as usual
  yo.e.fun.hold(arglist)   fun(arglist), but hold&return use of result
  yo.e.ary.hold[ndxlist]   fun(arglist), but hold&return use of result
Any held-reference object has a value attribute and the various query
attributes, like ordinary reference-by-name objects:
  x = yo.e.random.hold(100,100,1000)  # 1e7 numbers held in yorick
  y = x.v  # or x.value, transmits 1e7 numbers to python
  y = numpy.zeros(x.shape)  # make python array of same shape as x
By default, held-reference objects have evaluate-semantics.  You can
get call semantics with x.call(arglist) as usual.  You can also hold
the result of a function call or slice with x.hold(arglist) or
x.hold[ndxlist].

When you try to send a non-encodable python object to yorick (as a
variable value or a function argument, for example), pyorick will
pickle it if possible.  It then sends the pickled object as a 1D array
of type char, beginning with 'thisispickled_' plus the md5sum of
'thisispickled\n'.  Conversely, if pyorick receives a 1D char array
beginning with this prefix, it unpickles the bytes and returns the
resulting object.  Thus, although yorick cannot interpret such
objects, it can, for example, store them in save files, which will
make sense when pyorick reads them back.  You can turn this behavior
off by calling ypickling(False) or back to the default on state with
ypickling(True).  (The pickling behavior lives in the pyorick pipeline
codec, not in the yorick process handles.)

The following special objects are available for use in expressions used
to set variable values in yorick:
  ystring0     yorick string(0) is C NULL, different than ""
  ynewaxis     np.newaxis is None, which yorick interprets as :
The ystring0 value is also passed back to python to represent a string(0)
value in yorick.  It is derived from str and has value '' in python.  You
can check for it with "s is ystring0" if you need to distinguish.

Pyorick also provides a Key2AttrWrapper function that wraps an object
instance so that its get/setitem methods are called when the
get/setattr methods of the wrapped instance are invoked.  You can use
this to mimic yorick member extract syntax in python objects which are
references to yorick objects, struct instances, or file handles.

All pyorick generated errors use the PYorickError exception class,
although PicklingError may be raised if pickling fails.

Finally, pyorick can turn the python command line into a yorick terminal:
  yo()          enter yorick terminal mode, special yorick commands are:
    py            from yorick terminal mode returns to python
    py, "code"    from yorick terminal mode to exec code in python
    py("expr")    from yorick terminal mode to eval expr in python
    py, "expr=", value  sets python expr to value
    py("expr", arg1, arg2, ...)  returns python expr(arg1,arg2,...)
    py("expr:", ndx1, ndx2, ...) returns python expr[ndx1,ndx2,...]
    py, "expr:", ndx1, ..., value  sets python expr[ndx1,...]=value
By default, python expressions are evaluated in the context of __main__,
not in the context of the pyorick module.
Python errors in terminal mode are caught and ignored by python, but will
raise an exception in yorick.
"""

from .pyorick import *

# limit names exported by "from pyorick import *"
__all__ = ['Yorick', 'PYorickError', 'Key2AttrWrapper',
           'ynewaxis', 'ystring0', 'yencodable', 'ypickling']
