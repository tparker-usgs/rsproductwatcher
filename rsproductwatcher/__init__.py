# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#  Purpose: keep an eye on remote sensing product generation
#   Author: Tom Parker
#
# -----------------------------------------------------------------------------
"""
rsproductwatcher
=========

Keep an eye on remote sensing product generation.

:license:
    CC0 1.0 Universal
    http://creativecommons.org/publicdomain/zero/1.0/
"""

import tomputils.util as tutil
from rsproductwatcher.version import __version__

logger = tutil.setup_logging("rsproductwatcher - errors")
