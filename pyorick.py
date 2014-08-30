# pyorick.py

"""Interface to yorick as a subprocess.

yo, oy = yorick()          start and connect to yorick
yo.var = <expr>            redefine variable var in yorick
yo.var                     retrieve contents of yorick variable var
yo("yorick code")          parse and execute yorick code, returning None
yo("pyformat", arg1, ...)    means yo("pyformat".format(arg1, arg2, ...))
yo.fun(arg1, arg2, ...)    invoke yorick function fun as subroutine
oy.var                     create reference to yorick variable var
oy("yorick expression")    parse, execute, and return yorick expression
oy.ary[ndx1, ndx2, ...]            retrieve slice of yorick array ary
oy.ary[ndx1, ndx2, ...] = <expr>   set slice of yorick array ary
oy.fun(arg1, arg2, ...)    invoke yorick function fun, returning result

The following are not yorick variables, but python attributes:
yo._yorick   is connection object
oy._yorick   is connection object
yo._flike    is False (subroutine-like interface)
oy._flike    is True  (function-like interface)

Deleting the last interface object for a given connection closes the
connection, terminating yorick.

yo._yorick.setdebug(1)   turns on debugging output, 0 turns off (default)
yo._yorick.setmode(0)    turns off interactive mode, 1 turns on (default)
"""

# pyorick implements a request-reply message passing model:
# Python sends a request message, yorick sends a reply message.  Request
# messages are also called "active"; reply messages are also called "passive".
#
# - Each message must be sent or received atomically; any failures due
#   to a noisy channel or other interruption are fatal because the
#   state of the partner becomes unknown.
#
# - Between message pairs, yorick blocks waiting for the next request,
#   while the python program or interactive session continues.
#   - However, in the default interactive mode, we arrange for yorick to be
#     blocked waiting for stdin, rather than the request channel.  This
#     yorick free to respond to events on other channels, such as graphics
#     window input.
#   - An optional batch mode works by installing a yorick idler function.
#     Yorick graphics windows and stdin are both non-responsive in batch mode.
#
# - Yorick (or the side receiving a request message in general) guarantees
#   prompt attention to request messages, sending the reply as soon as
#   it finishes processing the request.  The protocol defines an error
#   reply, delivered immediately upon the failure of the request.
#
# - Python (or the side sending a request message in general) blocks
#   waiting for the reply.
#
# - Each message begins with two C-long values [ident, info] where ident
#   identifies the type of message, and info provides more information about
#   the following parts of the message.  Messages may appear "quoted" as
#   part of another message.  Such quoted messages lose their stand-alone
#   meaning (including whether they are active or passive) when quoted;
#   they are merely part of the containing message.
#
# - The reply (passive) messages are:
#
#   ident  info
#    0-4   ndim   integer array of C-type  char, short, int, long, long long
#    5-7   ndim   floating array of C-type  float, double, long double
#   8-12   ndim   unsigned array of C-type char, short, int, long, long long
#  13-15   ndim   complex array based on C-type float, double, long double
#    16    ndim   array of 0-terminated strings
#   For all the array types, the header is followed by ndim long values:
#      [len1, len2, len3, ...]
#   where lenN is the length of the Nth dimension, and len1 varies fastest
#   (that is, dimensions are always expressed in yorick order).
#   For the numeric types, product(lenN) values of the specified C-type
#   follow the dimension list, completing the message.
#   For the string type, product(lenN) long values slen1, slen2, ... slenM,
#   representing the individual string lengths in bytes, including a trailing
#   '\0' byte for each string.  Any of the slenM may also equal 0 to indicate
#   the NULL string (in yorick -- python has no such string value).  Strings
#   are always encoded as ISO-8859-1, with a single byte per character,
#   which is the yorick string format.  Immediately after the string lengths
#   come sum(slenM) chars, all the strings concatenated together.
#
#   ident  info
#    17    flags   a slice, header is followed by [start, stop, step]
#          flags specify default values for start or stop,
#                and any yorick range function sum, psum, -, .., *, etc.
#    18     0      nil ([] in yorick, None in python)
#    19    flag    group of objects with types 0-19
#          flag =0 if group is python list, =1 if group is python dict with
#                  string-valued keys (both yorick oxy objects)
#                  - list of quoted messages follow representing items
#                  - for flag=1, all item messages are SETVAR to specify key
#    20    flag    special value marker
#          flag =0 end-of-list marker,
#               =1 to indicate error,
#               =2 to indicate an _ID_GETVAR request produced an object that
#                  cannot be represented in a reply message (e.g.- a function)
#
# - The request (active) messages are:
#
#   ident  info
#    32    nchars   EVAL, following nchars chars are yorick expression
#    33    nchars   EXEC, following nchars chars are yorick code
#                   - EVAL reply is expression value, EXEC reply is None
#                   - may consist of multiple lines separated by '\0' or '\n'
#    34    nchars   GETVAR, following nchars chars are yorick variable name
#                   - reply is variable value
#    35    nchars   SETVAR, following nchars chars are yorick variable name,
#                   then quoted message 0-19 or FUNCALL or GETSLICE is value
#                   - reply is None
#    36    nchars   FUNCALL, following nchars chars are yorick variable name
#                   followed by list of quoted messages representing arguments
#                   - arguments can be message 0-19 or FUNCALL or GETSLICE,
#                     or GETVAR to represent a yorick variable, or SETVAR
#                     to represent a keyword argument
#                   - reply is variable value
#    37    nchars   SUBCALL, following nchars chars are yorick variable name,
#                   followed by list of quoted messages representing arguments
#                   - arguments same as for FUNCALL
#                   - reply is None
#    38    nchars   GETSLICE, following nchars chars are yorick variable name,
#                   followed by list of quoted messages representing indices
#                   - indices can be message 0-19 or FUNCALL or GETSLICE,
#                     or GETVAR to represent a yorick variable
#                   - yorick index order and slice semantics assumed
#                   - reply is slice value
#    39    nchars   SETSLICE, following nchars chars are yorick variable name,
#                   followed by list of quoted messages representing indices,
#                   followed by final message representing value
#                   - indices and value can be message 0-19 or FUNCALL or
#                     GETSLICE, or GETVAR to represent a yorick variable
#                   - yorick index order and slice semantics assumed
#                   - reply is None
#    40    nchars   GETSHAPE, following nchars chars are yorick variable name
#                   - reply is {'dtype':dtype, 'ndim':ndim, 'shape':shape}
#                     of the ndarray GETVAR would return
#                     If the variable is a string array, 'dtype':None and
#                     the dict reply has item 'string':True.
#                     For all other cases, 'dtype', 'ndim' and 'shape' are
#                     all None.  If the variable is a function, the dict reply
#                     has item 'func':True.

