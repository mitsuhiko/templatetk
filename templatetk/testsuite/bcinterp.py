# -*- coding: utf-8 -*-
"""
    templatetk.testsuite.bcinterp
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests the bytecode "interpreter".

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from . import _basicexec

from .. import nodes
from ..bcinterp import run_bytecode, RuntimeState


class BCInterpTestCase(_basicexec.BasicExecTestCase):

    def get_exec_namespace(self, node, ctx, config, info=None):
        rtstate = RuntimeState(ctx, config, 'dummy', info)
        return run_bytecode(node, '<dummy>'), rtstate

    def _execute(self, node, ctx, config, info):
        ns, rtstate = self.get_exec_namespace(node, ctx, config, info)
        ns['setup'](rtstate)
        return ns['root'](rtstate)

    def _evaluate(self, node, ctx, config, info):
        n = nodes
        node = n.Template(
            [n.Assign(n.Name('__result__', 'store'), node)], lineno=1
        ).set_config(config)
        ns, rtstate = self.get_exec_namespace(node, ctx, config)
        ns['setup'](rtstate)
        for event in ns['root'](rtstate):
            pass
        return rtstate.info.exports['__result__']


def suite():
    return _basicexec.make_suite(BCInterpTestCase, __name__)
