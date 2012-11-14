#!/usr/bin/env python
# coding=utf-8

"""
Copyright 2012 Load Impact

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../'))

from li_metrics_agent import PERF_DATA_OPTS_REGEX


def assertOptsMatchesExpected(self, opts, expected):
    perf_data_opts = {}
    for match in PERF_DATA_OPTS_REGEX.finditer(opts):
        perf_data_opts[match.group(1) if match.group(1) else match.group(2)] = match.group(3)
    self.assertEqual(perf_data_opts, expected,
                     '%s did\'t match expected %s'
                     % (repr(perf_data_opts), repr(expected)))


class ConfigPerfDataOptsParsingTests(unittest.TestCase):
    def test_single_metric_without_unit(self):
        assertOptsMatchesExpected(self, 'time', {'time': None})

    def test_single_metric_single_quoted_without_unit(self):
        assertOptsMatchesExpected(self, '\'time\'', {'time': None})

    def test_single_metric_double_quoted_without_unit(self):
        assertOptsMatchesExpected(self, '"time"', {'time': None})

    def test_single_metric_with_unit(self):
        assertOptsMatchesExpected(self, 'time:s', {'time': 's'})

    def test_single_metric_single_quoted_with_unit(self):
        assertOptsMatchesExpected(self, '\'time\':s', {'time': 's'})

    def test_single_metric_with_space_single_quoted_with_unit(self):
        assertOptsMatchesExpected(self, '\'long name\':s', {'long name': 's'})

    def test_single_metric_with_space_double_quoted_with_unit(self):
        assertOptsMatchesExpected(self, '"long name":s', {'long name': 's'})

    def test_multi_metric_without_unit_space_separator(self):
        assertOptsMatchesExpected(self, 'time size',
                                  {'time': None, 'size': None})

    def test_multi_metric_without_unit_single_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '\'time\' \'size\'',
                                  {'time': None, 'size': None})

    def test_multi_metric_without_unit_double_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '"time" "size"',
                                  {'time': None, 'size': None})

    def test_multi_metric_with_unit_space_separator(self):
        assertOptsMatchesExpected(self, 'time:s size:b',
                                  {'time': 's', 'size': 'b'})

    def test_multi_metric_with_unit_single_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '\'time\':s \'size\':b',
                                  {'time': 's', 'size': 'b'})

    def test_multi_metric_with_unit_double_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '"time":s "size":b',
                                  {'time': 's', 'size': 'b'})

    def test_multi_metric_mixed_unit_space_separator(self):
        assertOptsMatchesExpected(self, 'time size:b',
                                  {'time': None, 'size': 'b'})

    def test_multi_metric_mixed_unit_single_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '\'time\' \'size\':b',
                                  {'time': None, 'size': 'b'})

    def test_multi_metric_mixed_unit_double_quoted_space_separator(self):
        assertOptsMatchesExpected(self, '"time" "size":b',
                                  {'time': None, 'size': 'b'})
