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
from templatetk.interpreter import Interpreter, Context
from templatetk.config import Config


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
            ], None)
        ])

        ctx = self.make_context(iterable=[1, 2, 3, 4])
        self.assert_result_matches(template, ctx, '1234')

    def test_loop_with_counter(self):
        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(':'),
                          n.Getattr(n.Name('loop', 'load'),
                                    n.Const('index0'), 'load'),
                          n.Const(';')])
            ], None)
        ])

        ctx = self.make_context(iterable=[1, 2, 3, 4])
        self.assert_result_matches(template, ctx, '1:0;2:1;3:2;4:3;')


def suite():
    import unittest
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ForLoopTestCase))
    return suite
