# pyorick.py
"""Interface to a yorick process.

yo = Yorick()      start a yorick process
yo.kill()          kill a yorick process (like kill -9)

yo("code")         execute code in yorick, return None
yo("=expr")        execute expr in yorick, return value
yo.call("code")    execute code in yorick, return None
yo.eval("expr")    execute expr in yorick, return value

yo.value.varname   return value of yorick variable varname
yo.call.varname    return call-reference to yorick variable varname
yo.eval.varname    return eval-reference to yorick variable varname
  The value, call, and eval handles may be abbreviated v, c, and e.
  If varname is a yorick function or other non-data object,
  yo.value.varname returns the same call-reference as yo.call.varname.
yo.value.varname = expr   set value of yorick variable varname
  Any of the three handles (call, eval, or value) may be used to set varname.

yo.call.fname(arg1, arg2, ..., key1=kw1, ...)  invoke fname as subroutine
yo.eval.fname(arg1, arg2, ..., key1=kw1, ...)  invoke fname as function

yo.eval.aname[index1, index2, ...]         return slice of array aname
yo.eval.aname[index1, index2, ...] = expr  set slice of array aname
  The index list uses yorick slice semantics with the eval handle;
  if you get or set a slice using the call handle, the index list uses
  python slice semantics.

Given any one of <handle> = value, call, eval, you can retrieve the
parent Yorick object with yo.<handle>[], e.g.- yo.call[].

A few potential yorick variable names cannot be accessed using the
yo.<handle>.varname syntax (e.g.- __init__).  For these cases, all
three handles accept a dict-like key:
  yo.value['varname']   same as yo.value.varname (same for call, eval)

Given a yorick variable reference of any type, you can get a different
type of handle to the same variable by using the value, call, or eval
attribute (or their abbreviations v, c, e), for example:
  cvar = yo.call.varname
  cvar.eval(args)     invoke varname as function
  cvar.value          get the value of varname

Yorick variable references also support an info attribute, which returns
the type and shape of the yorick variable:
  type, shape = yo.eval.varname.info
This can be an important query if varname itself is a large array.

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

yo()               enter yorick terminal mode, special yorick commands are:
  py                 from yorick terminal mode returns to python
  py, "code"         from yorick terminal mode to exec code in python
  py("expr")         from yorick terminal mode to eval expr in python
"""

# Attempt to make it work for both python 2.6+ and python 3.x.
# Avoid both six and future modules, which are often not installed.
#from __future__ import (absolute_import, division,
#                        print_function, unicode_literals)
# Note that these __future__ imports apply only to this module, not to
# others which may import it.
# In particular, under 2.x, arguments passed in to this module from callers
# that do not have unicode_literals in place will generally be non-unicode.
# Therefore, better to stick to the default str than to use unicode_literals.
from __future__ import print_function
import sys
if sys.version_info[0] >= 3:
  basestring = str    # need basestring for 2.x isinstance tests for string
  xrange = range      # only use xrange where list might be large
  def _iteritems(d):  # only use iteritems when dict might be large
    return d.items()
  raw_input = input
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
from collections import Sequence, Mapping
from ctypes import (c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint,
                    c_long, c_ulong, c_longlong, c_ulonglong,
                    c_float, c_double, c_longdouble, sizeof)

########################################################################

