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


empty_iter = iter(())


class InterpreterInternalException(BaseException):
    pass


class ContinueLoop(InterpreterInternalException):
    pass


class BreakLoop(InterpreterInternalException):
    pass


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
        try:
            return self.visit(node, state)
        except InterpreterInternalException, e:
            raise AssertionError('An interpreter internal exception '
                                 'was raised.  ASTS might be invalid. '
                                 'Got (%r)' % e)

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
                rv = self.visit(node, state)
                assert rv is not None, 'visitor for %r failed' % node
                for event in rv:
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
            try:
                iterated = True
                state.assign_var(self.config.forloop_accessor, loop_state)
                assign_to_state(node.target, item, state)
                for event in self.visit_block(node.body, state):
                    yield event
            except ContinueLoop:
                continue
            except BreakLoop:
                break
        state.pop_frame()

        if not iterated and node.else_ is not None:
            state.push_frame()
            for event in self.visit_block(node.else_, state):
                yield event
            state.pop_frame()

    def visit_Continue(self, node, state):
        raise ContinueLoop()

    def visit_Break(self, node, state):
        raise BreakLoop()

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

    def visit_Assign(self, node, state):
        assert node.target.ctx == 'store'
        value = self.visit(node.node, state)
        assign_to_state(node.target, value, state)
        return empty_iter

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

    def visit_TemplateData(self, node, state):
        return state.config.markup_type(node.data)

    def visit_Tuple(self, node, state):
        assert node.ctx == 'load'
        return tuple(self.visit(x, state) for x in node.items)

    def visit_List(self, node, state):
        return list(self.visit(x, state) for x in node.items)

    def visit_Dict(self, node, state):
        return dict(self.visit(x, state) for x in node.items)

    def visit_Pair(self, node, state):
        return self.visit(node.key, state), self.visit(node.value, state)

    def visit_CondExpr(self, node, state):
        if self.visit(node.test, state):
            return self.visit(node.true, state)
        return self.visit(node.false, state)

    def binexpr(node_class):
        functor = nodes.binop_to_func[node_class.operator]
        def visitor(self, node, state):
            a = self.visit(node.left, state)
            b = self.visit(node.right, state)
            return functor(a, b)
        return visitor

    visit_Add = binexpr(nodes.Add)
    visit_Sub = binexpr(nodes.Sub)
    visit_Mul = binexpr(nodes.Mul)
    visit_Div = binexpr(nodes.Div)
    visit_FloorDiv = binexpr(nodes.FloorDiv)
    visit_Mod = binexpr(nodes.Mod)
    visit_Pow = binexpr(nodes.Pow)
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

    def unary(node_class):
        functor = nodes.uaop_to_func[node_class.operator]
        def visitor(self, node, state):
            return functor(self.visit(node.node, state))
        return visitor

    visit_Pos = unary(nodes.Pos)
    visit_Neg = unary(nodes.Neg)
    visit_Not = unary(nodes.Not)
    del unary

    def visit_Compare(self, node, state):
        left = self.visit(node.expr, state)
        for op in node.ops:
            right = self.visit(op.expr, state)
            if not nodes.cmpop_to_func[op.op](left, right):
                return False
            left = right
        return True
