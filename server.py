"""
server.py — Flask backend for ReportGenie.

Run:  python server.py  →  opens at http://localhost:7860

Endpoints:
  GET  /                → serves the frontend
  POST /api/generate    → AI or Smart mode report generation
  POST /api/manual      → Manual mode report generation
  GET  /api/health      → health check
"""

import json
import os
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv, set_key

load_dotenv()

import uuid
import fitz
from ai_agent import generate_report_content
from pdf_writer import fill_report

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

TEMP_PDF_DIR = Path("tmp_pdfs")
TEMP_PDF_DIR.mkdir(exist_ok=True)


# ── Static Frontend ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Health Check ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "2.0.0",
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY", "")),
        "has_groq_key": bool(os.getenv("GROQ_API_KEY", "")),
        "has_openrouter_key": bool(os.getenv("OPENROUTER_API_KEY", "")),
    })


# ── AI / Smart Mode ─────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Generate a report using AI or Smart mode.

    Expects JSON body:
    {
        "raw_notes": "...",
        "from_date": "MM/DD/YYYY",
        "to_date": "MM/DD/YYYY",
        "department": "Development ( Risk Tech)",
        "remarks": "...",
        "employee_name": "...",
        "project_name": "...",
        "mode": "ai" | "smart",
        "gemini_key": "...",
        "groq_key": "...",
        "openrouter_key": "...",
        "save_keys": true/false
    }
    """
    try:
        data = request.get_json(force=True)

        raw_notes = (data.get("raw_notes") or "").strip()
        from_date = (data.get("from_date") or "").strip()
        to_date = (data.get("to_date") or "").strip()
        department = (data.get("department") or "Development ( Risk Tech)").strip()
        remarks = (data.get("remarks") or "").strip()
        employee_name = (data.get("employee_name") or "Rohith Rudrapati").strip()
        project_name = (data.get("project_name") or "Modelone").strip()
        upcoming_tasks = data.get("upcoming_tasks")
        mode = (data.get("mode") or "ai").strip()

        # API keys (from request or env)
        gemini_key = (data.get("gemini_key") or "").strip()
        groq_key = (data.get("groq_key") or "").strip()
        openrouter_key = (data.get("openrouter_key") or "").strip()

        # Validation
        if not raw_notes:
            return jsonify({"error": "Work notes are empty. Describe what you worked on."}), 400
        if not from_date or not to_date:
            return jsonify({"error": "Both From and To dates are required."}), 400

        # Save keys to .env if requested
        if data.get("save_keys"):
            env_path = Path(".env")
            if not env_path.exists():
                env_path.write_text("")
            if gemini_key:
                set_key(str(env_path), "GEMINI_API_KEY", gemini_key)
                os.environ["GEMINI_API_KEY"] = gemini_key
            if groq_key:
                set_key(str(env_path), "GROQ_API_KEY", groq_key)
                os.environ["GROQ_API_KEY"] = groq_key
            if openrouter_key:
                set_key(str(env_path), "OPENROUTER_API_KEY", openrouter_key)
                os.environ["OPENROUTER_API_KEY"] = openrouter_key

        # Generate report content
        result = generate_report_content(
            raw_notes=raw_notes,
            from_date=from_date,
            to_date=to_date,
            department=department,
            remarks=remarks,
            employee_name=employee_name,
            project_name=project_name,
            upcoming_tasks=upcoming_tasks,
            gemini_key=gemini_key,
            groq_key=groq_key,
            openrouter_key=openrouter_key,
            mode=mode,
        )

        model_used = result.pop("_model_used", "unknown")

        # Handle signature if uploaded
        sig_path = data.get("signature_path")

        # Generate PDF
        pdf_path = fill_report(result, signature_path=sig_path)

        return jsonify({
            "success": True,
            "model_used": model_used,
            "data": result,
            "pdf_filename": pdf_path.name,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Manual Mode ──────────────────────────────────────────────────────────────

@app.route("/api/manual", methods=["POST"])
def manual():
    """
    Generate a report using manual input (no AI).

    Expects JSON body with all fields pre-filled by the user.
    """
    try:
        data = request.get_json(force=True)

        from_date = (data.get("from_date") or "").strip()
        to_date = (data.get("to_date") or "").strip()
        department = (data.get("department") or "Development ( Risk Tech)").strip()
        remarks = (data.get("remarks") or "").strip()
        employee_name = (data.get("employee_name") or "Rohith Rudrapati").strip()
        project_name = (data.get("project_name") or "Modelone").strip()

        tasks = data.get("tasks_performed", ["-", "-", "-"])
        upcoming = data.get("upcoming_tasks", [])

        if not from_date or not to_date:
            return jsonify({"error": "Both From and To dates are required."}), 400
        if not any(t.strip() for t in tasks if t.strip() and t.strip() != "-"):
            return jsonify({"error": "Enter at least one task performed."}), 400

        # Ensure exactly 3 tasks
        while len(tasks) < 3:
            tasks.append("-")
        tasks = tasks[:3]

        # Ensure exactly 3 upcoming tasks
        while len(upcoming) < 3:
            try:
                base = datetime.strptime(to_date, "%m/%d/%Y")
            except ValueError:
                base = datetime.today()
            d = (base + timedelta(weeks=1, days=len(upcoming) * 2)).strftime("%m/%d/%Y")
            upcoming.append({"task": "-", "date": d})
        upcoming = upcoming[:3]

        report_data = {
            "department": department,
            "from_date": from_date,
            "to_date": to_date,
            "remarks": remarks,
            "employee_name": employee_name,
            "project_name": project_name,
            "tasks_performed": tasks,
            "upcoming_tasks": upcoming,
        }

        sig_path = data.get("signature_path")
        pdf_path = fill_report(report_data, signature_path=sig_path)

        return jsonify({
            "success": True,
            "model_used": "Manual",
            "data": report_data,
            "pdf_filename": pdf_path.name,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Download PDF ─────────────────────────────────────────────────────────────

@app.route("/api/download/<filename>")
def download(filename):
    """Download a generated PDF report."""
    pdf_path = Path("outputs") / filename
    if not pdf_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(
        str(pdf_path),
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


# ── Signature Upload ─────────────────────────────────────────────────────────

@app.route("/api/upload-signature", methods=["POST"])
def upload_signature():
    """Upload a signature image. Returns the file path for later use."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    save_path = uploads_dir / f"signature_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    f.save(str(save_path))

    return jsonify({"success": True, "path": str(save_path)})


