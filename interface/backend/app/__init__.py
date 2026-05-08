from flask import Flask, send_from_directory


def create_app():
    app = Flask(__name__, static_folder="frontend_dist", static_url_path="")

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(404)
    def not_found(e):
        return send_from_directory(app.static_folder, "index.html")

    from app.v1.app_v1 import bp as v1_bp

    app.register_blueprint(v1_bp)

    return app
