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


try:
    import ast
    have_ast = True
except ImportError:
    have_ast = False


class FrameState(object):

    def __init__(self, config):
        self.config = config
        self.parent = None


def to_ast(node, config):
    transformer = ASTTransformer(config)
    return transformer.transform(node, FrameState(config))


class ASTTransformer(NodeVisitor):

    def __init__(self, config):
        NodeVisitor.__init__(self)
        if not have_ast:
            raise RuntimeError('Python 2.6 or later required for AST')
        self.config = config

    def transform(self, node, fstate):
        assert fstate.config is self.config, 'config mismatch'
        return self.visit(node, fstate)

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

    def make_config_call(self, _method, args=None):
        return ast.Call(ast.Attribute(ast.Name('config', ast.Load()), ast.Load()),
                        [self.visit(x) for x in (args or ())], [], None, None)

    def make_render_func(self, name, lineno=None):
        body = [ast.Assign(ast.Name('config', ast.Store()),
                           ast.Attribute(ast.Name('rtstate', ast.Load()),
                                         'config', ast.Load()))]
        funcargs = ast.arguments([ast.Name('rtstate', ast.Param())], None,
                                 None, [])
        return ast.FunctionDef(name, funcargs, body, [], lineno=lineno)

    def visit_Template(self, node, fstate):
        rv = ast.Module(lineno=1)
        root = self.make_render_func('root')
        root.body.extend(self.visit_block(node.body, fstate))
        rv.body = [root]
        return ast.fix_missing_locations(rv)

    def visit_Output(self, node, fstate):
        for child in node.nodes:
            yield ast.Expr(self.make_config_call('to_unicode', [child]),
                           lineno=child.lineno)
