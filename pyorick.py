# pyorick.py

"""Interface to yorick as a subprocess.

yo, oy = yorick()          start and connect to yorick
yo.var = <expr>            redefine variable var in yorick
yo.var                     retrieve contents of yorick variable var
yo("yorick code")          parse and execute yorick code, returning None
yo("=yorick expression")   parse, execute, and return yorick expression
yo("pyformat", parg1, ...)    means yo("pyformat".format(arg1, arg2, ...))
yo.fun(arg1, arg2, ...)    invoke yorick function fun as subroutine
oy.var                     create reference to yorick variable var
oy("yorick expression")    parse, execute, and return yorick expression
oy.ary[ndx1, ndx2, ...]            retrieve slice of yorick array ary
oy.ary[ndx1, ndx2, ...] = <expr>   set slice of yorick array ary
oy.fun(arg1, arg2, ...)    invoke yorick function fun, returning result

Notes:
1. yo.fun(args) discards any return value, oy.fun(args) does not
2. yo.fun[args] and oy.fun[args] are the same as oy.fun(args)
   except that keyword arguments are not permitted in args list
3. Using oy.var as an argument gives same result as yo.var, but
   without sending yorick var value to python and back.
4. Currently no direct support for yorick output &argument, but could be?
5. Future extension: yo() enters yorick interactive mode, does not return
   until user types matching yorick command.
"""

# attempt to make it work for both python 2.6+ and python 3.0+
import six

# TODO:
# Currently, deleting yo and oy will leave the connection open,
# but reconnectable by calling yorick() again.  Think about whether
# __del__ method should call kill=1.  Since there is only one instance
# of yorick, my current thought is no.

import numpy as np

import os
import select
import shlex
from numbers import Number
from collections import Sequence
from ctypes import c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint,\
                   c_long, c_ulong, c_longlong, c_ulonglong,\
                   c_float, c_double, c_longdouble

import termios

# set to full path if not on PATH or yorick's .i search path, respectively
_yorick_command = "yorick"
_pyorick_dot_i = "pyorick.i"
_yorick_command = "/home/dave/gh/yorick/relocate/bin/yorick"
_pyorick_dot_i = "/home/dave/gh/pyorick/pyorick.i"

def yorick(args="", debug=None, batch=None, kill=None, mode=None):
  """Return (yo,oy) pair of yorick interface objects.

  Optional parameters:
  args      (default "") additional yorick command line arguments
  debug     (default None) turn on pyorick.i debugging (pydebug=1)
  batch     (default None) true to start yorick in batch mode
  kill      (default None) kill existing yorick and return None

  Starts yorick as a subprocess with two pipes, one for python
  to yorick, and one for yorick to python messages.  The yorick
  stdin, stdout, and stderr streams are captured as a pty-tty,
  but are unused for exchanging data or commands.  The interface
  objects manage data and commands flowing through the pipes.
  Roughly speaking, the yo interface is by value, while the oy
  interface is by reference.
  """
  # only one yorick can be attached at a time
  # this mimics what would happen if yorick were built into python
  # if ever implement connections to remote machines, may want to revisit
  global _pid, _pfd, _rfd, _wfd, _batch, _need_response
  global _debug, _mode, _mode_tmp
  if kill:
    _yorick_destroy()
    return None

  if batch:
    mode = False
  elif (mode is None):   # set default mode
    mode = True
  else:
    mode = bool(mode)

  if (_pid is None) and (not kill):
    if batch:
      argv = [_yorick_command, "-batch", _pyorick_dot_i]
    else:
      argv = [_yorick_command, "-q", "-i", _pyorick_dot_i]
    _rfd, _wfd, _pfd, _pid = _yorick_create(_yorick_command, argv, args)
    _need_response = False
    _debug = _mode = _mode_tmp = False
    _batch = bool(batch)
  rslt = (_YorickInterface(0), _YorickInterface(1))

  if mode != _mode:
    _yorick_flush()
    _mode_tmp = mode
    _subcall("pyorick", (int(mode),), {})

  if debug is not None:
    if bool(debug) != _debug:
      _debug = bool(debug)
      _parsex("pydebug = 1" if _debug else "pydebug = 0")

  return rslt

