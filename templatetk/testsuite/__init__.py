# -*- coding: utf-8 -*-
"""
    templatetk.testsuite
    ~~~~~~~~~~~~~~~~~~~~

    Implements all the tests.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import sys
import unittest
from contextlib import contextmanager


class _ExceptionCatcher(object):

    def __init__(self, test_case, exception_class):
        self.test_case = test_case
        self.exception_class = exception_class

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        exception_name = self.exception_class.__name__
        if exc_type is None:
            self.test_case.fail('Expected exception of type %r' %
                                exception_name)
        elif exc_type is not self.exception_class:
            self.test_case.fail('Expected exception of type %r, got %r' %
                                (exception_name, exc_type.__name__))
        return True


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

    def assert_raises(self, exception_class):
        return _ExceptionCatcher(self, exception_class)


def suite():
    from templatetk.testsuite import interpreter
    suite = unittest.TestSuite()
    suite.addTest(interpreter.suite())
    return suite
