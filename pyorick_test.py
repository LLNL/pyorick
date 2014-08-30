import numpy as np
from pyorick import *

def pytest(test=None, ypath="yorick", ipath="pyorick.i"):
  """Test and example suite for pyorick."""

  # Create handles for yorick connection, starting yorick if necessary.
  # Deleting the handles does not close the connection (see kill=1 below),
  # calling yorick() again gives you an equivalent handle pair, referring
  # to the existing connection if yorick is already running.
  yo, oy = yorick(ypath=ypath, ipath=ipath)
  if test:
    yo._yorick.setdebug(1)

  svals = [65, 6.5, 0.+6.5j, bytearray(b'B'), np.array(65, dtype=np.short),
           np.array(65, dtype=np.intc), np.array(6.5, dtype=np.single),
           'test string', '',
           slice(1,5,2), Ellipsis, NewAxis, None]
  if test==1 or not test:
    for v in svals:
      yo.sval = v
      w = yo.sval
      if w != v:
        print(v)
        raise PYorickError("error passing scalar data")
    print("1: PASSED send and receive scalar data")

  avals = [s+np.zeros((3,2), dtype=s.__class__) for s in svals[0:3]]
  avals.append(np.array([[66,66],[66,66],[66,66]], dtype=np.uint8))
  avals.extend([s+np.zeros((3,2), dtype=s.dtype) for s in svals[4:7]])
  if test==2 or not test:
    for v in avals:
      yo.aval = v
      w = yo.aval
      if not np.array_equal(w, v):
        print(v)
        raise PYorickError("error passing numeric array data")
    print("2: PASSED send and receive numeric array data")

  if test==3 or not test:
    yo.s = v = ['', 'test 1', 'another string']
    w = yo.s
    if len(w) != 3 or w != v:
      raise PYorickError("error passing string array data")
    yo.s = v = [v, v]
    w = yo.s
    if len(w) != 2 or len(w[0]) != 3 or w != v:
      raise PYorickError("error passing 2D string array data")
    print("3: PASSED send and receive string array data")

  if test==4 or not test:
    yo.list = svals
    w = yo.list
    if len(w) != len(svals) or w != svals:
      raise PYorickError("error passing python list data")
    print("4: PASSED send and receive python list data")

  dsvals = {i[0]:i[1]
            for i in zip(['key'+str(j) for j in range(len(svals))], svals)}
  if test==5 or not test:
    yo.dict = dsvals
    w = yo.dict
    if w != dsvals:
      raise PYorickError("error passing python dict data")
    print("5: PASSED send and receive python dict data")

  if test==6 or not test:
    svals.append(dsvals)
    yo.list = svals
    w = yo.list
    if len(w) != len(svals) or w != svals:
      raise PYorickError("error passing python nested list data")
    print("6: PASSED send and receive nested python list data")

  if test==7 or not test:
    yo('x = [3,5,7]')
    x = yo.x
    if len(x)!=3 or any(x != [3,5,7]):
      raise PYorickError("subcall failed")
    x = oy('[3, 5, 7]')
    if len(x)!=3 or any(x != [3,5,7]):
      raise PYorickError("funcall failed")
    print("7: PASSED string exec and eval tests")

  if test==8 or not test:
    x = np.array([3,5,7])
    yo.eq_nocopy(oy.y, x-5)
    x = yo.y
    if len(x)!=3 or any(x != [-2,0,2]):
      raise PYorickError("subroutine call failed")
    x = oy.where(yo.y)
    if len(x)!=2 or any(x != [1, 3]):
      raise PYorickError("function call failed")
    yo("""
func test(a, b=) {
  return a-b;
}
""")
    x = oy.test(3, b=oy.y)
    if len(x)!=3 or any(x != [5, 3, 1]):
      raise PYorickError("error function call with keyword failed")
    print("8: PASSED yorick subroutine and function call tests")

  if test==9 or not test:
    yo.x = avals[0]
    oy.x[:, 3] = [5, 6]
    oy.x[1, 1:2] = [1, 3]
    y = oy.x[::-1,:]
    if not np.array_equal(y, [[65, 1], [65, 3], [6, 5]]):
      raise PYorickError("setslice/getslice failed")
    print("9: PASSED getslice/setslice tests")