class PYorickError(Exception):
  """Exception raised by pyorick module."""
  pass

NewAxis = {}  # use this as non-None flag for numpy.newaxis
# eventually could support yorick index range in this way

########################################################################
# Remainder of module is hidden from users, who interact only with
# the two instances of _YorickInterface returned by yorick().

_pid = None  # else used before defined

def _yorick_create(_yorick_command, argv, args):
  ptoy = os.pipe()
  ytop = os.pipe()
  _pid, _pfd = os.forkpty()
  #_pid = os.fork()
  if not _pid:   # subprocess side
    os.close(ptoy[1])
    os.close(ytop[0])
    argv.extend([str(ptoy[0]), str(ytop[1])])
    #if _debug:
    #  argv.append("--debug")
    if args:
      argv.extend(shlex.split(args))
    os.execvp(_yorick_command, argv)
    os._exit(1)            # failed to launch yorick
  os.close(ptoy[0])
  os.close(ytop[1])
  _rfd = ytop[0]
  _wfd = ptoy[1]
  # set reasonable termios attributes
  t = termios.tcgetattr(_pfd)
  t[3] = t[3] & ~termios.ECHO
  termios.tcsetattr(_pfd, termios.TCSANOW, t)
  return _rfd, _wfd, _pfd, _pid

def _yorick_destroy():
  global _pid, _pfd, _rfd, _wfd
  global _batch, _need_response, _debug
  if _pid is not None:
    try:
      os.close(_pfd)
      os.close(_rfd)
      os.close(_wfd)
      os.waitpid(_pid, 0)   # otherwise yorick becomes a zombie
    finally:
      _pid = _pfd = _rfd = _wfd = _batch = None
      _debug = _mode = _mode_tmp = False
      _need_response = False

_last_prompt = ''
def _yorick_flush(clear=None):
  global _last_prompt
  if clear:
    _last_prompt = ''
  s = ''
  i = 0    # curiously hard to get response promptly?
  while _pfd is not None and i < 3:
    try:
      p = select.select([_pfd], [], [_pfd], 0)
    except:
      p = (0, 0, 1)
    if p[0]:
      try:
        s += os.read(_pfd, 16384)
      except:
        p = (0, 0, 1)
    if p[2]:
      yorick(kill=1)
    if not p[0]:
      i += 1
  if s:
    # remove prompt in one-shot mode
    if _mode and s.endswith("> "):
      i = s.rfind('\n') + 1  # 0 on failure
      _last_prompt = s[i:]
      s = s[0:i]
    # remove final newline, since print adds one
    # -- consider python 3 print function
    if s and s[-1]=='\n':
      s = s[0:-1]
      if s and s[-1] == '\r':
        s = s[0:-1]
    if s:
      print(s)

def _wait_for_prompt():
  _yorick_flush(1)
  while not _last_prompt:
    p = select.select([_pfd], [], [_pfd])
    _yorick_flush()

