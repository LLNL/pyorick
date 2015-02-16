import unittest
import numpy as np
from pyorick import *    # pyorick exposes only intended APIs
# non-APIs which must be exposed for testing
from pyorick import Message, YorickVar, YorickHold, YorickVarCall
from pyorick import (ID_EOL, ID_EVAL, ID_EXEC, ID_GETVAR, ID_SETVAR,
                     ID_FUNCALL, ID_SUBCALL, ID_GETSLICE, ID_SETSLICE,
                     ID_GETSHAPE)
import __main__

# nosetests --with-coverage --cover-package=pyorick

class ExampleClass(object):
    def __init__(self, thing):
        self.thing = thing
    def __eq__(self, other):
        return self.thing == other.thing

def example_func(x):
    return x

# create test fixtures
def setup_data(self):
    # various types of scalar objects which must be encodable
    self.scalars = [65, 6.5, 0.+6.5j, True, bytearray(b'B'),
                    np.array(65, dtype=np.short),
                    np.array(65, dtype=np.intc),
                    np.array(6.5, dtype=np.single),
                    'test string', '', ystring0,
                    slice(1,5,2), Ellipsis, ynewaxis, None]
    # various types of array objects which must be encodable
    self.arrays = [s+np.zeros((3,2), dtype=s.__class__) 
                   for s in self.scalars[0:4]]
    self.arrays.append(np.array([[66,66],[66,66],[66,66]], dtype=np.uint8))
    self.arrays.extend([s+np.zeros((3,2), dtype=s.dtype)
                        for s in self.scalars[5:8]])
    self.arrays.append([[66,66],[66,66],[66,66]])
    self.arrays.append(bytearray(b'BABABABA'))
    # various types of string array objects which must be encodable
    self.strings = [['', 'test 1', 'another string'],
                    [['', 'test 1', 'another string'],
                     ['test 2', ystring0, 'more']]]
    self.strings.append(np.array(self.strings[1]))  # corrupts string0?
    # representable list and dict objects
    self.groups = [(), [], ([], None), self.scalars, {},
                   {'key'+str(k):self.scalars[k]
                    for k in range(len(self.scalars))},
                   [[1,'abc'], {'a':1, 'b':[2,'c',4]}],
                   {'key0':[1,'abc'], 'key1':{'a':1, 'b':2}}]
    # unrepresentable objects
    self.bad = [{'a':[1,2,3], 2:[4,5,6]},  # illegal key type
                example_func,              # function
                ExampleClass,              # class
                ExampleClass([1,2,3])]     # class instance

