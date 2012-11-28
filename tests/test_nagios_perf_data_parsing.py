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

from li_metrics_agent import NAGIOS_PERF_DATA_REGEX


def assertOutputMatchesExpected(self, output, expected):
    try:
        human_str, perf_data = output.split('|')
    except ValueError:
        perf_data = ''
    if not isinstance(expected, list):
        expected = [expected]
    for match, exp in zip(NAGIOS_PERF_DATA_REGEX.finditer(perf_data.strip()), expected):
        self.assertNotEquals(match, None, 'no match')
        groups = match.groups()
        self.assertEqual(groups, exp,
                         '%s did\'t match expected %s'
                         % (repr(groups), repr(exp)))


class NagiosPerfDataParsingTests(unittest.TestCase):
    def test_single_value_with_unit(self):
        output = 'DNS OK: 0.061 seconds response time. loadimpact.com returns 195.178.177.179|time=0.061025s'
        expected = ('time', '0.061025', 's', None, None, None, None)
        assertOutputMatchesExpected(self, output, expected)

    def test_single_value_with_unit_empty_levels_min(self):
        output = 'DNS OK: 0.061 seconds response time. loadimpact.com returns 195.178.177.179|time=0.061025s;;;0.000000'
        expected = ('time', '0.061025', 's', None, None, '0.000000', None)
        assertOutputMatchesExpected(self, output, expected)

    def test_single_value_with_unit_levels_min_max(self):
        output = 'DISK OK - free space: / 82415 MB (39% inode=89%);| /=127105MB;215734;210734;0;220734'
        expected = ('/', '127105', 'MB', '215734', '210734', '0', '220734')
        assertOutputMatchesExpected(self, output, expected)

    def test_single_value_without_unit(self):
        output = 'CRITICAL - load average: 0.18, 0.15, 0.12|load1=0.177'
        expected = ('load1', '0.177', None, None, None, None, None)
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_space_separator(self):
        output = 'POSTGRES_BACKENDS OK: (host:localhost) 4 of 100 connections (4%) | time=0.58 \'test1\'=2;90;95;0;100 \'test2\'=2;90;95;0;100 \'postgres\'=0;90;95;0;100 \'template0\'=0;90;95;0;100 \'template1\'=0;90;95;0;100'
        expected = [
            ('time', '0.58', None, None, None, None, None),
            ('test1', '2', None, '90', '95', '0', '100'),
            ('test2', '2', None, '90', '95', '0', '100'),
            ('postgres', '0', None, '90', '95', '0', '100'),
            ('template0', '0', None, '90', '95', '0', '100'),
            ('template1', '0', None, '90', '95', '0', '100'),
        ]
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_comma_separator(self):
        output = 'NTP OK: Offset 0.098886 secs|offset=0.098886, jitter=0,peer_stratum=2'
        expected = [
            ('offset', '0.098886', None, None, None, None, None),
            ('jitter', '0', None, None, None, None, None),
            ('peer_stratum', '2', None, None, None, None, None),
        ]
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_semicolon_separator(self):
        output = 'CPU OK | user=19298988;; nice=149448;; system=4921618;; idle=243377966;; iowait=4001050;; irq=173;; softirq=162305;; steal=0;; guest=0;;'
        expected = [
            ('user', '19298988', None, None, None, None, None),
            ('nice', '149448', None, None, None, None, None),
            ('system', '4921618', None, None, None, None, None),
            ('idle', '243377966', None, None, None, None, None),
            ('iowait', '4001050', None, None, None, None, None),
            ('irq', '173', None, None, None, None, None),
            ('softirq', '162305', None, None, None, None, None),
            ('steal', '0', None, None, None, None, None),
            ('guest', '0', None, None, None, None, None),
        ]
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_with_levels(self):
        output = 'QUEUE OK - queue_1187: 0; pa_queue: 0; v_queue: 0; ft_queue: 0; t_queue: 0; s_queue: 0; |length=0ITEMS;100;200;; length=0ITEMS;100;200;; length=0ITEMS;100;200;; length=0ITEMS;100;200;; length=0ITEMS;100;200;; length=0ITEMS;100;200;;'
        expected = [
            ('length', '0', 'ITEMS', '100', '200', None, None),
            ('length', '0', 'ITEMS', '100', '200', None, None),
            ('length', '0', 'ITEMS', '100', '200', None, None),
            ('length', '0', 'ITEMS', '100', '200', None, None),
            ('length', '0', 'ITEMS', '100', '200', None, None),
            ('length', '0', 'ITEMS', '100', '200', None, None),
        ]
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_space_separator_with_empty_levels_min(self):
        output = 'HTTP OK: HTTP/1.1 200 OK - 20242 bytes in 6.147 second response time |time=6.146574s;;;0.000000 size=20242B;;;0'
        expected = [
            ('time', '6.146574', 's', None, None, '0.000000', None),
            ('size', '20242', 'B', None, None, '0', None),
        ]
        assertOutputMatchesExpected(self, output, expected)

    def test_multi_value_semicolon_separator_with_levels_min(self):
        output = 'CRITICAL - load average: 0.18, 0.15, 0.12|load1=0.177;0.000;0.000;0; load5=0.155;0.000;0.000;0; load15=0.122;0.000;0.000;0;'
        expected = [
            ('load1', '0.177', None, '0.000', '0.000', '0', None),
            ('load5', '0.155', None, '0.000', '0.000', '0', None),
            ('load15', '0.122', None, '0.000', '0.000', '0', None),
        ]
        assertOutputMatchesExpected(self, output, expected)

if __name__ == '__main__':
    sys.exit(unittest.main())
