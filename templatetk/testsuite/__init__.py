# -*- coding: utf-8 -*-
"""
    templatetk.testsuite
    ~~~~~~~~~~~~~~~~~~~~

    Implements all the tests.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import unittest


class TemplateTestCase(unittest.TestCase):

    def setUp(self):
        self.setup()

    def tearDown(self):
        self.teardown()

    def setup(self):
        pass

    def teardown(self):
        pass

    def assert_equal(self, a, b):
        return self.assertEqual(a, b)

    def assert_raises(self, *args, **kwargs):
        return self.assertRaises(*args, **kwargs)


def suite():
    from templatetk.testsuite import interpreter
    suite = unittest.TestSuite()
    suite.addTest(interpreter.suite())
    return suite
