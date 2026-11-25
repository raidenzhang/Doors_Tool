import unittest
from dxl_export import generate, quote

class DxlTests(unittest.TestCase):
    def test_hierarchy_and_escaping(self):
        rows=[dict(level=n,text=t) for n,t in [(0,'父'),(1,'子"项'),(1,'次子'),(0,'第二根')]]
        script=generate(rows)
        self.assertIn('Object obj0 = create m',script)
        self.assertIn('Object obj1 = create below obj0',script)
        self.assertIn('Object obj2 = create after obj1',script)
        self.assertIn('Object obj3 = create after obj0',script)
        self.assertIn('子\\"项',script)
        self.assertIn('Module is not empty',script)
    def test_invalid_level(self):
        with self.assertRaises(ValueError): generate([dict(level=2,text='a')])

if __name__ == '__main__': unittest.main()