# Attempt to make it work for both python 2.6+ and python 3.x.
# Avoid both six and future modules, which are often not installed.
#from __future__ import (absolute_import, division,
#                        print_function, unicode_literals)
from __future__ import print_function
# Note that these __future__ imports apply only to this module, not to
# others which may import it.
# In particular, under 2.x, arguments passed in to this module from callers
# that do not have unicode_literals in place will generally be non-unicode.
import sys
if sys.version_info[0] >= 3:
  basestring = str   # need basestring for 2.x isinstance tests for string
  xrange = range     # below only use xrange where list might be large
  def _iteritems(d):
    return d.items()
else:
  def _iteritems(d):
    return d.iteritems()

import numpy as np

import os
import shlex
import termios
import fcntl
import select
from numbers import Number
from collections import Sequence
from ctypes import c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint,\
                   c_long, c_ulong, c_longlong, c_ulonglong,\
                   c_float, c_double, c_longdouble

def yorick(flike=None, batch=False, args="", ypath="yorick", ipath="pyorick.i"):
  """Return (yo,oy) pair of yorick interface objects.

  Optional parameters:
  flike     just return function-like interface if True, subroutine-like
              interface if False, or opposite kind if a Yorick instance
    Following arguments ignored if flike is a Yorick instance:
  args      (default "") additional yorick command line arguments
  batch     (default False) true to start yorick in batch mode
  ypath     (default "yorick") path to yorick executable
  ipath     (default "pyorick.i") path to pyorick.i startup script

  Starts yorick as a subprocess with two pipes, one for python
  to yorick, and one for yorick to python messages.  The yorick
  stdin, stdout, and stderr streams are captured as a pty-tty,
  but are unused for exchanging data or commands.  The interface
  objects manage data and commands flowing through the pipes.
  Roughly speaking, the yo interface is subroutine-like, while
  the oy interface is function-like.
  """
  if flike is not None:
    return Yorick(flike, None, batch, args, ypath, ipath)
  yo = Yorick(connection=_YorickConnection(batch, args, ypath, ipath))
  return (yo, Yorick(yo))

