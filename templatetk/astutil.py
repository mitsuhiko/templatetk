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
    if isinstance(node, list):
        return [to_sexpr(x) for x in node]
    if not isinstance(node, ast.AST):
        return node
    rv = []
    rv.append(node.__class__.__name__)
    for field, value in ast.iter_fields(node):
        rv.append((field, to_sexpr(value)))
    if len(rv) == 1:
        return rv[0]
    return tuple(rv)


def debug_ast(node):
    from pprint import pformat
    return pformat(to_sexpr(node))
