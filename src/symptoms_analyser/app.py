import os
import sqlite3
import uuid
import json
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

from symptoms_analyser.controllers.admin import (
    create_patient,
    get_evaluation_telemetry,
    get_patients,
    get_sanitization_telemetry,
    get_stats,
    get_transcripts,
)
from symptoms_analyser.controllers.pipeline import get_evaluation_payload, list_evaluation_ids
from symptoms_analyser.controllers.sessions import (
    allowed_file,
    create_session_from_parameters,
    handle_session_upload_task,
    tasks,
)
from symptoms_analyser.utils import DB_PATH

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_FOLDER = PROJECT_ROOT / "input/uploads"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/therapy_sessions/new")
def new_therapy_session():
    return render_template("new_therapy_session.html")


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
# Evaluations API  (/api/evaluations)
# ---------------------------------------------------------------------------

@app.route("/api/evaluations")
def list_evaluations():
    try:
        return jsonify(list_evaluation_ids())
    except Exception as e:
        print(f"Error listing evaluations from DB: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluations/<eval_id>")
def serve_evaluation(eval_id):
    try:
        payload = get_evaluation_payload(eval_id)
        if payload is not None:
            return jsonify(payload)
        return jsonify({"error": "Evaluation not found"}), 404
    except Exception as e:
        print(f"Error fetching evaluation payload for {eval_id}: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Upload & pipeline
# ---------------------------------------------------------------------------

@app.route("/api/upload_transcript", methods=["POST"])
def handle_upload_transcript():
    # Form data checklist
    skip_sanitization = request.form.get("skip_sanitization") == "true"
    
    form_data = {
        "skip_sanitization": skip_sanitization,
        "therapy_session_id": request.form.get("therapy_session_id"),
        "auto_fill": request.form.get("auto_fill"),
        "session_name": request.form.get("session_name"),
        "clinician_id": request.form.get("clinician_id"),
        "start_at": request.form.get("start_at"),
        "duration": request.form.get("duration"),
        "patient_ids": request.form.get("patient_ids")
    }

    # If transcript file is uploaded, secure and save it, then delegate to async runner
    if "file" in request.files and request.files["file"].filename != "":
        file = request.files["file"]
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed"}), 400

        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)

        task_id = handle_session_upload_task(filepath, form_data)
        return jsonify({"task_id": task_id})

    # Otherwise: This is a manual session creation without immediate transcript processing
    try:
        session_name = form_data.get("session_name")
        if not session_name:
            return jsonify({"error": "Session name is required for manual creation"}), 400

        clinician_id = form_data.get("clinician_id") or "clinician_1"
        start_at = form_data.get("start_at")
        if not start_at:
            start_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            duration = int(form_data.get("duration") or 3600)
        except ValueError:
            duration = 3600

        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        session_id = create_session_from_parameters(conn, session_name, clinician_id, start_at, duration, form_data.get("patient_ids"))
        conn.close()

        return jsonify({"message": "Sessão criada com sucesso!", "session_id": session_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status/<task_id>")
def get_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(tasks[task_id])


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


@app.route("/api/admin/sessions", methods=["GET", "POST"])
def api_admin_sessions():
    if request.method == "POST":
        try:
            data = request.get_json() or {}
            name = data.get("name")
            if not name:
                return jsonify({"error": "Session name is required"}), 400
                
            clinician_id = data.get("clinician_id", "clinician_1")
            start_at = data.get("start_at")
            if not start_at:
                start_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                
            try:
                duration = int(data.get("duration", 3600))
            except ValueError:
                duration = 3600
                
            patient_ids_str = data.get("patient_ids", "")
            
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA foreign_keys = ON")
            session_id = create_session_from_parameters(conn, name, clinician_id, start_at, duration, patient_ids_str)
            conn.close()
            
            return jsonify({"message": "Sessão criada com sucesso!", "session_id": session_id}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    # GET
    try:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.name, s.clinician_id, s.start_at, s.duration, s.created_at,
                       u.name as clinician_name,
                       (SELECT group_concat(patient_id, ', ') FROM therapy_session_patients WHERE therapy_session_id = s.id) as patients
                FROM therapy_sessions s
                LEFT JOIN users u ON s.clinician_id = u.id
                ORDER BY s.created_at DESC
            """)
            sessions = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "clinician_id": r["clinician_id"],
                    "clinician_name": r["clinician_name"] or "Sem clínico",
                    "start_at": r["start_at"],
                    "duration": r["duration"],
                    "patients": r["patients"] or "Nenhum paciente",
                    "created_at": r["created_at"],
                }
                for r in cursor.fetchall()
            ]
        return jsonify(sessions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
