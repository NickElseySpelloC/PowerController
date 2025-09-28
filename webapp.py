from threading import Thread

from flask import Flask, jsonify, render_template, request
from org_enums import AppMode
from sc_utility import SCConfigManager, SCLogger
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from controller import PowerController
from local_enumerations import Command


def create_flask_app(controller: PowerController, config: SCConfigManager, logger: SCLogger) -> Flask:
    app = Flask(__name__)
    app.config["DEBUG"] = config.get("Website", "DebugMode", default=False) or False

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
            return "Access forbidden.", 403

        snapshot = controller.get_webapp_data()
        json_data = jsonify(snapshot)
        logger.log_message("API call list_output() for all output data", "debug")
        return json_data

    @app.get("/api/outputs/<output_id>")
    def get_output(output_id):
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        if not is_valid_output_id(output_id):
            logger.log_message(f"Output ID {output_id} not found", "warning")
            return jsonify({"error": "invalid output_id"}), 400

        snapshot = controller.get_webapp_data()
        json_data = jsonify(snapshot["outputs"][output_id])
        logger.log_message(f"API call get_output() for output for {output_id}", "debug")
        return json_data

    @app.post("/api/outputs/<output_id>/mode")
    def set_mode(output_id):
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        if not controller.is_valid_output_id(output_id):
            return jsonify({"error": "invalid output_id"}), 400

        data = request.get_json(silent=True) or {}
        mode = sanitize_mode(data.get("mode", ""))
        if not mode:
            return jsonify({"error": "mode must be one of on/off/auto"}), 400

        controller.post_command(Command("set_mode", {"output_id": output_id, "mode": mode}))

        webapp_data = controller.get_webapp_data()
        output_data = webapp_data["outputs"].get(output_id)

        logger.log_message(f"API call set_mode() for {output_id}, changing mode to to {mode}.", "debug")
        return jsonify(output_data or {"status": "ok"})

    @app.get("/")
    def index():
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        snapshot = controller.get_webapp_data()
        logger.log_message("API call get() returning home page", "debug")
        return render_template("index.html",
                             global_data=snapshot["global"],
                             outputs=snapshot["outputs"])

    return app


class FlaskServerThread(Thread):
    def __init__(self, app: Flask, config: SCConfigManager, logger: SCLogger):
        super().__init__(daemon=True)
        self.config = config
        self.logger = logger
        assert isinstance(self.config, SCConfigManager), "Configuration instance is not initialized."
        assert isinstance(self.logger, SCLogger), "Logger instance is not initialized."

        hosting_ip = self.config.get("Website", "HostingIP", default="127.0.0.1")
        hosting_port = self.config.get("Website", "Port", default=8000)

        self.server = make_server(hosting_ip, hosting_port, app)  # pyright: ignore[reportArgumentType]
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.logger.log_message(f"Starting Flask server on {self.server.server_address}", "debug")
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()
        self.logger.log_message(f"Stopping Flask server on {self.server.server_address}", "debug")
