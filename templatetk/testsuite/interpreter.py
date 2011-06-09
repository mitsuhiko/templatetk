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
from templatetk.interpreter import Interpreter, BasicInterpreterState
from templatetk.config import Config


class InterpreterTestCase(TemplateTestCase):

    def assert_result_matches(self, node, ctx, expected, config=None):
        if config is None:
            config = Config()
        intrptr = Interpreter(config)
        state = BasicInterpreterState(intrptr.config, ctx)
        rv = u''.join(intrptr.evaluate(node, state))
        self.assert_equal(rv, expected)

    def assert_template_fails(self, node, ctx, exception, config=None):
        if config is None:
            config = Config()
        intrptr = Interpreter(config)
        state = BasicInterpreterState(intrptr.config, ctx)
        try:
            for item in intrptr.evaluate(node, state):
                pass
        except Exception, e:
            self.assert_equal(type(e), exception)
        else:
            self.fail('Expected exception of type %r' % exception.__name__)


class ForLoopTestCase(InterpreterTestCase):

    def test_basic_loop(self):
        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load')])
            ], None)
        ])

        self.assert_result_matches(template, dict(
            iterable=[1, 2, 3, 4]
        ), '1234')

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

        self.assert_result_matches(template, dict(
            iterable=[1, 2, 3, 4]
        ), '1:0;2:1;3:2;4:3;')

    def test_loop_with_custom_context(self):
        from templatetk.runtime import LoopContextBase
        class CustomLoopContext(LoopContextBase):
            def __call__(self):
                return unicode(self.index0)

        class MyConfig(Config):
            def wrap_loop(self, iterator, parent=None):
                return CustomLoopContext(iterator)

        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(':'),
                          n.Call(n.Name('loop', 'load'), [], [], None, None),
                          n.Const(';')])
            ], None)
        ])

        self.assert_result_matches(template, dict(
            iterable=[1, 2, 3, 4]
        ), '1:0;2:1;3:2;4:3;', config=MyConfig())

    def test_silent_loop_unpacking(self):
        config = Config()
        config.allow_noniter_unpacking = True
        config.undefined_variable = lambda x: '<%s>' % x

        n = nodes
        template = n.Template([
            n.For(n.Tuple([n.Name('item', 'store'), n.Name('whoop', 'store')],
                          'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(';')])
            ], None)
        ])

        self.assert_result_matches(template, dict(
            iterable=[1, 2, 3, 4]
        ), '<item>;<item>;<item>;<item>;', config=config)

    def test_loud_loop_unpacking(self):
        config = Config()
        config.allow_noniter_unpacking = False

        n = nodes
        template = n.Template([
            n.For(n.Tuple([n.Name('item', 'store'), n.Name('whoop', 'store')],
                          'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(';')])
            ], None)
        ])

        self.assert_template_fails(template, dict(iterable=[1, 2, 3]),
                                   exception=TypeError, config=config)

    def test_strict_loop_unpacking_behavior(self):
        config = Config()
        config.strict_tuple_unpacking = True

        n = nodes
        template = n.Template([
            n.For(n.Tuple([n.Name('item', 'store'), n.Name('whoop', 'store')],
                          'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(';')])
            ], None)
        ])

        self.assert_template_fails(template, dict(iterable=[(1, 2, 3)]),
                                   exception=ValueError, config=config)

    def test_lenient_loop_unpacking_behavior(self):
        config = Config()
        config.strict_tuple_unpacking = False
        config.undefined_variable = lambda x: '<%s>' % x

        n = nodes
        template = n.Template([
            n.For(n.Tuple([n.Name('item', 'store'), n.Name('whoop', 'store')],
                          'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(';'),
                          n.Name('whoop', 'load')])
            ], None)
        ])

        self.assert_result_matches(template, dict(iterable=[(1, 2, 3)]),
            '1;2', config=config)

        template = n.Template([
            n.For(n.Tuple([n.Name('item', 'store'), n.Name('whoop', 'store')],
                          'store'), n.Name('iterable', 'load'), [
                n.Output([n.Name('item', 'load'), n.Const(';'),
                          n.Name('whoop', 'load')])
            ], None)
        ])

        self.assert_result_matches(template, dict(iterable=[(1,)]),
            '1;<whoop>', config=config)


class ExpressionTestCase(InterpreterTestCase):

    def assert_expression_equals(self, node, expected, ctx=None, config=None):
        if config is None:
            config = Config()
        intrptr = Interpreter(config)
        if ctx is None:
            ctx = {}
        state = BasicInterpreterState(intrptr.config, ctx)
        rv = intrptr.evaluate(node, state)
        self.assert_equal(rv, expected)

    def test_basic_binary_arithmetic(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Add(n.Const(1), n.Const(1)), 2)
        test(n.Sub(n.Const(42), n.Const(19)), 23)
        test(n.Sub(n.Const(42), n.Const(19)), 23)
        test(n.Mul(n.Const(2), n.Name('var', 'load')), 6, ctx=dict(var=3))
        test(n.Mul(n.Const('test'), n.Const(3)), 'testtesttest')
        test(n.Div(n.Const(42), n.Const(2)), 21.0)
        test(n.Div(n.Const(42), n.Const(4)), 10.5)
        test(n.FloorDiv(n.Const(42), n.Const(4)), 10)
        test(n.Mod(n.Const(42), n.Const(4)), 2)
        test(n.Pow(n.Const(2), n.Const(4)), 16)

    def test_basic_binary_logicals(self):
        n = nodes
        test = self.assert_expression_equals
        not_called_buffer = []

        def simplecall(func):
            return n.Call(n.Name(func, 'load'), [], [], None, None)

        def not_called():
            not_called_buffer.append(42)

        test(n.And(n.Const(42), n.Const(23)), 23)
        test(n.And(n.Const(0), n.Const(23)), False)
        test(n.Or(n.Const(42), n.Const(23)), 42)
        test(n.Or(n.Const(0), n.Const(23)), 23)
        test(n.And(n.Const(0), simplecall(not_called)), False)
        test(n.Or(n.Const(42), simplecall(not_called)), 42)
        self.assert_equal(not_called_buffer, [])

    def test_unary(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Pos(n.Const(-42)), -42)
        test(n.Neg(n.Const(-42)), 42)
        test(n.Neg(n.Const(42)), -42)
        test(n.Not(n.Const(0)), True)
        test(n.Not(n.Const(42)), False)


def suite():
    import unittest
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ForLoopTestCase))
    suite.addTest(unittest.makeSuite(ExpressionTestCase))
    return suite
