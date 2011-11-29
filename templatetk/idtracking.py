# -*- coding: utf-8 -*-
"""
    templatetk.idtracking
    ~~~~~~~~~~~~~~~~~~~~~

    Tracks how identifiers are being used in a frame.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from .nodeutils import NodeVisitor


class IdentTracker(NodeVisitor):
    """A helper class that tracks the usage of identifiers."""

    def __init__(self, frame):
        NodeVisitor.__init__(self)
        self.frame = frame

    def visit_Name(self, node):
        from_outer_scope = False
        reused_local_id = False
        local_id = None

        for idmap in self.frame.ident_manager.iter_identifier_maps(self.frame):
            if node.name not in idmap:
                continue
            local_id = idmap[node.name]
            reused_local_id = True
            if idmap is not self.frame.local_identifiers:
                from_outer_scope = True
                if node.ctx != 'load':
                    old = local_id
                    local_id = self.frame.ident_manager.override(node.name)
                    self.frame.required_aliases[local_id] = old
            break

        if local_id is None:
            local_id = self.frame.ident_manager.encode(node.name)

        if node.ctx != 'load' or not reused_local_id:
            self.frame.local_identifiers[node.name] = local_id
            unassigned_until = node.ctx != 'param' and node or None
            self.frame.unassigned_until[node.name] = unassigned_until
        if node.ctx == 'load' and not reused_local_id:
            self.frame.requires_lookup[local_id] = node.name
            self.frame.unassigned_until[node.name] = None

        self.frame.referenced_identifiers[node.name] = local_id
        if from_outer_scope:
            self.frame.from_outer_scope.add(node.name)

    def visit_For(self, node):
        self.visit(node.iter)

    def visit_If(self, node):
        self.visit(node.test)

    def vist_Block(self):
        pass

    def visit_Function(self, node):
        self.visit(node.name)
        for arg in node.defaults:
            self.visit(arg)

    def visit_FilterBlock(self, node):
        for arg in node.args:
            self.visit(arg)
        for kwarg in node.kwargs:
            self.visit(kwarg)
        if node.dyn_args is not None:
            self.visit(node.dyn_args)
        if node.dyn_kwargs is not None:
            self.visit(node.dyn_kwargs)


class IdentManager(object):

    def __init__(self, short_ids=False):
        self.index = 1
        self.short_ids = short_ids

    def next_num(self):
        num = self.index
        self.index += 1
        return num

    def override(self, name):
        return self.encode(name, self.next_num())

    def encode(self, name, suffix=0):
        if self.short_ids:
            return 'l%d' % self.next_num()
        return 'l_%s_%d' % (name, suffix)

    def decode(self, name):
        if self.short_ids:
            raise RuntimeError('Cannot decode with short ids')
        if name[:2] != 'l_':
            return False
        return name[2:].rsplit('_', 1)[0]

    def iter_identifier_maps(self, start, stop_at_hard=True):
        ptr = start
        while ptr is not None:
            yield ptr.local_identifiers
            if stop_at_hard and ptr.scope == 'hard':
                break
            ptr = ptr.parent

    def temporary(self):
        return 't%d' % self.next_num()
