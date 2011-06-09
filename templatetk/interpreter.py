# -*- coding: utf-8 -*-
"""
    templatetk.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~

    Interprets the abstract template syntax tree.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import operator
from itertools import izip, chain

from templatetk.nodeutils import NodeVisitor
from templatetk import nodes


def _assign_name(node, value, state):
    state.assign_var(node.name, value)


def _assign_tuple(node, value, state):
    try:
        values = tuple(value)
    except TypeError:
        if not state.config.allow_noniter_unpacking:
            raise
        return
    if state.config.strict_tuple_unpacking and \
       len(values) != len(node.items):
        raise ValueError('Dimension mismatch on tuple unpacking')
    for subnode, item_val in izip(node.items, value):
        assign_to_state(subnode, item_val, state)


_node_assigners = {
    nodes.Name:         _assign_name,
    nodes.Tuple:        _assign_tuple
}


def assign_to_state(node, value, state):
    func = _node_assigners[node.__class__]
    assert node.can_assign() and func is not None, \
        'Cannot assign to %r' % node
    return func(node, value, state)


class InterpreterState(object):

    def __init__(self, config):
        self.config = config

    def push_frame(self):
        pass

    def pop_frame(self):
        pass

    def assign_var(self, key, value):
        pass

    def resolve_var(self, key):
        pass


class BasicInterpreterState(InterpreterState):

    def __init__(self, config, context):
        self.config = config
        self.context = [context]

    def push_frame(self):
        self.context.append({})

    def pop_frame(self):
        self.context.pop()

    def assign_var(self, key, value):
        self.context[-1][key] = value

    def resolve_var(self, key):
        for d in reversed(self.context):
            if key in d:
                return d[key]
        return self.config.undefined_variable(key)


class Interpreter(NodeVisitor):
    """The interpreter can be used to evaluate a given ASTS.  Internally
    it is based on a generator model.  Statement nodes yield unicode
    chunks and can be evaluated one after another based on that.  Expression
    nodes return the result of their operation.
    """

    def __init__(self, config):
        NodeVisitor.__init__(self)
        self.config = config

    def evaluate(self, node, state):
        assert state.config is self.config, 'config mismatch'
        return self.visit(node, state)

    def assign_to_state(self, state, node, item):
        assert node.can_assign(), 'tried to assign to %r' % item
        items = tuple(item)
        if len(items) != len(self.items):
            raise ValueError('Error on tuple unpacking, dimensions dont match')
        for node, tuple_item in izip(self.items, items):
            node.assign_to_state(state, tuple_item)

    def visit_block(self, nodes, state):
        if nodes:
            for node in nodes:
                for event in self.visit(node, state):
                    yield event

    def visit_Template(self, node, state):
        for event in self.visit_block(node.body, state):
            yield event

    def visit_Output(self, node, state):
        for node in node.nodes:
            yield self.config.to_unicode(self.visit(node, state))

    def visit_Extends(self, node, state):
        raise NotImplementedError('add me, add me')

    def visit_For(self, node, state):
        parent = None
        if self.config.forloop_parent_access:
            parent = state.resolve_var(self.config.forloop_accessor)
        iterator = self.visit(node.iter, state)

        state.push_frame()
        iterated = False
        for item, loop_state in self.config.wrap_loop(iterator, parent):
            iterated = True
            state.assign_var(self.config.forloop_accessor, loop_state)
            assign_to_state(node.target, item, state)
            for event in self.visit_block(node.body, state):
                yield event
        state.pop_frame()

        if not iterated and node.else_ is not None:
            state.push_frame()
            for event in self.visit_block(node.else_, state):
                yield event
            state.pop_frame()

    def visit_If(self, node, state):
        test = self.visit(node.test, state)
        eventiter = ()
        if test:
            eventiter = self.visit_block(node.body, state)
        elif node.else_ is not None:
            eventiter = self.visit_block(node.else_, state)

        state.push_frame()
        for event in eventiter:
            yield event
        state.pop_frame()

    def visit_Name(self, node, state):
        assert node.ctx == 'load', 'visiting store nodes does not make sense'
        return state.resolve_var(node.name)

    def visit_Getattr(self, node, state):
        obj = self.visit(node.node, state)
        attr = self.visit(node.attr, state)
        return self.config.getattr(obj, attr)

    def visit_Getitem(self, node, state):
        obj = self.visit(node.node, state)
        attr = self.visit(node.arg, state)
        return self.config.getitem(obj, attr)

    def visit_Call(self, node, state):
        obj = self.visit(node.node, state)
        args = [self.visit(arg, state) for arg in node.args]
        kwargs = dict(self.visit(arg, state) for arg in node.kwargs)
        if node.dyn_args is not None:
            dyn_args = self.visit(node.dyn_args, state)
        else:
            dyn_args = ()
        if node.dyn_kwargs is not None:
            for key, value in self.visit(node.dyn_kwargs, state).iteritems():
                if key in kwargs:
                    raise TypeError('got multiple values for keyword '
                                    'argument %r' % key)
                kwargs[key] = value
        return obj(*chain(args, dyn_args), **kwargs)

    def visit_Keyword(self, node, state):
        return node.key, self.visit(node.value, state)

    def visit_Const(self, node, state):
        return node.value

    def binexpr(functor):
        def visitor(self, node, state):
            a = self.visit(node.left, state)
            b = self.visit(node.right, state)
            return functor(a, b)
        return visitor

    visit_Add = binexpr(operator.add)
    visit_Sub = binexpr(operator.sub)
    visit_Mul = binexpr(operator.mul)
    visit_Div = binexpr(operator.truediv)
    visit_FloorDiv = binexpr(operator.floordiv)
    visit_Mod = binexpr(operator.mod)
    visit_Pow = binexpr(operator.pow)
    del binexpr

    def visit_And(self, node, state):
        rv = self.visit(node.left, state)
        if not rv:
            return False
        return self.visit(node.right, state)

    def visit_Or(self, node, state):
        rv = self.visit(node.left, state)
        if rv:
            return rv
        return self.visit(node.right, state)

    def unary(functor):
        def visitor(self, node, state):
            return functor(self.visit(node.node, state))
        return visitor

    visit_Pos = unary(operator.pos)
    visit_Neg = unary(operator.neg)
    visit_Not = unary(operator.not_)
