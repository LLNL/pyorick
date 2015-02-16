# pyorick.py
# Copyright (c) 2014, David H. Munro and John E. Field
# All rights reserved.
# This is Open Source software, released under the BSD 2-clause license,
# see http://opensource.org/licenses/BSD-2-Clause for details.

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
  raw_input = input
  import pickle
else:
  import cPickle as pickle

import numpy as np

from numbers import Number
from collections import Sequence, Mapping
from ctypes import (c_byte, c_ubyte, c_short, c_ushort, c_int, c_uint,
                    c_long, c_ulong, c_longlong, c_ulonglong,
                    c_float, c_double, c_longdouble, sizeof)
import os
import shlex
import fcntl
import select

import subprocess
import time

# code executed by a yorick request runs in __main__ module by default
import __main__

########################################################################

class Yorick(object):
  """Interface to a yorick process.

  Attributes:
    c or call -     call-semantics handle
    e or evaluate - eval-semantics handle
    v or value -    value-semantics handle

    Handles are objects whose attributes represent yorick variables.
  """
  def __init__(self, extra='', **kwargs):
    """Start a yorick process.

    Parameters:
      extra (str or list of str):  additional command line arguments
    """
    if isinstance(extra, Process):
      self.bare = YorickBare(extra)
    elif isinstance(extra, YorickBare):
      self.bare = extra
    else:
      self.bare = YorickBare(ProcessDefault(extra, **kwargs))
    self._call = self._eval = self._value = None

  def __repr__(self):
    return "<connection to {0}>".format(repr(self.bare)[1:-1])

  def __nonzero__(self):
    return bool(self.bare)

  def kill(self):
    """Kill yorick process."""
    self.bare.proc.kill()
  def debug(self, on):
    """Set or unset debug mode for yorick process."""
    self.bare.proc.debug(on)

  def handles(self, which=3):
    """Return handles whose attributes are yorick variables.

    Parameters:
      which (int, default is 3):
        - 1 returns call-semantics handle
        - 2 returns eval-semantics handle
        - 4 returns value-semantics handle
        - add to return tuple with up to three handles
    """
    h = [['call', 'evaluate', 'value'][i//2] for i in [1, 2, 4] if (which&i)]
    if len(h) == 1:
      return getattr(self, h[0])
    else:
      return tuple([getattr(self,h[i]) for i in range(len(h))])

  # first reference creates handle, subsequent references simply use it
  @property
  def call(self):
    if not self._call:
      self._call = YorickHandle(0, self.bare)
    return self._call
  @property
  def evaluate(self):
    if not self._eval:
      self._eval = YorickHandle(1, self.bare)
    return self._eval
  @property
  def value(self):
    if not self._value:
      self._value = YorickHandle(2, self.bare)
    return self._value
  # single character abbreviations for interactive use
  c = call
  e = evaluate
  v = value

  @property
  def namespace(self):
    return self.bare._namespace
  @namespace.setter
  def namespace(self, value):
    if not isinstance(value, Mapping):
      value = value.__dict__
    self.bare._namespace = value

  def __call__(self, command=None, *args, **kwargs):  # pipe(command)
    """Execute a yorick command."""
    return self.call(command, *args, **kwargs)

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

def yencodable(value):
  """Return True if object can be encoded for transfer to yorick."""
  return codec.encode_data(value, True)

def ypickling(both=None, encode=None, decode=None):
  """Set whether unencodable objects are pickled for transfer to yorick.

  Arguments:
  both    True or False to turn pickling on or off in both directions
  encode  turn pickling on or off in encoding direction only
  decode  turn pickling on or off in decoding direction only

  Pickling is turned on in both directions by default.

  PYorick uses protocol 2 pickling, prepends a string beginning with
  'thisispickled_', then transmits the byte string as a 1D array of char.
  """
  if both is not None:
    codec.enpickle = codec.depickle = bool(both)
  if encode is not None:
    codec.enpickle = bool(encode)
  if decode is not None:
    codec.depickle = bool(decode)

########################################################################

server_namespace = __main__.__dict__  # for python code invoked by yorick

class YorickBare(object):
  """Avoids circular references among Yorick, YorickHandle, and YorickVar."""
  def __init__(self, proc):
    self.proc = proc
    self._namespace = server_namespace  # default namespace (__main__)

  def __del__(self):
    self.proc.kill()

  def __repr__(self):
    return "<bare connection to {0}>".format(repr(self.proc)[1:-1])

  def __nonzero__(self):
    return bool(self.proc)

  def _reqrep(self, msgid, *args, **kwargs):  # convenience for YorickHandle
    hold = args[0]
    if hold and isinstance(hold, basestring) and hold[0]=='\05':
      hold = True
    else:
      hold = False
    reply = Message()
    self.proc.reqrep(Message(msgid, *args, **kwargs), reply)
    while reply.packets and reply.packets[0][0] >= ID_EVAL:
      if self.proc._debug:
        print("P>_reqrep: begin processing request (non-passive reply)")
      reply = reply.getreply(self.proc._debug, self._namespace)
      if not reply:
        raise PYorickError("yorick sent unknown active reply to request")
      if self.proc._debug:
        print("P>_reqrep: sending reply to request")
      self.proc.sendmsg(reply)
      reply = Message()  # get the next reply from yorick
      self.proc.recvmsg(reply)
    if self.proc._debug:
      print("P>_reqrep: got passive reply to original request")
    reply = reply.decode()
    if not isinstance(reply, tuple):
      if not hold:
        return reply
      if (isinstance(reply, np.ndarray) and reply.dtype==np.dtype(c_long)
          and reply.shape==()):
        return YorickHold(self, reply)
    if reply == (ID_EOL, (2,), {}):
      if msgid == ID_GETVAR:
        return YorickVarDerived(self, 0, args[0])
      elif msgid in [ID_EVAL, ID_FUNCALL, ID_GETSLICE]:
        return YorickHold(self, self._reqrep(ID_GETVAR, ''))
    raise PYorickError("yorick sent error reply to request")

  def _server(self, namespace=None):
    print("--> yorick prompt (type py to return to python):")
    self.proc.interact(YorickServer(namespace))
    print("--> python prompt:")

class Key2Attr(object):
  """Base class to convert attributes to keys, s/getattr --> s/getitem."""
  def __getattr__(self, name):                   # pipe.name
    """Convert get attribute to get item."""
    # inspect module causes serious problems by probing for names
    # ipython also probes for getdoc attribute
    if (len(name)>3 and name[0:2]=='__' and name[-2:]=='__') or name=='getdoc':
      raise AttributeError("Key2Attr instance has no attribute '"+name+"'")
    if name not in self.__dict__:  # unnecessary?  never false?
      return self[name]
    else:
      return self.__dict__[name]
  def __setattr__(self, name, value):
    """Convert set attribute to set item."""
    if name not in self.__dict__:
      self[name] = value
    else:
      object.__setattr__(self, name, value)

# this is intended to wrap yorick file handles or oxy objects
class Key2AttrWrapper(Key2Attr):
  """Wrap an arbitrary object so its attributes become its mapping keys."""
  def __init__(self, obj):
    self.__dict__['_key2attr__'] = obj
  # eventually may want to retain more extensive set of obj methods
  def __repr__(self):
    s = "<Key2Attr wrapper for {0}>"
    return s.format(repr(self.__dict__['_key2attr__']))
  def __nonzero__(self):
    return bool(self.__dict__['_key2attr__'])
  def __getitem__(self, key=None):
    return self.__dict__['_key2attr__'][key]
  def __setitem__(self, key, value):
    self.__dict__['_key2attr__'][key] = value
  def __call__(self, command=None, *args, **kwargs):
    return self.__dict__['_key2attr__'](*args, **kwargs)

class YorickHandle(Key2Attr):
  """Object whose attributes are yorick variables.

  Do not attempt to probe with hasattribute or other introspection!
  """

  # Every attribute in this class should represent a yorick variable.
  # The __XXX__ system names cannot be retrieved, nor can the
  # practically unavoidable _reftype__ and _yorick__ attributes.
  # However, no other attributes are permitted.

  # must avoid __setattr__, __getattr__ by explicit calls through __dict__
  def __init__(self, reftype, bare):
    self.__dict__['_reftype__'] = reftype
    self.__dict__['_yorick__'] = bare

  def __repr__(self):
    bare = self.__dict__['_yorick__']
    typ = ['call', 'evaluate', 'value'][self.__dict__['_reftype__']]
    s = "<yorick {0}-semantics handle to {1}>"
    return s.format(typ, repr(bare.proc)[1:-1])

  def __nonzero__(self):
    return bool(self.__dict__['_yorick__'])

  def __getitem__(self, key=None):
    """Return parent connection, avoiding use of an attribute."""
    bare = self.__dict__['_yorick__']
    if not key:
      return Yorick(bare)
    typ = self.__dict__['_reftype__']
    if typ == 2:
      return bare._reqrep(ID_GETVAR, key)
    return YorickVarDerived(bare, typ, key)

  def __setitem__(self, key, value):
    """Implement handle.name = value."""
    bare = self.__dict__['_yorick__']
    if key not in self.__dict__:
      bare._reqrep(ID_SETVAR, key, value)
    else:
      object.__setattr__(self, key, value)

  def __call__(self, command=None, *args, **kwargs):
    """Implement handle(command) or handle(format, args, key=kwds)."""
    if args or kwargs:
      command = command.format(*args, **kwargs)
    bare = self.__dict__['_yorick__']
    typ = self.__dict__['_reftype__']
    if command:
      if command[0] == '=':    # leading = forces eval semantics
        command = command[1:]
        typ = 1
      elif command[0] == '@':  # hold return value
        command = '\05' + command[1:]
        typ = 1
    if command is None:
      bare._server(bare._namespace)
    elif typ:
      rslt = bare._reqrep(ID_EVAL, command)
      if command[0] == '\05':
        return rslt
      return rslt
    else:
      return bare._reqrep(ID_EXEC, command)

class YorickVar(object):
  """Reference to a yorick variable."""
  def __init__(self, bare, reftype, name):
    if not isinstance(name, basestring):
      raise PYorickError("illegal yorick variable name")
    self.bare = bare
    self.reftype = bool(reftype)
    self.name = name
    self._info = None

  def __repr__(self):
    bare = self.bare
    typ = ['call', 'evaluate'][self.reftype]
    s = "<yorick variable {0} ({1}) in {2}>"
    return s.format(self.name, typ, repr(bare.proc)[1:-1])

  def __nonzero__(self):
    return bool(self.bare)

  def __call__(self, *args, **kwargs):
    """Implement handle.name(args, kwargs)."""
    if self.reftype:
      return self.bare._reqrep(ID_FUNCALL, self.name, *args, **kwargs)
    else:
      self.bare._reqrep(ID_SUBCALL, self.name, *args, **kwargs)

  def __getitem__(self, key): 
    """Implement handle.name[key]."""
    key = self._fix_indexing(key)
    return self.bare._reqrep(ID_GETSLICE, self.name, *key)

  def __setitem__(self, key, value):
    """Implement handle.name[key] = value."""
    key = self._fix_indexing(key) + (value,)
    return self.bare._reqrep(ID_SETSLICE, self.name, *key)

  def _fix_indexing(self, key, force=False):
    if not isinstance(key, tuple):
      key = (key,)  # only single index provided
    if self.reftype and not force:
      return key
    # convert from python index semantics to yorick index semantics
    ndxs = []
    for ndx in key[::-1]:  # reverse index order
      if isinstance(ndx, slice):
        if ndx:
          i, j, s = ndx.start, ndx.stop, ndx.step
          if i is None:
            i = 0
          i += 1        # python.x[i:etc] --> yorick.x(i+1:etc)
          if (s is not None) and s < 0:
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

  @property
  def info(self):
    """Implement handle.name.info."""
    name = self.name
    if name[0] == '\05':
      name = name[1:]
    if self._info is None:
      self._info = tuple(self.bare._reqrep(ID_GETSHAPE, name))
    return self._info

  @property
  def is_string(self): return self.info[0] == ID_STRING
  @property
  def is_number(self): return self.info[0] in range(0,15)
  @property
  def is_bytes(self): return self.info[0] == 8
  @property
  def is_integer(self): return self.info[0] in [0,1,2,3,4,8,9,10,11,12]
  @property
  def is_real(self): return self.info[0] in [5, 6, 7]
  @property
  def is_complex(self): return self.info[0] in [13, 14, 15]
  @property
  def is_func(self): return self.info[0] == -1
  @property
  def is_list(self): return self.info[0] == -2
  @property
  def is_dict(self): return self.info[0] == -3
  @property
  def is_range(self): return self.info[0] == -4
  @property
  def is_nil(self): return self.info[0] == -5
  @property
  def is_obj(self): return self.info[0] == -8  # oxy obj not list or dict
  @property
  def shape(self):
    if self.info[0] >= 0:
      return self._info[-1:1:-1]
    else:
      return None
  @property
  def is_file(self):
    if self.info[0] == -6:
      return 1
    elif self._info[0] == -7:
      return 2
    else:
      return 0

  @property
  def value(self):
    """Implement handle.name.value."""
    name = self.name
    if name[0] == '\05':
      name = name[1:]
    return self.bare._reqrep(ID_GETVAR, name)
  # single character alias for interactive use
  v = value

  @property
  def call(self):
    """Implement handle.name.call."""
    if self.reftype:
      name = self.name
      if name[0] == '\05':
        name = name[1:]
      if name[0]>='9' or name[0]<='0':
        return YorickVarDerived(self.bare, False, name)
      else:
        return YorickVarCall(self, name, False)
    return self
  # single character alias for interactive use
  c = call

  @property
  def evaluate(self):
    """Implement handle.name.evaluate."""
    if not self.reftype:
      if self.name[0]>='9' or self.name[0]<='0':
        return YorickVarDerived(self.bare, True, self.name)
      else:
        return YorickVarCall(self, self.name, True)
    return self
  # single character alias for interactive use
  e = evaluate

  @property
  def hold(self):
    """Implement handle.name.hold."""
    if self.name[0] != '\05':
      if self.name[0]>='9' or self.name[0]<='0':
        return YorickVarDerived(self.bare, True, '\05'+self.name)
      else:
        return YorickVarCall(self, '\05'+self.name, True)
    return self

# Hook for packages (like a lazy evaluator) to customize YorickVar;
# YorickVarDerived is the object a YorickHandle uses.
# The YorickVarDerived class must be a derived class of YorickVar.
# The derived class must call YorickVar.__init__ in its constructor.
YorickVarDerived = YorickVar

class YorickHold(YorickVar):
  """Reference to a yorick anonymous result, holding use of result."""
  def __init__(self, bare, n):
    if isinstance(n, np.ndarray):
      n = int(n)
    if (not isinstance(n, Number)) or n<=3:
      raise PYorickError("illegal yorick reference number")
    self.bare = bare
    self.reftype = True
    self.name = str(n)
    self._info = None

  def __del__(self):  # free use of value in yorick
    if (self.bare):
      name = self.name
      if name[0] == '\05':
        name = name[1:]
      self.bare._reqrep(ID_EXEC, "_pyorick_refs,1,"+name)

class YorickVarCall(object):
  """Reference to anonymous yorick variable callable only."""
  def __init__(self, var, name, reftype):
    self.var = var    # holds use of YorickHold object var
    self.name = name
    self.reftype = reftype

  def __call__(self, *args, **kwargs):
    """Implement handle.name(args, kwargs)."""
    if self.reftype:
      return self.var.bare._reqrep(ID_FUNCALL, self.name, *args, **kwargs)
    else:
      self.var.bare._reqrep(ID_SUBCALL, self.name, *args, **kwargs)

  def __getitem__(self, key): 
    """Implement handle.name[key]."""
    if not self.reftype:
      key = self.var._fix_indexing(key, True)
    return self.var.bare._reqrep(ID_GETSLICE, self.name, *key)

  @property
  def call(self):
    """Implement handle.name.call."""
    if self.reftype:
      name = self.name
      if name[0] == '\05':
        name = name[1:]
      return YorickVarCall(self.var, name, False)
    return self
  # single character alias for interactive use
  c = call

  @property
  def hold(self):
    """Implement handle.name.hold."""
    if self.name[0] != '\05':
      return YorickVarCall(self.var, '\05'+self.name, True)
    return self

class YorickServer(object):
  """Server to accept requests from and generate replies to yorick."""
  def __init__(self, namespace, debug=False):
    self.namespace = namespace
    self.debug = debug

  def start(self, command=None):
    """Start server, optionally returning exec msg to be sent to yorick."""
    self.started = False
    self.request = Message()  # provide container for first request
    if command:
      # Unless this Process has some out-of-band way to enter terminal mode,
      # yorick will be expecting a request.  Execing this yorick command
      # must cause yorick to begin emitting requests rather than replies.
      return Message(ID_EXEC, command)

  def reply(self, debug=False):
    """Return message to be sent in reply to self.request."""
    if debug:
      print("P>server reply: decoding")
    rep = self.request.getreply(debug, self.namespace)
    self.request = Message()  # empty container for next request
    if rep is False:
      if debug:
        print("P>server reply: got signal to exit terminal mode")
      return None   # signal to exit terminal mode
    if isinstance(rep, Message):
      self.started = True
      return rep
    if not self.started:   # assume yorick never entered terminal mode
      if debug:
        print("P>server reply: yorick never entered terminal mode")
      self.request = None
      return None
    return Message(ID_EOL, 1)  # yorick needs error to continue

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
     msg = Message()                for an empty message, to call reader
     packetlist = msg.reader()      return generator to receive from process
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

  The reader method returns a generator which can be used to build a
  message starting from an empty message:
    packetlist = msg.reader()
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
  def __init__(self, *args, **kwargs):
    self.packets = []
    if not args:
      return None
    msgid = args[0]
    if msgid is None:
      msgid, args, kwargs = codec.encode_data(*args[1:])
    else:
      args = args[1:]
    codec.idtable[msgid].encoder(self, msgid, *args, **kwargs)

  def reader(self):
    return codec.reader(self)

  def decode(self):
    if not self.packets:
      raise PYorickError("cannot decode empty message")
    self.pos = 1  # pos=0 already processed here
    return codec.idtable[self.packets[0][0]].decoder(self)

  def getreply(self, debug=False, namespace=None):
    """Return message to be sent in reply to this request."""
    if debug:
      print("P>getreply: decoding")
    if namespace is None:
      namespace = server_namespace
    elif not isinstance(namespace, Mapping):
      namespace = namespace.__dict__
    # decode presumed request message
    # returns:
    # Message   reply, including EOL for syntax or
    # None      if not a recognized request
    # False     if signal to exit terminal mode
    req = self.decode()
    code = None
    if isinstance(req, tuple):
      if debug:
        print("P>getreply: req[0]="+str(req[0]))
      if req[0] in [ID_EXEC, ID_EVAL, ID_GETVAR, ID_SETVAR,
                    ID_FUNCALL, ID_SUBCALL, ID_GETSLICE, ID_SETSLICE]:
        text = req[1][0].replace('\0', '\n')
        if req[0] == ID_SETVAR:
          namespace['_pyorick_setvar_rhs_'] = req[1][-1]
          text += '=_pyorick_setvar_rhs_'
          # note: if locals dict specified, must prepend "global varname;"
        try:
          if req[0] in [ID_EXEC, ID_SETVAR]:
            if not text:
              # alternate signal to exit terminal mode (if no start command)
              if debug:
                print("P>getreply: got exit terminal signal")
              return False
            code = compile(text, '<pyorick command>', 'exec')
          else:
            code = compile(text, '<pyorick command>', 'eval')
          if debug:
            print("P>getreply: compiled text="+text)
        except SyntaxError:
          if debug:
            print("P>getreply: syntax error, text="+text)
          return Message(ID_EOL, 1)  # reply with error to yorick
      elif req[0]==ID_EOL and not req[1][0]:
        # this is signal to exit terminal mode (matches start command)
        if debug:
          print("P>getreply: got exit terminal signal")
        return False
    if code:
      try:
        # first, eval the text sent as command or variable name
        obj = eval(code, namespace)
        rslt = None
        if req[0] in [ID_EXEC, ID_EVAL, ID_GETVAR, ID_SETVAR]:
          rslt = obj
          if req[0] == ID_SETVAR:
            del namespace['_pyorick_setvar_rhs_']
        elif req[0] in [ID_FUNCALL, ID_SUBCALL]:
          rslt = obj(*req[1][1:], **req[2])
          if req[0] == ID_SUBCALL:
            rslt = None  # discard any return value
        elif req[0] == ID_GETSLICE:
          rslt = obj[req[1][1:]]
        elif req[0] == ID_SETSLICE:
          obj[req[1][1:]] = req[1][-1]
        return Message(None, rslt)
      except:
        if debug:
          print("P>getreply: execution error")
          raise
        # any exceptions trying to eval or encode reply are yorick's problem
        pass
      return Message(ID_EOL, 1)  # reply with error to yorick
    return None

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

# numeric protocol datatypes are C-types (byte is C char)
id_types = [c_byte, c_short, c_int, c_long, c_longlong,
            c_float, c_double, c_longdouble,
            c_ubyte, c_ushort, c_uint, c_ulong, c_ulonglong,
            np.csingle, np.complex_, None]  # no portable complex long double

# other passive messages (reply prohibited):
ID_STRING, ID_SLICE, ID_NIL, ID_LST, ID_DCT, ID_EOL =\
   16,        17,       18,     19,     20,     21
# ID_STRING: yorick assumes iso_8859_1, need separate id for utf-8?

# active messages (passive reply required):
ID_EVAL, ID_EXEC, ID_GETVAR, ID_SETVAR, ID_FUNCALL, ID_SUBCALL =\
   32,      33,      34,        35,        36,         37
ID_GETSLICE, ID_SETSLICE, ID_GETSHAPE =\
   38,          39,          40

# convenience values
ID_LONG = 3
ID_NUMERIC = [i for i in range(16)]

# Each instance of Clause represents a clause of the message grammar.
# At minimum, the functions to build, encode, and decode that clause must
# be defined.  These definitions are in codec below.
# Clause primarily implements the decorators used to cleanly construct
# codec.
class Clause(object):
  def __init__(self, idtable=None, *idlist):
    self.idlist = idlist  # tuple of message ids if top level clause
    for msgid in idlist:
      idtable[msgid] = self

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

# These were originally members of the codec class, but that breaks in
# python 3.
# See http://stackoverflow.com/questions/13905741/accessing-class-variables-from-a-list-comprehension-in-the-class-definition
typesz = [np.dtype(id_types[i]).itemsize for i in range(15)] + [0]
typesk = ['i']*5 + ['f']*3 + ['u']*5 + ['c']*2 + ['none']
typesk = [typesk[i]+str(typesz[i]) for i in range(16)]  # keys for id_typtab
# lookup table for msgid given typesk (computable from dtype)
id_typtab = [0, 1, 2, 4, 3, 5, 7, 6, 8, 9, 10, 12, 11, 13, 15, 14]
id_typtab = dict([[typesk[id_typtab[i]], id_typtab[i]] for i in range(16)])
del typesz, typesk

# prefix is 'thisispickled_'+md5sum('thisispickled\n')
ypickling_prefix = bytearray(b'thisispickled_8ad5f009982d6a1bcb5d3de476751a79')
ypickling_nprefix = len(ypickling_prefix)

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

  # dict of top level clauses by key=message id
  idtable = {}  # idtable[msgid] --> top level message handler for msgid

  enpickle = depickle = True  # pickling is on by default

  @staticmethod
  def reader(msg):
    if msg.packets:
      raise PYorickError("attempt to read into non-empty message")
    packet = nplongs(0, 0)
    msg.packets.append(packet)
    yield packet
    for packet in codec.idtable[packet[0]].reader(msg):
      yield packet

  narray = Clause(idtable, *ID_NUMERIC)
  @narray.reader()
  def narray(msg):
    msgid, rank = msg.packets[-1]
    shape = np.zeros(rank, dtype=c_long)
    if rank > 0:
      msg.packets.append(shape)
      yield shape
    msg.packets.append(np.zeros(shape[::-1], dtype=id_types[msgid]))
    yield msg.packets[-1]
  @narray.encoder()
  def narray(msg, msgid, shape, value):
    rank = len(shape)
    msg.packets.append(nplongs(msgid, rank))
    if rank:
      msg.packets.append(nplongs(*shape[::-1]))
    msg.packets.append(value)
  @narray.decoder()
  def narray(msg):
    pos = msg.pos
    ischar = (msg.packets[pos-1][0] in [0,8])
    rank = msg.packets[pos-1][1]
    if rank:
      msg.pos = pos = pos+1
    msg.pos += 1
    if ischar and rank==1 and codec.depickle:
      return codec.pickleloads(msg.packets[pos])
    return msg.packets[pos]

  sarray = Clause(idtable, ID_STRING)
  @sarray.reader()
  def sarray(msg):
    msgid, rank = msg.packets[-1]
    shape = np.zeros(rank, dtype=c_long)
    if rank > 0:
      msg.packets.append(shape)
      yield shape
    lens = np.zeros(shape[::-1], dtype=c_long)
    msg.packets.append(lens)
    yield lens
    lens = lens.sum()
    if lens:
      msg.packets.append(np.zeros(lens, dtype=np.uint8))
      yield msg.packets[-1]
  @sarray.encoder()
  def sarray(msg, msgid, shape, lens, value):
    codec.narray.encoder(msg, ID_LONG, shape, lens)
    if len(shape):
      msg.packets[-3][0] = ID_STRING
    else:
      msg.packets[-2][0] = ID_STRING
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
    msg.packets.append(nplongs(0, 0, 0))
    yield msg.packets[-1]
  @slice.encoder()
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
        sinc = (-1, 1)[bool(flags) or smin<=smax]
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
    return
    yield  # this is a generator that raises StopIteration on first call
  @nil.encoder()
  def nil(msg, msgid):
    msg.packets.append(nplongs(msgid, 0))
  @nil.decoder()
  def nil(msg):
    return None

  lst = Clause(idtable, ID_LST)
  @lst.reader()
  def lst(msg):
    for packet in codec.qmlist.reader(msg, 0):
      yield packet
  @lst.encoder()
  def lst(msg, msgid, value):
    msg.packets.append(nplongs(msgid, 0))
    codec.qmlist.encoder(msg, 0, value, {})
  @lst.decoder()
  def lst(msg):
    value = []
    codec.qmlist.decoder(msg, 0, value, {})
    return value

  dct = Clause(idtable, ID_DCT)
  @dct.reader()
  def dct(msg):
    for packet in codec.qmlist.reader(msg, 1):
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
    return
    yield  # this is a generator that raises StopIteration on first call
  @eol.encoder()
  def eol(msg, msgid, flag=0):
    msg.packets.append(nplongs(ID_EOL, flag))
  @eol.decoder()
  def eol(msg):
    return (ID_EOL, (int(msg.packets[msg.pos-1][1]),), {})

  evaluate = Clause(idtable, ID_EVAL, ID_EXEC)
  @evaluate.reader()
  def evaluate(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
  @evaluate.encoder()
  def evaluate(msg, msgid, text):
    text = np.fromiter(bytearray(text.encode('iso_8859_1')), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(text)))
    if len(text):
      msg.packets.append(text)
  @evaluate.decoder()
  def evaluate(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      text = codec.array2string(msg.packets[pos])
    else:
      text = ''
    return (msg.packets[pos-1][0], (text,), {})

  # same as evaluate, but may want to add name sanity checks someday
  getvar = Clause(idtable, ID_GETVAR, ID_GETSHAPE)
  @getvar.reader()
  def getvar(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
  @getvar.encoder()
  def getvar(msg, msgid, name):
    name = np.fromiter(bytearray(name.encode('iso_8859_1')), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(name)))
    if len(name):
      msg.packets.append(name)
  @getvar.decoder()
  def getvar(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = codec.array2string(msg.packets[pos])
    else:
      name = ''
    return (msg.packets[pos-1][0], (name,), {})

  setvar = Clause(idtable, ID_SETVAR)
  @setvar.reader()
  def setvar(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
    packet = nplongs(0, 0)
    msg.packets.append(packet)
    yield packet
    msgid = msg.packets[-1][0]
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setvar value msgid in reader")
    for packet in codec.idtable[msgid].reader(msg):
      yield packet
  @setvar.encoder()
  def setvar(msg, msgid, name, value):
    name = np.fromiter(bytearray(name.encode('iso_8859_1')), dtype=np.uint8)
    msg.packets.append(nplongs(msgid, len(name)))
    if len(name):
      msg.packets.append(name)
    msgid, args, kwargs = codec.encode_data(value)
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setvar value msgid in encoder")
    codec.idtable[msgid].encoder(msg, msgid, *args, **kwargs)
  @setvar.decoder()
  def setvar(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      name = codec.array2string(msg.packets[pos])
      pos += 1
    else:
      name = ''
    msg.pos = pos + 1
    args = (name, codec.idtable[msg.packets[pos][0]].decoder(msg))
    return (ID_SETVAR, args, {})

  funcall = Clause(idtable, ID_FUNCALL, ID_SUBCALL)
  @funcall.reader()
  def funcall(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
    for packet in codec.qmlist.reader(msg, 2):
      yield packet
  @funcall.encoder()
  def funcall(msg, msgid, name, *args, **kwargs):
    codec.getvar.encoder(msg, msgid, name)
    codec.qmlist.encoder(msg, 2, args, kwargs)
  @funcall.decoder()
  def funcall(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = codec.array2string(msg.packets[pos])
    else:
      name = ''
    args = []
    kwargs = {}
    codec.qmlist.decoder(msg, 2, args, kwargs)
    return (msg.packets[pos-1][0], (name,)+tuple(args), kwargs)

  getslice = Clause(idtable, ID_GETSLICE)
  @getslice.reader()
  def getslice(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
    for packet in codec.qmlist.reader(msg, 0):
      yield packet
  @getslice.encoder()
  def getslice(msg, msgid, name, *args):
    codec.getvar.encoder(msg, msgid, name)
    codec.qmlist.encoder(msg, 0, args, {})
  @getslice.decoder()
  def getslice(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = codec.array2string(msg.packets[pos])
    else:
      name = ''
    args = []
    codec.qmlist.decoder(msg, 0, args, {})
    return (msg.packets[pos-1][0], (name,)+tuple(args), {})

  setslice = Clause(idtable, ID_SETSLICE)
  @setslice.reader()
  def setslice(msg):
    packet = np.zeros(msg.packets[-1][1], dtype=np.uint8)
    if packet.nbytes:
      msg.packets.append(packet)
      yield packet
    for packet in codec.qmlist.reader(msg, 0):
      yield packet
    packet = nplongs(0, 0)
    msg.packets.append(packet)
    yield packet
    msgid = msg.packets[-1][0]
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setslice value msgid in reader")
    for packet in codec.idtable[msgid].reader(msg):
      yield packet
  @setslice.encoder()
  def setslice(msg, msgid, name, *args):
    codec.getvar.encoder(msg, msgid, name)
    if len(args) < 1:
      raise PYorickError("missing setvar value msgid in encoder")
    codec.qmlist.encoder(msg, 0, args[0:-1], {})
    msgid, args, kwargs = codec.encode_data(args[-1])
    if msgid not in codec.qmlist.allowed[0]:
      raise PYorickError("illegal setvar value msgid in encoder")
    codec.idtable[msgid].encoder(msg, msgid, *args, **kwargs)
  @setslice.decoder()
  def setslice(msg):
    pos = msg.pos
    if msg.packets[pos-1][1]:
      msg.pos += 1
      name = codec.array2string(msg.packets[pos])
    else:
      name = ''
    args = []
    codec.qmlist.decoder(msg, 0, args, {})
    pos = msg.pos
    msg.pos += 1
    value = codec.idtable[msg.packets[pos][0]].decoder(msg)
    return (ID_SETSLICE, (name,)+tuple(args)+(value,), {})

  # eol terminated lists, qmlist means "quoted message list"
  qmlist = Clause()
  @qmlist.reader()
  def qmlist(msg, kind):
    allowed = codec.qmlist.allowed[kind]
    while True:
      packet = nplongs(0, 0)
      msg.packets.append(packet)
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
      msgid, iargs, ikwargs = codec.encode_data(arg)
      codec.idtable[msgid].encoder(msg, msgid, *iargs, **ikwargs)
    for key in kwargs:
      codec.setvar.encoder(msg, ID_SETVAR, key, kwargs[key])
    codec.eol.encoder(msg, ID_EOL)
  @qmlist.decoder()
  def qmlist(msg, kind, args, kwargs):
    allowed = codec.qmlist.allowed[kind]
    while True:
      pos = msg.pos
      msg.pos += 1
      packet = msg.packets[pos]
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
  qmlist.allowed = [i for i in range(ID_EOL)] + [ID_GETVAR]
  qmlist.allowed = [qmlist.allowed,              # llist
                    [ID_SETVAR],                 # dlist
                    qmlist.allowed+[ID_SETVAR]]  # alist

  @staticmethod
  def array2string(a):
    s = a.tostring().decode('iso_8859_1')
    if s.endswith('\x00'):
      s = s[0:-1]
    return s

  @staticmethod
  def decode_sarray(lens, value):
    shape = lens.shape
    if shape:
      n = np.prod(shape)
      shape = shape[::-1]
    else:
      n = 1
    # split value into 1D list of strings v
    lens = np.ravel(lens)
    i1 = np.cumsum(lens)
    i0 = i1 - lens
    i1 -= 1
    v = []
    for i in xrange(n):
      if lens[i]:
        v.append(codec.array2string(value[i0[i]:i1[i]]))
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
    val = []
    lens = []
    for v in value:
      if '\0' in v:
        v = v[0:v.index('\0')+1]  # truncate after first NULL
      elif not isinstance(v, YString0):
        v += '\0'
      v = v.encode('iso_8859_1')
      lens.append(len(v))
      val.append(v)
    lens = np.array(lens, dtype=c_long).reshape(shape)
    val = np.array(bytearray(b''.join(val)), dtype=np.uint8)
    return (ID_STRING, (shape, lens, val), {})

  # decode work done, but encode still needs to recogize python data
  @staticmethod
  def encode_data(value, dryrun=False):   # return (msgid, args, kwargs)
    msgid = -1  # unknown initially

    if isinstance(value, Number):
      if dryrun: return True
      value = np.array(value)

    elif isinstance(value, bytearray):
      if dryrun: return True
      value = np.frombuffer(value, dtype=np.uint8)

    elif isinstance(value, basestring):
      if dryrun: return True
      return codec.encode_sarray((), value)

    elif isinstance(value, Sequence):   # check for array-like nested sequence
      shape, typ = codec.nested_test(value)
      if typ == basestring:
        if dryrun: return True
        return codec.encode_sarray(shape, value)
      elif typ != Number:
        if dryrun:
          for v in value:
            if not codec.encode_data(v, True):
              return False
          return True
        # may raise errors later, but not array-like
        return (ID_LST, (value,), {})
      if dryrun: return True
      # np.array converts nested list of numbers to ndarray
      value = np.array(value)

    # numeric arrays are the "money message"
    if isinstance(value, np.ndarray):
      shape = value.shape
      k = str(value.dtype.kind)
      if k in 'SUa':
        if dryrun: return True
        return codec.encode_sarray(shape, value.tolist())
      if k not in 'biufc':
        if dryrun: return False
        if codec.enpickle:
          return codec.pickledumps(value)
        raise PYorickError("cannot encode unsupported array item type")
      if k == 'b':
        k = 'u'
      k += str(value.dtype.itemsize)
      if k not in id_typtab:
        if dryrun: return False
        if codec.enpickle:
          return codec.pickledumps(value)
        raise PYorickError("cannot encode unsupported array numeric dtype")
      if dryrun: return True
      msgid = id_typtab[k]
      if not value.flags['CARRAY']:
        value = np.copy(value, 'C')
      return (msgid, (shape, value), {})

    # index range, including (newaxis, Ellipsis) <--> (-, ..)
    elif isinstance(value, NewAxis):  # np.newaxis is unfortunately None
      if dryrun: return True
      return (ID_SLICE, (None, 7), {})
    elif value is Ellipsis:
      if dryrun: return True
      return (ID_SLICE, (None, 11), {})
    elif isinstance(value, slice):
      if dryrun: return True
      return (ID_SLICE, (value,), {})

    elif value is None:
      if dryrun: return True
      return (ID_NIL, (), {})

    # dict objects only allowed if all keys are strings
    elif isinstance(value, Mapping):
      if not all(isinstance(key, basestring) for key in value):
        if dryrun: return False
        if codec.enpickle:
          return codec.pickledumps(value)
        raise PYorickError("cannot encode dict with non-string key")
      if dryrun:
        for key in value:
          if not codec.encode_data(value[key], True):
            return False
        return True
      return (ID_DCT, (value,), {})

    elif isinstance(value, YorickVar):
      if dryrun: return True
      return (ID_GETVAR, (value.name,), {})

    else:
      if dryrun: return False
      if codec.enpickle:
        return codec.pickledumps(value)
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

  @staticmethod
  def pickledumps(obj):
    v = np.frombuffer(ypickling_prefix + bytearray(pickle.dumps(obj, 2)),
                      dtype=np.uint8)
    return (8, (v.shape, v), {})

  @staticmethod
  def pickleloads(chars):
    if ypickling_prefix == bytearray(chars[0:ypickling_nprefix]):
      return pickle.loads(chars[ypickling_nprefix:].tostring())
    return chars

def nplongs(*args):
  return np.array(args, dtype=c_long)

########################################################################

def find_package_data(name):
  """See https://wiki.python.org/moin/Distutils/Tutorial"""
  # Idea: 
  # The yorick startup script pyorick.i0 is a sibling of pyorick.py,
  # so that pyorick.i0 is found relative to __file__.
  # The setup.py packaging script can install pyorick.i0 in this way
  # by declaring it in package_data.  However, this strategy may
  # fail for python platforms where packages are placed in zip files
  # or other non-filesystem places, see PEP 302 and pkgutil.get_data().
  # The name pyorick.i0 (with a trailing 0) is necessary to prevent
  # distutils from recognizing the ".i" extension and treating the
  # file specially.  Note that there may be portability issues relating
  # to the newline character.
  # This convention makes it straightforward to install pyorick "by hand"
  # when distutils cannot be used.
  # When pyorick.i0 is not found, check for it in the yorick user directory
  # ~/.yorick/ (or similar).  If not found there, but pkgutil.get_data finds
  # it, unpack pyorick.i0 to ~/.yorick/ (or an existing yorick customization
  # directory).
  path = None
  try:
    p = __file__
    if os.path.islink(p):
      p = os.path.realpath(p)
    p = os.path.join(os.path.dirname(os.path.abspath(p)), name)
    if os.path.isfile(p):
      path = p
    else:
      # before giving up, try ~/yorick directories
      home = os.path.expanduser('~')
      d = yuser = '.yorick'  # first choice is ~/.yorick
      for d in [yuser, 'yorick', 'Library/Yorick', 'Application Data/Yorick',
                'Yorick']:  # possibilities, in order, checked in yorick/std0.c
        p = os.path.join(home, d)
        if os.path.isdir(p):
          yuser = p
          break
      p = os.path.join(yuser, name)
      if not os.path.isfile(p):
        path = p
      else:
        # last ditch effort, needed if pyorick loaded from a zip file
        import pkgutil
        d = pkgutil.get_data('pyorick', 'pyorick.i0')
        if d:
          d = d.decode('utf-8').splitlines() # removes universal newlines
          if not os.path.isdir(yuser):
            os.mkdir(yuser)
          with open(p, 'w') as f:
            for line in d:
              f.write("{0}\n".format(line))
          path = p
  except:
    pass
  if path is None:
    raise PYorickError('unable to find '+name)
  return os.path.normcase(path)

ypathd = "yorick"   # default yorick command
ipathd = find_package_data("pyorick.i0")  # default pyorick.i0 include file

class Process(object):
  def kill(self, dead=False):
    raise NotImplementedError("This process does not implement kill.")
  def reqrep(self, request, reply):
    raise NotImplementedError("This process does not implement reqrep.")
  def interact(self, server):
    raise NotImplementedError("This process does not implement interact.")
  def debug(self, on):
    raise NotImplementedError("This process does not implement debug.")

class PipeProcess(Process):
  """Process using subprocess, binary pipes, and stdin/out/err pipes."""
  def __init__(self, extra, ypath=None, ipath=None):
    if ypath is None:
      ypath = ypathd
    if ipath is None:
      ipath = ipathd
    self._debug = False
    argv = [ypath, '-q', '-i', ipath]
    # complete argv will be:   argv rfd wfd extra
    ptoy = self.inheritable_pipe(0)
    ytop = self.inheritable_pipe(1)
    argv.extend([str(ptoy[0]), str(ytop[1])])
    if extra:
      argv.extend(shlex.split(extra))
    self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 close_fds=False)
    # also consider:
    # universal_newlines=True
    # preexec_fn=function(closure?) of no arguments to close ptoy[1], ytop[0]
    #  (unix only), see functools.partial
    # creationflags=CREATE_NEW_PROCESS_GROUP to be able to send CTRL_C_EVENT
    #  (windows only)
    os.close(ptoy[0])
    os.close(ytop[1])
    self.rfd = ytop[0]
    self.wfd = ptoy[1]
    self.pid = self.proc.pid
    self.pfdw = self.proc.stdin.fileno()
    self.pfd = self.proc.stdout.fileno()
    self.killing = False
    # put yorick into interactive mode (no batch mode support)
    reply = Message()
    self.reqrep(Message(ID_EXEC, "pyorick, 1;"), reply, True)

  def __del__(self):
    self.kill()

  def __nonzero__(self):
    return self.pid is not None

  def kill(self, dead=False):
    if self.proc is not None and not self.killing:
      self.killing = True
      try:
        if not dead:
          self.send0("\nquit;")
          time.sleep(0.001)
          self.echo_pty()
        self.proc.stdin.close()  # EOF on stdin also causes yorick to quit
        i = 0
        while self.proc.poll() is None:
          time.sleep(0.001)
          i += 1
          if i > 4:
            self.proc.kill()
            break
      finally:
        try:
          os.close(self.rfd)
          os.close(self.wfd)
        finally:
          self.kill(True)
    self.proc = None
    self.pid = self.pfdw = self.pfd = self.rfd = self.wfd = None
    self._debug = False

  def debug(self, on=None):
    if on is None:
      on = not self._debug
    if on != self._debug:
      # turn on/off pydebug flag in yorick
      reply = Message()
      self.reqrep(Message(ID_SETVAR, "pydebug", int(on)), reply)
      self._debug = on

  def sendmsg(self, request):
    try:  # send request
      for packet in request.packets:
        self.send(packet)
    except:
      self.kill()
      raise PYorickError("failed to send complete message, yorick killed")

  def recvmsg(self, reply):
    prompt = None
    try:  # receive reply
      for packet in reply.reader():
        while True:  # do not block on rfd when pfd pending
          p = select.select([self.pfd, self.rfd], [], [self.pfd, self.rfd])
          if self.rfd in p[0]:
            break
          prompt = self.echo_pty()
          if prompt == 'PYORICK-QUIT> ':
            return prompt
        self.recv(packet)
    except:
      self.kill()
      raise PYorickError("failed to receive complete message, yorick killed")
    if prompt == 'PYORICK-QUIT> ':
      return  # yorick has quit
    if self._debug:
      print("P>reqrep: reply="+str(reply.packets[0]))
    if reply.packets[0][0]==ID_EOL and reply.packets[0][1]==-1:
      self.kill(True)
      reply.packets[0][0] = ID_NIL
    elif (not prompt) and reply.packets[0][0]<ID_EVAL:
      # not finished until yorick comes back to its prompt
      self.wait_for_prompt()

  def reqrep(self, request, reply, supress=False):
    self.echo_pty()  # flush any pending output
    if self.pid is None:
      raise PYorickError("no yorick process running")
    if not supress:
      self.send0("pyorick;")  # tell yorick to read pipe for request
    if self._debug:
      print("P>reqrep: request="+str(request.packets[0]))
    self.sendmsg(request)
    if self._debug:
      print("P>reqrep: blocking for reply...")
    self.recvmsg(reply)

  def interact(self, server):
    if self.pid is None:
      raise PYorickError("no yorick process running")
    self.echo_pty()  # flush out any pending output
    server.start()
    if self._debug:
      print("P>interact: telling yorick to enter terminal mode")
    self.send0("pyorick, -1;")  # tell yorick to enter terminal mode
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
          for packet in server.request.reader():
            self.recv(packet)
          rep = server.reply(self._debug)
          if self._debug:
            print("P>interact: reply ready to send? "+str(bool(rep)))
          if rep:
            for packet in rep.packets:
              self.send(packet)  # yorick is blocked waiting for this
          else:
            break
        elif self.pfd in p[0]:
          # only get here when no more requests on rfd
          prompt = self.echo_pty()
          if prompt:  # pass along prompt and wait for user to respond
            if prompt == 'PYORICK-QUIT> ':
              return
            self.send0(raw_input(prompt))
      except KeyboardInterrupt:
        self.send0('\x03', True)  # send ctrl-c to pty
    if server.request:  # if not, never entered terminal mode
      self.echo_pty()  # flush pending output before releasing yorick
      for packet in server.final(None).packets:
        self.send(packet)       # handshake to exit terminal mode
    self.wait_for_prompt()

  def wait_for_prompt(self):
    if self._debug:
      print("P>wait_for_prompt: blocking...")
    while True:
      p = select.select([self.pfd], [], [self.pfd])
      prompt = self.echo_pty()
      if prompt:
        return prompt

  def echo_pty(self):
    """Print yorick stdout/stderr, returning final prompt if any."""
    if self.pfd is None:
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
        if not self.killing:
          self.kill()
          raise PYorickError("Read or select error on pty, yorick killed.")
        else:
          break
      if not p[0]:
        i += 1
    prompt = None
    if s:
      # remove prompt in interactive (no idler) mode
      if s.endswith("> "):
        i = s.rfind('\n') + 1  # 0 on failure
        prompt = s[i:]
        s = s[0:i]
      if s:
        print(s, end='')  # terminal newline already in s
    if prompt:
      if self._debug:
        print("P>echo_pty: prompt="+prompt)
      if prompt == 'PYORICK-QUIT> ' and not self.killing:
        self.kill(True)
    return prompt

  def send0(self, text, nolf=False):
    if self.pfd is not None:
      if not nolf:
        if not text.endswith('\n'):
          text += '\n'
      if self._debug and len(text):
        print("P>send0: nolf={0} text={1}".format(nolf, text))
      n = 0
      while n < len(text):
        try:
          n += os.write(self.pfdw, text[n:].encode('iso_8859_1'))
        except UnicodeEncodeError:
          print("<--- did not send non-ISO-8859-1 text to yorick --->")
          text = '\n'
          n = 0
        except:
          self.kill(True)
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
    if self.rfd is None:
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
    if self._debug and n:
      print("P>recv: {0} bytes".format(n))

  def send(self, packet):
    """Write numpy array packet to self.wfd."""
    if self.wfd is None:
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
    if self._debug and n:
      print("P>send: {0} bytes sent".format(n))

ProcessDefault = PipeProcess

########################################################################