class TestCodec(unittest.TestCase):
    def setUp(self):
        setup_data(self)

    def tearDown(self):
        pass

    def test_scalars(self):
        """Check that scalar types can be encoded and decoded."""
        for i in range(len(self.scalars)):
            s = self.scalars[i]
            self.assertTrue(yencodable(s), 'yencodable fails item '+str(i))
            msg = Message(None, s)
            v = msg.decode()
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_arrays(self):
        """Check that array types can be encoded and decoded."""
        for i in range(len(self.arrays)):
            s = self.arrays[i]
            self.assertTrue(yencodable(s), 'yencodable fails item '+str(i))
            msg = Message(None, s)
            v = msg.decode()
            self.assertTrue(np.array_equal(np.array(s), v),
                            'codec failed on item '+str(i))

    def test_strings(self):
        """Check that string types can be encoded and decoded."""
        for i in range(len(self.strings)):
            s = self.strings[i]
            self.assertTrue(yencodable(s), 'yencodable fails item '+str(i))
            msg = Message(None, s)
            v = msg.decode()
            if isinstance(s, np.ndarray):
                s = s.tolist()
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_groups(self):
        """Check that group types can be encoded and decoded."""
        for i in range(len(self.groups)):
            s = self.groups[i]
            self.assertTrue(yencodable(s), 'yencodable fails item '+str(i))
            msg = Message(None, s)
            v = msg.decode()
            if isinstance(s, tuple):
                s = list(s)
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_bad(self):
        """Check that unencodable types cannot be encoded."""
        for i in range(len(self.bad)):
            s = self.bad[i]
            self.assertFalse(yencodable(s), 'yencodable fails item '+str(i))
            ypickling(False)
            with self.assertRaises(PYorickError) as cm:
                msg = Message(None, s)
            self.assertIsInstance(cm.exception, PYorickError,
                                  'codec failed on item '+str(i))
            ypickling(encode=True, decode=True)
            print('doing {}'.format(i))
            msg = Message(None, s)
            v = msg.decode()
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_active(self):
        """Check codec for active messages."""
        msg = Message(ID_EOL, 4)
        v = msg.decode()
        self.assertTrue(v[0]==ID_EOL and v[1][0]==4, 'ID_EOL broken')
        msg = Message(ID_EVAL, 'hi mom')
        v = msg.decode()
        self.assertTrue(v[0]==ID_EVAL and v[1][0]=='hi mom', 'ID_EVAL broken')
        msg = Message(ID_EXEC, 'hi mom')
        v = msg.decode()
        self.assertTrue(v[0]==ID_EXEC and v[1][0]=='hi mom', 'ID_EXEC broken')
        msg = Message(ID_GETVAR, 'vvv')
        v = msg.decode()
        self.assertTrue(v[0]==ID_GETVAR and v[1][0]=='vvv', 'ID_GETVAR broken')
        msg = Message(ID_GETSHAPE, 'vvv')
        v = msg.decode()
        self.assertTrue(v[0]==ID_GETSHAPE and v[1][0]=='vvv',
                        'ID_GETSHAPE broken')
        msg = Message(ID_SETVAR, 'vvv', 31.7)
        v = msg.decode()
        self.assertTrue(v[0]==ID_SETVAR and v[1][0]=='vvv' and v[1][1]==31.7,
                        'ID_SETVAR broken')
        for ident in [ID_FUNCALL, ID_SUBCALL]:
            if ident == ID_FUNCALL:
                err = 'ID_FUNCALL broken'
            else:
                err = 'ID_SUBCALL broken'
            msg = Message(ident, 'vvv')
            v = msg.decode()
            self.assertTrue(v[0]==ident and v[1][0]=='vvv' and len(v[1])==1,
                            err+' 1')
            msg = Message(ident, 'vvv', 31.7)
            v = msg.decode()
            self.assertTrue(v[0]==ident and v[1][0]=='vvv' and v[1][1]==31.7,
                            err+' 2')
            msg = Message(ident, 'vvv', wow=-21)
            v = msg.decode()
            self.assertTrue(v[0]==ident and v[1][0]=='vvv' and len(v[1])==1 and
                            v[2]['wow']==-21, err+' 3')
            msg = Message(ident, 'vvv', 31.7, wow=-21)
            v = msg.decode()
            self.assertTrue(v[0]==ident and v[1][0]=='vvv' and v[1][1]==31.7 and
                            v[2]['wow']==-21, err+' 4')
            msg = Message(ident, 'vvv', 31.7, None, wow=-21, zow='abc')
            v = msg.decode()
            self.assertTrue(v[0]==ident and v[1][0]=='vvv' and v[1][1]==31.7 and
                            v[1][2]==None and v[2]['wow']==-21 and
                            v[2]['zow']=='abc', err+' 5')
        msg = Message(ID_GETSLICE, 'vvv')
        v = msg.decode()
        self.assertTrue(v[0]==ID_GETSLICE and v[1][0]=='vvv' and len(v[1])==1,
                        'ID_GETSLICE broken')
        msg = Message(ID_GETSLICE, 'vvv', 42, Ellipsis)
        v = msg.decode()
        self.assertTrue(v[0]==ID_GETSLICE and v[1][0]=='vvv' and v[1][1]==42 and
                        v[1][2]==Ellipsis, 'ID_GETSLICE broken')
        msg = Message(ID_SETSLICE, 'vvv', 'q')
        v = msg.decode()
        self.assertTrue(v[0]==ID_SETSLICE and v[1][0]=='vvv' and v[1][1]=='q',
                        'ID_SETSLICE broken 1')
        msg = Message(ID_SETSLICE, 'vvv', 42, Ellipsis, 'q')
        v = msg.decode()
        self.assertTrue(v[0]==ID_SETSLICE and v[1][0]=='vvv' and v[1][1]==42 and
                        v[1][2]==Ellipsis and v[1][3]=='q',
                        'ID_SETSLICE broken 2')

    def gen_messages(self):  # for test_reader
        for obj in self.scalars + self.arrays + self.strings + self.groups:
            yield obj, Message(None, obj)
        yield 'ID_EOL', Message(ID_EOL, 4)
        yield 'ID_EVAL', Message(ID_EVAL, 'hi mom')
        yield 'ID_EXEC', Message(ID_EXEC, 'hi mom')
        yield 'ID_GETVAR', Message(ID_GETVAR, 'vvv')
        yield 'ID_GETSHAPE', Message(ID_GETSHAPE, 'vvv')
        yield 'ID_SETVAR', Message(ID_SETVAR, 'vvv', 31.7)
        yield 'ID_FUNCALL', Message(ID_FUNCALL, 'vvv', 31.7, None, wow=-21)
        yield 'ID_SUBCALL', Message(ID_SUBCALL, 'vvv', 31.7, None, wow=-21)
        yield 'ID_GETSLICE', Message(ID_GETSLICE, 'vvv', 42, Ellipsis)
        yield 'ID_SETSLICE', Message(ID_SETSLICE, 'vvv', 42, Ellipsis, 'q')

    def test_reader(self):
        """Check codec readers."""
        for obj, m in self.gen_messages():
            mlen = len(m.packets)
            msg = Message()
            i = 0
            for packet in msg.reader():
                em = str(i)+': '+repr(obj)
                self.assertLess(i, mlen, 'reader stopped late on ' + em)
                self.assertEqual(packet.dtype.itemsize,
                                 m.packets[i].dtype.itemsize,
                                 'reader wrong size on ' + em)
                # np.copyto(packet, m.packets[i], casting='safe')
                # following two lines work back to numpy 1.5:
                self.assertTrue(np.can_cast(m.packets[i].dtype, packet.dtype,
                                            casting='safe'),
                                'reader wrong type on '+ em)
                packet[...] = m.packets[i]
                i += 1
            self.assertEqual(i, mlen, 'reader stopped early on ' + 
                             str(i)+': '+repr(obj))

