/* pyorick.i
 * run yorick as a subprocess of python
 */

/* This script normally runs from the command line:
 *   yorick -i pyorick.i RFD WFD ...
 *   yorick -batch pyorick.i RFD WFD ...
 * where
 *   RFD is the read file descriptor number and
 *   WFD is the write file descriptor number
 * Binary messages from python to yorick flow through RFD pipe, while
 * binary messages from yorick to python flow through the WFD pipe.
 * You may also set _pyorick_rfd and _pyorick_wfd by hand before invoking
 * this script for debugging purposes.
 */
_pyorick_mode = 1n;
if (is_void(_pyorick_rfd)) {
  if (is_void(command_line)) command_line = get_argv(); /* e.g. -batch */
  if (numberof(command_line) >= 2) {
    _pyorick_rfd = tonum(command_line(1:2));
    if (allof((_pyorick_rfd>=0) & (_pyorick_rfd<1e8) & !(_pyorick_rfd%1))) {
      _pyorick_wfd = long(_pyorick_rfd(2));
      _pyorick_rfd = long(_pyorick_rfd(1));
      command_line = (numberof(command_line)>2)? command_line(3:) : [];
      _pyorick_mode = 0n;
      set_idler, , 4;  /* print error with line# before after_error */
    }
  }
}

func pyorick(mode)
/* DOCUMENT pyorick
 *          pyorick, mode
 *   With no argument, receives active message from python-to-yorick
 *   pipe, performs the requested action, and sends the response to
 *   the yorick-to-python pipe.
 *   With the MODE argument, switches from one-shot mode to idler mode.
 *   MODE=0 is idler mode (the initial state if this file included from
 *   the command line), the only communication channel is through the
 *   python-yorick pipes; yorick ignores stdin, and installs an idler
 *   which continues the request-response cycle indefinitely, until
 *   the mode is set to one-shot.
 *   MODE=1 is one-shot mode, in which only a single request-response
 *   cycle executes.  (This is the intial state if this file is not
 *   included from the command line.)
 *   In idler mode, yorick spends the time between request-response
 *   cycles blocked waiting for the next request to come through the
 *   python-to-yorick pipe.
 *   In one-shot mode, the time between cycles is spent blocked waiting
 *   for input from stdin, as if this were an ordinary interactive session.
 *   If you want yorick to make screen plots, you must use one-shot mode,
 *   because screen plots must process windowing system events, which only
 *   happens waiting for input from stdin.
 *   On the other hand, if you are running in unattended batch mode,
 *   yorick quits instead of waiting for stdin, so you must use idler mode.
 * SEE ALSO: pydebug
 */
{
  extern _pyorick_mode, after_error;
  if (is_void(mode)) {
    local __, ___;
    if (_pyorick_wait() && _pyorick_sending && !is_void(___)) {
      if (pydebug) { write, "Y>pyorick request is:"; print, ___; }
      _pydebug = pydebug;
      include, grow("___=[];" , ___), 1;
      swap, pydebug, _pydebug;
      if (pydebug) { write, "Y>pyorick response is:"; info, ___; }
      _pyorick_put, _pyorick_encode(___);
      _pyorick_sending = 0;
      swap, pydebug, _pydebug;
    }
  } else {
    _pyorick_mode = (mode != 0);
    if (!_pyorick_mode) set_idler, _pyorick_idler, 4;
    after_error = _pyorick_err_handler;
  }
}

local pydebug;
/* DOCUMENT pydebug = 1
 *   Causes debugging messages to be printed to stdout during each
 *   request-response cycle.  Set pydebug to 0 or [] to turn off
 *   debugging messages.
 */

/* yorick API for sending active messages to python:
 *
 * py, "python code"        parse and execute python code
 * py("python expression")  parse and execute python expression
 * py, "subroutine", arg1, arg2, ...   execute subroutine with arguments
 * py("function", arg1, arg2, ...)     execute function with arguments
 *                          argN may be keyword argument
 * py("variable:")          reference to variable for use as argument
 * py, "variable:", value)             set variable to value
 * py("array:", index1, index2, ...)   get array slice
 * py, "array:", index1, index2, ..., value      set array slice
 *   note: index order and meaning as interpreted by python
 */
