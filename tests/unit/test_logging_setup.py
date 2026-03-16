from __future__ import annotations

import warnings

from duty_schedule.logging import setup_logging


class TestSetupLogging:
    def test_valid_level_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging("DEBUG")
            log_warnings = [x for x in w if "log level" in str(x.message).lower()]
            assert len(log_warnings) == 0

    def test_invalid_level_emits_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging("BOGUS")
            log_warnings = [x for x in w if "BOGUS" in str(x.message)]
            assert len(log_warnings) == 1
