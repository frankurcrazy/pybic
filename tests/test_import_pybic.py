import unittest

class TestImportPyBic(unittest.TestCase):

    def test_import_pybic(self):
        try:
            import pybic
        except Exception as e:
            self.fail(f"failed importing pybic: {e}")
