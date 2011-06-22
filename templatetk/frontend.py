# -*- coding: utf-8 -*-
"""
    templatetk.frontend
    ~~~~~~~~~~~~~~~~~~~

    Basic interface to extend on for template evaluation.  This interface
    is recommended but not necessary.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

from .bcinterp import run_bytecode, RuntimeState
from .interpreter import Interpreter, BasicInterpreterState


class Template(object):

    def __init__(self, name, config):
        self.name = name
        self.config = config

    def render(self, context):
        return u''.join(self.execute(context))

    def execute(self, context):
        raise NotImplementedError()


class CompiledTemplate(Template):

    def __init__(self, name, config, code_or_node):
        Template.__init__(self, name, config)
        namespace = run_bytecode(code_or_node)
        self.root_func = namespace['root']

    def execute(self, context):
        rtstate = RuntimeState(context, self.config)
        return self.root_func(rtstate)


class InterpretedTemplate(Template):
    interpreter_state_class = BasicInterpreterState

    def __init__(self, name, config, node):
        Template.__init__(self, name, config)
        self.node = node

    def execute(self, context):
        state = self.interpreter_state_class(self.config, context)
        interpreter = Interpreter(self.config)
        return interpreter.execute(self.node, state)