class _YorickInterface:
  """Main interface to yorick process.

  There are two slightly different interface instances, called
  by convention yo and oy.  In both cases, attributes represent the
  yorick variable of the same name, for example, yo.var represents
  the yorick variable var.  The difference is that yo.var is the value
  of var (potentially requiring a large data transfer from yorick to
  python), while oy.var is a reference to yorick's var (requiring no
  transfer of data at all).  You can use either yo or oy to set the
  value of a yorick variable: yo.var=value is same as oy.var=value.

  When var is a yorick function, yo.var and oy.var both return references
  to the function, since there is no way in yorick to represent a function
  as a value.   However, there is a difference between the two reference
  objects: yo.fun(args) invokes fun in yorick as a subroutine, returning
  None to python, while oy.fun(args) invokes fun in yorick as a function,
  returning whatever fun returns to python.

  Reference objects can be used to slice arrays, as in oy.a[index_list],
  which passes only the required subset back to python.  This is very
  different from yo.a[index_list]: Not only does yo.a move the whole array
  from yorick to python before extracting the slice, but also python's
  dimension order and indexing conventions are different from yorick's.
  The index_list in oy.a[index_list] obeys yorick's indexing conventions,
  while in yo.a[index_list], it obeys python's indexing conventions.
  You can use oy.a[index_list]=value to set the value of a slice of a
  yorick array, while yo.a[index_list]=value is meaningless.

  Finally, yo(text) parses and executes a string or sequence of strings
  in yorick.  The return value is None, unless the first character is "=",
  in which case the text must be a single yorick expression, whose value
  is returned.  To provide a shorthand, oy(expr_text) prepends an "="
  to the text, always returning an expression value.  This is somewhat
  similar to the usage yo.fun(args), which always retuns None, whereas
  oy.fun(args) returns the function value.  Anticipating that you will
  often want to construct text using python's format method, additional
  arguments after text invoke its format method: yo(text,arg1,arg2) is
  the same thing as yo(text.format(arg1,arg2)).
  """
  def __init__(self, ref):
    self.__dict__['__ref'] = ref  # self.ref calls __setattr__
  def __repr__(self):
    return "".join(["<yorick process by ",
                    "reference" if self.__dict__['__ref'] else "value", ">"])
  def __call__(self, command, *args, **kwargs):  # pipe(command)
    if args or kwargs:
      command = command.format(*args, **kwargs)
    if self.__dict__['__ref']:
      command = "=" + command
    _check_live()
    return _parsex(command)
  def __setattr__(self, name, value):            # pipe.name = value
    if name not in self.__dict__:
      _check_live()
      _setvar(name, value)
    else:
      object.__setattr__(self, name, value)
  def __getattr__(self, name):                   # pipe.name
    # inspect module causes serious problems by probing for names
    # ipython also probes for getdoc attribute
    if _is_sysattr(name) or name=='getdoc':
      raise NameError("_YorickInterface instance has no attribute '"+name+"'")
    ref = self.__dict__['__ref']
    if name == '__ref':
      return ref
    _check_live()
    if ref:
      return _YorickRef(self, name)
    else:
      return _getvar(name, self)

class _YorickRef:
  def __init__(self, pipe, name):
    """Reference to a yorick variable, created by interface object."""
    self.pipe = pipe
    self.name = name
  def __repr__(self):
    flag = "invoke" if self.pipe.__ref else "call"
    return "<yorick variable {0} ({1})>".format(self.name, flag)
  def __call__(self, *args, **kwargs):   # ref(arglist)
    _check_live()
    if self.pipe.__ref:
      return _funcall(self.name, args, kwargs)
    _subcall(self.name, args, kwargs)
  def __setitem__(self, key, value):     # ref[key] = value
    _check_live()
    _setslice(self.name, key, value)
  def __getitem__(self, key):            # ref[key]
    _check_live()
    return _getslice(self.name, key)

def _is_sysattr(name):
  return len(name)>3 and name[0:2]=='__' and name[-2:]=='__'

def _check_live():
  if (_rfd is None) or (_wfd is None):
    raise PYorickError("no yorick connection")

# numpy dtype to C-type correspondence
# C-types: char short int  long longlong float  double longdouble
# dtypes:  byte short intc int_ longlong single double   <none?>
#          unsigned: u prefix except uint instead of uint_
#          complex: csingle (float) and complex_ (double)
# Python types: int_ (long), float_ (double), complex_
# - better to use ctypes module
# - someday construct complex dtypes from ctypes floats?
_types = [c_byte, c_short, c_int, c_long, c_longlong,
          c_float, c_double, c_longdouble,
          c_ubyte, c_ushort, c_uint, c_ulong, c_ulonglong,
          np.csingle, np.complex_, None]
_types = [(np.dtype(t) if t else None) for t in _types]
_isizes = [t.itemsize for t in _types[0:5]]
_fsizes = [t.itemsize for t in _types[5:8]]
_py_long = _types[3]

