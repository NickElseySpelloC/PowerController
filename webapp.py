from threading import Thread

from flask import Flask, jsonify, render_template, request
from sc_utility import SCConfigManager, SCLogger
from werkzeug.serving import make_server

from controller import AppMode, Command, PowerController


def create_flask_app(controller: PowerController, config: SCConfigManager, logger: SCLogger) -> Flask:  # noqa: ARG001
    app = Flask(__name__, static_folder=None)
    app.config["DEBUG"] = True  # TO DO: Make configurable

    # TO DO: Add support for access key

    @app.get("/api/outputs")
    def list_outputs():
        return jsonify(controller.get_webapp_data())

    @app.get("/api/outputs/<output_id>")
    def get_output(output_id):
        snapshot = controller.get_webapp_data()
        if output_id not in snapshot["outputs"]:
            logger.log_message(f"Output ID {output_id} not found", "warning")
            return jsonify({"error": "not found"}), 404
        return jsonify(snapshot["outputs"][output_id])

    @app.post("/api/outputs/<output_id>/mode")
    def set_mode(output_id):
        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "").lower()
        if mode not in {m.value for m in AppMode}:
            return jsonify({"error": "mode must be one of on/off/auto"}), 400
        controller.post_command(Command("set_mode", {"output_id": output_id, "mode": mode}))
        return jsonify({"status": "ok"})

    @app.get("/")
    def index():
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
