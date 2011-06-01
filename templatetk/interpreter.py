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
from templatetk.utils import missing
from templatetk import nodes


def _assign_name(node, value, context):
    context[node.name] = value


def _assign_tuple(node, value, context):
    values = tuple(value)
    if context.config.strict_tuple_unpacking and \
       len(values) != len(node.items):
        raise ValueError('Dimension mismatch on tuple unpacking')
    for subnode, item_val in izip(node.items, value):
        assign_to_context(subnode, item_val, context)


_node_assigners = {
    nodes.Name:         _assign_name,
    nodes.Tuple:        _assign_tuple
}


def assign_to_context(node, value, context):
    func = _node_assigners[node.__class__]
    assert node.can_assign() and func is not None, \
        'Cannot assign to %r' % node
    return func(node, value, context)


class ContextMixin(object):
    """Baseclass for native contexts and context adapters."""

    def push(self):
        raise NotImplementedError()

    def pop(self):
        raise NotImplementedError()

    def __setitem__(self, key, value):
        raise NotImplementedError()

    def __getitem__(self, key):
        raise NotImplementedError()

    def __contains__(self, key):
        raise NotImplementedError()

    def __iter__(self):
        return self.iterkeys()

    def resolve(self, key):
        try:
            return self[key]
        except KeyError:
            return self.config.undefined_variable(key)

    def iterkeys(self):
        raise NotImplementedError()

    def iteritems(self):
        for key in self.iterkeys():
            yield key, self[key]

    def itervalues(self):
        for key, value in self.iteritems():
            yield value

    def items(self):
        return list(self.iteritems())

    def keys(self):
        return list(self.iterkeys())

    def values(self):
        return list(self.itervalues())


class ContextAdapter(ContextMixin):
    """Can be used to convert the interface of a template engine's context
    object to the interface the interpreter expects.
    """

    def __init__(self, config, context):
        self.config = config
        self.context = context

    def __setitem__(self, key, value):
        self.context[key] = value

    def __getitem__(self, key):
        return self.context[key]

    def __contains__(self, key):
        return key in self.context


class Context(ContextMixin):
    """Data source and store for the interpreter."""

    def __init__(self, config):
        self.config = config
        self._variables = {}
        self._stacked = []

        # TODO: track push state per level?  (if if if for, outer three not
        # modified, no need to copy).  Push dicts into stack alternatively?
        # TODO: timing
        self._needs_push = 0

    def push(self):
        self._needs_push = True

    def pop(self):
        if self._needs_push > 0:
            self._needs_push -= 1
        else:
            self._variables = self._stacked.pop()

    def __setitem__(self, key, value):
        if self._needs_push > 0:
            for x in xrange(self._needs_push):
                self._stacked.append(self._variables.copy())
            self._needs_push = 0
        self._variables[key] = value

    def __getitem__(self, key):
        return self._variables[key]

    def __contains__(self, key):
        return key in self._variables

    def resolve(self, key):
        rv = self._variables.get(key, missing)
        if rv is not missing:
            return rv
        return self.config.undefined_variable(key)

    def iteritems(self):
        return self._variables.iteritems()

    def iterkeys(self):
        return self._variables.iterkeys()

    def itervalues(self):
        return self._variables.itervalues()


class Interpreter(NodeVisitor):
    """The interpreter can be used to evaluate a given ASTS.  Internally
    it is based on a generator model.  Statement nodes yield unicode
    chunks and can be evaluated one after another based on that.  Expression
    nodes return the result of their operation.
    """

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
            yield self.config.to_unicode(self.visit(node, context))

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
