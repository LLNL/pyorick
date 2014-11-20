Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.  Pyorick provides a full interface to yorick,
plus a simpler interface.

Simplified interface
--------------------

You can launch yorick as a subprocess with:

    from pyorick import *
    yo = Yorick()

To kill a running yorick, do this:

    yo.kill()

You can execute yorick code, or evaluate a yorick expression like this:

    yo('code')
    v = yo('=expr')

However, the main way to interact with yorick is through one of three
handles:

    chandle = yo.call
    ehandle = yo.evaluate
    vhandle = yo.value

These may be abbreviated to their first character: yo.c for yo.call, or
yo.e for yo.evaluate, or yo.v for yo.value.

Attributes of any of the three handle objects represent yorick
variables.  Use the value handle to immediately set or get a whole
variable values from yorick:

    yo.v.varname = <expr, any python expression>
    yo.v.varname

The data passed to yorick by setting an attribute, or retrieved from
yorick by getting an attribute can be any numeric or string scalar or
array, or an index range (slice in python), or nil (None in python),
or an oxy object whose members are all supported data types.  The oxy
object in yorick will be a list in python if all its members are
anonymous, and a dict in python if all its members have names.  Yorick
numeric scalars or arrays become python numpy arrays.  Yorick scalar
strings become python unicode strings, while yorick arrays of strings
become nested lists of python unicode strings.  Yorick strings are
encoded and decoded as iso_8859_1 python character sequences, and only
the part of a python string up to the first ``'0x00'`` character, if
any, is transmitted to yorick.  Yorick struct instances and pointers
are unsupported, as are python class instances.

The call and evaluate handles are primarily intended for referring to
yorick functions.  Unlike python, yorick has two syntaxes for invoking
functions:

    funcname, arglist
    funcname(arglist)

The first form invokes funcname as a subroutine, discarding any return
value, while the second invokes funcname as a function, returning its
value.  Yorick functions frequently have return values, even if they
are usually intended to be invoked as subroutines.  Hence, a python
interface to yorick needs separate call and evaluate handles to allow
for the fact that python has only a single syntax for invoking a
function.  Thus,

    yo.c.funcname(arglist)

invokes the yorick funcname as a subroutine, discarding any return value,
while

    yo.e.funcname(arglist)

invokes the yorick funcname as a function, returning its value.  The
arglist may include either positional or keyword arguments or both:

    yo.c.plg(y, x, color='red')
    4 * yo.e.atan(1)

The evaluate and call handle attributes do not communicate with yorick
(unlike the value handle attributes, which do).  Instead, they return
references to yorick variables.  Thus, yo.c.plg is a call-semantics
reference to the yorick variable plg, while yo.e.atan is an
eval-semantics handle to the yorick variable atan.  The communication
with yorick only occurs when you call the reference, as in the examples.

Variable references can be useful for data variables as well as for
function variables.  In particular, you may want to query the data
type and shape of a variable without actually transferring its data.
Or, if you know a variable is large, you may want to set or get only a
slice, without transferring the entire array.  You can do those things
with an eval-sematics handle instead of a value-semantics handle:

    yo.e.varname.info
    yo.e.varname[indexlist] = <expr>
    yo.e.varname[indexlist]

The info property is an integer array with info[0] a data type code,
and for array types info[1] is the rank, and info[2:2+rank] are the
dimension lengths in yorick order.  The indexlist also has yorick
index semantics (first index varies fastest in memory, 1-origin
indices, slices include their stop value).  The call handle attempts
to convert indexlist from python index list semantics (first index
slowest, 0-origin, slice stop non-inclusive) in
yo.c.varname[indexlist], but you are better off sticking with yorick
semantics if you possibly can.  Finally, you can read the whole value
from a reference using:

    yo.e.varname.value
    yo.e.varname.v

In general, you can switch from any type of reference to any other by
getting the c, e, or v (or call, evaluate, or value) attribute.  For
example, yo.e.varname.c is the same as yo.c.varname.

A few attribute names are reserved for use by python (e.g.- __init__),
and so cannot be accessed.  If you need them, you can use the
alternate syntax yo.e['funcname'] or yo.c['funcname'] or
yo.v['varname'] wherever you wanted yo.e.funcname, etc.  This syntax
is also useful when the yorick variable name is the value of a python
variable.  As a special case, an empty string item of any handle
returns the original top-level yorick process object.  For example,
yo.v[''] returns yo.

Two special objects can be used in data or arguments passed to yorick:

    ystring0
    ynewaxis

The former looks like '' to python, but will be interpreted as
string(0) (as opposed to "") in yorick.  The latter is the yorick
pseudo-index -, which is np.newaxis in python.  Unfortunately,
np.newaxis is None in python, which is [] in yorick, and interpreted
as : in the context of an index list.

Lastly, pyorick can turn python into a terminal emulator for yorick:

    yo()

returns a yorick prompt, at which you can type arbitrary yorick commands.
The py function in yorick returns you to the python prompt if invoked as
a subroutine, or execs or evals python code if passed a string:

    py;
    py, "python code";
    py, ["python code line 1", "python code line 2", ...];
    py("python expression")