# id 0-15 are numeric types:
#    char short int long longlong   float double longdouble
# followed by unsigned, complex variants
# passive messages (response prohibited):
_ID_STRING = 16   # yorick assumes iso_8859_1, need separate id for utf-8?
_ID_SLICE = 17
_ID_NIL = 18
_ID_GROUP = 19
_ID_EOL = 20
# active messages (passive response required):
_ID_PARSEX = 32
# arguably should split PARSEX into EVAL and EXEC, to make four pairs
_ID_GETVAR = 33
_ID_SETVAR = 34
_ID_FUNCALL = 35
_ID_SUBCALL = 36
_ID_GETSLICE = 37
_ID_SETSLICE = 38

def _array_dtype(x):
  k = x.dtype.kind
  n = x.dtype.itemsize
  if k=='i' or k=='u' or k=='b':
    if n in _isizes:
      n = _isizes.index(n) if (n!=_isizes[3]) else 3
    else:
      n = -1
    if n == 4:
      n = -1   # longlong unsupported in yorick if bigger than long
    if k!='i' and n>=0:
      n += 8
    t = _types[n] if n>=0 else None
  elif k=='f':
    if n in _fsizes:
      n = _fsizes.index(n)+5 if (n!=_fsizes[1]) else 6
    else:
      n = -1
    if n == 7:
      n = -1    # longdouble unsupported in yorick
  elif k=='c':
    if n == _types[14].itemsize:
      n = 14
    elif n == _types[13].itemsize:
      n = 13
    else:
      n = -1
  if n < 0:
    raise PYorickError("unsupported np.array dtype for pyorick")
  return n

# Since reading and writing need to be atomic operations, we implement
# no nonsense _get_msg and _put_msg functions that read or write a complete
# message.  No error checking or value decoding is done in _get_msg, and
# _put_msg expects all the encoding work, including error checking to
# already have been done.  The raw message format is simply a dict
# with several items depending on message type.  The passive GROUP
# message and several of the active messages contain a list of such
# dicts, corresponding to the GROUP members, function argument list,
# or array indices.
#
# value = _decode(msg) and msg = _encode(value) are the higher level
# functions which translate between python values and messages

def _get_msg(restrict=None):
  global _need_response
  if not _need_response:
    raise PYorickError("expecting to send message, not receive")
  if not _rfd:
    return None   # some fatal exception has already occurred
  die = 0
  hdr = np.zeros(2, dtype=_py_long)
  try:
    if _debug and not restrict:
      print("P>_get_msg: blocking to recv hdr")
    _fd_recv(hdr)
    if _debug and not restrict:
      print(("P>_get_msg: got hdr = [{0},{1}]".format(hdr[0],hdr[1])))
    ident = hdr[0]
    msg = {'_pyorick_id': ident, 'hdr': hdr}

    if ident<0 or (restrict and ident>_ID_EOL and (ident not in restrict)):
      ident = 1000

    # process passive messages first
    if ident <= _ID_STRING:   # array message
      ndim = hdr[1]
      if ndim:
        shape = np.zeros(ndim, dtype=_py_long)
        _fd_recv(shape)
      else:
        shape = np.array((), dtype=_py_long)
      msg['shape'] = shape
      if ident < _ID_STRING:
        value = np.zeros(shape[::-1], dtype=_types[ident])
      else:
        lens = np.zeros(np.prod(shape) if ndim else 1, dtype=_py_long)
        _fd_recv(lens)
        msg['lens'] = lens
        value = np.zeros(np.sum(lens), dtype=np.uint8)
      _fd_recv(value)
      msg['value'] = value

    elif ident == _ID_SLICE:
      value = np.zeros(3, dtype=_py_long)
      _fd_recv(value)
      msg['value'] = value

    elif ident == _ID_NIL:
      msg['value'] = None

    elif ident == _ID_GROUP:
      v = []
      while True:   # go until matching EOL sub-message
        m = _get_msg([_ID_SETVAR])
        if m['_pyorick_id'] == _ID_EOL:
          break
        v.append(m)
      msg['value'] = v

    elif ident == _ID_EOL:
      msg['value'] = None

    # remaining messages are active
    elif ident==_ID_PARSEX or ident==_ID_GETVAR or ident==_ID_SETVAR:
      if hdr[1]:
        name = np.zeros(hdr[1], dtype=np.uint8)
        _fd_recv(name)
      else:
        pkt.name = ''
      msg['name'] = name
      if ident == _ID_SETVAR:
        msg['value'] = _get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

    elif ident == _ID_SETVAR:
      if hdr[1]:
        name = np.zeros(hdr[1], dtype=np.uint8)
        _fd_recv(name)
      else:
        pkt.name = ''
      msg['name'] = name
      msg['value'] = _get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

    elif ident==_ID_FUNCALL or ident==_ID_SUBCALL:
      if hdr[1]:
        name = np.zeros(hdr[1], dtype=np.uint8)
        _fd_recv(name)
      else:
        pkt.name = ''
      msg['name'] = name
      v = []
      while True:   # go until matching EOL sub-message
        m = _get_msg([_ID_GETVAR, _ID_SETVAR, _ID_FUNCALL, _ID_GETSLICE])
        if m['_pyorick_id'] == _ID_EOL:
          break
        v.append(m)
      msg['args'] = v

    elif ident==_ID_GETSLICE or ident==_ID_SETSLICE:
      if hdr[1]:
        name = np.zeros(hdr[1], dtype=np.uint8)
        _fd_recv(name)
      else:
        pkt.name = ''
      msg['name'] = name
      v = []
      while True:   # go until matching EOL sub-message
        m = _get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])
        if m['_pyorick_id'] == _ID_EOL:
          break
        v.append(m)
      msg['args'] = v
      if ident == _ID_SETSLICE:
        msg['value'] = _get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

    else:
      # panic on unrecognized or out-of-context message
      die = 1

    if restrict is None:
      _need_response = False
  except:
    # panic if interrupted for any reason during reading of the message
    yorick(kill=1)
    raise PYorickError("interrupted reading message, yorick killed")

  if die:
    yorick(kill=1)
    if die == 1:
      raise PYorickError("unrecognized message id, yorick killed")

  if _debug and not restrict:
    print(("P>_get_msg: completed hdr = [{0},{1}]".format(hdr[0],hdr[1])))
  return msg

