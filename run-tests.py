import sys
import unittest
from unittest.loader import TestLoader
from templatetk.testsuite import suite

root_suite = suite()
common_prefix = 'templatetk.testsuite.'


def find_all_tests():
    suites = [suite()]
    while suites:
        s = suites.pop()
        try:
            suites.extend(s)
        except TypeError:
            yield s


class BetterLoader(TestLoader):

    def loadTestsFromName(self, name, module=None):
        if name == 'suite':
            return suite()
        for testcase in find_all_tests():
            testname = '%s.%s.%s' % (
                testcase.__class__.__module__,
                testcase.__class__.__name__,
                testcase._testMethodName
            )
            if testname == name:
                return testcase
            if testname.startswith(common_prefix):
                if testname[len(common_prefix):] == name:
                    return testcase
        print >> sys.stderr, 'Error: could not find testcase "%s"' % name
        sys.exit(1)


unittest.main(testLoader=BetterLoader(), defaultTest='suite')
