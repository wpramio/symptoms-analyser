from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, redirect, url_for

from symptoms_analyser.controllers.admin import (
    create_patient,
    get_evaluation_telemetry,
    get_patients,
    get_clinical_analysis_telemetry,
    get_stats,
    get_transcripts,
    get_patients_list_with_stats,
    get_patient_evolution_data,
    update_patient,
    get_tdpm_table_data,
    get_clinicians,
    get_sessions_admin,
    update_session_admin,
    delete_transcript_admin,
    get_sessions_api_data,
)
from symptoms_analyser.controllers.evaluations import (
    get_evaluation_payload,
    list_evaluation_ids,
    align_evaluations,
    save_clinical_analysis,
)
from symptoms_analyser.controllers.revisions import save_revision_logic
from symptoms_analyser.controllers.therapy_sessions import (
    handle_new_therapy_session,
    get_therapy_sessions,
    get_therapy_session_detail,
    get_session_transcript_status,
)
from symptoms_analyser.controllers.therapy_groups import (
    get_group_dynamics_data,
    get_therapy_groups_admin,
    create_therapy_group,
    update_therapy_group,
    get_therapy_groups,
    get_therapy_group_detail,
)
from symptoms_analyser.controllers.transcript_upload import tasks, handle_transcript_upload
from symptoms_analyser.controllers.risk_alerts import get_group_risk_alerts


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
    return redirect(url_for("therapy_groups"))


@app.route("/therapy_sessions/new")
def new_therapy_session():
    try:
        groups = get_therapy_groups()
    except Exception as e:
        print(f"Error fetching groups for new session form: {e}")
        groups = []
    return render_template("new_therapy_session.html", groups=groups)


@app.route("/therapy_sessions")
def therapy_sessions():
    try:
        therapy_groups = get_therapy_groups()
        group_id = request.args.get("group_id")
        if group_id is None and therapy_groups:
            group_id = str(therapy_groups[0]["id"])

        sessions = get_therapy_sessions(group_id)

        return render_template(
            "therapy_sessions.html", 
            sessions=sessions, 
            therapy_groups=therapy_groups,
            selected_group_id=group_id
        )
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
        import traceback
        traceback.print_exc()
        print(f"Error serving session detail for {session_id}: {e}")
        return str(e), 500


@app.route("/therapy_sessions/<int:session_id>/upload_transcript", methods=["POST"])
def therapy_session_upload_transcript(session_id):
    try:
        if "file" not in request.files or request.files["file"].filename == "":
            return jsonify({"error": "Nenhum arquivo enviado"}), 400
            
        file = request.files["file"]
        task_id = handle_transcript_upload(
            file_stream=file,
            filename=file.filename,
            therapy_session_id=session_id,
            extract_metadata=False,
            skip_extension_check=False
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
        therapy_groups = get_therapy_groups()
        group_id = request.args.get("group_id")
        if group_id is None and therapy_groups:
            group_id = str(therapy_groups[0]["id"])

        patient_list = get_patients_list_with_stats(group_id)

        # Build alert severity map {pseudonym -> 'critical'|'warning'|'info'}
        patient_alert_map = {}
        try:
            from symptoms_analyser.controllers.risk_alerts import get_patients_alert_map
            if group_id and str(group_id).strip() not in ("", "None"):
                group_ids = [int(group_id)]
            else:
                group_ids = [g["id"] for g in therapy_groups if g.get("id")]
            patient_alert_map = get_patients_alert_map(group_ids)
        except Exception as e:
            print(f"Error building patient alert map: {e}")

        return render_template(
            "patients.html",
            patients=patient_list,
            therapy_groups=therapy_groups,
            selected_group_id=group_id,
            patient_alert_map=patient_alert_map
        )
    except Exception as e:
        print(f"Error serving patients list: {e}")
        return str(e), 500



@app.route("/patients/<patient_id>")
def patient_detail(patient_id):
    try:
        data = get_patient_evolution_data(patient_id)
        if not data:
            return "Patient not found", 404

        # Get patient risk alerts
        group_id = data["patient"].get("therapy_group_id")
        patient_alerts = []
        if group_id:
            try:
                from symptoms_analyser.controllers.risk_alerts import get_group_risk_alerts
                res = get_group_risk_alerts(group_id)
                alerts = res.get("alerts", [])
                patient_alerts = [a for a in alerts if a.get("patient") == patient_id]
            except Exception as e:
                print(f"Error fetching risk alerts for patient {patient_id}: {e}")

        # Get latest dimensions for radar chart
        import json
        timeline = data.get("timeline", [])
        latest_dimensions = []
        from symptoms_analyser.controllers.admin import ONTOLOGY_DIMENSIONS
        latest_entry_dims = {}
        if timeline:
            latest_entry_dims = timeline[-1].get("dimensions", {})
        for i in range(1, 21):
            dim_key = str(i)
            latest_dimensions.append({
                "key": dim_key,
                "name": f"{dim_key}. {ONTOLOGY_DIMENSIONS.get(dim_key, dim_key)}",
                "value": latest_entry_dims.get(dim_key, 0.0)
            })

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
            patient_alerts=patient_alerts,
            latest_dimensions=json.dumps(latest_dimensions),
            latest_dimensions_raw=latest_dimensions,
        )
    except Exception as e:
        print(f"Error serving patient detail: {e}")
        return str(e), 500


