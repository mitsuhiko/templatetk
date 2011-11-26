# -*- coding: utf-8 -*-
"""
    templatetk.fstate
    ~~~~~~~~~~~~~~~~~

    Provides an object that encapsulates the state in a frame.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from . import nodes
from .idtracking import IdentTracker, IdentManager


class FrameState(object):

    def __init__(self, config, parent=None, scope='soft',
                 ident_manager=None, root=False):
        assert scope in ('soft', 'hard'), 'unknown scope type'
        self.config = config
        self.parent = parent
        self.scope = scope

        # a map of all identifiers that are active for this current frame.
        # The key is the actual name in the source (y), the value is the
        # name of the local identifier (l_y_0 for instance).
        self.local_identifiers = {}

        # A set of all source names (y) that were referenced from an outer
        # scope at any point in the execution.
        self.from_outer_scope = set()

        # Like `local_identifiers` but also includes identifiers that were
        # referenced from an outer scope.
        self.referenced_identifiers = {}

        # Variables that need to have aliases set up.  The key is the
        # new local name (as in local_identifiers ie: l_y_1) and the value
        # is the old name (l_y_0)
        self.required_aliases = {}

        # variables that require lookup.  The key is the local id (l_y_0),
        # the value is the sourcename (y).
        self.requires_lookup = {}

        # A helper mapping that stores for each source name (y) the node
        # that assigns it.  This is used to to figure out if a variable is
        # assigned at the beginning of the block or later.  If the source
        # node is `None` it means the variable is assigned at the very top.
        self.unassigned_until = {}

        self.inner_functions = []
        self.inner_frames = []
        self.nodes = []
        if ident_manager is None:
            ident_manager = IdentManager()
        self.ident_manager = ident_manager
        self.root = root
        self.buffer = None

    def derive(self, scope='soft', record=True):
        rv = self.__class__(self.config, self, scope, self.ident_manager)
        if record:
            self.inner_frames.append(rv)
        return rv

    def analyze_identfiers(self, nodes):
        tracker = IdentTracker(self)
        for node in nodes:
            tracker.visit(node)
            self.nodes.append(node)

    def add_special_identifier(self, name):
        self.analyze_identfiers([nodes.Name(name, 'param')])

    def iter_vars(self, reference_node=None):
        found = set()
        for idmap in self.ident_manager.iter_identifier_maps(self):
            for name, local_id in idmap.iteritems():
                if name in found:
                    continue
                found.add(name)
                if reference_node is not None and \
                   self.var_unassigned(name, reference_node):
                    continue
                yield name, local_id

    def var_unassigned(self, name, reference_node):
        assigning_node = self.unassigned_until[name]
        # assigned on block start
        if assigning_node is None:
            return False

        for node in self.iter_frame_nodes():
            if node is reference_node:
                break
            if node is assigning_node:
                return False
        return True

    def iter_inner_referenced_vars(self):
        """Iterates over all variables that are referenced by any of the
        inner frame states from this frame state.  This way we can exactly
        know what variables need to be resolved by an outer frame.
        """
        for inner_frame in self.inner_frames:
            for name, local_id in inner_frame.referenced_identifiers.iteritems():
                if name not in inner_frame.from_outer_scope:
                    continue
                if local_id in inner_frame.required_aliases:
                    local_id = inner_frame.required_aliases[local_id]
                yield local_id, name

    def iter_frame_nodes(self):
        """Iterates over all nodes in the frame in the order they
        appear.
        """
        for node in self.nodes:
            yield node
            for child in node.iter_child_nodes():
                yield child

    def lookup_name(self, name, ctx):
        """Looks up a name to a generated identifier."""
        assert ctx in ('load', 'store', 'param'), 'unknown context'
        for idmap in self.ident_manager.iter_identifier_maps(self):
            if name not in idmap:
                continue
            if ctx != 'load' and idmap is not self.local_identifiers:
                raise AssertionError('tried to store to an identifier '
                                     'that does not have an alias in the '
                                     'identifier map.  Did you forget to '
                                     'analyze_identfiers()?')
            return idmap[name]

        raise AssertionError('identifier %r not found.  Did you forget to '
                             'analyze_identfiers()?' % name)

    def iter_required_lookups(self):
        """Return a dictionary with all required lookups."""
        rv = dict(self.requires_lookup)
        rv.update(self.iter_inner_referenced_vars())
        return rv.iteritems()
