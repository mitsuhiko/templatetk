# -*- coding: utf-8 -*-
"""
    templatetk.testsuite._basicexec
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Some basic baseclasses for execution that are used by the interpreter
    and the compiled-code runner.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from . import TemplateTestCase
from .. import nodes
from ..config import Config
from ..exceptions import TemplateNotFound


class _SimpleTemplate(object):

    def __init__(self, template_name, node, test_case):
        self.template_name = template_name
        self.node = node
        self.test_case = test_case


class _CallOutContext(object):

    def __init__(self, lookup):
        self.lookup = lookup
        self.local_changes = {}

    def __getitem__(self, key):
        if key in self.local_changes:
            return self.local_changes[key]
        return self.lookup[key]

    def __setitem__(self, key, value):
        self.local_changes[key] = value


class BasicExecTestCase(TemplateTestCase):

    def assert_result_matches(self, node, ctx, expected, config=None):
        if config is None:
            config = Config()
        node.set_config(config)
        rv = u''.join(self.execute(node, ctx, config))
        self.assert_equal(rv, expected)

    def assert_template_fails(self, node, ctx, exception, config=None):
        if config is None:
            config = Config()
        node.set_config(config)
        with self.assert_raises(exception):
            for event in self.execute(node, ctx, config):
                pass

    def make_inheritance_config(self, templates):
        test_case = self

        class Module(object):

            def __init__(self, name, exports, contents):
                self.__dict__.update(exports)
                self.__name__ = name
                self.body = contents

        class CustomConfig(Config):
            def get_template(self, name):
                try:
                    return _SimpleTemplate(name, templates[name], test_case)
                except KeyError:
                    raise TemplateNotFound(name)
            def yield_from_template(self, template, info, vars=None):
                return template.test_case.execute(template.node, ctx=vars,
                                                  config=self, info=info)
            def iter_template_blocks(self, template):
                return test_case.iter_template_blocks(template, self)
            def make_module(self, template_name, exports, body):
                return Module(template_name, exports, ''.join(body))
            def make_callout_context(self, info, lookup):
                return _CallOutContext(lookup)
            def callout_context_changes(self, callout_context):
                return callout_context.local_changes.iteritems()
        return CustomConfig()

    def find_ctx_config(self, ctx, config, node):
        if config is None:
            config = node.config
            if config is None:
                config = Config()
        node.set_config(config)
        if ctx is None:
            ctx = {}
        return ctx, config

    def execute(self, node, ctx=None, config=None, info=None):
        ctx, config = self.find_ctx_config(ctx, config, node)
        return self._execute(node, ctx, config, info)

    def evaluate(self, node, ctx=None, config=None, info=None):
        ctx, config = self.find_ctx_config(ctx, config, node)
        return self._evaluate(node, ctx, config, info)

    def _execute(self, node, ctx, config, info):
        raise NotImplementedError()

    def _evaluate(self, node, ctx, config, info):
        raise NotImplementedError()

    def iter_template_blocks(self, template, config):
        raise NotImplementedError()


class IfConditionTestCase(object):

    def test_basic_if(self):
        n = nodes

        template = n.Template([
            n.If(n.Name('value', 'load'), [n.Output([n.Const('body')])],
                 [n.Output([n.Const('else')])])])

        self.assert_result_matches(template, dict(value=True), 'body')
        self.assert_result_matches(template, dict(value=False), 'else')

    def test_if_scoping(self):
        n = nodes

        template = n.Template([
            n.Output([n.Name('a', 'load'), n.Const(';')]),
            n.If(n.Const(True), [n.Assign(n.Name('a', 'store'), n.Const(23)),
                                 n.Output([n.Name('a', 'load')])], []),
            n.Output([n.Const(';'), n.Name('a', 'load')])])

        self.assert_result_matches(template, dict(a=42), '42;23;42')


class FilterBlockTestCase(object):

    def test_basic_filtering(self):
        n = nodes
        config = Config()
        config.get_filters = lambda: {'uppercase': lambda x: x.upper()}

        template = n.Template([
            n.FilterBlock([
                n.Output([n.Const('Hello '), n.Name('name', 'load')])
            ], 'uppercase', [], [], None, None)
        ])

        self.assert_result_matches(template, dict(name='World'), 'HELLO WORLD',
                                   config=config)

    def test_filter_scoping(self):
        n = nodes
        config = Config()
        config.get_filters = lambda: {'uppercase': lambda x: x.upper()}

        template = n.Template([
            n.FilterBlock([
                n.Output([n.Const('Hello '), n.Name('x', 'load'),
                          n.Const(';')]),
                n.Assign(n.Name('x', 'store'), n.Const(23)),
                n.Output([n.Name('x', 'load')])
            ], 'uppercase', [], [], None, None),
            n.Output([n.Const(';'), n.Name('x', 'load')])
        ])

        self.assert_result_matches(template, dict(x=42), 'HELLO 42;23;42',
                                   config=config)


class ForLoopTestCase(object):

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
                                    n.Const('index0')),
                          n.Const(';')])
            ], None)
        ])

        self.assert_result_matches(template, dict(
            iterable=[1, 2, 3, 4]
        ), '1:0;2:1;3:2;4:3;')

    def test_loop_with_custom_context(self):
        from ..runtime import LoopContextBase

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

    def test_loop_with_parent_access(self):
        config = Config()

        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Getattr(n.Name('loop', 'load'), n.Const('parent'))])
            ], None)
        ])

        self.assert_result_matches(template, dict(
            loop=42,
            iterable=[1]
        ), '42', config=config)

    def test_loop_else_body(self):
        config = Config()

        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Name('iterable', 'load'), [
                n.Output([n.Getattr(n.Name('loop', 'load'), n.Const('parent'))])
            ], [n.Output([n.Const('ELSE')])])
        ])

        self.assert_result_matches(template, dict(
            iterable=[]
        ), 'ELSE', config=config)

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

    def test_loop_controls(self):
        n = nodes
        template = n.Template([
            n.For(n.Name('item', 'store'), n.Const([1, 2, 3]), [
                n.Output([n.Name('item', 'load'), n.Const(';')]),
                n.If(n.Compare(n.Getattr(n.Name('loop', 'load'),
                                         n.Const('index0')),
                               [n.Operand('eq', n.Const(1))]), [n.Break()], [])
            ], [])])

        self.assert_result_matches(template, dict(), '1;2;')

        template = n.Template([
            n.For(n.Name('item', 'store'), n.Const([1, 2, 3]), [
                n.If(n.Compare(n.Getattr(n.Name('loop', 'load'),
                                         n.Const('index0')),
                               [n.Operand('eq', n.Const(1))]), [n.Continue()], []),
                n.Output([n.Name('item', 'load'), n.Const(';')])
            ], [])])

        self.assert_result_matches(template, dict(), '1;3;')

    def test_artifical_scope(self):
        n = nodes

        template = n.Template([
            n.Assign(n.Name('testing', 'store'), n.Const(42)),
            n.Output([n.Name('testing', 'load'), n.Const(';')]),
            n.Scope([
                n.Assign(n.Name('testing', 'store'), n.Const(23)),
                n.Output([n.Name('testing', 'load'), n.Const(';')])
            ]),
            n.Output([n.Name('testing', 'load'), n.Const(';')])
        ])

        self.assert_result_matches(template, dict(), '42;23;42;')

    def test_exprstmt(self):
        n = nodes
        called = []

        def testfunc():
            called.append(23)

        template = n.Template([
            n.ExprStmt(n.Call(n.Name('test', 'load'), [], [], None, None)),
            n.Output([n.Const('42')])
        ])

        self.assert_result_matches(template, dict(test=testfunc), '42')
        self.assert_equal(called, [23])


class ExpressionTestCase(object):

    def assert_expression_equals(self, node, expected, ctx=None, config=None):
        rv = self.evaluate(node, ctx, config)
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
            return n.Call(n.Name(func.__name__, 'load'), [], [], None, None)

        def not_called():
            not_called_buffer.append(42)

        test(n.And(n.Const(42), n.Const(23)), 23)
        test(n.And(n.Const(0), n.Const(23)), False)
        test(n.Or(n.Const(42), n.Const(23)), 42)
        test(n.Or(n.Const(0), n.Const(23)), 23)
        test(n.And(n.Const(0), simplecall(not_called)), False,
             ctx=dict(not_called=not_called))
        test(n.Or(n.Const(42), simplecall(not_called)), 42,
             ctx=dict(not_called=not_called))
        self.assert_equal(not_called_buffer, [])

    def test_unary(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Pos(n.Const(-42)), -42)
        test(n.Neg(n.Const(-42)), 42)
        test(n.Neg(n.Const(42)), -42)
        test(n.Not(n.Const(0)), True)
        test(n.Not(n.Const(42)), False)

    def test_general_expressions(self):
        n = nodes
        test = self.assert_expression_equals

        weird_getattr_config = Config()
        weird_getattr_config.getattr = lambda obj, attr: (obj, attr, 'attr')
        weird_getattr_config.getitem = lambda obj, item: (obj, item, 'item')

        test(n.Const(42), 42)
        test(n.Const("test"), "test")
        test(n.Getattr(n.Const('something'),
                       n.Const('the_attribute')),
             ('something', 'the_attribute', 'attr'),
             config=weird_getattr_config)
        test(n.Getitem(n.Const('something'),
                       n.Const('the_attribute')),
             ('something', 'the_attribute', 'item'),
             config=weird_getattr_config)

    def test_compare_expressions(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Compare(n.Const(1), [
            n.Operand('lt', n.Const(2)),
            n.Operand('lt', n.Const(3))
        ]), True)

        test(n.Compare(n.Const(1), [
            n.Operand('lt', n.Const(32)),
            n.Operand('lt', n.Const(3))
        ]), False)

        test(n.Compare(n.Const(42), [
            n.Operand('gt', n.Const(32)),
            n.Operand('lt', n.Const(100))
        ]), True)

        test(n.Compare(n.Const('test'), [
            n.Operand('in', n.Const('testing'))
        ]), True)

        test(n.Compare(n.Const('testing'), [
            n.Operand('notin', n.Const('test'))
        ]), True)

    def test_template_literal(self):
        n = nodes
        cfg = Config()

        rv = self.evaluate(n.TemplateData('Hello World!'), config=cfg)
        self.assert_equal(type(rv), cfg.markup_type)
        self.assert_equal(unicode(rv), 'Hello World!')

    def test_complex_literals(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Tuple([n.Const(1), n.Name('test', 'load')], 'load'), (1, 2),
             ctx=dict(test=2))
        test(n.List([n.Const(1), n.Name('test', 'load')]), [1, 2],
             ctx=dict(test=2))
        test(n.Dict([n.Pair(n.Const('foo'), n.Const('bar')),
                     n.Pair(n.Const('baz'), n.Const('blah'))]),
             dict(foo='bar', baz='blah'))

    def test_condexpr(self):
        n = nodes
        test = self.assert_expression_equals
        not_called_buffer = []

        def simplecall(func):
            return n.Call(n.Name(func.__name__, 'load'), [], [], None, None)

        def not_called():
            not_called_buffer.append(42)

        test(n.CondExpr(n.Const(1), n.Const(42), simplecall(not_called)), 42,
             ctx=dict(not_called=not_called))
        test(n.CondExpr(n.Const(0), simplecall(not_called), n.Const(23)), 23,
             ctx=dict(not_called=not_called))

        self.assert_equal(not_called_buffer, [])

    def test_call(self):
        n = nodes
        test = self.assert_expression_equals

        def foo(a, b, c, d):
            return a, b, c, d

        test(n.Call(n.Name('foo', 'load'), [n.Const(1)],
             [n.Keyword('c', n.Const(3))], n.Const((2,)),
             n.Const({'d': 4})), (1, 2, 3, 4), ctx=dict(foo=foo))

        test(n.Call(n.Name('foo', 'load'), [n.Const(1), n.Const(2)],
             [n.Keyword('c', n.Const(3))], None,
             n.Const({'d': 4})), (1, 2, 3, 4), ctx=dict(foo=foo))

        test(n.Call(n.Name('foo', 'load'), [n.Const(1)],
             [n.Keyword('c', n.Const(3))], None,
             n.Const({'b': 2, 'd': 4})), (1, 2, 3, 4), ctx=dict(foo=foo))

        self.assert_template_fails(n.Template(
            n.Output([n.Call(n.Name('foo', 'load'), [n.Const(1)],
            [n.Keyword('c', n.Const(3))], None,
            n.Const({'c': 2, 'b': 23, 'd': 4}))])), ctx=dict(foo=foo),
            exception=TypeError)

    def test_filters(self):
        n = nodes
        test = self.assert_expression_equals

        config = Config()
        config.get_filters = lambda: {'uppercase': lambda x: x.upper()}

        test(n.Filter(n.Const('hello'), 'uppercase', [], [], None, None),
             'HELLO', config=config)

    def test_slicing(self):
        n = nodes
        test = self.assert_expression_equals

        test(n.Getitem(n.Const('Hello'), n.Slice(n.Const(1), n.Const(None),
                                                 n.Const(2))), 'el')
        test(n.Getitem(n.Const('Hello'), n.Slice(n.Const(None), n.Const(-1),
                                                 n.Const(1))), 'Hell')
        test(n.Getitem(n.Const('Hello'), n.Slice(n.Const(None), n.Const(-1),
                                                 n.Const(None))), 'Hell')

    def test_mark_safe(self):
        n = nodes
        cfg = Config()

        rv = self.evaluate(n.MarkSafe(n.Const('<Hello World!>')), config=cfg)
        self.assert_equal(type(rv), cfg.markup_type)
        self.assert_equal(unicode(rv), '<Hello World!>')

    def test_mark_safe_if_autoescape(self):
        n = nodes

        cfg = Config()
        cfg.get_autoescape_default = lambda x: False
        rv = self.evaluate(n.MarkSafeIfAutoescape(n.Const('<Hello World!>')), config=cfg)
        self.assert_not_equal(type(rv), unicode)
        self.assert_equal(unicode(rv), '<Hello World!>')

        cfg = Config()
        cfg.get_autoescape_default = lambda x: True
        rv = self.evaluate(n.MarkSafeIfAutoescape(n.Const('<Hello World!>')),
                           config=cfg)
        self.assert_equal(type(rv), cfg.markup_type)
        self.assert_equal(unicode(rv), '<Hello World!>')


class InheritanceTestCase(object):

    def test_blocks(self):
        n = nodes

        index_template = n.Template([
            n.Assign(n.Name('foo', 'store'), n.Const(42)),
            n.Assign(n.Name('bar', 'store'), n.Const(23)),
            n.Block('the_block', [
                n.Output([n.Const('block contents')])
            ])
        ])

        self.assert_result_matches(index_template, dict(), 'block contents')

    def test_basic_inheritance(self):
        n = nodes

        index_template = n.Template([
            n.Extends(n.Const('layout.html')),
            n.Block('the_block', [
                n.Output([n.Const('block contents')])
            ])
        ])
        layout_template = n.Template([
            n.Output([n.Const('before block;')]),
            n.Block('the_block', [n.Output([n.Const('default contents')])]),
            n.Output([n.Const(';after block')])
        ])

        config = self.make_inheritance_config({
            'index.html':       index_template,
            'layout.html':      layout_template
        })

        self.assert_result_matches(index_template, dict(),
            'before block;block contents;after block', config=config)


class IncludeTestCase(object):

    def test_basic_include(self):
        n = nodes

        index_template = n.Template([
            n.Output([n.Const('1\n')]),
            n.Include(n.Const('include.html'), False),
            n.Output([n.Const('\n2')])
        ])
        include_template = n.Template([
            n.Output([n.Const('A')]),
        ])

        config = self.make_inheritance_config({
            'index.html':       index_template,
            'include.html':     include_template
        })

        self.assert_result_matches(index_template, dict(),
            '1\nA\n2', config=config)

    def test_basic_include_ignore_missing(self):
        n = nodes

        index_template = n.Template([
            n.Output([n.Const('1\n')]),
            n.Include(n.Const('includemissing.html'), True),
            n.Output([n.Const('\n2')])
        ])
        include_template = n.Template([
            n.Output([n.Const('A')]),
        ])

        config = self.make_inheritance_config({
            'index.html':       index_template
        })

        self.assert_result_matches(index_template, dict(),
            '1\n\n2', config=config)


class ImportTestCase(object):

    def test_basic_imports(self):
        n = nodes

        index_template = n.Template([
            n.Import(n.Const('import.html'), n.Name('foo', 'store')),
            n.Output([n.Getattr(n.Name('foo', 'load'), n.Const('bar'))])
        ])
        import_template = n.Template([
            n.Assign(n.Name('bar', 'store'), n.Const(42))
        ])

        config = self.make_inheritance_config({
            'index.html':       index_template,
            'import.html':      import_template
        })

        self.assert_result_matches(index_template, dict(),
            '42', config=config)

    def test_from_imports(self):
        n = nodes

        index_template = n.Template([
            n.FromImport(n.Const('import.html'), [
                n.FromImportItem(n.Name('foo', 'store'), n.Const('foo')),
                n.FromImportItem(n.Name('x', 'store'), n.Const('bar'))]),
            n.Output([n.Name('foo', 'load'), n.Const('|'), n.Name('x', 'load')])
        ])
        import_template = n.Template([
            n.Assign(n.Name('foo', 'store'), n.Const(42)),
            n.Assign(n.Name('bar', 'store'), n.Const(23))
        ])

        config = self.make_inheritance_config({
            'index.html':       index_template,
            'import.html':      import_template
        })

        self.assert_result_matches(index_template, dict(),
            '42|23', config=config)


class FunctionTestCase(object):

    def test_basic_function(self):
        n = nodes

        t = n.Template([
            n.Assign(n.Name('test', 'store'), n.Function(n.Const('test'),
                [n.Name('x', 'param')], [], [
                n.Output([n.Const('x: '), n.Name('x', 'load')])
            ])),
            n.Output([n.Call(n.Name('test', 'load'), [n.Const(42)],
                             [], None, None)])
        ])

        self.assert_result_matches(t, dict(), 'x: 42')

    def test_as_expression(self):
        n = nodes

        t = n.Template([
            n.Output([n.Call(n.Function(n.Const('test'),
                [n.Name('x', 'param')], [], [
                n.Output([n.Const('x: '), n.Name('x', 'load')])
            ]), [n.Const(23)], [], None, None)])
        ])

        self.assert_result_matches(t, dict(), 'x: 23')

    def test_scoping(self):
        n = nodes

        t = n.Template([
            n.Assign(n.Name('y', 'store'), n.Const(42)),
            n.Output([n.Call(n.Function(n.Const('test'),
                [n.Name('x', 'param')], [], [
                n.Output([n.Name('y', 'load'), n.Const(' '),
                          n.Name('x', 'load')])
            ]), [n.Const(23)], [], None, None)])
        ])

        self.assert_result_matches(t, dict(), '42 23')

    def test_problematic_scoping(self):
        n = nodes

        t = n.Template([
            n.Assign(n.Name('test', 'store'), n.Function(n.Const('test'),
                [n.Name('x', 'param')], [], [
                n.Output([n.Name('y', 'load'), n.Const(' '),
                          n.Name('x', 'load')])
            ])),
            n.Output([n.Call(n.Name('test', 'load'), [n.Const(2)],
                             [], None, None), n.Const(' ')]),
            n.Assign(n.Name('y', 'store'), n.Const(3)),
            n.Output([n.Call(n.Name('test', 'load'), [n.Const(2)],
                             [], None, None)])
        ])

        self.assert_result_matches(t, dict(y=1), '1 2 3 2')


class CallOutTestCase(object):

    def test_basic_callout(self):
        def callback(context):
            old_var = context['var']
            context['var'] = 42
            yield unicode(old_var)

        n = nodes

        t = n.Template([
            n.Assign(n.Name('var', 'store'), n.Const(23)),
            n.CallOut(n.Name('callback', 'load')),
            n.Output([n.Const('|')]),
            n.Output([n.Name('var', 'load')])
        ])

        config = self.make_inheritance_config({})
        self.assert_result_matches(t, dict(callback=callback),
                                   '23|42', config=config)


def make_suite(test_class, module):
    import unittest

    def mixin(class_):
        return type(class_.__name__, (test_class, class_), {
            '__module__': module
        })

    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(mixin(IfConditionTestCase)))
    suite.addTest(unittest.makeSuite(mixin(ForLoopTestCase)))
    suite.addTest(unittest.makeSuite(mixin(FilterBlockTestCase)))
    suite.addTest(unittest.makeSuite(mixin(ExpressionTestCase)))
    suite.addTest(unittest.makeSuite(mixin(InheritanceTestCase)))
    suite.addTest(unittest.makeSuite(mixin(IncludeTestCase)))
    suite.addTest(unittest.makeSuite(mixin(ImportTestCase)))
    suite.addTest(unittest.makeSuite(mixin(FunctionTestCase)))
    suite.addTest(unittest.makeSuite(mixin(CallOutTestCase)))
    return suite