func py(command, ..)
{
  error, "not yet implemented -- only responds to python requests for now";
}

/* ------------------------------------------------------------------------ */
/* remainder is not part of user interface, supports pyorick.py */

/* message id 0-15 are numeric types:
 *    char short int long longlong   float double longdouble
 * followed by unsigned, complex variants
 * passive messages (response to request):
 */
_ID_STRING = 16;   // yorick assumes iso_8859_1, need separate id for utf-8?
_ID_SLICE = 17;
_ID_NIL = 18;
_ID_GROUP = 19;
_ID_EOL = 20;
/* active messages (passive response required): */
_ID_EVAL = 32;
_ID_EXEC = 33;
_ID_GETVAR = 34;
_ID_SETVAR = 35;
_ID_FUNCALL = 36;
_ID_SUBCALL = 37;
_ID_GETSLICE = 38;
_ID_SETSLICE = 39;
_ID_GETSHAPE = 40;

/* garbled messages are fatal, shut down the pipes and exit idler loop */
func _pyorick_panic(msg)
{
  extern _pyorick_mode;
  _pyorick_mode = 1n;
  msg = "PANIC: " + msg;
  if (pydebug) write, "Y>"+msg;
  r = _pyorick_rfd;
  w = _pyorick_wfd;
  _pyorick_rfd = _pyorick_wfd = [];
  if (is_array(r)) fd_close, r;
  if (is_array(w)) fd_close, w;
  error, msg;
}
errs2caller, _pyorick_panic;

_pyorick_type = save(char, short, int, long, longlong=1, float, double,
                     longdouble=2, uchar=char, ushort=short, uint=int,
                     ulong=long, ulonglong=1, fcomplex=3, complex, lcomplex=4);

/* make it easy to use alternative to fd_read/write pipe i/o channels */
func _pyorick_recv(x) { return fd_read(_pyorick_rfd, x); }
func _pyorick_send(x) { return fd_write(_pyorick_wfd, x); }

/* _pyorick_err_handler
 *    Installed as after_error function by _pyorick_idler and pyorick,mode.
 *    Reinstalls _pyorick_idler in idler mode.  Always calls dbexit.
 * _pyorick_idler
 *    Perpetual loop: Read a complete message from python, perform the
 *    requested action, and write the response message to python.
 *    If a python sends a passive message, raises an error (causing
 *    _pyorick_err_handler to generate an error-EOL message).
 * _pyorick_wait
 *    Called by _pyorick_idler: Wait for active message from python
 *    by calling _pyorick_get, then call _pyorick_action to interpret
 *    the message and generate the text of the yorick code to be
 *    executed back in _pyorick_idler.
 * _pyorick_get
 *    Read complete message from python with as little interpretation
 *    as possible.  This must be an atomic operation -- if it is
 *    interrupted, there is no way to resynchronize the pipe, and the
 *    whole connection must shut down.
 *    A complete message (called msg in the code) is an oxy object; it
 *    may contain a list of quoted messages in the case of the passive
 *    GROUP message, or the active messages which have argument or index
 *    lists (FUNCALL, SUBCALL, GETSLICE, SETSLICE).
 * _pyorick_action
 *    Thin wrapper over _pyorick_unparse to interpret active message.
 * _pyorick_unparse
 *    For active messages, generate the text of the expression or statement
 *    which causes yorick to perform the requested action.  For quoted
 *    passive messages, add their value to the stack of arguments referenced
 *    by this text.
 * _pyorick_decode
 *    Decode passive messages from the uninterpreted form returned by
 *    _pyorick_get.  Most of the work is for string array and group objects.
 * _pyorick_setslice
 *    The SETSLICE active message needs this special helper function.
 * _pyorick_encode
 *    Produce the passive message representing the yorick value which
 *    is the response to the python request.  The format is the same as
 *    the output returned by _pyorick_get.  Performs all the error checking
 *    and repackaging without actually sending the response.
 * _pyorick_put
 *    Send the response message to python.  This must be an atomic operation;
 *    there is no way to resynchronize the pipe, so any interruption is
 *    fatal and causes the connection to shut down.
 * _pyorick_puterr
 *    Send an error-EOL message to python, for when some error prevents
 *    the request from being completed.
 */