# User interface to a _YorickConnection
class Yorick:
  """Interface to a yorick process."""
  def __init__(self, flike=False, connection=None,
               batch=False, args="", ypath="yorick", ipath="pyorick.i"):
    """Construct a yorick interface object.

    Optional arguments:
    flike  Is this interface function-like (True) or subroutine-like (False)?
           Default: False, or not connection._flike if connection specified.
    connection  Another Yorick instance connected to the yorick process.
           Returned interface will have the opposite _flike as connection.
           Default: None
      Following arguments are ignored if connection is not None:
    batch  True to start yorick with -batch (instead of -i).
           Default: False
    args   Arguments to add to yorick command line, parsed by shlex.split.
           Default: ""
    ypath  Path to yorick executable.  Mostly useful for debugging.
           Default: "yorick"
    ipath  Path to pyorick.i yorick startup code.  Mostly useful for debugging.
           Default: "pyorick.i"

    Yorick interface objects (say yo) have custom call, get and set attribute
    methods so that:
      yo("yorick code")   sends yorick code to be parsed and executed
      yo.x                represents the yorick variable named x

    There are two different kinds of interface object, subroutine-like (yo)
    objects and function-like (oy) objects.  The differences are:
      yo("yorick command")     executes the command, discarding any result
      oy("yorick expression")  evaluates the yorick expression and returns it
      yo.f(arglist)   executes yorick function f as a subroutine
      oy.f(arglist)   executes yorick function f as a function, returns result
      yo.a[indexlist] uses python index list semantics on yorick array a
      oy.a[indexlist] uses yorick index list semantics on yorick array a

    When you delete the last Yorick interface object for a given yorick
    process, the process is killed.
    """
    if isinstance(flike, Yorick): # easy way to get opposite connection flike
      if connection is None:
        connection = flike._yorick
      flike = not flike._flike
    else:
      flike = bool(flike)
    self.__dict__['_flike'] = flike  # self._flike calls __setattr__
    if connection is None:
      connection = _YorickConnection(batch, args, ypath, ipath)
    self.__dict__['_yorick'] = connection.attach()

  def __del__(self):
    if self._yorick.detach():
      del self._yorick  # last interface to disconnect kills connection

  def __repr__(self):
    kind = " function-like " if self._flike else " subroutine-like "
    return "".join(["<yorick", kind, "interface to pid=",
                    str(self._yorick.pid), ">"])

  def __call__(self, command, *args, **kwargs):  # pipe(command)
    if args or kwargs:
      command = command.format(*args, **kwargs)
    if self._flike:
      return self._yorick.evaluate(command)
    else:
      return self._yorick.execute(command)

  def __setattr__(self, name, value):            # pipe.name = value
    if name not in self.__dict__:
      self._yorick.setvar(name, value)
    else:
      object.__setattr__(self, name, value)

  def __getattr__(self, name):                   # pipe.name
    # inspect module causes serious problems by probing for names
    # ipython also probes for getdoc attribute
    if _is_sysattr(name) or name=='getdoc':
      raise AttributeError("Yorick instance has no attribute '"+name+"'")
    if name in ['_flike', '_yorick']:
      return self.__dict__[name]
    if self._flike:
      return _YorickRef(self._yorick, self._flike, name)
    else:
      # eventually want this to also return a _YorickRef
      return self._yorick.getvar(name)

class PYorickError(Exception):
  """Exception raised by pyorick module."""
  pass

NewAxis = {}  # use this as non-None flag for numpy.newaxis
# eventually could support yorick index range in this way

########################################################################
# Remainder of module is hidden from users, who interact only with
# the two instances of _YorickInterface returned by yorick().