class TestProcess(unittest.TestCase):
    def setUp(self):
        setup_data(self)
        self.yo = Yorick()

    def tearDown(self):
        self.yo.kill()

    def test_basic(self):
        """Check variety of simple yorick interface features."""
        self.yo("junk=42;")
        self.assertEqual(self.yo("=junk"), 42, 'process failed basic 1')
        self.assertEqual(self.yo.v.junk, 42, 'process failed basic 2')
        self.assertEqual(self.yo.call.junk.v, 42, 'process failed basic 3')
        self.assertEqual(self.yo.evaluate("junk"), 42, 'process failed basic 4')
        self.assertEqual(self.yo.handles(1), self.yo.call,
                         'process failed basic 5')
        self.assertEqual(self.yo.handles(7), (self.yo.c,self.yo.e,self.yo.v),
                         'process failed basic 6')
        self.assertEqual(self.yo.c[''].bare, self.yo.bare,
                         'process failed basic 7')
        self.assertEqual(self.yo.v['Y_HOME'], self.yo.v.Y_HOME,
                         'process failed basic 7')

    def test_scalars(self):
        """Check that scalar types can be sent and received."""
        for i in range(len(self.scalars)):
            s = self.scalars[i]
            self.yo.v.junk = s
            v = self.yo.v.junk
            self.assertEqual(s, v, 'process failed on item '+str(i))

    def test_arrays(self):
        """Check that array types can be sent and received."""
        for i in range(len(self.arrays)):
            s = self.arrays[i]
            self.yo.c.junk = s
            v = self.yo.e.junk.value
            self.assertTrue(np.array_equal(np.array(s), v),
                            'process failed on item '+str(i))

    def test_strings(self):
        """Check that string types can be sent and received."""
        for i in range(len(self.strings)):
            s = self.strings[i]
            self.yo.e.junk = s
            v = self.yo.c.junk.value
            if isinstance(s, np.ndarray):
                s = s.tolist()
            self.assertEqual(s, v, 'process failed on item '+str(i))

    def test_groups(self):
        """Check that group types can be sent and received."""
        for i in range(len(self.groups)):
            s = self.groups[i]
            self.yo.v.junk = s
            v = self.yo.value.junk
            if isinstance(s, tuple):
                s = list(s)
            elif not len(s):
                s = []  # yorick cannot distinguish {} from []
            self.assertEqual(s, v, 'process failed on item '+str(i)+
                             '\n'+str(s)+'\n'+str(v))

    def test_active(self):
        """Check that all requests can be sent and received."""
        # exec, eval, getvar, setvar already tested above
        x = self.yo.evaluate.where([1,0,-3])
        self.assertEqual(np.array(x).tolist(), [1,3],
                         'process failed on funcall')
        self.yo("""
func test(a, b=) {
  extern testv;
  testv = a - b;
  return testv;
}
""")
        self.assertEqual(self.yo.e("test({0}, b={1})", [2,1], 1.5).tolist(),
                         [0.5, -0.5], 'process failed on formatted eval')
        f = self.yo.value.test
        self.assertTrue(isinstance(f, YorickVar),
                        'process failed on non-data value return')
        self.yo.call.test([1,2], b=1.5)
        self.assertEqual(self.yo.v.testv.tolist(), [-0.5, 0.5],
                         'process failed on subcall with keyword')
        self.assertTrue(f([2,1], b=1.5) is None,
                        'process failed on value subcall semantics')
        self.assertEqual(self.yo.v.testv.tolist(), [0.5, -0.5],
                         'process failed on value subcall with keyword')
        self.assertEqual(self.yo.e.test([1,2], b=1.5).tolist(), [-0.5, 0.5],
                         'process failed on funcall with keyword')
        self.assertEqual(self.yo.e.testv[1], -0.5,
                         'process failed on getslice')
        self.assertEqual(self.yo.e.testv[...].tolist(), [-0.5, 0.5],
                         'process failed on getslice with ellipsis')
        self.yo.e.testv[1:2] = [2.0, 3.0]
        self.assertEqual(self.yo.v.testv.tolist(), [2.0, 3.0],
                         'process failed on setslice')
        self.yo.c.testv[0:] = [3.0, 2.0]
        self.assertEqual(self.yo.v.testv.tolist(), [3.0, 2.0],
                         'process failed on setslice, python semantics')
        i = self.yo.evaluate.testv.info
        self.assertEqual(i, (6, 1, 2), 'process failed on getshape')
        i = self.yo.evaluate.test.info
        self.assertEqual(i, (-1,), 'process failed on getshape')

    def test_hold(self):
        """Check that all requests can be sent and received."""
        # exec, eval, getvar, setvar already tested above
        #f = self.yo.e.create('~/gh/pyorick/junk')
        #self.yo.e.write(f, 'this is a test')
        #del f
        self.yo("""
struct PyTest {
  long mema;
  double memb(2,3);
  char memc;
}
""")
        struct = self.yo.e.PyTest(mema=-7, memb=[[11,12],[21,22],[31,32]],
                                  memc=65)
        self.assertEqual(struct['mema'], -7, 'string valued index failed')
        self.assertEqual(struct['memb',2,3], 32, 'string mixed index failed')
        s = Key2AttrWrapper(struct)
        self.assertEqual(s.memc, 65, 'Key2AttrWrapper get failed')
        s.memc = 97
        self.assertEqual(s.memc, 97, 'Key2AttrWrapper set failed')
        s = self.yo.e.random.hold(1000, 1001)
        self.assertTrue(isinstance(s, YorickVar), 'hold attribute failed')
        del struct  # checks that deleting held reference works
        self.yo.v.t = self.yo.e.noop(s)
        self.assertEqual(self.yo.e.t.shape, (1001,1000),
                         'passing held reference as argument failed')
        s = s[5,None]  # implicitly deletes object after retrieving one column
        self.assertEqual(s.shape, (1001,), 'indexing held reference failed')
        s = self.yo.e('@t')
        self.assertTrue(isinstance(s, YorickVar), 'hold @-syntax failed')
        self.assertEqual(s.shape, (1001,1000),
                         'held reference attribute failed')
        del s
        self.yo.v.t = None

    def test_recurse(self):
        """Check that a yorick reply can contain python requests."""
        self.yo("""
func recursive(x) {
  extern _recur;
  if (!_recur) { _recur=1; py, "import numpy as np"; }
  y = py("np.array", [x, 1-x]);
  py, "var=", 1+x;
  return py("var") - x;
}
""")
        self.yo.c.recursive(2)
        self.assertEqual(__main__.var, 3, 'recursive request set failed')
        self.assertEqual(self.yo.e.recursive(2), 1,
                         'recursive request reply value failed')


if __name__ == '__main__':
    unittest.main()
