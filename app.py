"""
Flask REST API — NBA PEO–Mission Mapping Service
-------------------------------------------------
Endpoints:
  POST /api/analyze        – Upload SAR + optional manual, run full pipeline
  POST /api/analyze/manual – Provide PEOs & DMs as JSON (no file upload needed)
  GET  /api/health         – Health check
  GET  /                   – Serve frontend HTML
"""

import json
import logging
import os
import sys
import signal
import threading
import time

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from orchestrator import run_pipeline, run_pipeline_stream
from services.document_ingestor import ingest_document
import services.llm_router as llm_router

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Max upload size: 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NBA Mapping Engine"})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Accepts multipart/form-data with:
      - sar_file   (required) : SAR document (PDF or DOCX)
      - manual_file (optional): NBA manual PDF
    Runs the full 4-agent pipeline and returns the report as JSON.
    """
    if "sar_file" not in request.files:
        return jsonify({"status": "error", "error": "No SAR file uploaded."}), 400

    if "llm_provider" in request.form:
        llm_router.PROVIDER = request.form["llm_provider"].strip().lower()

    sar_file = request.files["sar_file"]
    sar_bytes = sar_file.read()
    sar_filename = sar_file.filename

    manual_bytes = None
    manual_filename = ""
    if "manual_file" in request.files:
        mf = request.files["manual_file"]
        manual_bytes = mf.read()
        manual_filename = mf.filename

    logger.info("Received SAR file: %s (%d bytes)", sar_filename, len(sar_bytes))

    result = run_pipeline(
        sar_bytes=sar_bytes,
        sar_filename=sar_filename,
        manual_bytes=manual_bytes,
        manual_filename=manual_filename,
    )

    if result["status"] == "error":
        return jsonify(result), 422

    return jsonify(_serialize_result(result))


@app.route("/api/analyze/manual", methods=["POST"])
def analyze_manual():
    """
    Accepts JSON body:
    {
      "peos": [{"id": "PEO1", "text": "..."}, ...],
      "missions": [{"id": "DM1", "text": "..."}, ...]
    }
    Runs the full pipeline with manually provided PEOs & DMs.
    """
    data = request.get_json(force=True, silent=True) or {}
    peos = data.get("peos", [])
    missions = data.get("missions", [])

    if "llm_provider" in data:
        llm_router.PROVIDER = data["llm_provider"].strip().lower()

    if not peos:
        return jsonify({"status": "error", "error": "No PEOs provided."}), 400
    if not missions:
        return jsonify({"status": "error", "error": "No Mission statements provided."}), 400

    # Provide a minimal placeholder for the SAR document
    placeholder = "manual_input.txt"
    result = run_pipeline(
        sar_bytes=b"manual",
        sar_filename=placeholder,
        extra_peos=peos,
        extra_missions=missions,
    )

    if result["status"] == "error":
        return jsonify(result), 422

    return jsonify(_serialize_result(result))


@app.route("/api/analyze/stream", methods=["POST"])
def analyze_stream():
    """
    Accepts multipart/form-data with:
      - sar_file   (required) : SAR document (PDF or DOCX)
      - manual_file (optional): NBA manual PDF
    Runs the full 4-agent pipeline and streams progress updates using SSE.
    """
    if "sar_file" not in request.files:
        return jsonify({"status": "error", "error": "No SAR file uploaded."}), 400

    if "llm_provider" in request.form:
        llm_router.PROVIDER = request.form["llm_provider"].strip().lower()

    sar_file = request.files["sar_file"]
    sar_bytes = sar_file.read()
    sar_filename = sar_file.filename

    manual_bytes = None
    manual_filename = ""
    if "manual_file" in request.files:
        mf = request.files["manual_file"]
        manual_bytes = mf.read()
        manual_filename = mf.filename

    logger.info("Streamed SAR file: %s (%d bytes)", sar_filename, len(sar_bytes))

    def generate():
        generator = run_pipeline_stream(
            sar_bytes=sar_bytes,
            sar_filename=sar_filename,
            manual_bytes=manual_bytes,
            manual_filename=manual_filename,
        )
        for item in generator:
            if item.get("type") == "complete":
                serialized = _serialize_result(item.get("result"))
                yield f"data: {json.dumps({'type': 'complete', 'result': serialized})}\n\n"
            elif item.get("type") == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': item.get('error')})}\n\n"
            else:
                yield f"data: {json.dumps(item)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/analyze/manual/stream", methods=["POST"])
def analyze_manual_stream():
    """
    Accepts JSON body:
    {
      "peos": [{"id": "PEO1", "text": "..."}, ...],
      "missions": [{"id": "DM1", "text": "..."}, ...]
    }
    Runs the full pipeline and streams progress updates using SSE.
    """
    data = request.get_json(force=True, silent=True) or {}
    peos = data.get("peos", [])
    missions = data.get("missions", [])

    if "llm_provider" in data:
        llm_router.PROVIDER = data["llm_provider"].strip().lower()

    if not peos:
        return jsonify({"status": "error", "error": "No PEOs provided."}), 400
    if not missions:
        return jsonify({"status": "error", "error": "No Mission statements provided."}), 400

    placeholder = "manual_input.txt"
    logger.info("Streamed manual entry analysis requested.")

    def generate():
        generator = run_pipeline_stream(
            sar_bytes=b"manual",
            sar_filename=placeholder,
            extra_peos=peos,
            extra_missions=missions,
        )
        for item in generator:
            if item.get("type") == "complete":
                serialized = _serialize_result(item.get("result"))
                yield f"data: {json.dumps({'type': 'complete', 'result': serialized})}\n\n"
            elif item.get("type") == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': item.get('error')})}\n\n"
            else:
                yield f"data: {json.dumps(item)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/extract", methods=["POST"])
def extract():
    """
    Utility endpoint: extract PEOs and DMs from a document without scoring.
    Accepts: multipart/form-data with 'sar_file'
    Returns: {"peos": [...], "missions": [...]}
    """
    if "sar_file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["sar_file"]
    data = ingest_document(f.read(), f.filename)
    return jsonify({
        "peos": data["peos"],
        "missions": data["missions"],
        "source": data["source"],
    })


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    logger.info("Shutdown requested via API. Terminating servers...")
    
    def kill_servers():
        time.sleep(1) # Allow response to be sent
        # Kill the MCP Server window if it exists
        if os.name == 'nt':
            os.system('taskkill /FI "WINDOWTITLE eq Mech AI Agents MCP Server*" /T /F')
        
        # Kill Flask server by sending SIGTERM to self
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=kill_servers).start()
    return jsonify({"status": "success", "message": "Servers are shutting down..."})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_result(result: dict) -> dict:
    """
    Ensure the result dict is JSON-serialisable.
    The report's 'markdown' field is kept as a string.
    """
    report = result.get("report", {})
    return {
        "status": result["status"],
        "peos": result["peos"],
        "missions": result["missions"],
        "report": {
            "matrix_table": report.get("matrix_table", []),
            "averages": report.get("averages", {}),
            "justifications": report.get("justifications", []),
            "summary_stats": report.get("summary_stats", {}),
            "dm_ids": report.get("dm_ids", []),
            "peo_ids": report.get("peo_ids", []),
            "markdown": report.get("markdown", ""),
        },
        # Include raw breakdowns for debug / transparency panel
        "peo_breakdown": result.get("peo_breakdown", {}),
        "mission_breakdown": result.get("mission_breakdown", {}),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    logger.info("Starting NBA Mapping Engine on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
