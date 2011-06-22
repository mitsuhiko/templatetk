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

from .nodeutils import NodeVisitor
from .astutil import fix_missing_locations
from . import nodes


try:
    import ast
    have_ast = True
except ImportError:
    have_ast = False


_context_target_map = {
    'store':        ast.Store,
    'param':        ast.Param,
    'load':         ast.Load
}


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

    def make_call(self, name, method, args):
        return ast.Call(ast.Attribute(ast.Name(name, ast.Load()),
                        method, ast.Load()), args, [], None, None)

    def make_render_func(self, name, lineno=None):
        body = [ast.Assign([ast.Name('config', ast.Store())],
                           ast.Attribute(ast.Name('rtstate', ast.Load()),
                                         'config', ast.Load()))]
        funcargs = ast.arguments([ast.Name('rtstate', ast.Param())], None,
                                 None, [])
        return ast.FunctionDef(name, funcargs, body, [], lineno=lineno)

    def make_target_context(self, ctx):
        return _context_target_map[ctx]()

    def make_const(self, val, fstate):
        if isinstance(val, (int, float, long)):
            return ast.Num(val)
        elif isinstance(val, basestring):
            return ast.Str(val)
        elif isinstance(val, tuple):
            return ast.Tuple([self.visit(x, fstate) for x in val])
        elif isinstance(val, list):
            return ast.List([self.visit(x, fstate) for x in val])
        elif isinstance(val, dict):
            return ast.Dict(self.make_const(val.keys(), fstate),
                            self.make_const(val.values(), fstate))
        elif val in (None, True, False):
            return ast.Name(str(val), ast.Load())
        assert 0, 'Unsupported constant value for compiler'

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
        rv.body = [root]
        return fix_missing_locations(rv)

    def visit_Output(self, node, fstate):
        return [ast.Expr(ast.Yield(self.make_call('config', 'to_unicode',
                [self.visit(child, fstate)]), lineno=child.lineno))
                for child in node.nodes]

    def visit_For(self, node, fstate):
        loop_fstate = fstate.derive()
        target = self.visit(node.target, fstate)
        iter = self.visit(node.iter, fstate)
        did_iterate = self.ident_manager.temporary()
        rv = ast.For(target, iter, [ast.Assign([ast.Name(did_iterate, ast.Store())],
                                                ast.Name('True', ast.Load()))], [],
                     lineno=node.lineno)
        rv.body.extend(self.visit_block(node.body, loop_fstate))
        self.inject_scope_code(loop_fstate, rv.body)
        # TODO: else_
        return [ast.Assign([ast.Name(did_iterate, ast.Store())],
                           ast.Name('False', ast.Load())), rv]

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

    def visit_Const(self, node, fstate):
        return self.make_const(node.value, fstate)
