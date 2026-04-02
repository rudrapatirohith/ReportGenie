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

from ai_agent import generate_report_content
from pdf_writer import fill_report

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)


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
        "department": "Technology",
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
        department = (data.get("department") or "Technology").strip()
        remarks = (data.get("remarks") or "").strip()
        employee_name = (data.get("employee_name") or "Rohith Rudrapati").strip()
        project_name = (data.get("project_name") or "Modelone").strip()
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
            gemini_key=gemini_key,
            groq_key=groq_key,
            openrouter_key=openrouter_key,
            mode=mode,
        )

        model_used = result.pop("_model_used", "unknown")

        # Handle signature if uploaded
        sig_path = None
        # (signatures handled via separate upload in frontend)

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
        department = (data.get("department") or "Technology").strip()
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

        pdf_path = fill_report(report_data)

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


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    port = 7860
    print(f"\n  ReportGenie v2.0 — http://localhost:{port}\n")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