# Manage the actual connection to a yorick process.
class _YorickConnection:
  def __init__(self, batch=False, args="", ypath="yorick", ipath="pyorick.i"):
    self.batch = bool(batch)
    if batch:
      argv = [ypath, "-batch", ipath]
    else:
      argv = [ypath, "-q", "-i", ipath]
    self.rfd, self.wfd, self.pfd, self.pid = _yorick_create(ypath, argv, args)
    self.need_reply = False
    self.debug = self.mode = self.mode_tmp = False
    self.batch = bool(batch)
    self.uses = 0
    self.last_prompt = ''
    if not batch:  # immediately switch to interactive mode
      self.setmode(True)

  def __del__(self):
    _yorick_destroy(self)

  def __repr__(self):
    return "<yorick process, pid={0}>".format(self.pid)

  def check_live(self):
    if self.pid is None:
      raise PYorickError("no yorick connection")

  def attach(self):
    self.uses += 1
    return self
  def detach(self):
    self.uses -= 1
    if self.uses <= 0:
      _yorick_destroy(self)  # kill the yorick process
    return self.uses <= 0    # caller should del instance if true

  def setdebug(self, on):
    on = bool(on)
    if on != self.debug:
      self.execute("pydebug = {0}".format(int(on)))
      self.debug = on

  def setmode(self, mode):
    mode = bool(mode)
    if mode != self.mode:
      if self.batch:
        raise PYorickError("yorick started with -batch, no interactive mode")
      self.flush()
      self.mode_tmp = mode
      self.subcall("pyorick", int(mode))

  ########################################################################
  # low level stdin, stdout operations
  ########################################################################

  def py2yor(self, s, nolf=None):
    self.check_live()
    if not nolf:
      if not s.endswith('\n'):
        s += '\n'
    n = 0
    while n < len(s):
      try:
        # Note: must guarantee that s representable as 8859 latin-1
        n += os.write(self.pfd, s[n:].encode('iso_8859_1'))
      except:
        _yorick_destroy(self)
        raise PYorickError("unable to write to yorick stdin, yorick killed")

  def flush(self, clear=None):
    if clear:
      self.last_prompt = ''
    s = ''
    i = 0    # curiously hard to get reply promptly?
    while self.pfd is not None and i < 3:
      try:
        p = select.select([self.pfd], [], [self.pfd], 0)
      except:
        p = (0, 0, 1)
      if p[0]:
        try:
          s += os.read(self.pfd, 16384).decode('iso_8859_1')
        except:
          p = (0, 0, 1)
      if p[2]:
        _yorick_destroy(self)
      if not p[0]:
        i += 1
    if s:
      # remove prompt in interactive (no idler) mode
      if self.mode and s.endswith("> "):
        i = s.rfind('\n') + 1  # 0 on failure
        self.last_prompt = s[i:]
        s = s[0:i]
      if s:
        print(s, end='')  # terminal newline already in s

  def wait_for_prompt(self):
    self.flush(1)
    while not self.last_prompt:
      p = select.select([self.pfd], [], [self.pfd])
      self.flush()

  ########################################################################
  # active message senders
  ########################################################################

  def evaluate(self, command):
    if not isinstance(command, basestring):
      command = '\0'.join(command)  # convert sequence of lines to single line
    msg = _encode_name(_ID_EVAL, command)
    return self.get_reply(msg)

  def execute(self, command):
    if not isinstance(command, basestring):
      command = '\0'.join(command)  # convert sequence of lines to single line
    msg = _encode_name(_ID_EXEC, command)
    return self.get_reply(msg)

  def getvar(self, name, flike=None):
    msg = _encode_name(_ID_GETVAR, name)
    if flike is not None:
      msg['flike'] = flike
    return self.get_reply(msg)

  def setvar(self, name, value, passive=None):
    msg = _encode_name(_ID_SETVAR, name)
    msg['value'] = _encode(value)
    return self.get_reply(msg)

  def funcall(self, name, *args, **kwargs):
    return self._caller(_ID_FUNCALL, name, *args, **kwargs)

  def subcall(self, name, *args, **kwargs):
    x = self._caller(_ID_SUBCALL, name, *args, **kwargs)
    return None

  def _caller(self, ident, name, *args, **kwargs):
    msg = _encode_name(ident, name)
    v = [_encode(arg) for arg in args]
    for key, value in _iteritems(kwargs):
      m = _encode_name(_ID_SETVAR, key)
      m['value'] = _encode(value)
      v.append(m)
    msg['args'] = v
    return self.get_reply(msg)

  def getslice(self, flike, name, key):
    if not isinstance(key, tuple):  # single index case
      key = (key,)
    msg = _encode_name(_ID_GETSLICE, name)
    msg['args'] = [_encode(arg) for arg in key]
    if not flike:
      msg['args'] = _fix_index_list(msg['args'])
    return self.get_reply(msg)

  def setslice(self, flike, name, key, value):
    if not isinstance(key, tuple):  # single index case
      key = (key,)
    msg = _encode_name(_ID_SETSLICE, name)
    msg['args'] = [_encode(arg) for arg in key]
    if not flike:
      msg['args'] = _fix_index_list(msg['args'])
    msg['value'] = _encode(value)
    return self.get_reply(msg)

  def getshape(self, name):
    msg = _encode_name(_ID_GETSHAPE, name)
    return self.get_reply(msg)

  def get_reply(self, msg):
    self.check_live()
    if self.mode or self.debug:
      self.flush()
    if self.mode:  # have to send "here it comes" command through stdin
      self.py2yor("pyorick;")
      if self.debug:
        print("P>get_reply sent pyorick command to stdin")
    self.put_msg(msg)
    self.mode = self.mode_tmp   # msg caused mode to change
    m = self.get_msg()
    if self.mode:
      self.wait_for_prompt()
    else:
      self.flush()
    ident = m['_pyorick_id']
    if ident == _ID_EOL:
      if m['hdr'][1]==2 and msg['_pyorick_id']==_ID_GETVAR:
        # unrepresentable data gets variable reference
        flike = msg['flike'] if 'flike' in msg else False
        return _YorickRef(self, flike, _bytes2str(msg['name']))
      else:
        raise PYorickError("yorick reports error")
    elif ident < _ID_EVAL:  # got required passive message
      if msg['_pyorick_id']==_ID_GETSHAPE:
        if m['hdr'][0] != 3:
          PYorickError("unexpected reply to _ID_GETSHAPE request")
        result = {'dtype':None, 'ndim':None, 'shape':None}
        shape = msg['value'].tolist()
        if isinstance(shape, list):
          if shape[0] == _ID_STRING:
            result['string'] = True
          else:
            result['dtype'] = _types[shape[0]]
          result['ndim'] = shape[1]
          result['shape'] = tuple(shape[2:][::-1])
        elif shape == -1:
          result['func'] = True
        return result
      return _decode(m)
    raise PYorickError("active reply from yorick not yet supported")

  ########################################################################
  # high level binary pipe i/o
  ########################################################################

  # Since reading and writing need to be atomic operations, we implement
  # no nonsense get_msg and put_msg methods that read or write a complete
  # message.  No error checking or value decoding is done in get_msg, and
  # put_msg expects all the encoding work, including error checking to
  # already have been done.  The raw message format is simply a dict
  # with several items depending on message type.  The passive GROUP
  # message and several of the active messages contain a list of such
  # dicts, corresponding to the GROUP members, function argument list,
  # or array indices.
  #
  # value = _decode(msg) and msg = _encode(value) are the higher level
  # functions which translate between python values and messages

  def get_msg(self, restrict=None):
    if not self.need_reply:
      raise PYorickError("expecting to send message, not receive")
    if not self.rfd:
      return None   # some fatal exception has already occurred
    die = 0
    hdr = np.zeros(2, dtype=_py_long)
    try:
      if self.debug and not restrict:
        print("P>get_msg: blocking to recv hdr")
      self.recv(hdr)
      if self.debug and not restrict:
        print(("P>get_msg: got hdr = [{0},{1}]".format(hdr[0],hdr[1])))
      ident = hdr[0]
      msg = {'_pyorick_id': ident, 'hdr': hdr}

      if ident<0 or (restrict and ident>_ID_EOL and (ident not in restrict)):
        ident = 1000

      # process passive messages first
      if ident in _ID_YARRAY:   # array message
        ndim = hdr[1]
        if ndim:
          shape = np.zeros(ndim, dtype=_py_long)
          self.recv(shape)
        else:
          shape = np.array((), dtype=_py_long)
        msg['shape'] = shape
        if ident < _ID_STRING:
          value = np.zeros(shape[::-1], dtype=_types[ident])
        else:
          lens = np.zeros(np.prod(shape) if ndim else 1, dtype=_py_long)
          self.recv(lens)
          msg['lens'] = lens
          value = np.zeros(np.sum(lens), dtype=np.uint8)
        self.recv(value)
        msg['value'] = value

      elif ident == _ID_SLICE:
        value = np.zeros(3, dtype=_py_long)
        self.recv(value)
        msg['value'] = value

      elif ident == _ID_NIL:
        msg['value'] = None

      elif ident == _ID_GROUP:
        v = []
        while True:   # go until matching EOL sub-message
          m = self.get_msg([_ID_SETVAR])
          if m['_pyorick_id'] == _ID_EOL:
            break
          v.append(m)
        msg['value'] = v

      elif ident == _ID_EOL:
        msg['value'] = None

      # remaining messages are active
      elif ident in [_ID_EVAL, _ID_EXEC, _ID_GETVAR, _ID_SETVAR, _ID_GETSHAPE]:
        if hdr[1]:
          name = np.zeros(hdr[1], dtype=np.uint8)
          self.recv(name)
        else:
          pkt.name = ''
        msg['name'] = name
        if ident == _ID_SETVAR:
          msg['value'] = self.get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

      elif ident == _ID_SETVAR:
        if hdr[1]:
          name = np.zeros(hdr[1], dtype=np.uint8)
          self.recv(name)
        else:
          pkt.name = ''
        msg['name'] = name
        msg['value'] = self.get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

      elif ident==_ID_FUNCALL or ident==_ID_SUBCALL:
        if hdr[1]:
          name = np.zeros(hdr[1], dtype=np.uint8)
          self.recv(name)
        else:
          pkt.name = ''
        msg['name'] = name
        v = []
        while True:   # go until matching EOL sub-message
          m = self.get_msg([_ID_GETVAR, _ID_SETVAR, _ID_FUNCALL, _ID_GETSLICE])
          if m['_pyorick_id'] == _ID_EOL:
            break
          v.append(m)
        msg['args'] = v

      elif ident==_ID_GETSLICE or ident==_ID_SETSLICE:
        if hdr[1]:
          name = np.zeros(hdr[1], dtype=np.uint8)
          self.recv(name)
        else:
          pkt.name = ''
        msg['name'] = name
        v = []
        while True:   # go until matching EOL sub-message
          m = self.get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])
          if m['_pyorick_id'] == _ID_EOL:
            break
          v.append(m)
        msg['args'] = v
        if ident == _ID_SETSLICE:
          msg['value'] = self.get_msg([_ID_GETVAR, _ID_FUNCALL, _ID_GETSLICE])

      else:
        # panic on unrecognized or out-of-context message
        die = 1

      if restrict is None:
        self.need_reply = False
    except:
      # panic if interrupted for any reason during reading of the message
      _yorick_destroy(self)
      raise PYorickError("interrupted reading message, yorick killed")

    if die:
      _yorick_destroy(self)
      if die == 1:
        raise PYorickError("unrecognized message id, yorick killed")

    if self.debug and not restrict:
      print(("P>get_msg: completed hdr = [{0},{1}]".format(hdr[0],hdr[1])))
    return msg

  def put_msg(self, msg, recurse=None):
    if self.need_reply:
      msg = self.get_msg()   # read and ignore unexpected input
      raise PYorickError("received and discarded message, now ready to send")
    ident = msg['_pyorick_id']
    if self.debug and not recurse:
      print(("P>put_msg: hdr = [{0},{1}]...".format(msg['hdr'][0],
                                                     msg['hdr'][1])))
    try:
      self.send(msg['hdr'])
      if ident in _ID_YARRAY:
        if len(msg['shape']):
          self.send(msg['shape'])
        if ident == _ID_STRING:
          self.send(msg['lens'])
        self.send(msg['value'])
      elif ident == _ID_SLICE:
        self.send(msg['value'])
      elif ident == _ID_NIL:
        pass
      elif ident == _ID_GROUP:
        v = msg['value']
        for m in v:
          self.put_msg(m, 1)
        self.send(np.array([_ID_EOL, 0], dtype=_py_long))
      elif ident == _ID_EOL:
        pass

      elif ident in [_ID_EVAL, _ID_EXEC, _ID_GETVAR, _ID_SETVAR, _ID_GETSHAPE]:
        self.send(msg['name'])
        if ident == _ID_SETVAR:
          self.put_msg(msg['value'], 1)
      elif ident in [_ID_FUNCALL, _ID_SUBCALL, _ID_GETSLICE, _ID_SETSLICE]:
        self.send(msg['name'])
        v = msg['args']
        for m in v:
          self.put_msg(m, 1)
        self.send(np.array([_ID_EOL, 0], dtype=_py_long))
        if ident == _ID_SETSLICE:
          self.put_msg(msg['value'], 1)

      if not recurse:
        self.need_reply = True
    except:
      _yorick_destroy(self)
      raise PYorickError("interrupted writing message, yorick killed")

    if self.debug and not recurse:
      print(("P>put_msg: done hdr = [{0},{1}]".format(msg['hdr'][0],
                                                     msg['hdr'][1])))

  ########################################################################
  # low level binary pipe i/o
  ########################################################################

  def recv(self, x):
    """Read numpy array x from self.rfd."""
    # other interfaces are readinto, copyto, frombuffer, getbuffer
    if not self.rfd:
      return None   # some fatal exception has already occurred
    # note: x.data[n:] fails in python 3.4 if x is scalar
    xx = x.reshape(x.size).view(dtype=np.uint8)
    n = 0
    while n < x.nbytes:
      try:
        s = os.read(self.rfd, x.nbytes-n)  # no way to use readinto?
      except:
        _yorick_destroy(self)  # failure fatal, need to shut down yorick
        raise PYorickError("os.read failed, yorick killed")
      m = len(s)
      xx.data[n:n+m] = s  # fails in python 3.4 unless xx dtype=np.unit8
      n += m
    if self.debug and n:
      print(("P>recv: {0} bytes".format(n)))

  def send(self, x):
    """Write numpy array x to self.wfd."""
    if not self.wfd:
      return None   # some fatal exception has already occurred
    # note: x.data[n:] fails in python 3.4 if x is scalar
    xx = x.reshape(x.size).view(dtype=np.uint8)
    n = 0
    while n < x.nbytes:
      try:
        m = os.write(self.wfd, xx.data[n:])
      except:
        m = -1
      if m<0:
        _yorick_destroy(self)  # failure fatal, need to shut down yorick
        raise PYorickError("os.write failed, yorick killed")
      n += m
    if self.debug and n:
      print(("P>send: {0} bytes sent".format(n)))

