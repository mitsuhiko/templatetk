# -*- coding: utf-8 -*-
"""
    templatetk.testsuite.astutil
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests AST utilities.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

import ast

from . import TemplateTestCase
from .. import astutil


class SExprTestCase(TemplateTestCase):

    def test_to_sexpr(self):
        node = ast.parse('''def test():
            foo = 1
            bar = 2
            meh = [1, 2, bar, foo]
            return [-x for x in meh]\
        ''')

        expected = ('Module',
        ('body',
         [('FunctionDef',
           ('name', (':', 'test')),
           ('args',
            ('arguments',
             ('args', []),
             ('vararg', (':', None)),
             ('kwarg', (':', None)),
             ('defaults', []))),
           ('body',
            [('Assign',
              ('targets', [('Name', ('id', (':', 'foo')), ('ctx', 'Store'))]),
              ('value', ('Num', ('n', (':', 1))))),
             ('Assign',
              ('targets', [('Name', ('id', (':', 'bar')), ('ctx', 'Store'))]),
              ('value', ('Num', ('n', (':', 2))))),
             ('Assign',
              ('targets', [('Name', ('id', (':', 'meh')), ('ctx', 'Store'))]),
              ('value',
               ('List',
                ('elts',
                 [('Num', ('n', (':', 1))),
                  ('Num', ('n', (':', 2))),
                  ('Name', ('id', (':', 'bar')), ('ctx', 'Load')),
                  ('Name', ('id', (':', 'foo')), ('ctx', 'Load'))]),
                ('ctx', 'Load')))),
             ('Return',
              ('value',
               ('ListComp',
                ('elt',
                 ('UnaryOp',
                  ('op', 'USub'),
                  ('operand',
                   ('Name', ('id', (':', 'x')), ('ctx', 'Load'))))),
                ('generators',
                 [('comprehension',
                   ('target',
                    ('Name', ('id', (':', 'x')), ('ctx', 'Store'))),
                   ('iter',
                    ('Name', ('id', (':', 'meh')), ('ctx', 'Load'))),
                   ('ifs', []))]))))]),
           ('decorator_list', []))]))

        self.assert_equal(astutil.to_sexpr(node), expected)

    def test_from_sexpr(self):
        node = ast.parse('''def test():
            foo = 1
            bar = 2
            meh = [1, 2, bar, foo]

            class Foo(object):
                pass

            return [-x for x in meh], Foo()\
        ''')

        node2 = astutil.from_sexpr(astutil.to_sexpr(node))
        expected = astutil.to_sexpr(node)
        got = astutil.to_sexpr(node2)
        self.assert_equal(expected, got)
        astutil.fix_missing_locations(node2)

        ns = {}
        exec compile(node2, '', 'exec') in ns
        something, obj = ns['test']()
        self.assert_equal(something, [-1, -2, -2, -1])
        self.assert_equal(obj.__class__.__name__, 'Foo')


def suite():
    import unittest

    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SExprTestCase))
    return suite
