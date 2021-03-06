# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2019-2021  Patryk Obara <patryk.obara@gmail.com>

"""
Log functions
"""

import os
import sys

PREFIX = 'boxtron:'

QUIET: bool = os.environ.get('BOXTRON_QUIET', '0') != '0'


def print_err(*value, sep=' ', end='\n', flush=False):
    """Prints the values to stderr."""
    if QUIET:
        return
    print(*value, sep=sep, end=end, file=sys.stderr, flush=flush)


def log(*value, sep=' ', end='\n', flush=False):
    """Prints the values to stderr with prefix."""
    print_err(PREFIX, *value, sep=sep, end=end, flush=flush)


def log_err(*value, sep=' ', end='\n', flush=False):
    """Prints the values to stderr with prefix and 'error:'"""
    log('error:', *value, sep=sep, end=end, flush=flush)


def log_warn(*value, sep=' ', end='\n', flush=False):
    """Prints the values to stderr with prefix and 'warning:'"""
    log('warning:', *value, sep=sep, end=end, flush=flush)
