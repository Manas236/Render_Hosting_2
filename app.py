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
    from extractor import extractor_bp
    from batch_extractor import batch_extractor_bp
    from upload_image import upload_image_bp
    from upload2 import git_pusher_bp
    from mailchimp_bp import mailchimp_bp
    from schedule_mailchimp_bp import schedule_mailchimp_bp
    from schedule_mailchimp_2_bp import schedule_mailchimp_2_bp
    from social_pipeline_bp import social_pipeline_bp
    # ── Day 8 Editor (v2 — BS4-based) ──
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "day8_v2_editor", "editor_day8_v2.py")
    day8_module = importlib.util.module_from_spec(spec)
    sys.modules["day8_v2_editor"] = day8_module
    spec.loader.exec_module(day8_module)
    day8_editor_bp = day8_module.day8_v2_editor_bp

    # ── Day 9 Editor (BS4-based) ──
    spec_day9 = importlib.util.spec_from_file_location(
        "day9_editor", "editor(for Day9.html).py")
    day9_module = importlib.util.module_from_spec(spec_day9)
    sys.modules["day9_editor"] = day9_module
    spec_day9.loader.exec_module(day9_module)
    day9_editor_bp = day9_module.day9_editor_bp

    # ── Day6Temp Editor (BS4-based) ──
    from editor_day6temp import day6temp_editor_bp

    # ── Template1 Editor (BS4-based) ──
    from editor_template1 import template1_editor_bp

    # ── Day 11 Editor (BS4-based) ──
    spec_day11 = importlib.util.spec_from_file_location(
        "day11_editor", "app11.py")
    day11_module = importlib.util.module_from_spec(spec_day11)
    sys.modules["day11_editor"] = day11_module
    spec_day11.loader.exec_module(day11_module)
    day11_editor_bp = day11_module.day11_editor_bp

    # ── Day 12 Editor (BS4-based) ──
    spec_day12 = importlib.util.spec_from_file_location(
        "day12_editor", "editor(for Day12.html).py")
    day12_module = importlib.util.module_from_spec(spec_day12)
    sys.modules["day12_editor"] = day12_module
    spec_day12.loader.exec_module(day12_module)
    day12_editor_bp = day12_module.day12_editor_bp

    # ── Day 15 Editor (BS4-based) ──
    spec_day15 = importlib.util.spec_from_file_location(
        "day15_editor", "editor(for Day15.html).py")
    day15_module = importlib.util.module_from_spec(spec_day15)
    sys.modules["day15_editor"] = day15_module
    spec_day15.loader.exec_module(day15_module)
    day15_editor_bp = day15_module.day15_editor_bp

    # ── Day 12(2) Editor (BS4-based) ──
    spec_day12_2 = importlib.util.spec_from_file_location(
        "day12_2_editor", "editor(for Day12(2).html).py")
    day12_2_module = importlib.util.module_from_spec(spec_day12_2)
    sys.modules["day12_2_editor"] = day12_2_module
    spec_day12_2.loader.exec_module(day12_2_module)
    day12_2_editor_bp = day12_2_module.day12_2_editor_bp

    # ── Day 9(2) Editor (BS4-based, with markets ticker) ──
    spec_day9_2 = importlib.util.spec_from_file_location(
        "day9_2_editor", "editor(for Day9(2).html).py")
    day9_2_module = importlib.util.module_from_spec(spec_day9_2)
    sys.modules["day9_2_editor"] = day9_2_module
    spec_day9_2.loader.exec_module(day9_2_module)
    day9_2_editor_bp = day9_2_module.day9_2_editor_bp

    # ── Day 17 Editor (BS4-based) ──
    spec_day17 = importlib.util.spec_from_file_location(
        "day17_editor", "editor(for Day17.html).py")
    day17_module = importlib.util.module_from_spec(spec_day17)
    sys.modules["day17_editor"] = day17_module
    spec_day17.loader.exec_module(day17_module)
    day17_editor_bp = day17_module.day17_editor_bp

    app.register_blueprint(login_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(codeview_bp)
    app.register_blueprint(extractor_bp)
    app.register_blueprint(day8_editor_bp, url_prefix='/day8-editor')
    app.register_blueprint(day9_editor_bp, url_prefix='/day9-editor')
    app.register_blueprint(day6temp_editor_bp, url_prefix='/day6temp-editor')
    app.register_blueprint(template1_editor_bp, url_prefix='/template1-editor')
    app.register_blueprint(day11_editor_bp, url_prefix='/day11-editor')
    app.register_blueprint(day12_editor_bp, url_prefix='/day12-editor')
    app.register_blueprint(day15_editor_bp, url_prefix='/day15-editor')
    app.register_blueprint(day12_2_editor_bp, url_prefix='/day12-2-editor')
    app.register_blueprint(day9_2_editor_bp, url_prefix='/day9-2-editor')
    app.register_blueprint(day17_editor_bp, url_prefix='/day17-editor')
    app.register_blueprint(batch_extractor_bp, url_prefix='/batch-extractor')
    app.register_blueprint(upload_image_bp, url_prefix='/upload-image')
    app.register_blueprint(git_pusher_bp, url_prefix='/git-pusher')
    app.register_blueprint(mailchimp_bp, url_prefix='/mailchimp')
    app.register_blueprint(schedule_mailchimp_bp, url_prefix='/schedule-mailchimp')
    app.register_blueprint(schedule_mailchimp_2_bp, url_prefix='/schedule-mailchimp-2')
    app.register_blueprint(social_pipeline_bp)
    # ─────────────────────────────────────────────
    # Health Check (required by Render)
    # ─────────────────────────────────────────────

    @app.route('/health')
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route('/static_files/<path:filename>')
    def serve_static(filename):
        return send_from_directory('.', filename)

    # Serve uploaded images — Nginx intercepts this in production;
    # Flask handles it in dev/fallback.
    _upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_images")

    @app.route('/uploads/<filename>')
    def serve_upload(filename):
        return send_from_directory(_upload_dir, filename)

    return app


# ─────────────────────────────────────────────
# Module-level app instance for Gunicorn
# Gunicorn imports this as:  app:app
# ─────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    # Clean up legacy files if they exist
    if os.path.exists("opt-7.html"):
        os.remove("opt-7.html")

    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