def _put_msg(msg, recurse=None):
  global _need_response
  if _need_response:
    msg = _get_msg()   # read and ignore unexpected input
    raise PYorickError("received and discarded message, now ready to send")
  ident = msg['_pyorick_id']
  if _debug and not recurse:
    print(("P>_put_msg: hdr = [{0},{1}]...".format(msg['hdr'][0],msg['hdr'][1])))
  try:
    _fd_send(msg['hdr'])
    if ident <= _ID_STRING:
      if len(msg['shape']):
        _fd_send(msg['shape'])
      if ident == _ID_STRING:
        _fd_send(msg['lens'])
      _fd_send(msg['value'])
    elif ident == _ID_SLICE:
      _fd_send(msg['value'])
    elif ident == _ID_NIL:
      pass
    elif ident == _ID_GROUP:
      v = msg['value']
      for m in v:
        _put_msg(m, 1)
      _fd_send(np.array([_ID_EOL, 0], dtype=_py_long))
    elif ident == _ID_EOL:
      pass

    elif ident in [_ID_PARSEX, _ID_GETVAR, _ID_SETVAR]:
      _fd_send(msg['name'])
      if ident == _ID_SETVAR:
        _put_msg(msg['value'], 1)
    elif ident in [_ID_FUNCALL, _ID_SUBCALL, _ID_GETSLICE, _ID_SETSLICE]:
      _fd_send(msg['name'])
      v = msg['args']
      for m in v:
        _put_msg(m, 1)
      _fd_send(np.array([_ID_EOL, 0], dtype=_py_long))
      if ident == _ID_SETSLICE:
        _put_msg(msg['value'], 1)

    if not recurse:
      _need_response = True
  except:
    yorick(kill=1)
    raise    # this is not quite correct...

  if _debug and not recurse:
    print(("P>_put_msg: done hdr = [{0},{1}]".format(msg['hdr'][0],
                                                     msg['hdr'][1])))

