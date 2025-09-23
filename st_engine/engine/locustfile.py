"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import signal
import sys
import tempfile
import time
from typing import Any, Dict, Optional

import urllib3
from gevent import queue
from locust import HttpUser, between, events, task
from urllib3.exceptions import InsecureRequestWarning

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.base import (
    DEFAULT_PROMPT,
    DEFAULT_TIMEOUT,
    DEFAULT_WAIT_TIME_MAX,
    DEFAULT_WAIT_TIME_MIN,
)

# Local imports after path setup
from engine.core import (
    CertificateManager,
    ConfigManager,
    GlobalStateManager,
    ValidationManager,
)
from engine.request_processor import APIClient, PayloadBuilder
from utils.common import mask_sensitive_data
from utils.error_handler import ErrorResponse
from utils.logger import logger
from utils.stats_manager import StatsManager
from utils.token_counter import count_tokens

# Disable the specific InsecureRequestWarning from urllib3
urllib3.disable_warnings(InsecureRequestWarning)

# === SIGNAL HANDLING ===
# Flag to track if we're already in shutdown process
_shutdown_in_progress = False
custom_metrics_aggregated: Dict[str, Any] = {}
global_state = GlobalStateManager()
stats_manager = StatsManager()


def graceful_signal_handler(signum, frame):
    """
    Custom signal handler to gracefully handle SIGTERM when Locust is already shutting down.
    This prevents the "stopping state" exception from being raised.
    """
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return
    task_id = os.environ.get("TASK_ID", "unknown")
    task_logger = global_state.get_task_logger(task_id)
    _shutdown_in_progress = True

    try:
        # Ensure Worker process sends stats before exiting
        if hasattr(frame, "f_globals") and "environment" in frame.f_globals:
            env = frame.f_globals["environment"]
            try:
                from locust.runners import WorkerRunner

                is_worker = hasattr(env, "runner") and isinstance(
                    env.runner, WorkerRunner
                )
            except ImportError:
                is_worker = hasattr(env, "runner") and "WorkerRunner" in str(
                    type(env.runner)
                )

            if is_worker:
                task_logger.debug(
                    f"Worker process {os.getpid()} received signal {signum}, ensuring metrics are sent..."
                )
                try:
                    # Send emergency stats
                    stats_manager.send_stats_to_master(
                        env.runner,
                        reqs=0,  # Do not increment request count
                        completion_tokens=0,
                        all_tokens=0,
                    )
                    time.sleep(0.5)
                except Exception as e:
                    task_logger.error(f"Failed to send emergency metrics: {e}")
    except Exception as e:
        task_logger.warning(f"Error in graceful signal handler: {e}")

    # Restore default signal handler
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