# ── Drag & Drop Signer Endpoints ──────────────────────────────────────────

@app.route("/api/pdf/upload_raw", methods=["POST"])
def upload_raw_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Must be a PDF file"}), 400

    pdf_id = str(uuid.uuid4())
    pdf_path = TEMP_PDF_DIR / f"{pdf_id}.pdf"
    file.save(pdf_path)

    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()
        return jsonify({"success": True, "pdf_id": pdf_id, "pages": page_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf/render/<pdf_id>")
def render_pdf_page(pdf_id):
    page_num = int(request.args.get("page", 0))
    pdf_path = TEMP_PDF_DIR / f"{pdf_id}.pdf"
    img_path = TEMP_PDF_DIR / f"{pdf_id}_{page_num}.png"
    
    if not pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    if not img_path.exists():
        try:
            doc = fitz.open(pdf_path)
            if page_num < 0 or page_num >= len(doc):
                return jsonify({"error": "Invalid page number"}), 400
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Render at 2x resolution
            pix.save(str(img_path))
            doc.close()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return send_file(img_path, mimetype="image/png")

@app.route("/api/pdf/stamp_signature", methods=["POST"])
def stamp_signature():
    try:
        data = request.get_json(force=True)
        pdf_id = data.get("pdf_id")
        page_num = int(data.get("page", 0))
        sig_path_str = data.get("signature_path")
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        w = float(data.get("width", 100))
        h = float(data.get("height", 50))

        pdf_path = TEMP_PDF_DIR / f"{pdf_id}.pdf"
        if not pdf_path.exists():
            return jsonify({"error": "PDF not found"}), 404
            
        if not sig_path_str:
            return jsonify({"error": "No signature provided"}), 400

        sig_path = Path(sig_path_str)
        if not sig_path.exists():
            return jsonify({"error": "Signature file not found"}), 404

        original_filename = data.get("original_filename", f"{pdf_id}.pdf")
        
        # Format the filename if it matches the MMDDYYYY_to_MMDDYYYY pattern
        import re
        from datetime import datetime
        
        def format_date_str(d_str):
            try:
                date_obj = datetime.strptime(d_str, "%m%d%Y")
                return date_obj.strftime("%B_%d_%Y").lower()
            except ValueError:
                return d_str
                
        match = re.search(r'([0-9]{8})_to_([0-9]{8})', original_filename)
        if match:
            d1, d2 = match.groups()
            new_date_range = f"{format_date_str(d1)}_to_{format_date_str(d2)}"
            base_name = original_filename.replace(f"{d1}_to_{d2}", new_date_range)
            out_filename = f"signed_{base_name}"
        else:
            out_filename = f"signed_{original_filename}"

        out_path = UPLOAD_FOLDER / out_filename

        doc = fitz.open(pdf_path)
        if page_num < 0 or page_num >= len(doc):
            return jsonify({"error": "Invalid page number"}), 400

        page = doc[page_num]
        rect = fitz.Rect(x, y, x + w, y + h)
        page.insert_image(rect, filename=str(sig_path))
        doc.save(out_path)
        doc.close()

        return jsonify({"success": True, "download_url": f"/api/download/{out_filename}", "filename": out_filename})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/download/<filename>")
def download_file(filename):
    file_path = UPLOAD_FOLDER / filename
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(file_path.absolute()), as_attachment=True, download_name=filename)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    port = 7860
    print(f"\n  ReportGenie v2.0 — http://localhost:{port}\n")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
