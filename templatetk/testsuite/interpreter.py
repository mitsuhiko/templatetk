# -*- coding: utf-8 -*-
"""
    templatetk.testsuite.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests the AST interpreter.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from templatetk.testsuite import TemplateTestCase
from templatetk import nodes
from templatetk.interpreter import Interpreter
from templatetk.config import Config
from templatetk.context import Context


class ForLoopTestCase(TemplateTestCase):

    def setup(self):
        self.intrptr = Interpreter(Config())

    def assert_result_matches(self, node, ctx, expected):
        rv = u''.join(self.intrptr.evaluate(node, ctx))
        self.assert_equal(rv, expected)

    def make_context(self, *args, **kwargs):
        rv = Context(self.intrptr.config)
        for key, value in dict(*args, **kwargs).iteritems():
            rv[key] = value
        return rv

    def test_basic_loop(self):
        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load')])
            ], None, None)
        ])

        ctx = self.make_context(iterable=[1, 2, 3, 4])
        self.assert_result_matches(template, ctx, '1234')


def suite():
    import unittest
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ForLoopTestCase))
    return suite