func _pyorick_err_handler
{
  extern _pyorick_errmsg;
  if (pydebug) write, "Y>_pyorick_err_handler called";
  if (_pyorick_looping > 100)
    _pyorick_panic, "caught in exception loop\n" +
      (_pyorick_errmsg? _pyorick_errmsg : "");
  if (_pyorick_looping < 2) _pyorick_errmsg = catch_message;
  if (!_pyorick_mode) set_idler, _pyorick_idler, 4;
  _pyorick_puterr;  /* noop unless _pyorick_sending */
  dbexit, 0;        /* get out of debug mode from set_idler,,4 */
}

_pyorick_looping = 0;
func _pyorick_idler
{
  extern after_error;
  after_error = _pyorick_err_handler;
  _pyorick_looping += 1;
  if (pydebug) write, "Y>_pyorick_idler: enter";
  for (__=___=[] ; !_pyorick_mode ; __=___=[]) pyorick;
  if (pydebug) write, "Y>_pyorick_idler: exit";
  if (_pyorick_mode || _pyorick_looping>=100) set_idler, , 4;
  else if (!is_void(_pyorick_rfd)) set_idler, _pyorick_idler;
}

func _pyorick_wait(void)
{
  if (!is_void(_pyorick_rfd)) {
    if (_pyorick_sending) {
      if (!_pyorick_errmsg)
        _pyorick_errmsg = "ERROR (_pyorick_wait) <lost error message>";
      _pyorick_puterr;
      _pyorick_sending = 0;
    }
    msg = _pyorick_get();  /* atomic read */
    if (pydebug) write, "Y>_pyorick_wait: got message "+print(msg(hdr))(1);
    if (!is_void(_pyorick_rfd)) {
      /* perhaps should call _pyorick_puterr if _pyorick_errmsg is set? */
      _pyorick_sending = 1;
      if (_pyorick_action(msg))
        error, "got passive message when expecting active message";
      return 1n;
    }
  }
  return 0;
}

/* slurp complete message with no excess processing -- must be atomic op
 * panic (close connection) if dimensions or lengths make no sense,
 *   or if message (or quoted message) not recognized
 */