# === LOCUST EVENT HOOKS ===
@events.init_command_line_parser.add_listener
def init_parser(parser):
    """Add custom command-line arguments to the Locust parser."""
    parser.add_argument(
        "--task-id",
        type=str,
        default="",
        help="The unique identifier for the test task.",
    )
    parser.add_argument(
        "--api_path", type=str, default="/chat/completions", help="API path to test."
    )
    parser.add_argument(
        "--headers", type=str, default="", help="Request headers in JSON format."
    )
    parser.add_argument(
        "--cookies", type=str, default="", help="Request cookies in JSON format."
    )
    parser.add_argument(
        "--request_payload", type=str, default="", help="Request payload."
    )
    parser.add_argument(
        "--model_name", type=str, default="", help="Name of the model to test."
    )

    parser.add_argument(
        "--stream_mode",
        type=str,
        default="True",
        help="Whether to use streaming responses.",
    )
    parser.add_argument(
        "--chat_type",
        type=int,
        default=0,
        help="Type of chat (e.g., text:0, multimodal:1).",
    )
    parser.add_argument(
        "--cert_file", type=str, default="", help="Path to the client certificate file."
    )
    parser.add_argument(
        "--key_file", type=str, default="", help="Path to the client private key file."
    )
    parser.add_argument(
        "--field_mapping",
        type=str,
        default="",
        help="Field mapping configuration for custom APIs",
    )
    parser.add_argument(
        "--user_prompt", type=str, default="", help="User prompt for the model"
    )
    parser.add_argument(
        "--test_data",
        type=str,
        default="",
        help="Custom test data in JSONL format or file path",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (used as fallback when start_time is unavailable)",
    )


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Initialize Locust configuration and setup environment."""

    if not environment.parsed_options:
        logger.warning(
            "No parsed options found in environment. Skipping configuration."
        )
        return

    options = environment.parsed_options
    task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = global_state.get_task_logger(task_id)

    # Register custom signal handler to handle graceful shutdown
    try:
        signal.signal(signal.SIGTERM, graceful_signal_handler)
        signal.signal(signal.SIGINT, graceful_signal_handler)
    except Exception as e:
        task_logger.warning(f"Failed to register custom signal handlers: {e}")

    try:
        # Update global config
        config = global_state.config
        config.task_id = task_id
        config.api_path = options.api_path
        config.request_payload = options.request_payload
        config.model_name = options.model_name
        config.user_prompt = options.user_prompt
        config.stream_mode = str(options.stream_mode).lower() in ("true", "1")
        config.chat_type = int(options.chat_type)
        config.cert_file = options.cert_file
        config.key_file = options.key_file
        config.field_mapping = options.field_mapping
        config.test_data = options.test_data
        config.duration = int(options.duration)

        # Parse and validate configuration
        config.headers = ConfigManager.parse_headers(options.headers, task_logger)
        config.cookies = ConfigManager.parse_cookies(options.cookies, task_logger)
        config.cert_config = CertificateManager.configure_certificates(
            config.cert_file, config.key_file, task_logger
        )

        # Validate configuration before proceeding
        if not ValidationManager.validate_config(config, task_logger):
            raise ValueError("Invalid configuration provided")

        # Initialize prompt queue
        if not hasattr(environment, "prompt_queue"):
            try:
                from utils.common import init_prompt_queue

                environment.prompt_queue = init_prompt_queue(
                    chat_type=options.chat_type,
                    test_data=options.test_data or "",
                    task_logger=task_logger,
                )
            except Exception as e:
                task_logger.error(f"Failed to initialize prompt queue: {e}")
                environment.prompt_queue = queue.Queue()

        environment.global_config = config
        masked_config = mask_sensitive_data(config.__dict__)
        global_state.start_time = time.time()

        # Register message handlers
        runner = environment.runner
        try:
            from locust.runners import MasterRunner

            if isinstance(runner, MasterRunner):

                def on_token_stats(environment, msg, **kwargs):
                    """Master received token stats from Worker"""
                    data = msg.data
                    stats_manager.update_stats(
                        reqs=data.get("reqs", 0),
                        completion_tokens=data.get("completion_tokens", 0),
                        all_tokens=data.get("all_tokens", 0),
                    )
                    task_logger.debug(f"[Master] Received stats from worker: {data}")

                runner.register_message("token_stats", on_token_stats)
        except Exception as e:
            task_logger.warning(f"Error registering message handlers: {e}")

    except Exception as e:
        task_logger.error(f"Error during Locust initialization: {e}", exc_info=True)
        raise


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Handle metrics aggregation when test stops"""
    try:
        from locust.runners import LocalRunner, MasterRunner

        task_logger = global_state.get_task_logger(global_state.config.task_id)
        runner = environment.runner

        # Only Master and LocalRunner need to output report
        if not isinstance(runner, (MasterRunner, LocalRunner)):
            return
        if isinstance(runner, MasterRunner):
            task_logger.info("Waiting for workers to finish reporting...")
            from utils.common import wait_time_for_stats_sync

            concurrent_users = os.getenv("LOCUST_CONCURRENT_USERS", "0")
            wait_time = wait_time_for_stats_sync(runner, int(concurrent_users))
            time.sleep(wait_time)

        final_stats = stats_manager.get_final_stats()
        task_id = global_state.config.task_id
        result_file = os.path.join(
            tempfile.gettempdir(), "locust_result", task_id, "result.json"
        )
        os.makedirs(os.path.dirname(result_file), exist_ok=True)

        # Get Locust standard stats
        try:
            locust_stats = stats_manager.get_locust_stats(task_id, environment.stats)
            task_logger.info(f"Locust stats: {locust_stats}")
        except Exception as e:
            task_logger.warning(f"Failed to get Locust stats: {e}")
            locust_stats = {}

        # Save results
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "custom_metrics": final_stats,
                    "locust_stats": locust_stats,
                },
                f,
                indent=4,
                ensure_ascii=False,
            )

        task_logger.info(f"Final statistics: {final_stats}")

    except Exception as e:
        task_logger.error(f"Error in on_test_stop: {e}", exc_info=True)