@app.route("/therapy_groups")
def therapy_groups():
    try:
        groups = get_therapy_groups()
        return render_template("therapy_groups.html", groups=groups)
    except Exception as e:
        print(f"Error serving therapy groups list: {e}")
        return str(e), 500


@app.route("/therapy_groups/<int:group_id>")
def therapy_group_detail(group_id):
    try:
        data = get_therapy_group_detail(group_id)
        if not data:
            return "Grupo não encontrado", 404
            
        group = data["group"]
        patients = data["patients"]
            
        # First tab: Alertas de risco
        res = get_group_risk_alerts(group_id)
        alerts = res.get("alerts", [])
        
        # Second tab: Sessões passadas
        sessions = get_therapy_sessions(group_id=group_id)

        # Dynamics data (historically aggregated)
        dynamics_data = get_group_dynamics_data(group_id=group_id)
        
        return render_template(
            "therapy_group_detail.html",
            group=group,
            patients=patients,
            alerts=alerts,
            sessions=sessions,
            airtime=dynamics_data.get("airtime"),
            clinical_analysis=dynamics_data.get("clinical_analysis"),
            graph_data=dynamics_data.get("graph_data"),
        )
    except Exception as e:
        print(f"Error serving therapy group detail: {e}")
        return str(e), 500



@app.route("/tdpm_table")
def tdpm_table():
    try:
        grouped_dimensions = get_tdpm_table_data()
        return render_template(
            "tdpm_table.html",
            grouped_dimensions=grouped_dimensions
        )
    except Exception as e:
        print(f"Error serving tdpm_table: {e}")
        return str(e), 500


