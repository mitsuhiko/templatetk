# -*- coding: utf-8 -*-
"""
    templatetk.astutil
    ~~~~~~~~~~~~~~~~~~

    Provides utilities for the AST.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import ast


def to_sexpr(node):
    """Converts an AST into something that looks like sexpressions.  It's
    returning both lists and tuples to make it possible to reverse this
    without having to know what nodes expect.
    """
    if isinstance(node, list):
        return [to_sexpr(x) for x in node]
    if not isinstance(node, ast.AST):
        return ':', node
    rv = []
    rv.append(node.__class__.__name__)
    for field, value in ast.iter_fields(node):
        rv.append((field, to_sexpr(value)))
    if len(rv) == 1:
        return rv[0]
    return tuple(rv)


def from_sexpr(sexpr):
    """Reverse of :func:`to_sexpr`"""
    if isinstance(sexpr, list):
        return [from_sexpr(x) for x in sexpr]
    if not isinstance(sexpr, tuple):
        sexpr = (sexpr,)
    sexpriter = iter(sexpr)
    name = sexpriter.next()
    if name == ':':
        return sexpriter.next()
    rv = getattr(ast, str(name))()
    for field, val in sexpriter:
        setattr(rv, field, from_sexpr(val))
    return rv


def debug_ast(node):
    """Pretty prints the s-expression of an ast node."""
    from pprint import pformat
    return pformat(to_sexpr(node))


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
