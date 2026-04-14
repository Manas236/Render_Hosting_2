import os
import logging
from flask import Flask, send_from_directory, jsonify
import config

def create_app():
    """Application factory for modular Flask app."""
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    
    logging.basicConfig(level=logging.INFO)

    # ─────────────────────────────────────────────
    # Register Blueprints
    # ─────────────────────────────────────────────
    from login import login_bp
    from dashboard import dashboard_bp
    from codeview import codeview_bp
    from editor import editor_bp

    app.register_blueprint(login_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(codeview_bp)
    app.register_blueprint(editor_bp)

    # ─────────────────────────────────────────────
    # Health Check (required by Render)
    # ─────────────────────────────────────────────
    @app.route('/health')
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route('/static_files/<path:filename>')
    def serve_static(filename):
        return send_from_directory('.', filename)

    return app

# ─────────────────────────────────────────────
# Module-level app instance for Gunicorn
# Gunicorn imports this as:  main:app
# ─────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    # Clean up legacy files if they exist
    if os.path.exists("opt-7.html"):
        os.remove("opt-7.html")

    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
