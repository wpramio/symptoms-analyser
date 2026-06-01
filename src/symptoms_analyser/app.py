from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, redirect, url_for

from symptoms_analyser.controllers.admin import (
    create_patient,
    get_evaluation_telemetry,
    get_patients,
    get_sanitization_telemetry,
    get_stats,
    get_transcripts,
    get_patients_list_with_stats,
    get_patient_evolution_data,
    get_cohort_evolution_data,
    update_patient,
)
from symptoms_analyser.controllers.evaluations import get_evaluation_payload, list_evaluation_ids, align_evaluations
from symptoms_analyser.controllers.revisions import save_revision_logic
from symptoms_analyser.controllers.therapy_sessions import (
    handle_new_therapy_session,
    get_therapy_sessions,
    get_therapy_session_detail,
    get_session_transcript_status,
)
from symptoms_analyser.controllers.transcript_upload import tasks, handle_transcript_upload

app = Flask(__name__)
app.secret_key = "symptoms-analyser-secure-key"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_FOLDER = PROJECT_ROOT / "input/uploads"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

def format_datetime_py(val):
    if not val:
        return "-"
    clean_val = str(val).replace("T", " ").replace("Z", "").split(".")[0]
    try:
        dt = datetime.strptime(clean_val, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        try:
            dt = datetime.strptime(clean_val, "%Y-%m-%d %H:%M")
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return val

def format_datetime_dmyy_py(val):
    if not val:
        return "-"
    clean_val = str(val).replace("T", " ").replace("Z", "").split(".")[0]
    try:
        dt = datetime.strptime(clean_val, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%y %H:%M")
    except Exception:
        try:
            dt = datetime.strptime(clean_val, "%Y-%m-%d %H:%M")
            return dt.strftime("%d/%m/%y %H:%M")
        except Exception:
            try:
                dt = datetime.strptime(clean_val.split()[0], "%Y-%m-%d")
                return dt.strftime("%d/%m/%y")
            except Exception:
                return val

def format_bytes_py(val):
    if not val:
        return "0 Bytes"
    try:
        val = int(val)
    except Exception:
        return val
    if val == 0:
        return "0 Bytes"
    sizes = ["Bytes", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(val) / math.log(1024)))
    return f"{round(val / (1024 ** i), 1)} {sizes[i]}"

app.jinja_env.filters["format_datetime"] = format_datetime_py
app.jinja_env.filters["format_datetime_dmyy"] = format_datetime_dmyy_py
app.jinja_env.filters["format_bytes"] = format_bytes_py
app.jinja_env.filters["number_format"] = lambda val: f"{val or 0:,}".replace(",", ".")


@app.context_processor
def inject_current_user():
    # TODO: Once authentication/login features are implemented, update this function
    # to fetch the user dynamic from the active session/cookie (e.g., session.get("user_id"))
    # instead of hardcoding user ID 2.
    try:
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, role, email FROM users WHERE id = 2")
            user = cursor.fetchone()
            if user:
                # Role formatting
                role_display = "Administrador" if user["role"] == "admin" else ("Clínico" if user["role"] == "clinician" else "Paciente")
                # Generate initials (e.g. "Admin" -> "AD", "Dr. Félix" -> "DF")
                name = user["name"]
                initials = "".join([p[0] for p in name.split() if p]).upper()
                if len(initials) > 2:
                    initials = initials[:2]
                elif not initials:
                    initials = "US"
                return {"current_user": {
                    "name": name,
                    "role": role_display,
                    "email": user["email"],
                    "initials": initials
                }}
    except Exception as e:
        print(f"Error injecting current user: {e}")
    # Fallback
    return {"current_user": {
        "name": "Admin",
        "role": "Administrador",
        "email": "admin@symptomsanalyser.org",
        "initials": "AD"
    }}


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/therapy_sessions/new")
def new_therapy_session():
    return render_template("new_therapy_session.html")


@app.route("/therapy_sessions")
def therapy_sessions():
    try:
        sessions = get_therapy_sessions()
        return render_template("therapy_sessions.html", sessions=sessions)
    except Exception as e:
        print(f"Error serving therapy sessions list: {e}")
        return str(e), 500


@app.route("/therapy_sessions/<int:session_id>")
def therapy_session_detail(session_id):
    try:
        data = get_therapy_session_detail(session_id)
        if not data:
            return "Session not found", 404
            
        evaluation_payload = None
        if data["evaluation_id"]:
            evaluation_payload = get_evaluation_payload(data["evaluation_id"])
            
        return render_template(
            "therapy_session_detail.html",
            session=data["session"],
            patients_list=data["patients_list"],
            transcript=data["transcript"],
            evaluation_id=data["evaluation_id"],
            evaluation=evaluation_payload,
            airtime=data.get("airtime")
        )
    except Exception as e:
        print(f"Error serving session detail for {session_id}: {e}")
        return str(e), 500


@app.route("/therapy_sessions/<int:session_id>/upload_transcript", methods=["POST"])
def therapy_session_upload_transcript(session_id):
    try:
        apply_sanitization = request.form.get("apply_sanitization") == "true"
        if "file" not in request.files or request.files["file"].filename == "":
            return jsonify({"error": "Nenhum arquivo enviado"}), 400
            
        file = request.files["file"]
        task_id = handle_transcript_upload(
            file_stream=file,
            filename=file.filename,
            therapy_session_id=session_id,
            extract_metadata=False,
            skip_extension_check=False,
            apply_sanitization=apply_sanitization
        )
        return jsonify({"success": True, "task_id": task_id})
    except Exception as e:
        print(f"Error in upload for session {session_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<int:session_id>/status")
def get_session_status(session_id):
    try:
        return jsonify(get_session_transcript_status(session_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/patients")
def patients():
    try:
        patient_list = get_patients_list_with_stats()
        return render_template("patients.html", patients=patient_list)
    except Exception as e:
        print(f"Error serving patients list: {e}")
        return str(e), 500


@app.route("/patients/<patient_id>")
def patient_detail(patient_id):
    try:
        data = get_patient_evolution_data(patient_id)
        if not data:
            return "Patient not found", 404
        return render_template(
            "patient_detail.html",
            patient=data["patient"],
            sessions=data["sessions"],
            timeline=data["timeline"],
            kpis=data["kpis"],
            heatmap_dims=data["heatmap_dims"],
            chart_labels=data["chart_labels"],
            chart_totals=data["chart_totals"],
            chart_dimensions=data["chart_dimensions"],
        )
    except Exception as e:
        print(f"Error serving patient detail: {e}")
        return str(e), 500


@app.route("/cohort_analytics")
def cohort_analytics():
    try:
        data = get_cohort_evolution_data()
        return render_template(
            "cohort_analytics.html",
            timeline=data["timeline"],
            kpis=data["kpis"],
            heatmap_dims=data["heatmap_dims"],
            critical_sessions=data["critical_sessions"],
            chart_labels=data["chart_labels"],
            chart_mean_totals=data["chart_mean_totals"],
            chart_median_totals=data["chart_median_totals"],
            chart_dimensions=data["chart_dimensions"],
        )
    except Exception as e:
        print(f"Error serving cohort analytics: {e}")
        return str(e), 500


@app.route("/admin/compare_tdpm_analysis")
def admin_compare_tdpm_analysis():
    # 1. Fetch available evaluations list for the dropdown selectors
    evaluations_list = list_evaluation_ids()
    
    # 2. Retrieve A and B parameters (path or ID)
    a_param = request.args.get("a", "")
    b_param = request.args.get("b", "")
    
    # Extract IDs if paths are passed
    def extract_id(val):
        if not val:
            return ""
        if val.startswith("/api/evaluations/"):
            return val.split("/")[-1]
        return val
        
    eval_id_a = extract_id(a_param)
    eval_id_b = extract_id(b_param)
    
    data_a = None
    data_b = None
    aligned_data = []
    
    if eval_id_a:
        data_a = get_evaluation_payload(eval_id_a)
    if eval_id_b:
        data_b = get_evaluation_payload(eval_id_b)
        
    if data_a or data_b:
        aligned_data = align_evaluations(data_a, data_b)
        
    return render_template(
        "admin_compare_tdpm_analysis.html",
        evaluations_list=evaluations_list,
        selected_a=a_param or (f"/api/evaluations/{eval_id_a}" if eval_id_a else ""),
        selected_b=b_param or (f"/api/evaluations/{eval_id_b}" if eval_id_b else ""),
        data_a=data_a,
        data_b=data_b,
        aligned_data=aligned_data
    )


@app.route("/admin/transcripts")
def admin_transcripts():
    try:
        # 1. Fetch KPI stats
        stats = get_stats()
        
        # 2. Fetch jobs (transcripts)
        jobs = get_transcripts()
        
        # 3. Fetch therapy sessions
        from symptoms_analyser.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.name, s.clinician_id, s.start_at, s.duration, s.created_at,
                       u.name as clinician_name,
                       (SELECT group_concat(p.pseudonym, ', ') FROM therapy_session_patients tsp JOIN patients p ON tsp.patient_id = p.id WHERE tsp.therapy_session_id = s.id) as patients
                FROM therapy_sessions s
                LEFT JOIN users u ON s.clinician_id = u.id
                ORDER BY s.start_at DESC, s.created_at DESC
            """)
            sessions = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "clinician_id": r["clinician_id"],
                    "clinician_name": r["clinician_name"] or "Sem clínico",
                    "start_at": r["start_at"],
                    "duration": r["duration"],
                    "created_at": r["created_at"],
                    "patients": r["patients"] or "Nenhum"
                }
                for r in cursor.fetchall()
            ]
            
        # 4. Fetch sanitization telemetry
        telemetry = get_sanitization_telemetry()
        
        # 5. Fetch evaluation telemetry
        eval_telemetry = get_evaluation_telemetry()
        
        return render_template(
            "admin_transcripts.html",
            stats=stats,
            jobs=jobs,
            sessions=sessions,
            telemetry=telemetry,
            eval_telemetry=eval_telemetry
        )
    except Exception as e:
        print(f"Error serving admin transcripts: {e}")
        return str(e), 500


@app.route("/admin/patients", methods=["GET", "POST", "PATCH"])
def admin_patients():
    try:
        from flask import flash, redirect, url_for
        import re
        
        if request.method == "PATCH":
            data = request.get_json() or {}
            original_id = data.get("original_id") or request.form.get("original_id")
            pseudonym = data.get("pseudonym") or request.form.get("pseudonym")
            real_name = data.get("real_name") or request.form.get("real_name")
            
            result, status = update_patient(original_id, pseudonym, real_name)
            return jsonify(result), status

        if request.method == "POST":
            original_id = request.form.get("original_id", "").strip()
            pseudonym = request.form.get("pseudonym", "").strip()
            real_name = request.form.get("real_name", "").strip()

            if original_id:
                # Update existing patient (HTML form edit)
                if not pseudonym or not real_name:
                    flash("Erro: Todos os campos são obrigatórios.", "error")
                elif not re.match(r"^Paciente\d+$", pseudonym):
                    flash("Erro: O pseudônimo precisa estar no formato 'PacienteX', onde X é um número inteiro (ex: Paciente8).", "error")
                else:
                    result, status = update_patient(original_id, pseudonym, real_name)
                    if status == 200:
                        flash("✓ Paciente atualizado com sucesso!", "success")
                    else:
                        flash(f"Erro ao salvar paciente: {result.get('error', 'Erro desconhecido')}", "error")
            else:
                # Create new patient
                if not pseudonym or not real_name:
                    flash("Erro: Todos os campos são obrigatórios.", "error")
                elif not re.match(r"^Paciente\d+$", pseudonym):
                    flash("Erro: O pseudônimo precisa estar no formato 'PacienteX', onde X é um número inteiro (ex: Paciente8).", "error")
                else:
                    result, status = create_patient(pseudonym, real_name)
                    if status in (200, 201):
                        flash("✓ Paciente criado com sucesso!", "success")
                    else:
                        flash(f"Erro ao salvar paciente: {result.get('error', 'Erro desconhecido')}", "error")
            
            return redirect(url_for("admin_patients"))

        patients = get_patients()
        return render_template("admin_patients.html", patients=patients)
    except Exception as e:
        print(f"Error serving admin patients: {e}")
        return str(e), 500


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


@app.route("/api/evaluations/<int:eval_id>/revise", methods=["POST"])
def revise_evaluation(eval_id):
    try:
        edits_json = request.get_json() or {}
        new_eval_id = save_revision_logic(original_eval_id=eval_id, edits_json=edits_json, user_id=2)
        return jsonify({
            "success": True,
            "message": "Revisão salva com sucesso!",
            "evaluation_id": new_eval_id
        }), 201
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        print(f"Error saving revised evaluation: {e}")
        return jsonify({"success": False, "error": f"Erro interno do servidor: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Upload & pipeline
# ---------------------------------------------------------------------------

@app.route("/api/therapy_sessions", methods=["POST"])
def handle_new_session_api():
    try:
        form_data = {
            "session_name": request.form.get("session_name"),
            "start_at": request.form.get("start_at"),
            "duration": request.form.get("duration"),
            "clinician_id": request.form.get("clinician_id"),
            "patient_ids": request.form.get("patient_ids"),
            "auto_fill": request.form.get("auto_fill"),
            "apply_sanitization": request.form.get("apply_sanitization")
        }
        
        file = None
        if "file" in request.files and request.files["file"].filename != "":
            file = request.files["file"]
            
        result = handle_new_therapy_session(form_data, file)
        return jsonify(result), 201
    except Exception as e:
        print(f"Error creating therapy session: {e}")
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
            form_data = {
                "session_name": data.get("name"),
                "start_at": data.get("start_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "duration": data.get("duration"),
                "clinician_id": data.get("clinician_id"),
                "patient_ids": data.get("patient_ids")
            }
            result = handle_new_therapy_session(form_data)
            return jsonify({"message": "Sessão criada com sucesso!", "session_id": result["session_id"]}), 201
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
                ORDER BY s.start_at DESC, s.created_at DESC
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