# translate a passive value message (from _get_msg) to its python value
def _decode(msg):
  ident = msg['_pyorick_id']

  if ident < _ID_STRING:
    value = msg['value']

  elif ident == _ID_STRING:
    value = _from_bytes(msg['shape'], msg['lens'], msg['value'])

  elif ident == _ID_SLICE:
    flags = msg['hdr'][1]
    if flags == 7:
      value = NewAxis  # or np.newaxis ??
    elif flags == 11:
      value = Ellipsis
    else:
      value = msg['value']
      value = slice(None if (flags&1) else value[0],
                    None if (flags&2) else value[1], value[2])

  elif ident == _ID_NIL:
    value = None

  elif ident == _ID_GROUP:
    v = msg['value']
    if msg['hdr'][1]:
      value = {}
      for m in v:
        if m['_pyorick_id'] != _ID_SETVAR:
          raise PYorickError("misformatted dict in message from yorick")
        value[_bytes2str(m['name'])] = _decode(m['value'])
    else:
      value = [_decode(m) for m in v]

  elif ident == _ID_EOL:
    value = msg

  # should active messages be processed here?
  elif ident in [_ID_PARSEX, _ID_GETVAR, _ID_SETVAR,
                 _ID_FUNCALL, _ID_SUBCALL, _ID_GETSLICE, _ID_SETSLICE]:
    raise PYorickError("active message from yorick not yet supported")

  else:
    raise PYorickError("unrecognized message from yorick? (BUG?)")

  return value

# translate python value x into passive message for _put_msg
# (each active message has its own function)
def _encode(x):
  # set up a passive message as a sequence of packets
  # raises PYorickError if x is unsupported
  if isinstance(x, bytearray):
    x = np.array(x)
  if isinstance(x, np.ndarray):
    if x.size:
      isa = x.shape + (0,)  # to match _is_array_of
    else:
      x = None
      isa = False
    if x.dtype == np.bool:
      x = np.array(x, dtype=np.intc)
  else:
    isa = _is_array_of(x, Number)
    if isa:
      x = np.array(x)
    else:
      isa = _is_array_of(x, bool)
      if isa:
        x = np.array(x, dtype=int32)
  if isa and not x.flags['CARRAY']:
    x = np.copy(x, 'C')   # ensure nparray has C order, contiguous
  if isa and (x.dtype.type is np.string_):
    iss = x.shape + (0,)  # to match _is_array_of
    x = x.tolist()  # convert string arrays to nested string lists
    isa = False
  else:
    iss = _is_array_of(x, six.string_types)
  if isa:
    isan = _array_dtype(x)
  # Now numbers or lists/tuples of equal length lists/tuples of numbers have
  # been converted to arrays.  Also, arrays of strings have been converted
  # to such lists/tuples of strings, and such lists/tuples of strings have
  # been identified by iss.  Arrays have been copied to contiguous C-order
  # if necessary.

  # isa and iss are dimension lengths in python c-order.
  # This protocol specifies that dimension order is fastest first, that is,
  # yorick order, so shapes will be reversed in the protocol.
  # The order choice in the protocol is arbitrary, but if it is not
  # definite, then more information must be sent.

  # The active GETSLICE and SETSLICE methods pose a more difficult problem,
  # requiring the high level user to understand the dimension order difference
  # between the two languages, no matter how this simpler shape description
  # part of the passive messages is decided.

  if isa:    # numeric array
    msg = {'_pyorick_id': isan,
           'hdr': np.array([isan, x.ndim], dtype=_py_long),
           'shape': np.array(isa[0:-1][::-1], dtype=_py_long), 'value': x}

  elif iss:  # string array
    # flatten the string array to single unnested list
    n = ndim = len(iss) - 1
    if n == 0:
      x = [x]
    else :
      while (n > 1):
        x = [z for y in x for z in y]
        n -= 1
    # make sure all strings are 0-terminated, iso8859-1 encoded
    x = [_zero_terminate(y) for y in x]
    # send encoded string lengths, including trailing 0
    msg = {'_pyorick_id': _ID_STRING,
           'hdr': np.array([_ID_STRING, ndim], dtype=_py_long),
           'shape': np.array(iss[0:-1][::-1], dtype=_py_long),
           'lens': np.array([len(y) for y in x], dtype=_py_long),
           'value': np.fromstring(''.join(x).encode('iso_8859_1'),
                                  dtype=np.uint8)}

  # index range, including (newaxis, Ellipsis) <--> (-, ..)
  elif x is NewAxis:  # np.newaxis is unfortunately None
    msg = {'_pyorick_id': _ID_SLICE,
           'hdr': np.array([_ID_SLICE, 7], dtype=_py_long),
           'value': np.array([0, 0, 1], dtype=_py_long)}
  elif x is Ellipsis:
    msg = {'_pyorick_id': _ID_SLICE,
           'hdr': np.array([_ID_SLICE, 11], dtype=_py_long),
           'value': np.array([0, 0, 1], dtype=_py_long)}
  elif isinstance(x, slice):
    if x.start is None:
      smin = 0
      flags = 1
    else:
      smin = x.start
      flags = 0
    if x.stop is None:
      smax = 0
      flags += 2
    else:
      smax = x.stop
    if x.step is None:
      sinc = 1 if flags or smin<=smax else -1
    else:
      sinc = x.step
    msg = {'_pyorick_id': _ID_SLICE,
           'hdr': np.array([_ID_SLICE, flags], dtype=_py_long),
           'value': np.array([smin, smax, sinc], dtype=_py_long)}

  # nil
  elif x is None:
    msg = {'_pyorick_id': _ID_NIL,
           'hdr': np.array([_ID_NIL, 0], dtype=_py_long), 'value': None}

  # list or tuple objects
  elif isinstance(x, Sequence):
    msg = {'_pyorick_id': _ID_GROUP,
           'hdr': np.array([_ID_GROUP, 0], dtype=_py_long),
           'value': [_encode(value) for value in x]}

  # dict objects only allowed if all keys are strings
  elif isinstance(x, dict) and ('_pyorick_id' not in x):
    if all(isinstance(xx, six.string_types) for xx in six.iterkeys(x)):
      v = []
      for (key, value) in six.iteritems(x):
        m = _encode_name(_ID_SETVAR, key)
        m['value'] = _encode(value)
        v.append(m)
    else:
      raise PYorickError("non-string key in dictionary")
    msg = {'_pyorick_id': _ID_GROUP,
           'hdr': np.array([_ID_GROUP, 1], dtype=_py_long),
           'value': v}

  elif isinstance(x, _YorickRef):
    msg = _encode_name(_ID_GETVAR, x.name)

  else:
    raise PYorickError("unsupported passive object for yorick send")

  return msg