class _YorickRef:
  """Reference to a yorick variable, created by interface object."""
  def __init__(self, connection, flike, name):
    self.yorick = connection
    self.flike = flike
    self.name = name
  def __repr__(self):
    flag = "function-like" if self.flike else "subroutine-like"
    return "<yorick variable {0} ({1}), pid={2}>".format(self.name, flag,
                                                         self.yorick.pid)
  def __call__(self, *args, **kwargs):   # ref(arglist)
    if self.flike:
      return self.yorick.funcall(self.name, *args, **kwargs)
    else:
      self.yorick.subcall(self.name, *args, **kwargs)
  def __setitem__(self, key, value):     # ref[key] = value
    self.yorick.setslice(self.flike, self.name, key, value)
  def __getitem__(self, key):            # ref[key]
    return self.yorick.getslice(self.flike, self.name, key)

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
_kinds = ['i']*5 + ['f']*3 + ['u']*5 + ['c']*3   # 'b' same as 'u' here
# yorick does not support longlong unless it is same size as long
if _types[4].itemsize > _types[3].itemsize:
  _types[4] = _types[12] = None
_sizes = [(t.itemsize if t is not None else None) for t in _types]
_py_long = _types[3]

# id 0-15 are numeric types:
#    char short int long longlong   float double longdouble
# followed by unsigned, complex variants
# passive messages (reply prohibited):
_ID_STRING = 16   # yorick assumes iso_8859_1, need separate id for utf-8?
_ID_SLICE = 17
_ID_NIL = 18
_ID_GROUP = 19
_ID_EOL = 20
# active messages (passive reply required):
_ID_EVAL = 32
_ID_EXEC = 33
_ID_GETVAR = 34
_ID_SETVAR = 35
_ID_FUNCALL = 36
_ID_SUBCALL = 37
_ID_GETSLICE = 38
_ID_SETSLICE = 39
_ID_GETSHAPE = 40

