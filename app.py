import os
import re
import json
import uuid
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = Path('input/uploads')
PREPROCESS_OUTPUT = Path('output/preprocess')
ANALYSIS_OUTPUT = Path('output/tdpm_analysis')
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

@app.route('/viewer/calculator')
def viewer_calculator():
    return render_template('viewer_calculator.html')

@app.route('/viewer/evolution')
def viewer_evolution():
    return render_template('viewer_evolution.html')


# API Endpoints

@app.route('/api/files')
def list_files():
    files = []
    output_dir = Path("output")
    if output_dir.exists() and output_dir.is_dir():
        for f in output_dir.rglob("*.tdpm.json"):
            if f.is_file():
                match = re.search(r"(\d{8}_\d{6})\.tdpm\.json$", f.name)
                if match:
                    timestamp = match.group(1)
                else:
                    timestamp = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y%m%d_%H%M%S")

                files.append({
                    "name": f.name,
                    "path": f"/output/{f.relative_to(output_dir).as_posix()}",
                    "timestamp": timestamp
                })

    files.sort(key=lambda x: x["timestamp"], reverse=True)
    for f in files:
        del f["timestamp"]

    return jsonify(files)

@app.route('/output/<path:filepath>')
def serve_output(filepath):
    # Serve analysis JSON files
    return send_from_directory('output', filepath)

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
        
        cmd = ["python", "preprocess.py", str(filepath), "--output-dir", str(PREPROCESS_OUTPUT)]
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
            ["python", "tdpm_analysis.py", str(latest_sanitized), "--output", str(ANALYSIS_OUTPUT)],
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