def _is_array_of(x, aclass):
  if isinstance(x, aclass):
    return (0,)
  elif isinstance(x, Sequence) and len(x) and x.__class__!=x[0].__class__:
    x0 = _is_array_of(x[0], aclass)
    if x0 and all(_is_array_of(xx, aclass)==x0 for xx in x[1:]):
      return (len(x),) + x0
  return False

def _encode_name(ident, name):
  try:
    name = np.fromstring(name.encode('iso_8859_1'), dtype=np.uint8)
  except UnicodeEncodeError:
    raise PYorickError("non-iso_8859_1 names not recognized by yorick")
  return {'_pyorick_id': ident,
          'hdr': np.array([ident, len(name)], dtype=_py_long),
          'name': name}

def _parsex(command):
  if not isinstance(command, six.string_types):
    command = '\0'.join(command)  # convert sequence of lines to single line
  msg = _encode_name(_ID_PARSEX, command)
  return _get_response(msg)

def _getvar(name, yref=None):
  msg = _encode_name(_ID_GETVAR, name)
  msg['yref'] = yref
  return _get_response(msg)

def _setvar(name, value, passive=None):
  msg = _encode_name(_ID_SETVAR, name)
  msg['value'] = _encode(value)
  return _get_response(msg)

def _funcall(name, args, kwargs):
  return _caller(_ID_FUNCALL, name, args, kwargs)

def _subcall(name, args, kwargs):
  x = _caller(_ID_SUBCALL, name, args, kwargs)
  return None

def _caller(ident, name, args, kwargs):
  msg = _encode_name(ident, name)
  v = [_encode(arg) for arg in args]
  for (key, value) in six.iteritems(kwargs):
    m = _encode_name(_ID_SETVAR, key)
    m['value'] = _encode(value)
    v.append(m)
  msg['args'] = v
  return _get_response(msg)