_ID_INTEGER = [0, 1, 2, 3, 4] + [8, 9, 10, 11, 12]
_ID_NUMERIC = [i for i in range(16)]
_ID_YARRAY = [i for i in range(17)]
_ID_ACTIVE = [i for i in range(_ID_EVAL, _ID_GETSHAPE+1)]

# Numpy ndarrays have a dtype.kind = biufcSUV, meaning, respectively:
#   boolean, signed integer, unsigned integer, floating point, complex,
#   byte-string (b'...'), unicode (u'...'), and void (other object)
# The non-numeric kinds generally group several items - characters for
# S and U kinds - into each element of the ndarray, while the numeric kinds
# always have one item per element (counting a complex pair as one item).
#
# Here, we must figure out which primitive C numerical type - to be precise,
# which index into the _types array - corresponds to x.dtype.  The rules are:
# 0. Non-numeric kinds SUV are an error.  Eventually we could support them
#    by transferring as char or uchar raw data, with a leading dimension
#    added for the byte size of an individual ndarray element.
# 1. Kind i is a signed integer ctype, kinds b and u are unsigned integer
#    ctypes, kind f is a floating ctype, and kind c is a pair of floating
#    ctypes.
# 2. The dtype.itemsize must exactly match the _types[i].itemsize.
# 3. Among equal _types[i].itemsize, long is the preferred integer and
#    double is the preferred floating type.  Otherwise, the type with the
#    "smallest name" is preferred.
# long is preferred integer type, double is preferred floating type
_types_pref = [3, 0, 1, 2, 4, 6, 5, 7, 11, 8, 9, 10, 12, 14, 13, 15]
_sizes_pref = [_sizes[i] for i in _types_pref]
def _array_dtype(x):
  k = x.dtype.kind
  if k == 'b':
    k = 'u'   # no distinction between 'b' and 'u' in protocol
  szp = [(_sizes_pref[i] if _kinds[i]==k else 0) for i in xrange(16)]
  n = x.dtype.itemsize
  if n not in szp:
    raise PYorickError("unsupported np.array dtype for pyorick")
  return _types_pref[szp.index(n)]

