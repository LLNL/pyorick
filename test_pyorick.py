import unittest
import numpy as np
from pyorick import *    # pyorick exposes only intended APIs
from pyorick import Message    # not an API, but needed for testing

class ExampleClass(object):
    def __init__(self, thing):
        self.thing = thing

def example_func(x):
    return x

class TestCodec(unittest.TestCase):
    def setUp(self):
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

    def tearDown(self):
        pass

    def test_scalars(self):
        """Check that scalar types can be encoded and decoded."""
        for i in range(len(self.scalars)):
            s = self.scalars[i]
            msg = Message(None, s)
            v = msg.decode()
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_arrays(self):
        """Check that array types can be encoded and decoded."""
        for i in range(len(self.arrays)):
            s = self.arrays[i]
            msg = Message(None, s)
            v = msg.decode()
            self.assertTrue(np.array_equal(np.array(s), v),
                            'codec failed on item '+str(i))

    def test_strings(self):
        """Check that string types can be encoded and decoded."""
        for i in range(len(self.strings)):
            s = self.strings[i]
            msg = Message(None, s)
            v = msg.decode()
            if isinstance(s, np.ndarray):
                s = s.tolist()
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_groups(self):
        """Check that group types can be encoded and decoded."""
        for i in range(len(self.groups)):
            s = self.groups[i]
            msg = Message(None, s)
            v = msg.decode()
            if isinstance(s, tuple):
                s = list(s)
            self.assertEqual(s, v, 'codec failed on item '+str(i))

    def test_bad(self):
        """Check that unencodable types cannot be encoded."""
        for i in range(len(self.bad)):
            with self.assertRaises(PYorickError) as cm:
                msg = Message(None, self.bad[i])
            self.assertIsInstance(cm.exception, PYorickError,
                                  'codec failed on item '+str(i))

    def test_reader(self):
        """Check codec readers."""
        for obj in self.scalars + self.arrays + self.strings + self.groups:
            m = Message(None, obj)
            mlen = len(m.packets)
            msg = Message()
            i = 0
            for packet in msg.encoder():
                em = str(i)+': '+repr(obj)
                self.assertLess(i, mlen, 'reader stopped late on ' + em)
                self.assertEqual(packet.dtype.itemsize,
                                 m.packets[i].dtype.itemsize,
                                 'reader wrong size on ' + em)
                np.copyto(packet, m.packets[i], casting='safe')
                i += 1
            self.assertEqual(i, mlen, 'reader stopped early on ' + 
                             str(i)+': '+repr(obj))

if __name__ == '__main__':
    unittest.main()
