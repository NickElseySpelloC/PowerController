"""Web application module for the PowerController project."""
import contextlib
from threading import Event

from flask import Flask, jsonify, render_template, request
from org_enums import AppMode
from sc_utility import SCConfigManager, SCLogger
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from controller import PowerController
from local_enumerations import Command


def create_flask_app(controller: PowerController, config: SCConfigManager, logger: SCLogger) -> Flask:  # noqa: PLR0915
    """Create and configure the Flask web application.

    Args:
        controller (PowerController): The main controller instance.
        config (SCConfigManager): The configuration manager instance.
        logger (SCLogger): The logger instance.

    Returns:
        Flask: The configured Flask application instance.
    """
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    # Preserve Website section usage
    app.config["DEBUG"] = config.get("Website", "DebugMode", default=False) or False
    if app.config["DEBUG"]:
        logger.log_message("Flask debug mode is enabled.", "debug")
        app.jinja_env.auto_reload = True

    def validate_access_key(args: MultiDict[str, str]) -> bool:
        """Validate the access key from the request arguments.

        Args:
            args (dict): The request arguments containing the access key.

        Returns:
            bool: True if the access key is valid, False otherwise.
        """
        assert config is not None, "Config instance is not initialized."
        assert logger is not None, "Logger instance is not initialized."

        access_key = args.get("key", default=None, type=str)
        if access_key is not None:
            access_key = access_key.strip()
            if not access_key:
                logger.log_message("Blank access key used.", "warning")
                return False
        expected_key = config.get("Website", "AccessKey")
        if expected_key is not None and access_key != expected_key:
            logger.log_message(f"Invalid access key {access_key} used.", "warning")
            return False
        return True

    def sanitize_mode(mode: str) -> str | None:
        """Sanitize and validate mode input.

        Args:
            mode (str): The mode string to validate.

        Returns:
            str | None: The sanitized mode string if valid, None otherwise.
        """
        if not isinstance(mode, str):
            return None
        mode = mode.strip().lower()
        valid_modes = {m.value for m in AppMode}
        return mode if mode in valid_modes else None

    def is_valid_output_id(output_id: str) -> bool:
        """Validate that the output ID is valid.

        Args:
            output_id (str): The output ID to validate.

        Returns:
            bool: True if the output ID is valid, False otherwise.
        """
        return controller.is_valid_output_id(output_id)

    @app.get("/api/outputs")
    def list_outputs():
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return jsonify({"error": "Access forbidden."}), 403

        snapshot = controller.get_webapp_data()
        if not snapshot:
            logger.log_message("No web output data available yet", "warning")
            return jsonify({"error": "no output data available yet"}), 503

        json_data = jsonify(snapshot)
        logger.log_message("API call list_output() for all output data", "debug")
        return json_data

    @app.get("/api/outputs/<output_id>")
    def get_output(output_id):
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return jsonify({"error": "Access forbidden."}), 403

        if not is_valid_output_id(output_id):
            logger.log_message(f"Output ID {output_id} not found", "warning")
            return jsonify({"error": "invalid output_id"}), 400

        snapshot = controller.get_webapp_data()
        if not snapshot:
            logger.log_message("No web output data available yet", "warning")
            return jsonify({"error": "no output data available yet"}), 503

        json_data = jsonify(snapshot["outputs"][output_id])
        logger.log_message(f"API call get_output() for output for {output_id}", "debug")
        return json_data

    @app.post("/api/outputs/<output_id>/mode")
    def set_mode(output_id):
        if not validate_access_key(request.args):
            return jsonify({"error": "Access forbidden."}), 403

        if not controller.is_valid_output_id(output_id):
            return jsonify({"error": "invalid output_id"}), 400

        data = request.get_json(silent=True) or {}
        mode = sanitize_mode(data.get("mode", ""))
        if not mode:
            return jsonify({"error": "mode must be one of on/off/auto"}), 400

        controller.post_command(Command("set_mode", {"output_id": output_id, "mode": mode}))

        snapshot = controller.get_webapp_data()
        if not snapshot:
            logger.log_message("No web output data available yet", "warning")
            return jsonify({"error": "no output data available yet"}), 503

        output_data = snapshot["outputs"].get(output_id)

        logger.log_message(f"API call set_mode() for {output_id}, changing mode to to {mode}.", "debug")
        return jsonify(output_data or {"status": "ok"})

    @app.get("/")
    def index():
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        snapshot = controller.get_webapp_data()
        if not snapshot:
            logger.log_message("No web output data available yet", "warning")
            return "no output data available yet", 503

        logger.log_message("API call get() returning home page", "debug")
        return render_template("index.html",
                             global_data=snapshot["global"],
                             outputs=snapshot["outputs"])

    return app


def serve_flask_blocking(app: Flask, config: SCConfigManager, logger: SCLogger, stop_event: Event):
    """Run Flask in the current thread with cooperative shutdown using stop_event."""
    # Preserve Website.* config keys
    host = config.get("Website", "HostingIP", default="127.0.0.1") or "127.0.0.1"
    port = int(config.get("Website", "Port", default=8000) or 8000)  # pyright: ignore[reportArgumentType]

    server = make_server(host, port, app)  # pyright: ignore[reportArgumentType]
    ctx = app.app_context()
    ctx.push()
    server.timeout = 1.0
    logger.log_message(f"Flask server listening on http://{host}:{port}", "summary")
    try:
        while not stop_event.is_set():
            server.handle_request()
    finally:
        with contextlib.suppress(Exception):
            server.server_close()
        logger.log_message("Flask web server shutdown complete.", "detailed")