def _getslice(name, key):
  if not isinstance(key, tuple):  # single index case
    key = (key,)
  msg = _encode_name(_ID_GETSLICE, name)
  msg['args'] = [_encode(arg) for arg in key]
  return _get_response(msg)

def _setslice(name, key, value):
  if not isinstance(key, tuple):  # single index case
    key = (key,)
  msg = _encode_name(_ID_SETSLICE, name)
  msg['args'] = [_encode(arg) for arg in key]
  msg['value'] = _encode(value)
  return _get_response(msg)

def _zero_terminate(s):
  if (not len(s)) or (s[-1] != '\0'):
    s += '\0'
  return s[0:s.index('\0')+1]

def _from_bytes(shape, lens, v):
  # return string or possibly nested list of strings from byte encoding
  ndim = len(shape)
  size = np.prod(shape) if ndim else 1
  i1 = np.cumsum(lens)
  i0 = i1 - lens
  i1 -= 1     # skip trailing 0 bytes (not optional in string arrays)
  v = [v[i0[i]:i1[i]].tostring().decode('iso_8859_1') for i in range(size)]
  for i in range(ndim-1):
    # remains to convert 1D list of strings to nested lists
    # shape is in yorick order, fastest first (not python c-order)
    n = shape[i]
    v = [v[j:j+n] for j in range(0, size, n)]
    size /= n  # now top level is list of size lists
  return v if ndim else v[0]

def _bytes2str(b):
  b = b[0:-1] if (len(b) and not b[-1]) else b
  return b.tostring().decode('iso_8859_1')

# _fd_send, _fd_recv are the lowest level
def _fd_recv(x):
  """Read numpy array x from _rfd."""
  # other interfaces are readinto, copyto, frombuffer, getbuffer
  if not _rfd:
    return None   # some fatal exception has already occurred
  n = 0
  while n < x.nbytes:
    try:
      s = os.read(_rfd, x.nbytes-n)  # no way to use readinto?
    except:
      yorick(kill=1)  # failure fatal, need to shut down yorick
      raise PYorickError("os.read failed, yorick killed")
    m = len(s)
    x.data[n:n+m] = s
    n += m
  if _debug and n:
    print(("P>_fd_recv: {0} bytes".format(n)))

def _fd_send(x):
  """Write numpy array x to _wfd."""
  if not _wfd:
    return None   # some fatal exception has already occurred
  n = ntries = 0
  while n < x.nbytes:
    try:
      m = os.write(_wfd, x.data[n:])
    except:
      m = -1
    if m<0 or ntries>=1000:
      yorick(kill=1)  # failure fatal, need to shut down yorick
      raise PYorickError("os.write failed, yorick killed")
    if m:
      n += m
      ntries = 0
    else:
      ntries += 1
  if _debug and n:
    print(("P>_fd_send: {0} bytes".format(n)))

def _get_response(msg):
  global _mode
  if _mode or _debug:
    _yorick_flush()
  if _mode:  # have to send "here it comes" command through stdin
    _py2yor("pyorick;")
    if _debug:
      print("P>_get_response sent pyorick command to stdin")
  _put_msg(msg)
  _mode = _mode_tmp   # msg caused mode to change
  m = _get_msg()
  if _mode:
    _wait_for_prompt()
  else:
    _yorick_flush()
  ident = m['_pyorick_id']
  if ident == _ID_EOL:
    if m['hdr'][1]==2 and msg['_pyorick_id']==_ID_GETVAR and ('yref' in msg):
      # unrepresentable data gets variable reference
      return _YorickRef(msg['yref'], _bytes2str(msg['name']))
    else:
      raise PYorickError("yorick reports error")
  elif ident < _ID_PARSEX:  # got required passive message
    return _decode(m)
  raise PYorickError("active responses from yorick not yet supported")

def _py2yor(s, nolf=None):
  if not nolf:
    if not s.endswith('\n'):
      s += '\n'
  n = 0
  while n < len(s):
    n += os.write(_pfd, s[n:])

#if __name__ == "__main__":
#  from pyorick_test import pytest
#  pytest()
