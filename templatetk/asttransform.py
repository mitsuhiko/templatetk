# -*- coding: utf-8 -*-
"""
    templatetk.asttransform
    ~~~~~~~~~~~~~~~~~~~~~~~

    This module turns an ASTS into a regular Python ast for compilation.
    The generated AST is not a regular AST but will have all the template
    logic encapsulated in a function named 'root'.  If the ast is compiled
    and evaluated against a dictionary, that function can be cached::

        def compile_template(node):
            namespace = {}
            ast = to_ast(node, node.config)
            code = compile(ast, node.filename.encode('utf-8'), 'expr')
            exec code in namespace
            return namespace['root']

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from . import nodes
from .nodeutils import NodeVisitor


try:
    import ast
    have_ast = True
except ImportError:
    import _ast as ast
    have_ast = False


_context_target_map = {
    'store':        ast.Store,
    'param':        ast.Param,
    'load':         ast.Load
}


_cmpop_to_ast = {
    'eq':       ast.Eq,
    'ne':       ast.NotEq,
    'gt':       ast.Gt,
    'gteq':     ast.GtE,
    'lt':       ast.Lt,
    'lteq':     ast.LtE,
    'in':       ast.In,
    'notin':    ast.NotIn
}


def fix_missing_locations(node):
    def _fix(node, lineno, col_offset):
        if 'lineno' in node._attributes:
            if getattr(node, 'lineno', None) is None:
                node.lineno = lineno
            else:
                lineno = node.lineno
        if 'col_offset' in node._attributes:
            if getattr(node, 'col_offset', None) is None:
                node.col_offset = col_offset
            else:
                col_offset = node.col_offset
        for child in ast.iter_child_nodes(node):
            _fix(child, lineno, col_offset)
    _fix(node, 1, 0)
    return node


class IdentManager(object):

    def __init__(self):
        self.index = 1

    def next_num(self):
        num = self.index
        self.index += 1
        return num

    def override(self, name):
        return self.encode(name, self.next_num())

    def encode(self, name, suffix=0):
        return 'l_%s_%d' % (name, suffix)

    def decode(self, name):
        if name[:2] != 'l_':
            return False
        return name[2:].rsplit('_', 1)[0]

    def iter_identifier_maps(self, start):
        ptr = start
        while ptr is not None:
            yield ptr.local_identifiers
            ptr = ptr.parent

    def temporary(self):
        return 't_%d' % self.next_num()


class FrameState(object):

    def __init__(self, config, parent=None, scope='soft',
                 ident_manager=None, root=False):
        assert scope in ('soft', 'hard'), 'unknown scope type'
        self.config = config
        self.parent = parent
        self.scope = scope
        self.local_identifiers = {}
        self.required_aliases = {}
        self.requires_lookup = {}
        self.ident_manager = ident_manager
        self.root = root

    def derive(self, scope='soft'):
        return self.__class__(self.config, self, scope, self.ident_manager)

    def lookup_name(self, name, ctx):
        assert ctx in _context_target_map, 'unknown context'
        for idmap in self.ident_manager.iter_identifier_maps(self):
            if name in idmap:
                local_identifier = idmap[name]
                if idmap is not self.local_identifiers and ctx != 'load':
                    old = local_identifier
                    self.local_identifiers[name] = local_identifier = \
                        self.ident_manager.override(name)
                    self.required_aliases[local_identifier] = old
                return local_identifier

        local_identifier = self.ident_manager.encode(name)
        self.local_identifiers[name] = local_identifier
        if ctx == 'load':
            self.requires_lookup[local_identifier] = name
        return local_identifier


def to_ast(node):
    transformer = ASTTransformer(node.config)
    return transformer.transform(node)


class ASTTransformer(NodeVisitor):
    bcinterp_module = __name__.split('.')[0] + '.bcinterp'

    def __init__(self, config):
        NodeVisitor.__init__(self)
        if not have_ast:
            raise RuntimeError('Python 2.6 or later required for AST')
        self.config = config
        self.ident_manager = IdentManager()

    def transform(self, node):
        return self.visit(node, None)

    def visit_block(self, nodes, state):
        result = []
        if nodes:
            for node in nodes:
                rv = self.visit(node, state)
                assert rv is not None, 'visitor for %r failed' % node
                if isinstance(rv, ast.AST):
                    result.append(rv)
                else:
                    result.extend(rv)
        return result

    def make_call(self, name, method, args, lineno=None):
        return ast.Call(ast.Attribute(ast.Name(name, ast.Load()),
                        method, ast.Load()), args, [], None, None,
                        lineno=lineno)

    def make_render_func(self, name, lineno=None):
        body = [ast.Assign([ast.Name('config', ast.Store())],
                           ast.Attribute(ast.Name('rtstate', ast.Load()),
                                         'config', ast.Load()))]
        funcargs = ast.arguments([ast.Name('rtstate', ast.Param())], None,
                                 None, [])
        return ast.FunctionDef(name, funcargs, body, [], lineno=lineno)

    def make_target_context(self, ctx):
        return _context_target_map[ctx]()

    def make_cmp_op(self, opname):
        return _cmpop_to_ast[opname]()

    def make_name_tuple(self, target_tuple, as_ast=True):
        assert isinstance(target_tuple, nodes.Tuple)
        assert target_tuple.ctx in ('store', 'param')
        def walk(obj):
            rv = []
            for node in obj.items:
                if isinstance(node, nodes.Name):
                    val = node.name
                    if as_ast:
                        val = ast.Str(val)
                    rv.append(val)
                elif isinstance(node, nodes.Tuple):
                    rv.append(walk(node))
                else:
                    assert 0, 'unsupported assignment to %r' % node
            if as_ast:
                return ast.Tuple(rv, ast.Load())
            return tuple(rv)
        return walk(target_tuple)

    def make_const(self, val, fstate):
        if isinstance(val, (int, float, long)):
            return ast.Num(val)
        elif isinstance(val, basestring):
            return ast.Str(val)
        elif isinstance(val, tuple):
            return ast.Tuple([self.make_const(x, fstate) for x in val])
        elif isinstance(val, list):
            return ast.List([self.make_const(x, fstate) for x in val],
                            ast.Load())
        elif isinstance(val, dict):
            return ast.Dict(self.make_const(val.keys(), fstate),
                            self.make_const(val.values(), fstate))
        elif val in (None, True, False):
            return ast.Name(str(val), ast.Load())
        assert 0, 'Unsupported constant value for compiler'

    def make_runtime_imports(self):
        yield ast.ImportFrom(self.bcinterp_module,
                             [ast.alias('*', None)], 0)

    def inject_scope_code(self, fstate, body):
        before = []
        for alias, old_name in fstate.required_aliases.iteritems():
            before.append(ast.Assign([ast.Name(alias, ast.Store())],
                                     ast.Name(old_name, ast.Load())))

        for target, sourcename in fstate.requires_lookup.iteritems():
            before.append(ast.Assign([ast.Name(target, ast.Store())],
                self.make_call('rtstate', 'lookup_var',
                               [ast.Str(sourcename)])))

        body[:] = before + body

    def visit_Template(self, node, fstate):
        assert fstate is None, 'framestate passed to template visitor'
        fstate = FrameState(self.config, ident_manager=self.ident_manager,
                            root=True)
        rv = ast.Module(lineno=1)
        root = self.make_render_func('root')
        root.body.extend(self.visit_block(node.body, fstate))
        self.inject_scope_code(fstate, root.body)
        rv.body = list(self.make_runtime_imports()) + [root]
        return fix_missing_locations(rv)

    def visit_Output(self, node, fstate):
        return [ast.Expr(ast.Yield(self.make_call('config', 'to_unicode',
                [self.visit(child, fstate)]), lineno=child.lineno))
                for child in node.nodes]

    def visit_For(self, node, fstate):
        loop_fstate = fstate.derive()
        did_iterate = self.ident_manager.temporary()
        body = [ast.Assign([ast.Name(did_iterate, ast.Store())],
                           ast.Name('True', ast.Load()))]

        if (fstate.config.allow_noniter_unpacking or
            not fstate.config.strict_tuple_unpacking) and \
           isinstance(node.target, nodes.Tuple):
            iter_name = self.ident_manager.temporary()
            target = ast.Name(iter_name, ast.Store())
            body.append(ast.Assign([self.visit(node.target, loop_fstate)],
                ast.Call(ast.Name('lenient_unpack_helper', ast.Load()),
                         [ast.Name('config', ast.Load()),
                          ast.Name(iter_name, ast.Load()),
                          self.make_name_tuple(node.target)], [], None, None)))
        else:
            target = self.visit(node.target, loop_fstate)

        if self.config.forloop_parent_access:
            parent = self.visit(nodes.Name(self.config.forloop_accessor,
                                           'load'), fstate)
        else:
            parent = ast.Name('None', ast.Load())

        iter = self.visit(node.iter, fstate)
        wrapped_iter = self.make_call('config', 'wrap_loop', [iter, parent])

        loop_accessor = self.visit(nodes.Name(self.config.forloop_accessor,
                                              'store'), loop_fstate)
        tuple_target = ast.Tuple([target, loop_accessor], ast.Store())

        body.extend(self.visit_block(node.body, loop_fstate))
        self.inject_scope_code(loop_fstate, body)
        return [ast.Assign([ast.Name(did_iterate, ast.Store())],
                           ast.Name('False', ast.Load())),
                ast.For(tuple_target, wrapped_iter, body, [],
                        lineno=node.lineno)]

    def visit_Continue(self, node, fstate):
        return [ast.Continue(lineno=node.lineno)]

    def visit_Break(self, node, fstate):
        return [ast.Break(lineno=node.lineno)]

    def visit_If(self, node, fstate):
        test = self.visit(node.test, fstate)
        condition_fstate = fstate.derive()
        body = self.visit_block(node.body, condition_fstate)
        else_ = []
        if node.else_:
            else_ = self.visit_block(node.else_, condition_fstate)
        rv = [ast.If(test, body, else_)]
        self.inject_scope_code(condition_fstate, rv)
        return rv

    def visit_ExprStmt(self, node, fstate):
        return ast.Expr(self.visit(node.node, fstate), lineno=node.lineno)

    def visit_Scope(self, node, fstate):
        scope_fstate = fstate.derive()
        rv = list(self.visit_block(node.body, scope_fstate))
        self.inject_scope_code(scope_fstate, rv)
        return rv

    def visit_Name(self, node, fstate):
        name = fstate.lookup_name(node.name, node.ctx)
        ctx = self.make_target_context(node.ctx)
        return ast.Name(name, ctx)

    def visit_Assign(self, node, fstate):
        target = self.visit(node.target, fstate)
        expr = self.visit(node.node, fstate)
        if fstate.root and isinstance(target, ast.Name):
            yield ast.Expr(self.make_call('rtstate', 'export_var',
                                          [ast.Str(target.id), expr]))
        yield ast.Assign([target], expr, lineno=node.lineno)

    def visit_Getattr(self, node, fstate):
        obj = self.visit(node.node, fstate)
        attr = self.visit(node.attr, fstate)
        if node.ctx == 'load':
            return self.make_call('config', 'getattr', [obj, attr],
                                  lineno=node.lineno)
        return ast.Attribute(obj, attr, self.make_target_context(node.ctx),
                             lineno=node.lineno)

    def visit_Getitem(self, node, fstate):
        obj = self.visit(node.node, fstate)
        arg = self.visit(node.arg, fstate)
        if node.ctx == 'load':
            return self.make_call('config', 'getitem', [obj, arg],
                                  lineno=node.lineno)
        return ast.Subscript(obj, arg, self.make_target_context(node.ctx),
                             lineno=node.lineno)

    def visit_Call(self, node, fstate):
        obj = self.visit(node.node, fstate)
        args = [self.visit(x, fstate) for x in node.args]
        kwargs = [(self.visit(k, fstate), self.visit(v, fstate))
                  for k, v in node.kwargs]
        dyn_args = dyn_kwargs = None
        if node.dyn_args is not None:
            dyn_args = self.visit(dyn_args, fstate)
        if node.dyn_kwargs is not None:
            dyn_kwargs = self.visit(dyn_kwargs, fstate)
        return ast.Call(obj, args, kwargs, dyn_args, dyn_kwargs,
                        lineno=node.lineno)

    def visit_Const(self, node, fstate):
        return self.make_const(node.value, fstate)

    def visit_TemplateData(self, node, fstate):
        return self.make_call('config', 'markup_type', [ast.Str(node.data)],
                              lineno=node.lineno)

    def visit_Tuple(self, node, fstate):
        return ast.Tuple([self.visit(x, fstate) for x in node.items],
                         self.make_target_context(node.ctx))

    def visit_List(self, node, fstate):
        return ast.List([self.visit(x, fstate) for x in node.args],
                        self.make_target_context(node.ctx))

    def visit_Dict(self, node, fstate):
        keys = []
        values = []
        for pair in node.items:
            keys.append(self.visit(pair.key, fstate))
            values.append(self.visit(pair.value, fstate))
        return ast.Dict(keys, values, lineno=node.lineno)

    def visit_CondExpr(self, node, fstate):
        test = self.visit(node.test, fstate)
        true = self.visit(node.true, fstate)
        false = self.visit(node.false, fstate)
        return ast.IfExp(test, true, false, lineno=node.lineno)

    def binexpr(operator):
        def visitor(self, node, fstate):
            a = self.visit(node.left, fstate)
            b = self.visit(node.right, fstate)
            return ast.BinOp(a, operator(), b, lineno=node.lineno)
        return visitor

    visit_Add = binexpr(ast.Add)
    visit_Sub = binexpr(ast.Sub)
    visit_Mul = binexpr(ast.Mult)
    visit_Div = binexpr(ast.Div)
    visit_FloorDiv = binexpr(ast.FloorDiv)
    visit_Mod = binexpr(ast.Mod)
    visit_Pow = binexpr(ast.Pow)
    del binexpr

    def visit_And(self, node, fstate):
        left = self.visit(node.left, fstate)
        right = self.visit(node.right, fstate)
        return ast.BoolOp(ast.And(), [left, right], lineno=node.lineno)

    def visit_Or(self, node, fstate):
        left = self.visit(node.left, fstate)
        right = self.visit(node.right, fstate)
        return ast.BoolOp(ast.Or(), [left, right], lineno=node.lineno)

    def visit_Compare(self, node, fstate):
        left = self.visit(node.expr, fstate)
        ops = []
        comparators = []
        for op in node.ops:
            ops.append(self.make_cmp_op(op.op))
            comparators.append(self.visit(op.expr, fstate))
        return ast.Compare(left, ops, comparators, lineno=node.lineno)

    def unary(operator):
        def visitor(self, node, fstate):
            return ast.UnaryOp(operator(), self.visit(node.node, fstate),
                               lineno=node.lineno)
        return visitor

    visit_Pos = unary(ast.UAdd)
    visit_Neg = unary(ast.USub)
    visit_Not = unary(ast.Not)
    del unary