@app.route("/admin/compare_tdpm_evaluation")
def admin_compare_tdpm_evaluation():
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
        "admin_compare_tdpm_evaluation.html",
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
        # Fetch KPI stats
        stats = get_stats()
        
        # Fetch jobs (transcripts)
        jobs = get_transcripts()
        
        # Fetch therapy sessions
        sessions = get_sessions_admin()
            
        # Fetch evaluation telemetry
        eval_telemetry = get_evaluation_telemetry()
        
        # Fetch clinical analysis telemetry
        clinical_analysis_telemetry = get_clinical_analysis_telemetry()
        
        return render_template(
            "admin_transcripts.html",
            stats=stats,
            jobs=jobs,
            sessions=sessions,
            eval_telemetry=eval_telemetry,
            clinical_analysis_telemetry=clinical_analysis_telemetry
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
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
            therapy_group_id = data.get("therapy_group_id") or request.form.get("therapy_group_id")
            
            result, status = update_patient(original_id, pseudonym, real_name, therapy_group_id)
            return jsonify(result), status

        if request.method == "POST":
            original_id = request.form.get("original_id", "").strip()
            pseudonym = request.form.get("pseudonym", "").strip()
            real_name = request.form.get("real_name", "").strip()
            therapy_group_id = request.form.get("therapy_group_id", "").strip()

            if original_id:
                # Update existing patient (HTML form edit)
                if not pseudonym or not real_name:
                    flash("Erro: Todos os campos são obrigatórios.", "error")
                elif not re.match(r"^Paciente\d+$", pseudonym):
                    flash("Erro: O pseudônimo precisa estar no formato 'PacienteX', onde X é um número inteiro (ex: Paciente8).", "error")
                else:
                    result, status = update_patient(original_id, pseudonym, real_name, therapy_group_id)
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
                    result, status = create_patient(pseudonym, real_name, therapy_group_id)
                    if status in (200, 201):
                        flash("✓ Paciente criado com sucesso!", "success")
                    else:
                        flash(f"Erro ao salvar paciente: {result.get('error', 'Erro desconhecido')}", "error")
            
            return redirect(url_for("admin_patients"))

        # Fetch therapy groups for dropdowns
        therapy_groups = get_therapy_groups()

        patients = get_patients()
        return render_template("admin_patients.html", patients=patients, therapy_groups=therapy_groups)
    except Exception as e:
        print(f"Error serving admin patients: {e}")
        return str(e), 500


@app.route("/admin/therapy_sessions", methods=["GET", "POST", "PATCH"])
def admin_therapy_sessions():
    try:
        from flask import flash, redirect, url_for

        if request.method == "PATCH":
            data = request.get_json() or {}
            result, status = update_session_admin(
                data.get("session_id"),
                data.get("name"),
                data.get("start_at"),
                data.get("duration"),
                data.get("therapy_group_id"),
            )
            return jsonify(result), status

        if request.method == "POST":
            result, status = update_session_admin(
                request.form.get("session_id"),
                request.form.get("name"),
                request.form.get("start_at"),
                request.form.get("duration"),
                request.form.get("therapy_group_id"),
            )
            if status == 200:
                flash("✓ Sessão atualizada com sucesso!", "success")
            else:
                flash(f"Erro ao salvar sessão: {result.get('error', 'Erro desconhecido')}", "error")
            return redirect(url_for("admin_therapy_sessions"))

        # Fetch therapy groups for filter dropdown and modal
        therapy_groups = get_therapy_groups()

        group_id = request.args.get("group_id")
        sessions = get_sessions_admin(group_id)

        return render_template(
            "admin_therapy_sessions.html",
            sessions=sessions,
            therapy_groups=therapy_groups,
            selected_group_id=group_id,
        )
    except Exception as e:
        print(f"Error serving admin sessions: {e}")
        return str(e), 500


@app.route("/admin/therapy_groups", methods=["GET", "POST", "PATCH"])
def admin_therapy_groups():
    try:
        from flask import flash, redirect, url_for

        if request.method == "PATCH":
            data = request.get_json() or {}
            group_id = data.get("group_id") or request.form.get("group_id")
            name = data.get("name") or request.form.get("name")
            clinician_id = data.get("clinician_id") or request.form.get("clinician_id")
            result, status = update_therapy_group(group_id, name, clinician_id)
            return jsonify(result), status

        if request.method == "POST":
            group_id = request.form.get("group_id", "").strip()
            name = request.form.get("name", "").strip()
            clinician_id = request.form.get("clinician_id", "").strip()

            if group_id:
                # Update existing group (HTML form edit)
                result, status = update_therapy_group(group_id, name, clinician_id)
                if status == 200:
                    flash("✓ Grupo atualizado com sucesso!", "success")
                else:
                    flash(f"Erro ao salvar grupo: {result.get('error', 'Erro desconhecido')}", "error")
            else:
                # Create new group
                result, status = create_therapy_group(name, clinician_id)
                if status in (200, 201):
                    flash("✓ Grupo criado com sucesso!", "success")
                else:
                    flash(f"Erro ao criar grupo: {result.get('error', 'Erro desconhecido')}", "error")

            return redirect(url_for("admin_therapy_groups"))

        therapy_groups = get_therapy_groups_admin()
        clinicians = get_clinicians()
        return render_template("admin_therapy_groups.html", therapy_groups=therapy_groups, clinicians=clinicians)
    except Exception as e:
        print(f"Error serving admin therapy groups: {e}")
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
            "group_id": request.form.get("group_id")
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


@app.route("/api/admin/transcripts/<int:transcript_id>", methods=["DELETE"])
def api_delete_transcript(transcript_id):
    try:
        result, status = delete_transcript_admin(transcript_id)
        return jsonify(result), status
    except Exception as e:
        print(f"Error deleting transcript {transcript_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/evaluation-telemetry")
def api_admin_evaluation_telemetry():
    try:
        return jsonify(get_evaluation_telemetry())
    except Exception as e:
        print(f"Error fetching admin evaluation telemetry: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/clinical-analysis-telemetry")
def api_admin_clinical_analysis_telemetry():
    try:
        return jsonify(get_clinical_analysis_telemetry())
    except Exception as e:
        print(f"Error fetching admin clinical analysis telemetry: {e}")
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
@app.route("/api/evaluations/<int:eval_id>/clinical-analysis", methods=["POST"])
def api_save_clinical_analysis(eval_id: int):
    try:
        data = request.get_json() or {}
        note = data.get("group_progress_note")
        if note is None:
            return jsonify({"error": "Dados inválidos: campo 'group_progress_note' é obrigatório"}), 400
            
        save_clinical_analysis(eval_id, note)
        return jsonify({"message": "Resumo de tópicos da sessão salvo com sucesso!"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Error saving clinical analysis: {e}")
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
                "patient_ids": data.get("patient_ids"),
                "group_id": data.get("group_id")
            }
            result = handle_new_therapy_session(form_data)
            return jsonify({"message": "Sessão criada com sucesso!", "session_id": result["session_id"]}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    try:
        sessions = get_sessions_api_data()
        return jsonify(sessions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
