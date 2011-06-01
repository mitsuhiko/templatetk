# -*- coding: utf-8 -*-
"""
    templatetk.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~

    Interprets the abstract template syntax tree.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from itertools import izip

from templatetk.nodeutils import NodeVisitor
from templatetk import nodes


def assign_to_context(node, value, context):
    func = _node_assigners[node.__class__]
    assert node.can_assign() and func is not None, \
        'Cannot assign to %r' % node
    return func(node, value, context)


def _assign_name(node, value, context):
    context[node.name] = value


def _assign_tuple(node, value, context):
    values = tuple(value)
    if len(values) != len(node.items):
        raise ValueError('Dimension mismatch on tuple unpacking')
    for subnode, item_val in izip(node.items, value):
        assign_to_context(subnode, item_val, context)


_node_assigners = {
    nodes.Name:         _assign_name,
    nodes.Tuple:        _assign_tuple
}


class Interpreter(NodeVisitor):

    def __init__(self, config):
        NodeVisitor.__init__(self)
        self.config = config

    def evaluate(self, node, context):
        assert context.config is self.config, 'config mismatch'
        return self.visit(node, context)

    def assign_to_context(self, context, node, item):
        assert node.can_assign(), 'tried to assign to %r' % item
        items = tuple(item)
        if len(items) != len(self.items):
            raise ValueError('Error on tuple unpacking, dimensions dont match')
        for node, tuple_item in izip(self.items, items):
            node.assign_to_context(context, tuple_item)

    def visit_block(self, nodes, context):
        if nodes:
            for node in nodes:
                for event in self.visit(node, context):
                    yield event

    def visit_Template(self, node, context):
        for event in self.visit_block(node.body, context):
            yield event

    def visit_Output(self, node, context):
        for node in node.nodes:
            yield unicode(self.visit(node, context))

    def visit_Extends(self, node, context):
        raise NotImplementedError('add me, add me')

    def visit_For(self, node, context):
        parent = None
        if self.config.forloop_parent_access:
            parent = context.get(self.config.forloop_accessor)
        iterator = self.visit(node.iter, context)

        context.push()
        iterated = False
        for item, loop_context in self.config.wrap_loop(iterator, parent):
            iterated = True
            context[self.config.forloop_accessor] = loop_context
            assign_to_context(node.target, item, context)
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

    def visit_Name(self, node, context):
        assert node.ctx == 'load', 'visiting store nodes does not make sense'
        return context.resolve(node.name)

    def visit_Getattr(self, node, context):
        obj = self.visit(node.node, context)
        attr = self.visit(node.attr, context)
        return self.config.getattr(obj, attr)

    def visit_Const(self, node, context):
        return node.value
