# -*- coding: utf-8 -*-
"""
    templatetk.bcinterp
    ~~~~~~~~~~~~~~~~~~~

    Provides basic utilities that help interpreting the bytecode that comes
    from the AST transformer.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from types import CodeType

from .asttransform import to_ast
from .astutil import compile_ast
from .nodes import Node


def encode_filename(filename):
    """Python requires filenames to be strings."""
    if isinstance(filename, unicode):
        return filename.encode('utf-8')
    return filename


def run_bytecode(code_or_node, filename=None):
    """Evaluates given bytecode, an AST node or an actual ATST node.  This
    returns a dictionary with the results of the toplevel bytecode execution.
    """
    if isinstance(code_or_node, Node):
        code_or_node = to_ast(code_or_node)
        if filename is None:
            filename = encode_filename(code_or_node.filename)
    if not isinstance(code_or_node, CodeType):
        if filename is None:
            filename = '<string>'
        code_or_node = compile_ast(code_or_node, filename)
    namespace = {}
    exec code_or_node in namespace
    return namespace


class RuntimeState(object):

    def __init__(self, context, config):
        self.context = context
        self.config = config

    def resolve_var(self, name):
        return self.context[name]
