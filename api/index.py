"""
api/index.py — Vercel serverless entry (Flask)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request
from lib.reconcile import full_report, generate_dataset, run_reconciliation

app = Flask(__name__)

@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/api/reconcile", methods=["GET"])
def reconcile():
    n_clean = int(request.args.get("n_clean", 120))
    n_gaps  = int(request.args.get("n_gaps",  30))
    n_clean = min(max(n_clean, 10), 500)
    n_gaps  = min(max(n_gaps,  5),  100)
    platform, bank, injected = generate_dataset(n_clean, n_gaps)
    result = run_reconciliation(platform, bank)
    result["injected_gap_count"] = len(injected)
    return jsonify(result)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