# === MAIN USER CLASS ===
class LLMTestUser(HttpUser):
    """A user class that simulates a client making requests to an LLM service."""

    wait_time = between(DEFAULT_WAIT_TIME_MIN, DEFAULT_WAIT_TIME_MAX)
    # Align FastHttp timeouts with previous requests timeout
    connection_timeout = DEFAULT_TIMEOUT
    network_timeout = DEFAULT_TIMEOUT
    socket_timeout = DEFAULT_TIMEOUT * 2
    # Class-level shared instances to reduce memory usage
    _shared_request_handler = None
    _shared_stream_handler = None

    def __init__(self, environment):
        """Initialize the LLMTestUser with environment and handlers.

        Args:
            environment: Locust environment object
        """
        super().__init__(environment)
        self.config = global_state.config
        self.task_logger = global_state.get_task_logger(self.config.task_id)

        # Use shared handlers to reduce memory footprint
        self.request_handler = self._get_request_handler()
        self.stream_handler = self._get_stream_handler()

    @classmethod
    def _get_request_handler(cls):
        """Get or create shared request handler."""
        if cls._shared_request_handler is None:
            config = global_state.config
            cls._shared_request_handler = PayloadBuilder(
                config, global_state.get_task_logger(config.task_id)
            )
        return cls._shared_request_handler

    @classmethod
    def _get_stream_handler(cls):
        """Get or create shared stream handler."""
        if cls._shared_stream_handler is None:
            config = global_state.config
            cls._shared_stream_handler = APIClient(
                config, global_state.get_task_logger(config.task_id)
            )
        return cls._shared_stream_handler

    def get_next_prompt(self) -> Dict[str, Any]:
        """Fetch the next prompt from the shared queue."""
        try:
            # Use a more robust queue implementation
            if (
                hasattr(self.environment, "prompt_queue")
                and not self.environment.prompt_queue.empty()
            ):
                prompt_data = self.environment.prompt_queue.get_nowait()
                # Put back into queue for other users
                self.environment.prompt_queue.put_nowait(prompt_data)
                return prompt_data
            else:
                return {"id": "default", "prompt": DEFAULT_PROMPT}
        except queue.Empty:
            self.task_logger.warning("Prompt queue is empty. Using default prompt.")
            return {"id": "default", "prompt": DEFAULT_PROMPT}
        except Exception as e:
            self.task_logger.error(
                f"Error accessing prompt queue: {e}. Using default prompt."
            )
            return {"id": "default", "prompt": DEFAULT_PROMPT}

    def _log_token_counts(
        self,
        user_prompt: str,
        reasoning_content: str,
        content: str,
        usage: Optional[Dict[str, Optional[int]]] = None,
    ) -> None:
        """Record token counts"""
        try:
            model_name = self.config.model_name or ""
            user_prompt = user_prompt or ""
            reasoning_content = reasoning_content or ""
            content = content or ""

            def extract_token_from_usage(usage, keywords):
                """Extract the first valid integer value from the usage dictionary using fuzzy matching by keywords"""
                if not isinstance(usage, dict):
                    return 0
                for key in usage:
                    if any(kw in str(key).lower() for kw in keywords):
                        val = usage[key]
                        if isinstance(val, int) and val >= 0:
                            return val
                return 0

            input_tokens = completion_tokens = total_tokens = 0

            # Try to extract from usage
            if usage:
                input_tokens = extract_token_from_usage(usage, ["input", "prompt"])
                completion_tokens = extract_token_from_usage(
                    usage, ["output", "completion"]
                )
                total_tokens = extract_token_from_usage(usage, ["total", "all"])

                # Ensure total_tokens consistency
                total_tokens = input_tokens + completion_tokens

            # If completion_tokens is 0 and there is content to calculate, fallback to manual calculation
            if completion_tokens == 0 and (content or reasoning_content):
                input_tokens = (
                    count_tokens(user_prompt, model_name) if user_prompt else 0
                )
                reasoning_content_tokens = (
                    count_tokens(reasoning_content, model_name)
                    if reasoning_content
                    else 0
                )
                content_tokens = count_tokens(content, model_name) if content else 0
                completion_tokens = reasoning_content_tokens + content_tokens
                total_tokens = input_tokens + completion_tokens

            if completion_tokens > 0 or total_tokens > 0:
                # Select statistics based on runner type
                runner = self.environment.runner
                try:
                    from locust.runners import LocalRunner, MasterRunner, WorkerRunner

                    if isinstance(runner, (MasterRunner, LocalRunner)):
                        # Single process or Master: directly update local statistics
                        stats_manager.update_stats(
                            reqs=1,
                            completion_tokens=completion_tokens,
                            all_tokens=total_tokens,
                        )
                        if isinstance(runner, LocalRunner):
                            self.task_logger.debug(
                                f"[Standalone] Recorded stats: completion_tokens={completion_tokens}, all_tokens={total_tokens}"
                            )

                    elif isinstance(runner, WorkerRunner):
                        # Worker: send message to Master
                        stats_manager.send_stats_to_master(
                            runner,
                            reqs=1,
                            completion_tokens=completion_tokens,
                            all_tokens=total_tokens,
                        )

                    else:
                        # Unknown type: update local stats
                        stats_manager.update_stats(
                            reqs=1,
                            completion_tokens=completion_tokens,
                            all_tokens=total_tokens,
                        )
                        self.task_logger.warning(
                            f"[Warning] Unknown runner type: {type(runner)}"
                        )

                except Exception as e:
                    self.task_logger.error(f"Failed to update stats: {e}")
                    # Fallback: update global state
                    stats_manager.update_stats(
                        reqs=1,
                        completion_tokens=completion_tokens,
                        all_tokens=total_tokens,
                    )

        except Exception as e:
            self.task_logger.error(f"Failed to count tokens: {e}", exc_info=True)

    @task
    def chat_request(self):
        """Main Locust task that executes a single chat request."""
        needs_dataset = bool(self.config.test_data and self.config.test_data.strip())
        prompt_data = self.get_next_prompt() if needs_dataset else None

        base_request_kwargs, user_prompt = self.request_handler.prepare_request_kwargs(
            prompt_data
        )
        if not base_request_kwargs:
            self.task_logger.error(
                "Failed to generate request arguments. Skipping task."
            )
            return

        start_time = time.time()
        reasoning_content, content = "", ""
        usage: Dict[str, Optional[int]] = {
            "completion_tokens": None,
            "total_tokens": None,
        }
        request_name = base_request_kwargs.get("name", "failure")
        try:
            if self.config.stream_mode:
                reasoning_content, content, usage = (
                    self.stream_handler.handle_stream_request(
                        self.client, base_request_kwargs, start_time
                    )
                )
                # self.task_logger.debug(f"reasoning_content: {reasoning_content}")
                # self.task_logger.debug(f"content: {content}")
            else:
                reasoning_content, content, usage = (
                    self.stream_handler.handle_non_stream_request(
                        self.client, base_request_kwargs, start_time
                    )
                )
        except Exception as e:
            self.task_logger.error(f"Unhandled exception in chat_request: {e}")
            # Record the failure event for unhandled exceptions with enhanced context
            try:
                response_time = (
                    (time.time() - start_time) * 1000 if start_time is not None else 0
                )
            except Exception:
                response_time = 0

            ErrorResponse._handle_general_exception_event(
                error_msg=f"Unhandled exception in chat_request: {e}",
                response=None,
                response_time=response_time,
                additional_context={
                    "stream_mode": self.config.stream_mode,
                    "api_path": self.config.api_path,
                    "prompt_preview": (
                        str(user_prompt)[:100] if user_prompt else "No prompt"
                    ),
                    "task_id": self.config.task_id,
                    "request_name": request_name,
                },
            )

        if reasoning_content or content or usage:
            self._log_token_counts(user_prompt or "", reasoning_content, content, usage)

    def stop(self, force=False):
        """
        Override the default stop method to handle duplicate stop attempts gracefully.
        This prevents the "stopping state" exception when Locust receives multiple stop signals.
        """
        global _shutdown_in_progress

        # If we're already in shutdown process, return gracefully
        if _shutdown_in_progress:
            return

        # Check if user is already in stopping state
        if hasattr(self, "_state") and self._state == "stopping":
            return

        try:
            # Call the parent stop method with error handling
            super().stop(force=force)
        except Exception as e:
            # Handle the specific "stopping state" exception
            error_msg = str(e).lower()
            if "stopping" in error_msg or "unexpected state" in error_msg:
                # Mark as stopped to prevent further attempts
                if hasattr(self, "_state"):
                    self._state = "stopped"
            else:
                # Re-raise unexpected exceptions
                self.task_logger.error(f"Unexpected error during User.stop(): {e}")
                raise
