import os
import sys
import re
import json
import sqlite3
import uuid
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_FOLDER = PROJECT_ROOT / 'input/uploads'
PREPROCESS_OUTPUT = PROJECT_ROOT / 'output/preprocess'
ANALYSIS_OUTPUT = PROJECT_ROOT / 'output/tdpm_analysis'
ALLOWED_EXTENSIONS = {'txt', 'docx'}

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PREPROCESS_OUTPUT.mkdir(parents=True, exist_ok=True)
ANALYSIS_OUTPUT.mkdir(parents=True, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Background Tasks Store
# tasks = { task_id: { "status": "processing"|"completed"|"error", "logs": [], "error": "" } }
tasks = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload')
def upload():
    return render_template('upload.html')

@app.route('/viewer')
@app.route('/viewer/analysis')
def viewer_analysis():
    return render_template('viewer_analysis.html')

@app.route('/viewer/compare')
def viewer_compare():
    return render_template('viewer_compare.html')

@app.route('/viewer/evolution')
def viewer_evolution():
    return render_template('viewer_evolution.html')

@app.route('/admin/transcripts')
def admin_transcripts():
    return render_template('admin_transcripts.html')

@app.route('/admin/patients')
def admin_patients():
    return render_template('admin_patients.html')

@app.route('/admin/calculator')
def admin_calculator():
    return render_template('admin_calculator.html')


# API Endpoints

@app.route('/api/files')
def list_files():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    files = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT evaluation_id 
            FROM evaluation_telemetry 
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        for row in rows:
            eval_id = row["evaluation_id"]
            name = f"{eval_id}.tdpm.json"
            files.append({
                "name": name,
                "path": f"/output/tdpm_analysis/{name}"
            })
        conn.close()
    except Exception as e:
        print(f"Error listing files from DB: {e}")
        return jsonify({"error": str(e)}), 500
        
    return jsonify(files)

@app.route('/output/<path:filepath>')
def serve_output(filepath):
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    try:
        filename = Path(filepath).name
        eval_id = re.sub(r"\.tdpm\.json$", "", filename)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT raw_payload 
            FROM evaluation_telemetry 
            WHERE evaluation_id = ?
        """, (eval_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            payload = json.loads(row[0])
            return jsonify(payload)
    except Exception as e:
        print(f"Error fetching raw payload from DB for {filepath}: {e}")
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"error": "DB entry not found"}), 404


@app.route('/api/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)
        
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "status": "processing",
            "logs": [],
            "error": ""
        }
        
        # Check if skip_sanitization parameter is present
        skip_sanitization = request.form.get('skip_sanitization') == 'true'
        
        # Start background thread
        thread = threading.Thread(target=process_file, args=(task_id, filepath, skip_sanitization))
        thread.start()
        
        return jsonify({"task_id": task_id})
        
    return jsonify({"error": "File type not allowed"}), 400

@app.route('/api/status/<task_id>')
def get_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(tasks[task_id])

def process_file(task_id, filepath: Path, skip_sanitization: bool = False):
    task = tasks[task_id]
    
    def add_log(msg):
        task["logs"].append(msg)
        print(f"[{task_id}] {msg}")
        
    try:
        # Step 1: Preprocess
        add_log(f"Iniciando pré-processamento de {filepath.name}...")
        
        # We run preprocess.py as a subprocess
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        # Add src directory to PYTHONPATH so subprocesses can resolve symptoms_analyser package
        src_dir = str(Path(__file__).resolve().parents[1])
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = src_dir + os.pathsep + env['PYTHONPATH']
        else:
            env['PYTHONPATH'] = src_dir
        
        cmd = [sys.executable, "-m", "symptoms_analyser.preprocess", str(filepath), "--output-dir", str(PREPROCESS_OUTPUT)]
        if skip_sanitization:
            cmd.append("--skip-sanitization")
            
        proc_prep = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        for line in proc_prep.stdout:
            add_log(line.strip())
            
        proc_prep.wait()
        if proc_prep.returncode != 0:
            raise Exception("Falha no pré-processamento. Verifique os logs.")
            
        # Step 2: Analysis
        # We need to find the sanitized transcript that was just generated
        session_name = filepath.stem
        # It usually outputs to <session_name>.runX.sanitized.txt
        # Let's find the latest one
        sanitized_files = list(PREPROCESS_OUTPUT.glob(f"{session_name}.run*.sanitized.txt"))
        if not sanitized_files:
            # Fallback for .txt or other behavior
            sanitized_files = list(PREPROCESS_OUTPUT.glob(f"{session_name}*.sanitized.txt"))
            
        if not sanitized_files:
            raise Exception("Arquivo sanitizado não encontrado após pré-processamento.")
            
        # Sort by run number or modification time, we assume the latest modified
        latest_sanitized = max(sanitized_files, key=os.path.getmtime)
        
        add_log(f"Pré-processamento concluído. Iniciando análise TDPM-20 no arquivo {latest_sanitized.name}...")
        
        proc_ana = subprocess.Popen(
            [sys.executable, "-m", "symptoms_analyser.tdpm_analysis", str(latest_sanitized), "--output", str(ANALYSIS_OUTPUT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        for line in proc_ana.stdout:
            add_log(line.strip())
            
        proc_ana.wait()
        if proc_ana.returncode != 0:
            raise Exception("Falha na análise TDPM-20. Verifique os logs.")
            
        add_log("Análise concluída com sucesso.")
        task["status"] = "completed"
        
    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        add_log(f"Erro: {str(e)}")

@app.route('/api/admin/stats')
def api_admin_stats():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    stats = {
        "total_transcripts": 0,
        "success_rate": 100.0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_patients": 0
    }
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            cursor = conn.cursor()
            
            # Total Transcripts
            cursor.execute("SELECT count(*) FROM transcripts")
            stats["total_transcripts"] = cursor.fetchone()[0] or 0
            
            # Success rate
            cursor.execute("SELECT count(*) FROM transcripts WHERE status IN ('preprocessed', 'completed')")
            successes = cursor.fetchone()[0] or 0
            if stats["total_transcripts"] > 0:
                stats["success_rate"] = round((successes / stats["total_transcripts"]) * 100.0, 1)
                
            # Tokens usage
            cursor.execute("SELECT sum(prompt_tokens), sum(completion_tokens) FROM evaluation_telemetry")
            row = cursor.fetchone()
            stats["total_prompt_tokens"] = row[0] or 0
            stats["total_completion_tokens"] = row[1] or 0
            
            # Total Patients
            cursor.execute("SELECT count(*) FROM patients")
            stats["total_patients"] = cursor.fetchone()[0] or 0
            
            conn.close()
        except Exception as e:
            print(f"Error fetching admin stats: {e}")
    return jsonify(stats)

@app.route('/api/admin/transcripts')
def api_admin_transcripts():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    rows_list = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, filename, file_type, file_size_bytes, status, progress_percent, error_message, created_at 
                FROM transcripts 
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            for r in rows:
                rows_list.append({
                    "id": r["id"],
                    "filename": r["filename"],
                    "file_type": r["file_type"],
                    "file_size_bytes": r["file_size_bytes"],
                    "status": r["status"],
                    "progress_percent": r["progress_percent"],
                    "error_message": r["error_message"],
                    "created_at": r["created_at"]
                })
            conn.close()
        except Exception as e:
            print(f"Error fetching admin transcripts: {e}")
    return jsonify(rows_list)

@app.route('/api/admin/telemetry')
def api_admin_telemetry():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    telemetry_list = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, transcript_id, model, strategy, total_elapsed_seconds, turns_merged, noise_tokens_removed, corrections, anonymization_flags, prompt_tokens, completion_tokens, chunks_completed, created_at 
                FROM sanitization_telemetry 
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            for r in rows:
                telemetry_list.append({
                    "id": r["id"],
                    "transcript_id": r["transcript_id"],
                    "model": r["model"],
                    "strategy": r["strategy"],
                    "elapsed_seconds": r["total_elapsed_seconds"],
                    "turns_merged": r["turns_merged"],
                    "noise_removed": json.loads(r["noise_tokens_removed"]) if r["noise_tokens_removed"] else [],
                    "corrections_map": json.loads(r["corrections"]) if r["corrections"] else {},
                    "anonymization_flags": json.loads(r["anonymization_flags"]) if r["anonymization_flags"] else [],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "chunks_completed": r["chunks_completed"],
                    "created_at": r["created_at"]
                })
            conn.close()
        except Exception as e:
            print(f"Error fetching admin telemetry: {e}")
    return jsonify(telemetry_list)

@app.route('/api/admin/evaluation-telemetry')
def api_admin_evaluation_telemetry():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    telemetry_list = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT evaluation_id, model, chunks_analyzed, blocks_per_call, prompt_tokens, completion_tokens, total_elapsed_seconds, status, failure_reason, created_at 
                FROM evaluation_telemetry 
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            for r in rows:
                telemetry_list.append({
                    "evaluation_id": r["evaluation_id"],
                    "model": r["model"],
                    "chunks_analyzed": r["chunks_analyzed"],
                    "blocks_per_call": r["blocks_per_call"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "elapsed_seconds": r["total_elapsed_seconds"],
                    "status": r["status"],
                    "failure_reason": r["failure_reason"],
                    "created_at": r["created_at"]
                })
            conn.close()
        except Exception as e:
            print(f"Error fetching admin evaluation telemetry: {e}")
    return jsonify(telemetry_list)


@app.route('/api/admin/patients')
def api_admin_patients():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    patients_list = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pseudonym, real_name, created_at 
                FROM patients 
                ORDER BY id ASC
            """)
            rows = cursor.fetchall()
            for r in rows:
                patients_list.append({
                    "id": r["pseudonym"],
                    "real_name": r["real_name"],
                    "created_at": r["created_at"]
                })
            conn.close()
        except Exception as e:
            print(f"Error fetching admin patients: {e}")
    return jsonify(patients_list)

@app.route('/api/admin/patients/create', methods=['POST'])
def create_patient():
    db_path = PROJECT_ROOT / "data" / "sqlite.db"
    try:
        data = request.get_json()
        if not data or 'pseudonym' not in data or 'real_name' not in data:
            return jsonify({"error": "Dados inválidos ou incompletos"}), 400
            
        pseudonym = data['pseudonym'].strip()
        real_name = data['real_name'].strip()
        
        if not pseudonym or not real_name:
            return jsonify({"error": "Pseudônimo e nome real não podem estar vazios"}), 400
            
        if not re.match(r"^Paciente\d+$", pseudonym):
            return jsonify({"error": "Pseudônimo deve seguir o formato 'PacienteX' (ex: Paciente8)"}), 400
            
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Check if pseudonym already exists
        cursor.execute("SELECT id FROM patients WHERE pseudonym = ?", (pseudonym,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": f"O pseudônimo '{pseudonym}' já está cadastrado"}), 409
            
        cursor.execute("INSERT INTO patients (id, pseudonym, real_name) VALUES (?, ?, ?)", (pseudonym, pseudonym, real_name))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Paciente registrado com sucesso"}), 201
    except Exception as e:
        print(f"Error creating patient mapping: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
