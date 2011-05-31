# -*- coding: utf-8 -*-
"""
    templatetk.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~

    Interprets the abstract template syntax tree.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from templatetk.nodeutils import NodeVisitor



class Interpreter(NodeVisitor):

    def __init__(self, config):
        self.config = config

    def evaluate(self, node, context):
        assert context.config is self.config, 'config mismatch'
        return self.visit(node, context)

    def visit_block(self, node, context):
        for listval in self.visit_list(node, context):
            for event in listval:
                yield event

    def visit_Template(self, node, context):
        self.visit(node.body, context)

    def visit_Output(self, node, context):
        for node in node.nodes:
            yield self.visit(node, context)

    def visit_Extends(self, node, context):
        raise NotImplementedError('add me, add me')

    def visit_For(self, node, context):
        parent = None
        if self.config.forloop_parent_access:
            parent = context.get(self.config.forloop_accessor)
        iterator = self.visit(node.iter, context)

        # TODO: jinja2 leftover, should this be expressed differently?
        if node.test is not None:
            context.push()
            filtered = []
            for item in iterator:
                node.target.assign_to_context(context, item)
                if self.visit(node.test, context):
                    filtered.append(item)
            context.pop()
            iterator = filtered

        context.push()
        iterated = False
        for loop_context, item in self.config.wrap_loop(iterator, parent):
            iterated = True
            context[self.config.forloop_accessor] = loop_context
            node.target.assign_to_context(context, item)
            for event in self.visit_block(node.body, context):
                yield event
        context.pop()

        if not iterated and node.else_ is not None:
            context.push()
            for event in self.visit_block(node.else_, context):
                yield event
            context.pop()

    def visit_If(self, node, context):
        test = self.visit(node.test, context)
        eventiter = ()
        if test:
            eventiter = self.visit_block(node.body, context)
        elif node.else_ is not None:
            eventiter = self.visit_block(node.else_, context)

        context.push()
        for event in eventiter:
            yield event
        context.pop()
