Run Yorick from Python
======================

The pyorick package starts `yorick <http://yorick.github.com>`_ as a
subprocess and provides an interface between python and yorick
interpreted code.

Interface to yorick from python
-------------------------------

You can launch yorick as a subprocess with::

    from pyorick import *
    yo = Yorick()

You can execute yorick code, or evaluate a yorick expression like this::

    yo('code')
    v = yo('=expr')

However, the main way to interact with yorick is through one of three
handles::

    chandle = yo.call
    ehandle = yo.evaluate
    vhandle = yo.value

These may be abbreviated to their first character: ``yo.c`` for ``yo.call``, or
``yo.e`` for ``yo.evaluate``, or ``yo.v`` for ``yo.value``.

Attributes of any of the three handle objects represent yorick
variables.  Use the value handle to immediately set or get a whole
variable values from yorick::

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
any, is transmitted to yorick.  Pyorick does not support yorick struct
instances and pointers, nor python class instances.

The call and evaluate handles are primarily intended for referring to
yorick functions.  Unlike python, yorick has two syntaxes for invoking
functions::

    funcname, arglist
    funcname(arglist)

The first form invokes funcname as a subroutine, discarding any return
value, while the second invokes funcname as a function, returning its
value.  Yorick functions frequently have return values, even if they
are usually intended to be invoked as subroutines.  Hence, a python
interface to yorick needs separate call and evaluate handles to allow
for the fact that python has only a single syntax for invoking a
function.  Thus::

    yo.c.funcname(arglist)

invokes the yorick funcname as a subroutine, discarding any return value,
while::

    yo.e.funcname(arglist)

invokes the yorick funcname as a function, returning its value.  The
arglist may include either positional or keyword arguments or both::

    yo.c.plg(y, x, color='red')
    4 * yo.e.atan(1)

The evaluate and call handle attributes do not communicate with yorick
(unlike the value handle attributes, which do).  Instead, they return
references to yorick variables.  Thus, ``yo.c.plg`` is a call-semantics
reference to the yorick variable ``plg``, while ``yo.e.atan`` is an
eval-semantics handle to the yorick variable ``atan``.  The communication
with yorick only occurs when you call the reference, as in the examples.

To kill a running yorick, you can use any of these::

    yo.c.quit()
    yo('quit')
    yo.kill()

The last tries the quit command first, then sends SIGKILL to the
process if that doesn't work.

Variable references can be useful for data variables as well as for
function variables.  In particular, you may want to query the data
type and shape of a variable without actually transferring its data.
Or, if you know a variable is large, you may want to set or get only a
slice, without transferring the entire array.  You can do those things
with an eval-sematics handle instead of a value-semantics handle::

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
from a reference using::

    yo.e.varname.value   # or, if you prefer:
    yo.e.varname.v

Additional properties are available to test for specific types of
data, as a convenience in lieu of the general info property, all
without transferring the object itself::

    is_string  is_number  is_bytes  is_integer  is_real  is_complex
    shape    # tuple for numpy.ndarray or None if not array
    is_func   is_list   is_dict   is_range   is_nil   is_obj
    is_file  # 0 if not, 1 if binary, 2 if text

In general, you can switch from any type of reference to any other by
getting the c, e, or v (or call, evaluate, or value) attribute.  For
example, ``yo.e.varname.c`` is the same as ``yo.c.varname``.

A few attribute names are reserved for use by python (e.g.- ``__init__``),
and so cannot be accessed.  If you need them, you can use the
alternate syntax ``yo.e['funcname']`` or ``yo.c['funcname']`` or
``yo.v['varname']`` wherever you wanted ``yo.e.funcname``, etc.  This syntax
is also useful when the yorick variable name is stored in a python
variable.  As a special case, an empty string item of any handle
returns the original top-level yorick process object.  For example,
``yo.v['']`` returns ``yo``.

You can also call any of the three handles as a function, passing it
yorick code or an expression (the same as the top-level yo object).
When using the evaluate handle, you don't need the "=" prefix to
return an expression value::

    yo.e("expr")    # same as yo("=expr")
    yo.c("code")    # discards any return value, like yo("code")

Although pyorick cannot pass non-array data between python and yorick
(except dict or list aggregates), it does provide you with a means for
holding references to yorick values in a python variable.  For
example, the yorick createb function returns a file handle, which
cannot be transmitted to python.  However, when you ask pyorick to
evaluate an expression which returns an object it cannot transmit, it
returns instead a reference to the object.  You can pass such a
reference back to yorick as a function argument.  For example, you can
create a file, save something to it, and close the file like this::

    f = yo.e.createb("myfile.pdb")
    yo.c.save(f, test=[1.1, 1.2, 1.3])
    del f  # destroying the python reference closes the file

As a side effect, these python reference objects permit you to easily
and naturally create yorick variables holding non-transmittable objects::

    yo.e.f = yo.e.createb("myfile.pdb")
    yo.c.save(yo.e.f, test=[1.1, 1.2, 1.3])
    yo.c.close(yo.e.f)

