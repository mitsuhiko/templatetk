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

from ..interpreter import Interpreter, BasicInterpreterState
from ..config import Config


class InterpreterTestCase(_basicexec.BasicExecTestCase):
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

    def iter_template_blocks(self, template, config):
        intrptr = Interpreter(config)
        return intrptr.iter_blocks(template.node,
                                   self.interpreter_state_class)


def suite():
    return _basicexec.make_suite(InterpreterTestCase, __name__)
