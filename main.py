"""Main initialisation module for the PowerController app."""

# Check that Python version is >= 3.13, else exit with error.
import signal
import sys
from threading import Event

from sc_utility import SCConfigManager, SCLogger

from config_schemas import ConfigSchema
from controller import PowerController
from local_enumerations import CONFIG_FILE
from shelly_worker import ShellyWorker
from thread_manager import RestartPolicy, ThreadManager
from webapp import create_flask_app, serve_flask_blocking


def main():
    """Main entry point for the PowerController app."""
    wake_event = Event()    # Wakes the main controller loop from a timed sleep
    stop_event = Event()    # Use to signal the main controller loop that the app is exiting

    if sys.version_info < (3, 13):  # noqa: UP036
        print(f"ERROR: Python 3.13 or higher is required. You are running {sys.version}", file=sys.stderr)
        sys.exit(1)

    # Get our default schema, validation schema, and placeholders.
    schemas = ConfigSchema()

    # Initialize the SC_ConfigManager class
    try:
        config = SCConfigManager(
            config_file=CONFIG_FILE,
            validation_schema=schemas.validation,
            placeholders=schemas.placeholders
        )
    except RuntimeError as e:
        print(f"Configuration file error: {e}", file=sys.stderr)
        return

    # Initialize the SC_Logger class
    try:
        logger = SCLogger(config.get_logger_settings())
        # Setup email
        logger.register_email_settings(config.get_email_settings())
    except (RuntimeError, TypeError, ValueError) as e:
        print(f"Logger initialisation error: {e}", file=sys.stderr)
        return
    else:
        logger.log_message("", "summary")
        logger.log_message("", "summary")
        logger.log_message("PowerController application starting.", "summary")

    # Now create instances of the main worked classes
    try:
        # Create an instance of the ShellyWorker class
        shelly_worker = ShellyWorker(config, logger, wake_event)

        # Create an instance of the main PowerController class which orchestrates the power control
        controller = PowerController(config, logger, shelly_worker, wake_event)

        flask_app = create_flask_app(controller, config, logger)
    except (RuntimeError, TypeError) as e:
        logger.log_fatal_error(f"Fatal error at startup: {e}")

    # Now start the thread manager and create our worker threads
    tm = ThreadManager(logger, global_stop=stop_event)

    tm.add(
        name="shelly",
        target=shelly_worker.run,
        restart=RestartPolicy(mode="on_crash", max_restarts=3, backoff_seconds=2.0),
        stop_event=stop_event,  # share global stop
    )

    # Manage the controller loop as a thread too
    tm.add(
        name="controller",
        target=controller.run,
        kwargs={"stop_event": stop_event},
        restart=RestartPolicy(mode="never"),
    )

    # Manage Flask as a blocking worker in its own managed thread
    tm.add(
        name="webapp",
        target=serve_flask_blocking,
        args=(flask_app, config, logger, stop_event),
        restart=RestartPolicy(mode="on_crash", max_restarts=3, backoff_seconds=2.0),
    )

    tm.start_all()

    # Handle SIGINT (Ctrl-C) to trigger graceful shutdown via the manager
    def handle_sigint(_sig, _frame):
        logger.log_message("SIGINT received; shutting down.", "summary")
        stop_event.set()
        wake_event.set()
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        # Block until stop_event is set or a managed thread crashes
        while not stop_event.is_set():
            if tm.any_crashed():
                logger.log_fatal_error("A managed thread crashed. Initiating shutdown.", report_stack=False)
                stop_event.set()
                wake_event.set()
                break
            # Cooperative wait avoids busy loop
            stop_event.wait(timeout=1.0)
    finally:
        tm.stop_all()
        tm.join_all(timeout_per_thread=10.0)
        logger.log_message("PowerController application stopped.", "summary")


if __name__ == "__main__":
    main()
