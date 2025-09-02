from threading import Thread

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from controller import AppMode, Command, PowerController


def create_flask_app(controller: PowerController):
    app = Flask(__name__, static_folder=None)

    @app.get("/api/lights")
    def list_lights():
        return jsonify(controller.get_state_snapshot())

    @app.get("/api/lights/<light_id>")
    def get_light(light_id):
        snapshot = controller.get_state_snapshot()
        if light_id not in snapshot:
            return jsonify({"error": "not found"}), 404
        return jsonify(snapshot[light_id])

    @app.post("/api/lights/<light_id>/mode")
    def set_mode(light_id):
        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "").lower()
        if mode not in {m.value for m in AppMode}:
            return jsonify({"error": "mode must be one of on/off/auto"}), 400
        controller.post_command(Command("set_mode", {"light_id": light_id, "mode": mode}))
        return jsonify({"status": "ok"})

    @app.get("/")
    def index():
        return open("static/index.html", encoding="utf-8").read()  # noqa: PTH123

    return app


class FlaskServerThread(Thread):
    def __init__(self, app: Flask, host: str = "0.0.0.0", port: int = 8080):  # noqa: S104
        super().__init__(daemon=True)
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        print("[Flask] serving on http://0.0.0.0:8080")
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()
        print("[Flask] shutdown complete")