func _pyorick_get(void)
{
  if (pydebug) write, "Y>_pyorick_get: blocking...";
  hdr = _pyorick_recv([0, 0]);
  if (pydebug) write, "Y>_pyorick_get: got message "+print(hdr)(1);
  id = hdr(1);
  msg = save(_pyorick_id=id, hdr);
  if (id>=0 && id<_ID_STRING) {
    rank = hdr(2);
    dims = [rank];
    if (rank>0) grow, dims, _pyorick_recv(array(0, rank));
    if (rank<0 || (rank && anyof(dims(1:)<=0)))
      _pyorick_panic, "illegal dimensions";
    type = _pyorick_type(1+id);
    if (type == 1) {
      if (sizeof(long) == 8) type = long;
      else _pyorick_panic, "longlong unsupported";
    } else if (type == 3) {
      type = float;
      dims = grow(dims(1:1)+1, 2, (dims(1)? dims(2:) : []));
    } else if (is_array(type)) {
      _pyorick_panic, "longdouble unsupported";
    }
    dims = _pyorick_safedims(dims);
    save, msg, value = _pyorick_recv(array(type, dims));
  } else if (id == _ID_STRING) {
    rank = hdr(2);
    dims = [rank];
    if (rank) grow, dims, _pyorick_recv(array(0, rank));
    if (rank<0 || (rank && anyof(dims(1:)<=0)))
      _pyorick_panic, "illegal string array dimensions";
    dims = _pyorick_safedims(dims);
    lens = _pyorick_recv(array(0, dims));
    if (anyof(lens<0)) _pyorick_panic, "negative string length";
    save, msg, lens;
    lens = sum(lens);
    save, msg, value = (lens? _pyorick_recv(array(char, lens)) : []);
  } else if (id == _ID_SLICE) {
    save, msg, flag = hdr(2), value = _pyorick_recv([0, 0, 0]);
  } else if (id == _ID_NIL) {
    save, msg, value = [];
  } else if (id == _ID_GROUP) {
    save, msg, value = _pyorick_getlist();
  } else if (id == _ID_EOL) {
    save, msg, flag = hdr(2);

  } else if (anyof(id == [_ID_EVAL, _ID_EXEC])) {
    save, msg, value = _pyorick_getname(hdr(2));
  } else if (anyof(id == [_ID_GETVAR, _ID_SETVAR, _ID_GETSHAPE])) {
    save, msg, name = _pyorick_getname(hdr(2));
    if (id == _ID_SETVAR) save, msg, value = _pyorick_get();
  } else if (id>=_ID_FUNCALL && id<=_ID_SETSLICE) {
    save, msg, name = _pyorick_getname(hdr(2));
    save, msg, args = _pyorick_getlist();
    if (id == _ID_SETSLICE) save, msg, value = _pyorick_get();

  } else {
      _pyorick_panic, "unknown message id";
  }
  return msg;
}

func _pyorick_safedims(dims)
{
  rank = dims(1);
  while (rank > 10) {
    dims(1) = --rank;
    dims(1+rank) *= dims(2+rank);
  }
  if (numberof(dims) > 1+rank) dims = dims(1:1+rank);
  return dims;
}

func _pyorick_getname(len)
{
  if (len <= 0) _pyorick_panic, "zero length name";
  return _pyorick_recv(array(char, len));
}

func _pyorick_getlist(void)
{
  args = save();
  for (;;) {
    m = _pyorick_get();
    if (m._pyorick_id == _ID_EOL) break;
    save, args, string(0), m;
  }
  return args;
}

func _pyorick_action(msg)
{
  id = msg(_pyorick_id);
  if (id < _ID_EVAL) return 1n;
  extern ___, __;  /* command/expression string and arguments object */
  __ = save();
  ___ = _pyorick_unparse(msg);
  return 0n;
}

func _pyorick_unparse(msg, raw)
{
  local value, args;
  id = msg(_pyorick_id);
  if (id < _ID_EVAL) {
    if (!raw) error, "expecting active message";
    if (id == _ID_NIL) {
      txt = "[]";
    } else {
      save, __, string(0), _pyorick_decode(msg);
      txt = "__(" + totxt(__(*)) + ")";
    }

  } else if (id==_ID_EVAL || id==_ID_EXEC) {
    eq_nocopy, value, msg(value);
    isf = (id == _ID_EVAL);
    list = where((value == '\n') | (value == '\r'));
    if (numberof(list)) value(list) = '\0';
    txt = strchar(value);
    if (isf) txt(1) = raw? strpart(txt,2:) : "___=" + txt(1);
    else if (raw) error, "illegal value or argument";

  } else if (id == _ID_GETVAR) {
    txt = (raw? "" : "___=") + strchar(msg(name));
  } else if (id == _ID_SETVAR) {
    if (raw == 3) error, "illegal keyword argument in index list";
    txt = strchar(msg(name)) + "=" + _pyorick_unparse(msg(value), 1);
  } else if (id == _ID_GETSHAPE) {
    txt = "___=" + "_pyorick_shape(" + strchar(msg(name)) + ")";

  } else {
    if (raw && id!=_ID_FUNCALL) error, "illegal argument or index";
    args = msg(args);  /* args always an oxy object, no copy here */
    n = args(*);
    if (id==_ID_FUNCALL || id==_ID_GETSLICE)
      txt = (raw? "" : "___=") + strchar(msg(name)) + "(";
    else if (id == _ID_SUBCALL)
      txt = strchar(msg(name)) + (n? "," : "");
    else if (id == _ID_SETSLICE)
      txt = "_pyorick_setslice," + strchar(msg(name)) + "," +
        _pyorick_unparse(msg(value), 1) + ",";
    for (i=1 ; i<=n ; ++i) {
      txt += _pyorick_unparse(args(noop(i)), 2+(id>=_ID_GETSLICE));
      if (i < n) txt += ",";
    }
    if (id==_ID_FUNCALL || id==_ID_GETSLICE) txt += ")";
  }
  return txt;
}