class Yorick(object):
  """Interface to a yorick process.

  Attributes:
    call -    call-semantics handle
    eval -    eval-semantics handle
    value -   value-semantics handle

    Handles are objects whose attributes represent yorick variables.
  """
  def __init__(self, extra='', **kwargs):
    """Start a yorick process.

    Parameters:
      extra (str or list of str):  additional command line arguments
    """
    if isinstance(extra, Process):
      self.proc = extra
    else:
      self.proc = ProcessDefault(extra, **kwargs)

  def __del__(self):
    self.kill()

  def __repr__(self):
    return "<connection to {0}>".format(repr(self.proc)[1:-1])

  def kill(self):
    """Kill yorick process."""
    self.proc.kill()
  def debug(self, on):
    """Set or unset debug mode for yorick process."""
    self.proc.debug(on)

  def handles(self, which=3):
    """Return handles whose attributes are yorick variables.

    Parameters:
      which (int, default is 3):
        - 1 returns call-semantics handle
        - 2 returns eval-semantics handle
        - 4 returns value-semantics handle
        - add to return tuple with up to three handles
    """
    h = [['call', 'eval', 'value'][i//2] for i in [1, 2, 4] if (which&i)]
    if len(h) == 1:
      return getattr(self, h[0])
    else:
      return tuple([getattr(self,h[i]) for i in range(len(h))])

  # first reference shadows these properties (and abbreviations) in instance
  @property
  def call(self):
    self.call = self.c = YorickHandle(0, self)
    return self.call
  @property
  def eval(self):
    self.eval = self.e = YorickHandle(1, self)
    return self.eval
  @property
  def value(self):
    self.value = self.v = YorickHandle(2, self)
    return self.value
  # single character abbreviations for interactive use
  c = call
  e = eval
  v = value

  def __call__(self, command=None, *args, **kwargs):  # pipe(command)
    """Execute a yorick command."""
    self.call(command, *args, **kwargs)

  def _reqrep(self, msgid, *args, **kwargs):  # convenience for YorickHandle
    reply = Message()
    self.proc.reqrep(Message(msgid, *args, **kwargs), reply)
    reply = reply.decode()
    if isinstance(reply, tuple):
      if msgid!=ID_GETVAR or reply!=tuple(ID_EOL, (2,), {}):
        raise PYorickError("yorick sent error reply to request")
      reply = YorickVarDerived(self, 0, args[0])
    return reply

# expose this to allow user to catch pyorick exceptions
class PYorickError(Exception):
  pass

# np.newaxis is None, which is [] in yorick, not -
# ynewaxis provides a means for specifying yorick - in get/setslice
class NewAxis(object):
  pass
ynewaxis = NewAxis()

# yorick distinguishes string(0) from an empty string; python does not
# provide an empty string which can be used to pass string(0) to yorick,
# but still works like an empty string in python
class YString0(str):
  pass
ystring0 = YString0()

########################################################################

class YorickHandle(object):
  """Object whose attributes are yorick variables.

  Do not attempt to probe with hasattribute or other introspection!
  """

  # Every attribute in this class should represent a yorick variable.
  # The __XXX__ system names cannot be retrieved, nor can the
  # practically unavoidable _reftype__ and _yorick__ attributes.
  # However, no other attributes are permitted.

  # must avoid __setattr__, __getattr__ by explicit calls through __dict__
  def __init__(self, reftype, connection):
    self.__dict__['_reftype__'] = reftype
    self.__dict__['_yorick__'] = connection

  def __repr__(self):
    connection = self.__dict__['_yorick__']
    typ = ['call', 'eval', 'value'][self.__dict__['_reftype__']]
    s = "<yorick {0}-semantics handle to {1}>"
    return s.format(typ, repr(connection.proc)[1:-1])

  def __getitem__(self, key=None):
    """Return parent connection, avoiding use of an attribute."""
    connection = self.__dict__['_yorick__']
    if key is None:
      return connection
    typ = self.__dict__['_reftype__']
    if typ == 2:
      typ = 0
    return YorickVarDerived(connection, typ, key)

  def __call__(self, command=None, *args, **kwargs):
    """Implement handle(command) or handle(format, args, key=kwds)."""
    if args or kwargs:
      command = command.format(*args, **kwargs)
    connection = self.__dict__['_yorick__']
    typ = self.__dict__['_reftype__']
    if command[0] == '=':   # leading = forces eval semantics
      command = command[1:]
      typ = 1
    if command is None:
      connection.proc.interact(YorickServer())
    elif typ:
      return connection._reqrep(ID_EVAL, command)
    else:
      return connection._reqrep(ID_EXEC, command)

  def __setattr__(self, name, value):
    """Implement handle.name = value."""
    connection = self.__dict__['_yorick__']
    if name not in self.__dict__:
      connection._reqrep(ID_SETVAR, name, value)
    else:
      object.__setattr__(self, name, value)

  def __getattr__(self, name):                   # pipe.name
    # inspect module causes serious problems by probing for names
    # ipython also probes for getdoc attribute
    if (len(name)>3 and name[0:2]=='__' and name[-2:]=='__') or name=='getdoc':
      raise AttributeError("YorickHandle instance has no attribute '"+name+"'")
    if name in ['_reftype__', '_yorick__']:
      return self.__dict__[name]
    connection = self.__dict__['_yorick__']
    typ = self.__dict__['_reftype__']
    if typ == 2:
      return connection._reqrep(ID_GETVAR, name)
    return YorickVarDerived(connection, typ, name)

class YorickVar(object):
  """Reference to a yorick variable."""
  def __init__(self, connection, reftype, name):
    if not isinstance(name, basestr):
      raise PYorickError("illegal yorick variable name")
    self.yorick = connection
    self.reftype = bool(reftype)
    self.name = name

  def __repr__(self):
    connection = self.connection
    typ = ['call', 'eval'][self.reftype]
    s = "<yorick variable {0} ({1}) in {2}>"
    return s.format(self.name, typ, repr(connection.proc)[1:-1])

  def __call__(self, *args, **kwargs):
    """Implement handle.name(args, kwargs)."""
    if self.reftype:
      return self.connection._reqrep(ID_FUNCALL, self.name, *args, **kwargs)
    else:
      self.connection._reqrep(ID_SUBCALL, self.name, *args, **kwargs)

  def __getitem__(self, key): 
    """Implement handle.name[key]."""
    key = self._fix_indexing(key)
    return self.connection._reqrep(ID_GETSLICE, self.name, *key)

  def __setitem__(self, key, value):
    """Implement handle.name[key] = value."""
    key = self._fix_indexing(key) + (value,)
    return self.connection._reqrep(ID_SETSLICE, self.name, *key)

  def _fix_indexing(self, key):
    if not isinstance(key, tuple):
      key = (key,)  # only single index provided
    if self.reftype:
      return key
    # convert from python index semantics to yorick index semantics
    ndxs = []
    for ndx in key[::-1]:  # reverse index order
      if isinstance(ndx, slice):
        if ndx:
          i, j, s = ndx.start, ndx.stop, ndx.step
          i += 1        # python.x[i:etc] --> yorick.x(i+1:etc)
          if s < 0:
            j += 2      # len=stop-step --> len=stop-step+1
          # could also detect <nuller:> here?
          ndx = slice(i, j, s)
      elif isinstance(ndx, Number) or isinstance(ndx, np.ndarray):
        if isinstance(ndx, bool):
          ndx = int(ndx)
        ndx += 1        # python.x[i] --> yorick.x(i+1)
      elif isinstance(ndx, bytearray):
        ndx = np.frombuffer(ndx, dtype=np.uint8) + 1
      elif isinstance(ndx, Sequence):
        shape, typ = codec.nested_test(ndx)
        if typ == Number:
          ndx = np.array(ndx) + 1   # python.x[i] --> yorick.x(i+1)
      ndxs.append(ndx)
    return tuple(ndxs)

  def info(self):
    """Implement handle.name.info."""
    return self.connection._reqrep(ID_GETINFO, self.name)

  def value(self):
    """Implement handle.name.value."""
    return self.connection._reqrep(ID_GETVAR, self.name)
  # single character alias for interactive use
  v = value

# Hook for packages (like a lazy evaluator) to customize YorickVar;
# YorickVarDerived is the object a YorickHandle uses.
# The YorickVarDerived class must be a derived class of YorickVar.
# The derived class must call YorickVar.__init__ in its constructor.
YorickVarDerived = YorickVar

class YorickServer(object):
  """Server to accept requests from and generate replies to yorick."""
  def start(self, command=None):
    """Start server, optionally returning exec msg to be sent to yorick."""
    self.started = False
    self.request = Message()  # provide container for first request
    if command:
      # Unless this Process has some out-of-band way to enter terminal mode,
      # yorick will be expecting a request.  Execing this yorick command
      # must cause yorick to begin emitting requests rather than replies.
      return Message(ID_EXEC, command)

  def reply(self):
    """Return message to be sent in reply to self.request."""
    req = self.request.decode()
    self.request = Message()  # empty container for next request
    code = None
    if isinstance(req, tuple):
      if req[0]==ID_EOL and not req[1][0]:
        # this is signal to exit terminal mode (matches start command)
        return None
      if req[0] == ID_EXEC:
        text = req[1][0].replace('\0', '\n')
        if not text:
          # alternate signal to exit terminal mode (if no start command)
          return None
        code = compile(text, '<pyorick command>', 'exec')
      elif req[0] == ID_EVAL:
        text = req[1][0].replace('\0', '\n')
        if text:
          code = compile(text, '<pyorick command>', 'eval')
    if code:
      self.started = True
      try:
        msg = Message(None, eval(code, globals()))
        return msg
      except:
        # any exceptions trying to eval or encode reply are yorick's problem
        pass
    elif not self.started:
      self.request = None
      return None   # assume that yorick never entered terminal mode
    return Message(ID_EOL, 1)  # signal error to yorick

  # Provide two cleanup options:
  # 1. finish() or finish(command)  to optionally send a final yorick command
  #   - if command supplied, server.request and server.reply() one last time
  # 2. final(value)   to send a final value back to yorick
  def finish(self, command=None):
    """Stopping server, optionally returning exec msg to be sent to yorick."""
    if command:
      return Message(ID_EXEC, command)
    # Empty request message from start or reply already present.
    # Caller may call reply one final time if needed.

  def final(self, value):
    """Stopping server, returning data message to be sent to yorick."""
    return Message(None, value)

class Message(object):
  """Message to or from yorick in raw protocol-wire form.

     msg = Message(msgid, arglist)  for active messages
     msg = Message(None, value)     for data messages
     msg = Message()                for an empty message, to call encoder
     packetlist = msg.encoder()     return generator to receive from process
     value = msg.decode()           return value of msg built by packetlist
  """
  """
  A message is a list of packets, where each packet is an ndarray.

  Messages must be sent and received atomically, which is why they are
  marshalled in a Message instance in the raw format, so that none of
  the encode or decode logic, which may raise formatting exceptions,
  is interspersed with the sending or receiving.

  Constructor:
      Encode active message, where msgid is ID_EVAL, ID_EXEC, etc.,
      and the argument list depends on which message:
    msg = Message(ID_EVAL, 'yorick expression')
    msg = Message(ID_EXEC, 'yorick code')
    msg = Message(ID_GETVAR, 'varname')
    msg = Message(ID_SETVAR, 'varname', value)
    msg = Message(ID_FUN/SUBCALL, 'fname', arg1, arg2, ..., key1=k1, ...)
    msg = Message(ID_GETSLICE, 'aname', index1, index2, ...)
    msg = Message(ID_SETSLICE, 'aname', index1, index2, ..., value)
    msg = Message(ID_GETSHAPE, 'varname')
      Passive EOL end-of-list message:
    msg = Message(ID_EOL, flag)              flag defaults to 0
      Data messages ordinarily created using Message(None, value):
    msg = Message(ID_LST/DCT, list or dict)
    msg = Message(ID_NIL)
    msg = Message(ID_SLICE, flags, start, stop, step)
    msg = Message(ID_STRING, shape, lens, value)
    msg = Message(0 thru 15, shape, value)   for numeric arrays

  The encoder method returns a generator which can be used to build a
  message starting from an empty message:
    packetlist = msg.encoder()
    for packet in packetlist:
      read raw ndarray into packet, which has required dtype and shape
  After this loop, msg.packets will contain the list of ndarrays.

  The decode method converts msg.packets into a value if the message is
  data.  Otherwise (for active messages or EOL) it produces a tuple
  (msgid, args, kwargs) which could be passed to the Message constructor
  to recreate the message.
    value = msg.decode()
    if isinstance(value, tuple):
      this is an instruction (active message or ID_EOL)
    else:
      this is data
  """
  def __init__(self, *args, *kwargs):
    self.packets = []
    if not args:
      return None
    msgid = args[0]
    if msgid is None:
      msgid, args, kwargs = self.encode_data(*args[1:])
      codec.idtable[msgid].encoder(self, msgid, *args, **kwargs)

  def encoder(self):
    return codec.reader(self)

  def decode(self):
    if not self.packets:
      PYorickError("cannot decode empty message")
    self.pos = 1  # pos=0 already processed here
    return codec.idtable[self.packets[0][0]].decoder(self)

# Here is a pseudo-bnf description of the message grammar:
#
# message := narray     numeric array
#          | sarray     string array, nested list in python
#          | slice      array index selecting a subset
#          | nil        [] in yorick, None in python
#          | list       list in python, anonymous oxy object in yorick
#          | dict       dict in python, oxy object in yorick
#          | eol        end-of-list, variants used for other purposes
#          | eval       parse text and return expression value
#          | exec       parse text and execute code, no return value
#          | getvar     return variable value
#          | setvar     set variable value
#          | funcall    invoke function, returning value
#          | subcall    invoke function as subroutine, no return value
#          | getslice   return slice of array
#          | setslice   set slice of array
#          | getshape   return type and shape of array, but not value
# narray := long[2]=(0..15, rank) shape data
# sarray := long[2]=(16, rank) shape lens text
# slice := long[2]=(17, flags) long[3]=(start, stop, step)
# nil := long[2]=(18, 0)
# list := long[2]=(19, 0) llist
# dict := long[2]=(20, 0) dlist
# eol := long[2]=(21, flags)
# eval := long[2]=(32, textlen) text
# exec := long[2]=(33, textlen) text
# getvar := long[2]=(34, namelen) name
# setvar := long[2]=(35, namelen) name value
# funcall := long[2]=(36, namelen) name alist
# subcall := long[2]=(37, namelen) name alist
# getslice := long[2]=(38, namelen) name ilist
# setslice := long[2]=(39, namelen) name llist value
# getvar := long[2]=(40, namelen) name
#
# shape := long[rank]    nothing if rank=0
# data := type[shape]
# lens := long[shape]
# text := char[textlen or sum(lens)]
# llist := eol(0)
#        | value llist
# dlist := eol(0)
#        | setvar llist
# name := char[namelen]
# value := narray | sarray | slice | nil | list | dict | getvar
# alist := eol(0)
#       := value alist
#       := setvar alist

# type numbers needed during execution of class codec definition
# id 0-15 are numeric types:
#    char short int long longlong   float double longdouble
#    followed by unsigned (integer) or complex (floating) variants
# passive messages (reply prohibited):
ID_STRING, ID_SLICE, ID_NIL, ID_LST, ID_DCT, ID_EOL =\
   16,        17,       18,     19,     20,     21
# ID_STRING: yorick assumes iso_8859_1, need separate id for utf-8?

# active messages (passive reply required):
ID_EXEC, ID_EVAL, ID_GETVAR, ID_SETVAR, ID_FUNCALL, ID_SUBCALL =\
   32,      33,      34,        35,        36,         37
ID_GETSLICE, ID_SETSLICE, ID_GETSHAPE =\
   38,          39,          40

# Each instance of Clause represents a clause of the message grammar.
# At minimum, the functions to build, encode, and decode that clause must
# be defined.  These definitions are in codec below.
# Clause primarily implements the decorators used to cleanly construct
# codec.
class Clause(object):
  def __init__(self, idtable=None, *idlist):
    self.idlist = idlist  # tuple of message ids if top level clause
    for msgid in idlist:
      idtable[i] = self

  # The reader, encoder, and decoder are decorator functions for codec,
  # which shadow themselves in each instance.
  # Note that the shadow version is an ordinary function, not a method,
  # implicitly @staticmethod.
  # (Inspired by property setter and deleter decorators.)
  def reader(self):
    def add(func):
      self.reader = func
      return self
    return add
  def encoder(self):
    def add(func):
      self.encoder = func
      return self
    return add
  def decoder(self):
    def add(func):
      self.decoder = func
      return self
    return add

class codec(object):  # not really a class, just a convenient container
  """Functions and tables to build, encode, and decode messages."""
  # This collection of methods makes protocol flexible and extensible.
  # To add new message type(s):
  # 1. Choose a new msgid number(s), and a name for the top level clause.
  # 2. name = Clause(msgid [, ident2, ident3, ...])
  # 3. Write the reader, encoder, and decoder methods (see below).
  # Note that the reader method is a generator function; the others
  # are ordinary functions.  The first argument is always msg, the current
  # message, which you may use as you like to store state information.
  # The packets attribute of msg is the list of packets; each packet must
  # be an ndarray.

  # numeric protocol datatypes are C-types (byte is C char)
  types = [c_byte, c_short, c_int, c_long, c_longlong,
           c_float, c_double, c_longdouble,
           c_ubyte, c_ushort, c_uint, c_ulong, c_ulonglong,
           np.csingle, np.complex_, None]  # no portable complex long double
  typesz = [sizeof(types[i]) for i in range(15)].append(0)
  typesk = ['i']*5 + ['f']*3 + ['u']*5 + ['c']*2 + ['none']
  typesk = [typesk[i]+str(typesz[i]) for i in range(16)]  # keys for typtab
  # lookup table for msgid given typesk (computable from dtype)
  typtab = [0, 1, 2, 4, 3, 5, 7, 6, 8, 9, 10, 12, 11, 13, 15, 14]
  typtab = dict([[typesk[typtab[i]], typtab[i]] for i in range[16]])

  # dict of top level clauses by key=message id
  idtable = {}  # idtable[msgid] --> top level message handler for msgid

  @staticmethod
  def reader(msg):
    if msg.packets:
      PYorickError("attempt to read into non-empty message")
    packets[0] = packet = nplongs(0, 0)
    yield packet
    codec.idtable[packet[0]].reader(msg)

  narray = Clause(idtable, *ID_NUMERIC)
  @narray.reader()
  def narray(msg):
    msgid, rank = msg.packets[-1]
    shape = np.zeros(rank, dtype=c_long)
    if rank > 0:
      yield shape
    value = np.zeros(shape, dtype=codec.types[msgid])
    yield value
  @narray.encoder()
  def narray(msg, msgid, shape, value):
    rank = len(shape)
    msg.packets.append(nplongs(msgid, rank))
    if rank:
      msg.packets.append(shape)
    msg.packets.append(value)
  @narray.decoder()
  def narray(msg):
    pos = msg.pos
    rank = msg.packets[pos-1][1]
    if rank:
      msg.pos = pos = pos+1
    msg.pos += 1
    return msg.packets[pos]

  sarray = Clause(idtable, ID_STRING)
  @sarray.reader()
  def sarray(msg):
    msgid, rank = msg.packets[-1]
    shape = np.zeros(rank, dtype=c_long)
    if rank > 0:
      yield shape
    value = np.zeros(shape, dtype=np.uint8)
    yield value
  @sarray.encoder()
  def sarray(msg, msgid, shape, lens, value):
    codec.narray.encoder(msg, ID_LONG, shape, lens)
    if value.nbytes:
      msg.packets.append(value)
  @sarray.decoder()
  def sarray(msg):
    pos = msg.pos
    rank = msg.packets[pos-1][1]
    if rank:
      msg.pos = pos = pos+1
    msg.pos += 1
    lens = msg.packets[pos]
    if lens.sum():
      pos = msg.pos
      msg.pos += 1
      value = msg.packets[pos]
    else:
      value = np.zeros(0, dtype=np.uint8)
    return codec.decode_sarray(lens, value)  # as nested list

  slice = Clause(idtable, ID_SLICE)
  @slice.reader()
  def slice(msg):
    packet = nplongs(0, 0, 0)
    yield packet
  @slice.encoder(msg)
  def slice(msg, msgid, x, flags=None):
    if not flags: 
      if x.start is None:
        smin, flags = 0, 1
      else:
        smin, flags = x.start, 0
      if x.stop is None:
        smax, flags = 0, flags+2
      else:
        smax = x.stop
      if x.step is None:
        sinc = (-1, 1)[flags or smin<=smax]
      else:
        sinc = x.step
    else:
      smin = smax = 0
      sinc = 1
    msg.packets.append(nplongs(msgid, flags))
    msg.packets.append(nplongs(smin, smax, sinc))
  @slice.decoder()
  def slice(msg):
    pos = msg.pos
    flags = msg.packets[pos-1][1]
    if flags == 7:
      value = ynewaxis  # np.newaxis confused with nil
    elif flags == 11:
      value = Ellipsis
    else:
      value = msg.packets[pos].tolist()
      if flags&1:
        value[0] = None
      if flags&2:
        value[1] = None
      value = slice(*value)
    msg.pos += 1
    return value

  nil = Clause(idtable, ID_NIL)
  @nil.reader()
  def nil(msg):
    pass
  @nil.encoder()
  def nil(msg, msgid):
    msg.packets.append(nplongs(msgid, 0))
  @nil.decoder()
  def nil(msg):
    return None

  lst = Clause(idtable, ID_LST)
  @lst.reader()
  def lst(msg):
    for packet in codec.qmlist.reader(0):
      yield packet
  @lst.encoder()
  def lst(msg, msgid, value):
    msg.packets.append(nplongs(msgid, 0))
    codec.qmlist.encoder(msg, 0, value, {})
  @lst.decoder()
  def lst(msg):
    value = []
    codec.qmlist.decoder(msg, 0, value)
    return value

  dct = Clause(idtable, ID_DCT)
  @dct.reader()
  def dct(msg):
    for packet in codec.qmlist.reader(1):
      yield packet
  @dct.encoder()
  def dct(msg, msgid, value):
    msg.packets.append(nplongs(msgid, 0))
    codec.qmlist.encoder(msg, 1, (), value)
  @dct.decoder()
  def dct(msg):
    value = {}
    codec.qmlist.decoder(msg, 1, None, value)
    return value

  eol = Clause(idtable, ID_EOL)
  @eol.reader()
  def eol(msg):
    pass
  @eol.encoder()
  def eol(msg, flag=0):
    msg.packets.append(nplongs(msgid, flag))
  @eol.decoder()
  def eol(msg):
    return tuple(ID_EOL, (int(msg.packets[msg.pos-1][1]),), {})

  eval = Clause(idtable, ID_EVAL, ID_EXEC)
  @eval.reader()
  def eval(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      yield packet
  @eval.encoder()
  def eval(msg, msgid, text):
    text = np.fromiter(text.encode('iso_8859_1'), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(text)))
    if len(text):
      msg.packets.append(text)
  @eval.decoder()
  def eval(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      text = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      text = ''
    return (msg.packets[pos-1][0], (text,), {})

  # same as eval, but may want to add name sanity checks someday
  getvar = Clause(idtable, ID_GETVAR, ID_GETSHAPE)
  @getvar.reader()
  def getvar(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      yield packet
  @getvar.encoder()
  def getvar(msg, msgid, name):
    name = np.fromiter(name.encode('iso_8859_1'), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(name)))
    if len(name):
      msg.packets.append(name)
  @getvar.decoder()
  def getvar(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      name = ''
    return (msg.packets[pos-1][0], (name,), {})

  # same as eval, but may want to add name sanity checks someday
  setvar = Clause(idtable, ID_SETVAR)
  @setvar.reader()
  def setvar(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      yield packet
    packet = nplongs(0, 0)
    yield packet
    msgid = msg.packets[-1][0]
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setvar value msgid in reader")
    for packet in codec.idtable[msgid].reader(msg):
      yield packet
  @setvar.encoder()
  def setvar(msg, msgid, name, value):
    name = np.fromiter(name.encode('iso_8859_1'), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(name)))
    if len(name):
      msg.packets.append(name)
    msgid, args, kwargs = self.encode_data(value)
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setvar value msgid in encoder")
    codec.idtable[msgid].encoder(msg, msgid, *args, **kwargs)
  @setvar.decoder()
  def setvar(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      name = ''
    args = (name, codec.idtable[msg.packets[pos+1][0]].decoder(msg))
    return (msg.packets[pos-1][0], args, {})

  funcall = Clause(idtable, ID_FUNCALL, ID_SUBCALL)
  @funcall.reader()
  def funcall(msg):
    getvar(msg)
    codec.qmlist.reader(msg, 2)
  @funcall.encoder()
  def funcall(msg, msgid, name, *args, **kwargs):
    getvar(msg, msgid, name)
    codec.qmlist.encoder(msg, 2)
  @funcall.decoder()
  def funcall(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      name = ''
    args = []
    kwargs = {}
    codec.qmlist.decoder(msg, 2, kind, args, kwargs)
    return (msg.packets[pos-1][0], (name,)+tuple(args), kwargs)

  getslice = Clause(idtable, ID_GETSLICE)
  @getslice.reader()
  def getslice(msg):
    getvar(msg)
    codec.qmlist.reader(msg, 0)
  @getslice.encoder()
  def getslice(msg, msgid, name, *args):
    getvar(msg, msgid, name)
    codec.qmlist.encoder(msg, 0)
  @getslice.decoder()
  def getslice(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      name = ''
    args = []
    codec.qmlist.decoder(msg, 0, kind, args, {})
    return (msg.packets[pos-1][0], (name,)+tuple(args), kwargs)

  setslice = Clause(idtable, ID_SETSLICE)
  @setslice.reader()
  def setslice(msg):
    getvar(msg)
    codec.qmlist.reader(msg, 0)
  @setslice.encoder()
  def setslice(msg, msgid, name, *args):
    getvar(msg, msgid, name)
    codec.qmlist.encoder(msg, 0)
  @setslice.decoder()
  def setslice(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = msg.packets[pos].tostring().decode('iso_8859_1')
    else:
      name = ''
    args = []
    codec.qmlist.decoder(msg, 0, kind, args, {})
    value = codec.idtable[msg.packets[pos+1][0]].decoder(msg)
    return (msg.packets[pos-1][0], (name,)+tuple(args)+(value,), {})

  # eol terminated lists, qmlist means "quoted message list"
  qmlist = Clause()
  @qmlist.reader()
  def qmlist(msg, kind):
    allowed = codec.qmlist.allowed[kind]
    while True:
      packet = nplongs(0, 0)
      yield packet
      msgid = msg.packets[-1][0]
      if msgid not in allowed:
        if msgid!=ID_EOL or msg.packets[-1][1]:
          raise PYorickError("illegal list element msgid")
        break
      for packet in codec.idtable[msgid].reader(msg):
        yield packet
  @qmlist.encoder()
  def qmlist(msg, kind, args, kwargs):
    allowed = codec.qmlist.allowed[kind]
    for arg in args:
      msgid, iargs, ikwargs = self.encode_data(value)
      codec.idtable[msgid].encoder(msg, msgid, *iargs, **ikwargs)
    for key in kwargs:
      codec.setvar.encoder(msg, ID_SETVAR, key, kwargs[key])
    msg.packets.append(codec.eol.encoder(msg))
  @qmlist.decoder()
  def qmlist(msg, kind, args, kwargs):
    allowed = codec.qmlist.allowed[kind]
    while True:
      pos = msg.pos
      msg.pos += 1
      packet = packets[pos]
      msgid = packet[0]
      if msgid not in allowed:
        if msgid!=ID_EOL or packet[1]:  # always caught by reader or encoder?
          raise PYorickError("illegal list element msgid (BUG?)")
        break
      item = codec.idtable[msgid].decoder(msg)
      if msgid == ID_SETVAR:
        kwargs[item[1][0]] = item[1][1]  # dict[name] = value
      else:
        args.append(item)
  # set allowed msgids for the various types of list (used by reader)
  qmlist.allowed = [i for i in range(ID_EOL)].append(ID_GETVAR)
  qmlist.allowed = [qmlist.allowed                     # llist
                    [ID_SETVAR],                       # dlist
                    qmlist.allowed.append(ID_SETVAR)]  # alist

  @staticmethod
  def decode_sarray(lens, value):
    shape = lens.shape
    if shape:
      n = np.prod(shape)
    else:
      n = 1
    # split value into 1D list of strings v
    lens = ravel(lens)
    i1 = np.cumsum(lens)
    i0 = i1 - lens
    i1 -= 1
    v = []
    for i in xrange(n):
      if lens[i]:
        v.append(value[i0[i]:i1[i]].tostring().decode('iso_8859_1'))
      else:
        v.append(ystring0)
    # reorganize v into nested lists for multidimensional arrays
    ndim = len(shape)
    for i in range(ndim-1):
      m = shape[i]
      v = [v[j:j+m] for j in xrange(0, n, m)]
      n /= m
    # handle scalar
    if not ndim:
      v = v[0]
    return v

  @staticmethod
  def encode_sarray(shape, value):
    # flatten the nested list
    n = len(shape)
    if n:
      while n > 1:
        n -= 1
        v = []
        for item in value:
          v.extend(item)
        value = v
    else:
      value = [value]
    lens = []
    for i in xrange(len(value)):
      v = value[i]
      if '\0' in v:
        v = v[0:v.index('\0')+1]  # truncate after first NULL
      else if not isinstance(v, YString0):
        v += '\0'
      v = v.encode('iso_8859_1')
      lens.append(len(v))
      value[i] = v
    lens = np.array(lens, dtype=c_long).reshape(shape)
    value = np.array(b''.join(value), dtype=uint8)
    return (ID_STRING, (shape, lens, value), {})

  # decode work done, but encode still needs to recogize python data
  @staticmethod
  def encode_data(value):   # return (msgid, args, kwargs)
    msgid = -1  # unknown initially

    if isinstance(value, Number):
      value = np.array(value)

    elif isinstance(value, bytearray):
      value = np.frombuffer(value, dtype=np.uint8)

    elif isinstance(value, basestring):
      return codec.encode_sarray((), value)

    elif isinstance(value, Sequence):   # check for array-like nested sequence
      shape, typ = codec.nested_test(value)
      if type == basestr:
        return codec.encode_sarray(shape, value)
      elif typ != Number:
        # may raise errors later, but not array-like
        return (ID_LST, (value), {})
      # np.array converts nested list of numbers to ndarray
      value = np.array(value)

    # numeric arrays are the "money message"
    if isinstance(value, np.ndarray):
      shape = value.shape
      k = str(value.dtype.kind)
      if k in 'SUa':
        return codec.encode_sarray(shape, value.tolist())
      if k not in 'biufc':
        raise PYorickError("cannot encode unsupported array item type")
      if k == 'b':
        k = 'u'
      k += str(value.dtype.itemsize)
      if k not in typtab:
        PYorickError("cannot encode unsupported array numeric dtype")
      msgid = typtab[k]
      if not value.flags['CARRAY']:
        value = np.copy(value, 'C')
      return (msgid, (shape, value), {})

    # index range, including (newaxis, Ellipsis) <--> (-, ..)
    elif isinstance(value, NewAxis):  # np.newaxis is unfortunately None
      return (ID_SLICE, (None, 7), {})
    elif value is Ellipsis:
      return (ID_SLICE, (None, 11), {})
    elif isinstance(value, slice):
      return (ID_SLICE, (value), {})

    elif value is None:
      return (ID_NIL, (), {})

    # dict objects only allowed if all keys are strings
    elif isinstance(value, Mapping):
      if not all(isinstance(key, basestring) for key in value):
        raise PYorickError("cannot encode dict with non-string key")
      return (ID_DCT, (value), {})

    elif isinstance(value, YorickVar):
      return (ID_GETVAR, (value.name), {})

    else:
      raise PYorickError("cannot encode unsupported data object")

  @staticmethod
  def nested_test(value):  # value is a Sequence
    shape = (len(value),)
    if shape[0]:
      v = value[0]
      if isinstance(v, Number):
        if all(isinstance(v, Number) for v in value[1:]):
          return shape, Number
      elif isinstance(v, basestring):
        if all(isinstance(v, basestring) for v in value[1:]):
          return shape, basestring
      elif isinstance(v, Sequence):
        n, typ = codec.nested_test(v)
        if typ:
          for v in value[1:]:
            if isinstance(v, Sequence):
              m, t = codec.nested_test(v)
              if m==n and t==typ:
                continue
            return shape, None
        return shape + n, typ
    return shape, None
    

def nplongs(*args):
  return np.array(args, dtype=c_long)

########################################################################

class Process(object):
  def kill(self):
    raise NotImplementedError("This process does not implement kill.")
  def reqrep(self, request, encoder):
    raise NotImplementedError("This process does not implement reqrep.")
  def interact(self, server):
    raise NotImplementedError("This process does not implement interact.")
  def debug(self):
    raise NotImplementedError("This process does not implement debug.")

ypathd = "yorick"     # default yorick command
ipathd = "pyorick.i"  # default pyorick.i include file

class PtyProcess(Process):
  """Process using binary pipes and tty-pty for stdin/out/err."""
  def __init__(self, extra, ypath=None, ipath=None):
    if ypath is None:
      ypath = ypathd
    if ipath is None:
      ipath = ipathd
    argv = [ypath, '-q', '-i', ipath]
    # complete argv will be:   argv rfd wfd extra
    ptoy = self.inheritable_pipe(0)
    ytop = self.inheritable_pipe(1)
    self.pid, self.pfd = os.forkpty()
    # self.pid = os.fork()
    if not self.pid:   # subprocess side
      os.close(ptoy[1])
      os.close(ytop[0])
      argv.extend([str(ptoy[0]), str(ytop[1])])
      if extra:
        argv.extend(shlex.split(extra))
      os.execvp(ypath, argv)
      os._exit(1)            # failed to launch yorick
    os.close(ptoy[0])
    os.close(ytop[1])
    self.rfd = ytop[0]
    self.wfd = ptoy[1]
    # set reasonable termios attributes
    t = termios.tcgetattr(self.pfd)
    t[3] = t[3] & ~termios.ECHO
    termios.tcsetattr(self.pfd, termios.TCSANOW, t)

  def __del__(self):
    self.kill()

  def kill(self):
    if self.pid is not None:
      try:
        os.close(self.pfd)
        os.close(self.rfd)
        os.close(self.wfd)
        os.waitpid(self.pid, 0)   # otherwise yorick becomes a zombie
      finally:
        self.pid = self.pfd = self.rfd = self.wfd = self.batch = None
        self.debug = self.mode = self.mode_tmp = False
        self.need_reply = False

  def reqrep(self, request, encoder):
    self.echo_pty()  # flush out any pending output
    try:  # send request
      for packet in request:
        self.send(packet)
    except:
      self.kill()
      raise PYorickError("failed to send complete message, yorick killed")
    try:  # receive reply
      for packet in encoder:
        self.recv(packet)
    except:
      self.kill()
      raise PYorickError("failed to receive complete message, yorick killed")
    # not finished until yorick comes back to its prompt
    self.wait_for_prompt()

  def interact(self, server):
    self.echo_pty()  # flush out any pending output
    self.send(server.start("pyorick"))  # tell yorick to enter terminal mode
    # handshake for yorick never entering terminal mode below
    prompt = None
    while True:
      # either prompt will arrive or another request
      try:
        p = select.select([self.pfd, self.rfd], [], [self.pfd, self.rfd])
        if p[2]:
          self.kill()
          raise PYorickError("Select reports error, yorick killed.")
        if self.rfd in p[0]:
          self.recv(server.request)
          rep = server.reply()
          if rep:
            self.send(rep)  # yorick is blocked waiting for this
          else:
            break
        elif self.rfd in p[0]:
          # only get here when no more requests on rfd
          prompt = self.echo_pty(True)
          if prompt:  # pass along prompt and wait for user to respond
            self.send0(raw_input(prompt))
      except KeyboardInterrupt:
        self.send0('\x03', True)  # send ctrl-c to pty
    if server.request:  # if not, never entered terminal mode
      self.echo_pty(True)  # flush pending output before releasing yorick
      self.send(server.final(None))       # handshake to exit terminal mode
    self.wait_for_prompt()

  def wait_for_prompt(self, mode=False):
    while True:
      p = select.select([self.pfd], [], [self.pfd])
      prompt = echo_pty(mode)
      if prompt:
        return prompt

  def echo_pty(self, mode=False):
    """Print yorick stdout/stderr, returning final prompt if any."""
    if not self.pfd:
      return None
    s = ''
    i = 0    # curiously hard to get reply promptly?
    while i < 3:  # continue until no output pending
      try:
        p = select.select([self.pfd], [], [self.pfd], 0)
      except:
        p = ([], [], [self.pfd])
      if p[0]:
        try:
          s += os.read(self.pfd, 16384).decode('iso_8859_1')
        except:
          p = (0, 0, 1)
      if p[2]:
        self.kill()
        raise PYorickError("Read or select error on pty, yorick killed.")
      if not p[0]:
        i += 1
    prompt = None
    if s:
      # remove prompt in interactive (no idler) mode
      if mode and s.endswith("> "):
        i = s.rfind('\n') + 1  # 0 on failure
        prompt = s[i:]
        s = s[0:i]
      if s:
        print(s, end='')  # terminal newline already in s
    return prompt

  def send0(self, text, nolf=False):
    if self.pfd:
      if not nolf:
        if not text.endswith('\n'):
          text += '\n'
      n = 0
      while n < len(text):
        try:
          n += os.write(self.pfd, text[n:].encode('iso_8859_1'))
        except UnicodeEncodeError:
          print("<--- did not send non-ISO-8859-1 text to yorick --->")
          text = '\n'
          n = 0
        except:
          self.kill()
          raise PYorickError("Unable to write to yorick stdin, yorick killed.")

  # See PEP 433.  After about Python 3.3, pipes are close-on-exec by default.
  @staticmethod
  def inheritable_pipe(side):
    """Return a pipe that is *not* close-on-exec."""
    p = os.pipe()
    if hasattr(fcntl, 'F_SETFD') and hasattr(fcntl, 'FD_CLOEXEC'):
      flags = fcntl.fcntl(p[side], fcntl.F_GETFD)
      flags &= ~fcntl.FD_CLOEXEC
      fcntl.fcntl(p[side], fcntl.F_SETFD, flags)
    return p

  def recv(self, packet):
    """Read numpy array packet from self.rfd."""
    # other interfaces are readinto, copyto, frombuffer, getbuffer
    if not self.rfd:
      return None   # some fatal exception has already occurred
    # note: packet.data[n:] fails in python 3.4 if packet is scalar
    xx = packet.reshape(packet.size).view(dtype=np.uint8)
    n = 0
    while n < packet.nbytes:
      try:
        s = os.read(self.rfd, packet.nbytes-n)  # no way to use readinto?
      except:
        self.kill()  # failure fatal, need to shut down yorick
        raise PYorickError("os.read failed, yorick killed")
      m = len(s)
      xx.data[n:n+m] = s  # fails in python 3.4 unless xx dtype=np.unit8
      n += m
    if self.debug and n:
      print(("P>recv: {0} bytes".format(n)))

  def send(self, packet):
    """Write numpy array packet to self.wfd."""
    if not self.wfd:
      return None   # some fatal exception has already occurred
    # note: packet.data[n:] fails in python 3.4 if packet is scalar
    pp = packet.reshape(packet.size).view(dtype=np.uint8)
    n = 0
    while n < packet.nbytes:
      try:
        m = os.write(self.wfd, pp.data[n:])
      except:
        m = -1
      if m<0:
        self.kill()  # failure fatal, need to shut down yorick
        raise PYorickError("os.write failed, yorick killed")
      n += m
    if self.debug and n:
      print(("P>send: {0} bytes sent".format(n)))

ProcessDefault = PtyProcess

class PipeProcess(PtyProcess):
  """Process using subprocess, binary pipes, and stdin/out/err pipes."""
  pass

########################################################################

# limit names exported by "from pyorick import *"
__all__ = ['Yorick', 'PYorickError', 'ynewaxis', 'ystring0']
