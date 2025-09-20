from threading import Thread

from flask import Flask, jsonify, render_template, request
from sc_utility import SCConfigManager, SCLogger
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from controller import AppMode, Command, PowerController


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

        if config.get("Website", "AccessKey") is not None:
            access_key = args.get("key", default=None, type=str)
            if access_key != config.get("Website", "AccessKey"):
                logger.log_message(f"Invalid access key {access_key} used.", "warning")
                return False
        return True

    @app.get("/api/outputs")
    def list_outputs():
        # Validate the access key if provided
        print(request.args)
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        json_data = jsonify(controller.get_webapp_data())
        return json_data

    @app.get("/api/outputs/<output_id>")
    def get_output(output_id):
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        snapshot = controller.get_webapp_data()
        if output_id not in snapshot["outputs"]:
            logger.log_message(f"Output ID {output_id} not found", "warning")
            return jsonify({"error": "not found"}), 404
        json_data = jsonify(snapshot["outputs"][output_id])
        return json_data

    @app.post("/api/outputs/<output_id>/mode")
    def set_mode(output_id):
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "").lower()
        if mode not in {m.value for m in AppMode}:
            return jsonify({"error": "mode must be one of on/off/auto"}), 400
        controller.post_command(Command("set_mode", {"output_id": output_id, "mode": mode}))
        return jsonify({"status": "ok"})

    @app.get("/")
    def index():
        # Validate the access key if provided
        if not validate_access_key(request.args):
            return "Access forbidden.", 403

        snapshot = controller.get_webapp_data()
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
