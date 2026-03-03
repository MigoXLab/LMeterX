"""
Shared Stepped Load Shape for Locust load tests.

This module provides the SteppedLoadShape class that can be conditionally
activated by both LLM API and common API locustfiles via the LOAD_MODE
environment variable.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import math
import os
from typing import Optional, Tuple

from locust import LoadTestShape

from utils.logger import logger


class SteppedLoadShape(LoadTestShape):
    """
    Stepped load shape similar to JMeter Ultimate Thread Group.

    Pattern:
    - Start at ``step_start_users`` virtual users.
    - Every ``step_duration`` seconds, add ``step_increment`` users.
    - Once ``step_max_users`` is reached, sustain for ``step_sustain_duration``.
    - Then return None to signal test end.

    All parameters are read from environment variables set by the runner.
    """

    def __init__(self):
        """Initialize stepped load shape from environment variables."""
        super().__init__()
        self.step_start_users = int(os.environ.get("STEP_START_USERS", "1"))
        self.step_increment = int(os.environ.get("STEP_INCREMENT", "10"))
        self.step_duration = int(os.environ.get("STEP_DURATION", "30"))
        self.step_max_users = int(os.environ.get("STEP_MAX_USERS", "100"))
        self.step_sustain_duration = int(os.environ.get("STEP_SUSTAIN_DURATION", "60"))
        # Calculate the number of ramp-up steps (from start to just below max)
        self.num_steps = max(
            1,
            math.ceil(
                (self.step_max_users - self.step_start_users)
                / max(self.step_increment, 1)
            ),
        )
        # Total ramp phase time
        self.ramp_phase_time = self.num_steps * self.step_duration
        # Total test time
        self.total_time = self.ramp_phase_time + self.step_sustain_duration
        logger.debug(
            f"SteppedLoadShape initialized: start={self.step_start_users}, "
            f"increment={self.step_increment}, step_duration={self.step_duration}s, "
            f"max={self.step_max_users}, sustain={self.step_sustain_duration}s, "
            f"total_time={self.total_time}s"
        )

    def tick(self) -> Optional[Tuple[int, float]]:
        """Return (user_count, spawn_rate) or None to stop."""
        run_time = self.get_run_time()

        if run_time > self.total_time:
            return None  # Test complete

        if run_time <= self.ramp_phase_time:
            # Determine which step we are on
            current_step = int(run_time // self.step_duration)
            target_users = min(
                self.step_start_users + current_step * self.step_increment,
                self.step_max_users,
            )
        else:
            # Sustain phase at max users
            target_users = self.step_max_users

        # Use a high spawn rate to reach target quickly within each step
        spawn_rate = max(target_users, 1)
        return (target_users, float(spawn_rate))
