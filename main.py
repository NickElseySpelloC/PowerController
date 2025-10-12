"""Main initialisation module for the PowerController app."""

# Check that Python version is >= 3.13, else exit with error.
import signal
import sys
from threading import Event

from sc_utility import SCConfigManager, SCLogger

from config_schemas import ConfigSchema
from controller import PowerController
from local_enumerations import CONFIG_FILE
from webapp import FlaskServerThread, create_flask_app


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
    except RuntimeError as e:
        print(f"Logger initialisation error: {e}", file=sys.stderr)
        return
    else:
        logger.log_message("", "summary")
        logger.log_message("", "summary")
        logger.log_message("PowerController application starting.", "summary")

    # Setup email
    logger.register_email_settings(config.get_email_settings())

    # Create an instance of the main PowerController class which orchestrates the power control
    controller = PowerController(config, logger, wake_event)

    flask_app = create_flask_app(controller, config, logger)
    web_thread = FlaskServerThread(flask_app, config, logger)
    web_thread.start()

    # Handle the SIGINT signal (Ctrl-C) so that we can gracefull shut down when this is received.
    def handle_sigint(sig, frame):  # noqa: ARG001
        """Handle the SIGINT signal.

        Args:
            sig (signal.Signals): The signal number.
            frame (frame): The current stack frame.
        """
        stop_event.set()
        wake_event.set()
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        controller.run(stop_event=stop_event)
    except Exception as e:  # noqa: BLE001  # Final catch all for any unexpected errors
        logger.log_fatal_error(f"Unexpected error in main loop: {e}", report_stack=True)
    finally:
        web_thread.shutdown()


if __name__ == "__main__":
    main()