Without reference objects, the first line would fail -- the createb call
returns a reference object to python, which python passes back to yorick
redefining the yorick f symbol.  Between the first and second lines of
this python code, python discards the reference object, which sends an
implicit command back to yorick removing the original return value of the
createb function, leaving f in yorick as the sole reference to the file.

These reference objects differ from the objects returned by the
evaluate or call handles.  The latter merely hold the name of a yorick
variable, requiring no communication with yorick at all.  The former
hold an index into a list of references yorick holds, for values with
do not (necessarily) belong to any yorick variable, like the result of
an expression.  As we just described, references are created
automatically to hold any expression with an unsupported datatype.
You can also force yorick to return a reference value, even when an
expression or a function result could be transmitted::

    ref1 = yo.e("@expr")  # evaluate expr, return reference to result
    ref2 = yo.e.fun.hold(args)    # return reference to fun(args)
    ref3 = yo.e.ary.hold[indexs]  # return reference to ary(indexs)

Note that ref1, ref2, or ref3 is only useful to pass back to yorick as
a value, an argument, or an index.  In the (unlikely) event that the
reference is a function, it has evaluate semantics by default.  You can
get call semantics or hold-reference sematics like this::

    ref1(args)       # call ref1 as function, return result
    ref1.call(args)  # call ref1 as subroutine, discard result
    ref1.hold(args)  # call ref1 as function, return reference to result

Going in the other direction, when you try to send a non-encodable
python object to yorick (as a variable value or a function argument,
for example), pyorick will pickle it if possible.  It then sends the
pickled object as a 1D array of type char, beginning with
``'thisispickled_'`` plus the md5sum of ``'thisispickled\n'``.
Conversely, if pyorick receives a 1D char array beginning with this
prefix, it unpickles the bytes and returns the resulting object.
Thus, although yorick cannot interpret such objects, it can, for
example, store them in save files, which will make sense when pyorick
reads them back.  You can turn this behavior off by calling
``ypickling(False)`` or back to the default on state with
``ypickling(True)``.

Interface to python from yorick
-------------------------------

Pyorick can also turn python into a terminal emulator for yorick::

    yo()

returns a yorick prompt, at which you can type arbitrary yorick commands.
The py function in yorick returns you to the python prompt if invoked as
a subroutine, or execs or evals python code if passed a string::

    py;   // return to python prompt
    py, "python code";
    py, ["python code line 1", "python code line 2", ...];
    py("python expression")

Any python code or expression is evaluated in the namespace of the
python ``__main__`` program (not, for example, in the pyorick module).
(You can set the variable ``server_namespace`` in the pyorick module to
another namespace -- either a module or a dict -- before you create a
Yorick instance if you want something other than ``__main__`` to be the
namespace for these expressions.)

Additional arguments to the py function cause the expression in the first
argument to be called as a function in python, returning its value, or
discarding any return value if invoked as a subroutine::

    py, "callable_expr", arg1, arg2;
    py("callable_expr", arg1, arg2)

A postfix ``":"`` or ``"="`` at the end of the expression permits you
to set python variable values, or to get or set array slices::

    py, "settable_expr=", value;       # settable_expr = value
    py("array_expr:", i1, i2)          # array_expr[i1, i2]
    py, "array_expr:", i1, i2, value;  # array_expr[i1, i2] = value

Additional features
-------------------

Finally, some minor features or pyorick are worth mentioning:

1. The boolean value of most pyorick objects, such as ``yo``, ``yo.e``, or
   ``yo.e.name``, is True if and only if the underlying yorick process is
   alive.

2. The function ``yencodable(value)`` returns True if and only if the
   python value can be sent to yorick (without pickling).

3. For any of the top-level object or handle object function calls, you
   may supply additional arguments, which will be interpreted as format
   arguments::

    yo(string, a, b, c)   # same as yo(string.format(a,b,c)):
    yo.c("""func {0} {{
               {1}
            }}
         """, name, body)  # note {{ ... }} becomes { ... }

4. Two special objects can be used in data or arguments passed to yorick::

    ystring0
    ynewaxis

   The former looks like '' to python, but will be interpreted as
   string(0) (as opposed to "") in yorick.  The latter is the yorick
   pseudo-index -, which is np.newaxis in python.  Unfortunately,
   np.newaxis is None in python, which is [] in yorick, and interpreted
   as : in the context of an index list.

5. All pyorick generated errors use the ``PYorickError`` class.  There
   is currently no way to handle yorick errors (and continue a yorick
   program) in python, although the yorick error message will be
   printed.  Trying to send an unpicklable object to yorick will raise
   ``PicklingError``, not ``PYorickError``.  In terminal emulator
   mode, pyorick catches all python errors, ignoring them in python,
   but returning error indications to yorick as appropriate.

6. The ``Key2AttrWrapper`` function wraps a python object instance, so
   that its get/setitem methods are called when the get/setattr
   methods of the wrapped instance are invoked.  You can use this to
   mimic yorick member extract syntax in python objects which are
   references to yorick objects, struct instances, or file handles.
