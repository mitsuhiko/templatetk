# -*- coding: utf-8 -*-
"""
    templatetk.interpreter
    ~~~~~~~~~~~~~~~~~~~~~~

    Interprets the abstract template syntax tree.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from itertools import izip, chain
from contextlib import contextmanager

from .nodeutils import NodeVisitor
from .runtime import RuntimeInfo
from .exceptions import TemplateNotFound
from . import nodes


empty_iter = iter(())


class InterpreterInternalException(BaseException):
    pass


class ContinueLoop(InterpreterInternalException):
    pass


class BreakLoop(InterpreterInternalException):
    pass


class StopExecutionException(InterpreterInternalException):
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
    runtime_info_class = RuntimeInfo

    def __init__(self, config, template_name, info=None, vars=None):
        self.config = config
        if info is None:
            info = self.make_runtime_info(template_name)
        self.info = info

    def make_runtime_info(self, template_name):
        return self.runtime_info_class(self.config, template_name)

    def evaluate_block(self, node, level=1):
        return self.info.evaluate_block(node.name, level, self)

    @contextmanager
    def frame(self):
        self.push_frame()
        try:
            yield
        finally:
            self.pop_frame()

    def push_frame(self):
        pass

    def pop_frame(self):
        pass

    def __getitem__(self, key):
        raise NotImplementedError()

    def __contains__(self, key):
        try:
            self.__getitem__(key)
            return True
        except KeyError:
            return False

    def __iter__(self):
        raise NotImplementedError()

    def resolve_var(self, key):
        try:
            return self.__getitem__(key)
        except KeyError:
            return self.config.undefined_variable(key)

    def assign_var(self, key, value):
        raise NotImplementedError('assigning variables')

    def get_template(self, template_name):
        return self.info.get_template(template_name)

    def get_or_select_template(self, template_name_or_list):
        return self.info.get_or_select_template(template_name_or_list)


class BasicInterpreterState(InterpreterState):

    def __init__(self, config, template_name=None, info=None, vars=None):
        InterpreterState.__init__(self, config, template_name, info, vars)
        self.context = []
        if vars is not None:
            self.context.append(vars)
        self.push_frame()
        self.toplevel = self.context[-1]

    def push_frame(self):
        self.context.append({})

    def pop_frame(self):
        self.context.pop()

    def assign_var(self, key, value):
        ctx = self.context[-1]
        ctx[key] = value
        if ctx is self.toplevel:
            self.info.exports[key] = value

    def __getitem__(self, key):
        for d in reversed(self.context):
            try:
                return d[key]
            except KeyError:
                continue
        raise KeyError(key)

    def __iter__(self):
        found = set()
        for d in reversed(self.context):
            for key in d:
                if key not in found:
                    found.add(key)
                    yield key


class Interpreter(NodeVisitor):
    """The interpreter can be used to evaluate a given ASTS.  Internally
    it is based on a generator model.  Statement nodes yield unicode
    chunks and can be evaluated one after another based on that.  Expression
    nodes return the result of their operation.
    """

    def __init__(self, config):
        NodeVisitor.__init__(self)
        self.config = config

    def resolve_call_args(self, node, state):
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
        return chain(args, dyn_args), kwargs

    def evaluate(self, node, state):
        assert state.config is self.config, 'config mismatch'
        return self.visit(node, state)

    def execute(self, node, state):
        try:
            for event in self.evaluate(node, state):
                yield event
        except StopExecutionException:
            pass
        except InterpreterInternalException, e:
            raise AssertionError('An interpreter internal exception '
                                 'was raised.  ASTS might be invalid. '
                                 'Got (%r)' % e)

    def make_block_executor(self, node, state_class):
        def executor(info, vars):
            state = state_class(info.config, info.template_name, info, vars)
            for event in self.visit_block(node.body, state):
                yield event
        return executor

    def visit_block(self, nodes, state):
        if nodes:
            for node in nodes:
                rv = self.visit(node, state)
                assert rv is not None, 'visitor for %r failed' % node
                for event in rv:
                    yield event

    def iter_blocks(self, node, state_class):
        for block in node.find_all(nodes.Block):
            yield block.name, self.make_block_executor(block, state_class)

    def visit_Template(self, node, state):
        for block, executor in self.iter_blocks(node, type(state)):
            state.info.register_block(block, executor)
        for event in self.visit_block(node.body, state):
            yield event

    def visit_Output(self, node, state):
        for node in node.nodes:
            yield self.config.to_unicode(self.visit(node, state))

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
        args, kwargs = self.resolve_call_args(node, state)
        return obj(*args, **kwargs)

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

    def visit_Filter(self, node, state):
        value = self.visit(node.node, state)
        args, kwargs = self.resolve_call_args(node, state)
        return state.info.call_filter(node.name, value, args, kwargs)

    def visit_Test(self, node, state):
        value = self.visit(node.node, state)
        args, kwargs = self.resolve_call_args(node, state)
        return state.info.call_test(node.name, value, args, kwargs)

    def visit_Slice(self, node, state):
        return slice(self.visit(node.start, state),
                     self.visit(node.stop, state),
                     self.visit(node.step, state))

    def visit_MarkSafe(self, node, state):
        return state.config.markup_type(self.visit(node.expr, state))

    def visit_MarkSafeIfAutoescape(self, node, state):
        value = self.visit(node.expr, state)
        if state.info.autoescape:
            value = state.config.markup_type(self.visit(node.expr, state))
        return value

    def visit_Scope(self, node, state):
        with state.frame():
            for event in self.visit_block(node.body, state):
                yield event

    def visit_ExprStmt(self, node, state):
        self.visit(node.node, state)
        return empty_iter

    def visit_Block(self, node, state):
        with state.frame():
            for event in state.evaluate_block(node):
                yield event

    def visit_Extends(self, node, state):
        template_name = self.visit(node.template, state)
        template = state.get_template(template_name)
        info = state.info.make_info(template, template_name, 'extends')
        for event in state.config.yield_from_template(template, info,
                                                      state):
            yield event
        raise StopExecutionException()

    def visit_FilterBlock(self, node, state):
        with state.frame():
            value = ''.join(self.visit_block(node.body, state))
            args, kwargs = self.resolve_call_args(node, state)
            yield state.info.call_filter(node.name, value, args, kwargs)

    def visit_Include(self, node, state):
        template_name = self.visit(node.template, state)
        try:
            template = state.get_or_select_template(template_name)
        except TemplateNotFound:
            if not node.ignore_missing:
                raise
            return
        info = state.info.make_info(template, template_name, 'include')
        for event in state.config.yield_from_template(template, info,
                                                      state):
            yield event

    def resolve_import(self, node, state):
        template_name = self.visit(node.template, state)
        template = state.get_template(template_name)
        info = state.info.make_info(template, template_name, 'import')
        gen = state.config.yield_from_template(template, info,
                                               state)
        return info.make_module(gen)

    def visit_Import(self, node, state):
        module = self.resolve_import(node, state)
        assign_to_state(node.target, module, state)
        return empty_iter

    def visit_FromImport(self, node, state):
        module = self.resolve_import(node, state)
        for item in node.items:
            name = self.visit(item.name, state)
            imported_object = state.config.resolve_from_import(module, name)
            assign_to_state(item.target, imported_object, state)
        return empty_iter