func _pyorick_decode(msg)
{
  local lens, value, name;
  id = msg(_pyorick_id);
  if (id < _ID_STRING) {
    return msg(value);
  } else if (id == _ID_STRING) {
    eq_nocopy, lens, msg(lens);
    s = array(string, dimsof(lens));
    list = where(lens);
    if (numberof(list)) s(list) = strchar(msg(value));
    list = where(lens == 1);
    if (numberof(list)) s(list) = "";
    return s;
  } else if (id == _ID_SLICE) {
    return rangeof([msg(value,1), msg(value,2), msg(value,3), msg(hdr,2)])
  } else if (id == _ID_NIL) {
    return [];
  } else if (id == _ID_GROUP) {
    named = msg(hdr, 2);
    m = msg(value);
    value = save();
    for (i=1,n=m(*) ; i<=n ; ++i) {
      mi = m(noop(i));  /* mi is a message object, no copy here */
      if (named) {
        if (mi._pyorick_id != _ID_SETVAR)
          error, "missing member name in dict object";
        name = strchar(mi(name));
        mi = mi(value);
      } else {
        name = string(0);
      }
      if (mi._pyorick_id > _ID_GROUP)
        error, "illegal member in dict or list object";
      save, value, noop(name), _pyorick_decode(mi);
    }
    return value;
  } else {
    return msg;  /* other stuff is not decodable */
  }
}

func _pyorick_shape(a)
{
  id = where(_pyorick_type(*,) == typeof(a));
  if (numberof(id))
    id = grow(id-1, dimsof(a));
  else
    id = is_func(a)? -1 : -2;
  return id;
}

func _pyorick_setslice(a, value, ..)
{
  n = more_args();
  if (n == 0) 
    a() = value;  /* probably an error */
  else if (n == 1)
    a(next_arg()) = value;
  else if (n == 2)
    a(next_arg(), next_arg()) = value;
  else if (n == 3)
    a(next_arg(), next_arg(), next_arg()) = value;
  else if (n == 4)
    a(next_arg(), next_arg(), next_arg(), next_arg()) = value;
  else if (n == 5)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg()) = value;
  else if (n == 6)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg(),
      next_arg()) = value;
  else if (n == 7)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg(),
      next_arg(), next_arg()) = value;
  else if (n == 8)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg(),
      next_arg(), next_arg(), next_arg()) = value;
  else if (n == 9)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg(),
      next_arg(), next_arg(), next_arg(), next_arg()) = value;
  else if (n == 10)
    a(next_arg(), next_arg(), next_arg(), next_arg(), next_arg(),
      next_arg(), next_arg(), next_arg(), next_arg(), next_arg()) = value;
  else
    error, "cannot accept more than 10 dimensions";
}

