import os
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from symptoms_analyser.controllers.admin import (
    create_patient,
    get_evaluation_telemetry,
    get_patients,
    get_sanitization_telemetry,
    get_stats,
    get_transcripts,
)
from symptoms_analyser.controllers.pipeline import get_analysis_payload, list_analysis_files
from symptoms_analyser.preprocess import run_preprocess
from symptoms_analyser.tdpm_analysis import run_analysis

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_FOLDER = PROJECT_ROOT / "input/uploads"
ALLOWED_EXTENSIONS = {"txt", "docx"}

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# ---------------------------------------------------------------------------
# Background task store
# tasks = { task_id: { "status": "processing"|"completed"|"error", "logs": [], "error": "" } }
# ---------------------------------------------------------------------------

tasks: dict = {}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload")
def upload():
    return render_template("upload.html")


@app.route("/viewer")
@app.route("/viewer/analysis")
def viewer_analysis():
    return render_template("viewer_analysis.html")


@app.route("/viewer/compare")
def viewer_compare():
    return render_template("viewer_compare.html")


@app.route("/viewer/evolution")
def viewer_evolution():
    return render_template("viewer_evolution.html")


@app.route("/admin/transcripts")
def admin_transcripts():
    return render_template("admin_transcripts.html")


@app.route("/admin/patients")
def admin_patients():
    return render_template("admin_patients.html")


@app.route("/admin/calculator")
def admin_calculator():
    return render_template("admin_calculator.html")


# ---------------------------------------------------------------------------
# File / output API
# ---------------------------------------------------------------------------

@app.route("/api/files")
def list_files():
    try:
        return jsonify(list_analysis_files())
    except Exception as e:
        print(f"Error listing files from DB: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/output/<path:filepath>")
def serve_output(filepath):
    try:
        payload = get_analysis_payload(filepath)
        if payload is not None:
            return jsonify(payload)
        return jsonify({"error": "DB entry not found"}), 404
    except Exception as e:
        print(f"Error fetching raw payload from DB for {filepath}: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Upload & pipeline
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def handle_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not (file and allowed_file(file.filename)):
        return jsonify({"error": "File type not allowed"}), 400

    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    file.save(filepath)

    skip_sanitization = request.form.get("skip_sanitization") == "true"

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "logs": [], "error": ""}

    thread = threading.Thread(target=process_file, args=(task_id, filepath, skip_sanitization))
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(tasks[task_id])


def process_file(task_id: str, filepath: Path, skip_sanitization: bool = False) -> None:
    task = tasks[task_id]

    def add_log(msg: str) -> None:
        task["logs"].append(msg)
        print(f"[{task_id}] {msg}")

    try:
        add_log(f"Iniciando pré-processamento de {filepath.name}...")
        run_preprocess(filepath, skip_sanitization=skip_sanitization)

        session_name = filepath.stem
        add_log(f"Pré-processamento concluído. Iniciando análise TDPM-20 para: {session_name}...")
        run_analysis(transcript_id=session_name)

        add_log("Análise concluída com sucesso.")
        task["status"] = "completed"

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        add_log(f"Erro: {str(e)}")


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

@app.route("/api/admin/stats")
def api_admin_stats():
    try:
        return jsonify(get_stats())
    except Exception as e:
        print(f"Error fetching admin stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/transcripts")
def api_admin_transcripts():
    try:
        return jsonify(get_transcripts())
    except Exception as e:
        print(f"Error fetching admin transcripts: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/telemetry")
def api_admin_telemetry():
    try:
        return jsonify(get_sanitization_telemetry())
    except Exception as e:
        print(f"Error fetching admin telemetry: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/evaluation-telemetry")
def api_admin_evaluation_telemetry():
    try:
        return jsonify(get_evaluation_telemetry())
    except Exception as e:
        print(f"Error fetching admin evaluation telemetry: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/patients")
def api_admin_patients():
    try:
        return jsonify(get_patients())
    except Exception as e:
        print(f"Error fetching admin patients: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/patients/create", methods=["POST"])
def api_create_patient():
    try:
        data = request.get_json() or {}
        result, status = create_patient(data.get("pseudonym"), data.get("real_name"))
        return jsonify(result), status
    except Exception as e:
        print(f"Error creating patient mapping: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