def _is_array_of(x, aclass):
  if isinstance(x, aclass):
    return (0,)
  elif isinstance(x, Sequence) and len(x) and x.__class__!=x[0].__class__:
    x0 = _is_array_of(x[0], aclass)
    if x0 and all(_is_array_of(xx, aclass)==x0 for xx in x[1:]):
      return (len(x),) + x0
  return False

# translate a passive value message (from _get_msg) to its python value
def _decode(msg):
  ident = msg['_pyorick_id']

  if ident in _ID_NUMERIC:
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
  elif ident in _ID_ACTIVE:
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
  if isa and not x.flags['CARRAY']:
    x = np.copy(x, 'C')   # ensure nparray has C order, contiguous
  if isa and (x.dtype.type is np.string_):
    iss = x.shape + (0,)  # to match _is_array_of
    x = x.tolist()  # convert string arrays to nested string lists
    isa = False
  else:
    iss = _is_array_of(x, basestring)
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
    if all(isinstance(xx, basestring) for xx in x):
      v = []
      for key, value in _iteritems(x):
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

def _encode_name(ident, name):
  try:
    name = np.fromstring(name.encode('iso_8859_1'), dtype=np.uint8)
  except UnicodeEncodeError:
    raise PYorickError("non-iso_8859_1 names not recognized by yorick")
  return {'_pyorick_id': ident,
          'hdr': np.array([ident, len(name)], dtype=_py_long),
          'name': name}

