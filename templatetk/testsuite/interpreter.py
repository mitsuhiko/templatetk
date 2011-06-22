# -*- coding: utf-8 -*-
"""
    templatetk.testsuite.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests the AST interpreter.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from . import _basicexec

from . import TemplateTestCase
from ..interpreter import Interpreter, BasicInterpreterState
from ..config import Config


class _SimpleTemplate(object):

    def __init__(self, template_name, node, test_case):
        self.template_name = template_name
        self.node = node
        self.test_case = test_case


class InterpreterTestCase(TemplateTestCase):
    interpreter_state_class = BasicInterpreterState

    def make_interpreter_state(self, config, ctx, info=None):
        return self.interpreter_state_class(config, info=info, vars=ctx)

    def make_interpreter(self, config):
        return Interpreter(config)

    def make_interpreter_and_state(self, config, ctx, info):
        if config is None:
            config = Config()
        if ctx is None:
            ctx = {}
        state = self.make_interpreter_state(config, ctx, info)
        intrptr = self.make_interpreter(config)
        return intrptr, state

    def evaluate(self, node, ctx=None, config=None, info=None):
        intrptr, state = self.make_interpreter_and_state(config, ctx, info)
        return intrptr.evaluate(node, state)

    def execute(self, node, ctx=None, config=None, info=None):
        intrptr, state = self.make_interpreter_and_state(config, ctx, info)
        return intrptr.execute(node, state)

    def assert_result_matches(self, node, ctx, expected, config=None):
        rv = u''.join(self.execute(node, ctx, config))
        self.assert_equal(rv, expected)

    def assert_template_fails(self, node, ctx, exception, config=None):
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
                return _SimpleTemplate(name, templates[name], test_case)
            def yield_from_template(self, template, info, vars=None):
                return template.test_case.evaluate(template.node, ctx=vars,
                                                   config=self, info=info)
            def iter_template_blocks(self, template):
                intrptr = Interpreter(self)
                return intrptr.iter_blocks(template.node,
                                           test_case.interpreter_state_class)
            def make_module(self, template_name, exports, body):
                return Module(template_name, exports, ''.join(body))
        return CustomConfig()


def suite():
    return _basicexec.make_suite(InterpreterTestCase, __name__)