func _pyorick_encode(value)
{
  if (!is_obj(value) || is_void(value._pyorick_id)) {
    /* ordinary passive value */
    if (is_array(value)) {
      if (structof(value) == string) {
        id = 16;
        lens = strlen(value) + 1;
        list = where(!value);
        if (numberof(list)) {
          lens(list) = 0;
          value = value(where(value));
        }
        dims = dimsof(lens);
      } else {
        id = where(_pyorick_type(*,) == typeof(value));
        if (!numberof(id))
          error, "unsupported datatype " + typeof(value);
        id = id(1) - 1;
        if (!id) id = 8;
        dims = dimsof(value);
      }
      msg = save(_pyorick_id=id, hdr=[id,dims(1)]);
      if (id == 16) save, msg, lens, value=strchar(value);
      else save, msg, value;

    } else if (is_range(value)) {
      id = _ID_SLICE;
      r = rangeof(value);
      msg = save(_pyorick_id=id, hdr=[id,r(4)], value=r(1:3));

    } else if (is_void(value)) {
      msg = save(_pyorick_id=_ID_NIL, hdr=[_ID_NIL,0], value=[]);

    } else if (is_obj(value)) {
      names = value(*,);
      named = allof(names);
      if (!named && anyof(names))
        error, "oxy object members must be all named or all anonymous";
      v = save();
      msg = save(_pyorick_id=_ID_GROUP, hdr=[_ID_GROUP,named], value=v);
      n = numberof(names);
      if (named) {
        for (i=1 ; i<=n ; ++i) {
          name = strchar(names(i));
          m = save(_pyorick_id=_ID_SETVAR, hdr=[_ID_SETVAR,numberof(name)],
                   name, value=_pyorick_encode(value(noop(i))));
          save, v, string(0), m;
        }
      } else {
        for (i=1 ; i<=n ; ++i)
          save, v, string(0), _pyorick_encode(value(noop(i)));
      }

    } else {  /* unencodable value, indicate variable reference */
      msg = save(_pyorick_id=_ID_EOL, hdr=[_ID_EOL,2], value=[]);
    }

  } else {
    /* special or active value */
    error, "active messages to python currently unsupported";
  }

  return msg;
}

/* send complete message with no excess processing - must be atomic op
 * an unknown message or other error here is a bug in _pyorick_encode
 */
func _pyorick_put(msg)
{
  id = msg(_pyorick_id);
  if (pydebug) write, "Y>_pyorick_put: sending message "+print(msg(hdr))(1);
  _pyorick_send, msg(hdr);
  if (id < _ID_STRING) {
    dims = dimsof(msg(value));
    if (dims(1)) _pyorick_send, dims(2:);
    _pyorick_send, msg(value);
  } else if (id == _ID_STRING) {
    dims = dimsof(msg(lens));
    if (dims(1)) _pyorick_send, dims(2:);
    _pyorick_send, msg(lens);
    if (sum(msg(lens))) _pyorick_send, msg(value);
  } else if (id == _ID_SLICE) {
    _pyorick_send, msg(value);
  } else if (id == _ID_NIL) {
    /* hdr only */
  } else if (id == _ID_GROUP) {
    _pyorick_putlist, msg(value);
  } else if (id == _ID_EOL) {
    /* hdr only */
  } else if (id == _ID_EVAL || id == _ID_EXEC) {
    _pyorick_send, msg(value);
  } else if (id == _ID_GETVAR) {
    _pyorick_send, msg(name);
  } else if (id == _ID_SETVAR) {
    _pyorick_send, msg(name);
    _pyorick_put, msg(value);
  } else if (id>=_ID_FUNCALL && id<=_ID_SETSLICE) {
    _pyorick_send, msg(name);
    _pyorick_putlist, msg(args);
    if (id == _ID_SETSLICE) _pyorick_put, msg(value);
  } else if (id == _ID_GETSHAPE) {
    _pyorick_send, msg(name);
    _pyorick_put, msg(value);
  } else {
    _pyorick_panic, "unknown message id";
  }
  if (pydebug) write, "Y>_pyorick_put: sent message "+print(msg(hdr))(1);
}

func _pyorick_putlist(msg)
{
  n = msg(*);
  for (i=1 ; i<=n ; ++i) _pyorick_put, msg(noop(i));
  _pyorick_send, [_ID_EOL, 0];
}

func _pyorick_puterr
{
  if (_pyorick_sending) {
    if (!is_void(_pyorick_wfd)) _pyorick_send, [_ID_EOL, 1];
    _pyorick_sending = 0;
  }
}

_pyorick_sending = 0;
if (!_pyorick_mode) set_idler, _pyorick_idler, 1;