# given python index list, convert to equivalent yorick index list
def _fix_index_list(args):
  args = args[::-1]  # reverse index order
  for i in range(len(args)):
    msg = args[i]
    ident = msg['_pyorick_id']
    if ident in _ID_INTEGER:
      msg['value'] += 1     # index origin 0 --> 1
    elif ident == _ID_SLICE:
      msg['value'][0] += 1  # index origin 0 --> 1
      if msg['value'][3] < 0:
        msg['value'][1] += 2  # n=max-min --> n=max-min+1
      # could also detect <nuller:> here?
    # note that _ID_GETVAR index cannot be adjusted

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
  v = [v[i0[i]:i1[i]].tostring().decode('iso_8859_1') for i in xrange(size)]
  for i in range(ndim-1):
    # remains to convert 1D list of strings to nested lists
    # shape is in yorick order, fastest first (not python c-order)
    n = shape[i]
    v = [v[j:j+n] for j in xrange(0, size, n)]
    size /= n  # now top level is list of size lists
  return v if ndim else v[0]

def _bytes2str(b):
  b = b[0:-1] if (len(b) and not b[-1]) else b
  return b.tostring().decode('iso_8859_1')

def _is_sysattr(name):
  return len(name)>3 and name[0:2]=='__' and name[-2:]=='__'

def _yorick_create(yorick_command, argv, args):
  ptoy = _inheritable_pipe(0)
  ytop = _inheritable_pipe(1)
  pid, pfd = os.forkpty()
  # pid = os.fork()
  if not pid:   # subprocess side
    os.close(ptoy[1])
    os.close(ytop[0])
    argv.extend([str(ptoy[0]), str(ytop[1])])
    if args:
      argv.extend(shlex.split(args))
    os.execvp(yorick_command, argv)
    os._exit(1)            # failed to launch yorick
  os.close(ptoy[0])
  os.close(ytop[1])
  rfd = ytop[0]
  wfd = ptoy[1]
  # set reasonable termios attributes
  t = termios.tcgetattr(pfd)
  t[3] = t[3] & ~termios.ECHO
  termios.tcsetattr(pfd, termios.TCSANOW, t)
  return rfd, wfd, pfd, pid

# See PEP 443.  After about Python 3.3, pipes are close-on-exec by default.
def _inheritable_pipe(side):
  p = os.pipe()
  if hasattr(fcntl, 'F_SETFD') and hasattr(fcntl, 'FD_CLOEXEC'):
    flags = fcntl.fcntl(p[side], fcntl.F_GETFD)
    flags &= ~fcntl.FD_CLOEXEC
    fcntl.fcntl(p[side], fcntl.F_SETFD, flags)
  return p

def _yorick_destroy(yorick):
  if yorick.pid is not None:
    try:
      os.close(yorick.pfd)
      os.close(yorick.rfd)
      os.close(yorick.wfd)
      os.waitpid(yorick.pid, 0)   # otherwise yorick becomes a zombie
    finally:
      yorick.pid = yorick.pfd = yorick.rfd = yorick.wfd = yorick.batch = None
      yorick.debug = yorick.mode = yorick.mode_tmp = False
      yorick.need_reply = False

#if __name__ == "__main__":
#  from pyorick_test import pytest
#  pytest()
