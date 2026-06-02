import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from document_normalizer_service import document_normalizer_service


project_root = Path(__file__).resolve().parents[1]
app = Flask(__name__)
CORS(app)


def load_supabase_credentials():
    url = os.getenv("ANALYTICS_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = (
        os.getenv("ANALYTICS_SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if url and key:
        return url.rstrip("/"), key

    raise RuntimeError("Supabase credentials not configured in environment")


def build_recent_date_keys(days):
    from datetime import datetime, timedelta

    start = datetime.utcnow().date() - timedelta(days=days - 1)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days)]


def fetch_analytics_rows(since_iso):
    supabase_url, supabase_key = load_supabase_credentials()
    query = urlencode(
        {
            "select": "visitor_id,user_id,created_at,path",
            "created_at": f"gte.{since_iso}",
            "order": "created_at.desc",
        }
    )
    endpoint = f"{supabase_url}/rest/v1/analytics_page_views?{query}"
    req = Request(
        endpoint,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def aggregate_traffic_summary(rows, days=14):
    from datetime import datetime, timedelta

    def to_date_key(value):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()

    recent_keys = build_recent_date_keys(days)
    today_key = recent_keys[-1]
    stats_map = {
        key: {"date": key, "page_views": 0, "visitor_ids": set(), "user_ids": set(), "top_paths": {}}
        for key in recent_keys
    }

    unique_visitors = set()

    for row in rows:
        date_key = to_date_key(row["created_at"])
        if date_key not in stats_map:
            continue
        stats_map[date_key]["page_views"] += 1
        if row.get("visitor_id"):
            stats_map[date_key]["visitor_ids"].add(row["visitor_id"])
            unique_visitors.add(row["visitor_id"])
        if row.get("user_id"):
            stats_map[date_key]["user_ids"].add(row["user_id"])
        path = row.get("path") or "/"
        stats_map[date_key]["top_paths"][path] = stats_map[date_key]["top_paths"].get(path, 0) + 1

    recent_daily = []
    for key in reversed(recent_keys):
        day_stats = stats_map[key]
        recent_daily.append(
            {
                "date": key,
                "page_views": day_stats["page_views"],
                "active_visitors": len(day_stats["visitor_ids"]),
                "signed_in_active_users": len(day_stats["user_ids"]),
                "top_paths": [
                    {"path": path, "page_views": count}
                    for path, count in sorted(
                        day_stats["top_paths"].items(), key=lambda item: item[1], reverse=True
                    )[:5]
                ],
            }
        )

    today_stats = next(item for item in recent_daily if item["date"] == today_key)
    last_7_days = recent_daily[:7]
    avg_page_views = round(sum(item["page_views"] for item in last_7_days) / max(len(last_7_days), 1))
    avg_active_visitors = round(
        sum(item["active_visitors"] for item in last_7_days) / max(len(last_7_days), 1)
    )
    yesterday_key = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
    yesterday_stats = next((item for item in recent_daily if item["date"] == yesterday_key), None)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "window_days": days,
        "today": today_stats,
        "yesterday": yesterday_stats,
        "totals": {
            "page_views": sum(item["page_views"] for item in recent_daily),
            "unique_visitors": len(unique_visitors),
        },
        "averages": {
            "page_views_7d": avg_page_views,
            "active_visitors_7d": avg_active_visitors,
        },
        "recent_daily": recent_daily,
    }


def ensure_feed_access(request_obj):
    expected_token = os.getenv("TRAFFIC_FEED_TOKEN")
    if not expected_token:
        return
    supplied_token = request_obj.args.get("token") or request_obj.headers.get("X-Traffic-Token")
    if supplied_token != expected_token:
        raise PermissionError("Invalid traffic feed token")


@app.route("/")
def home():
    return send_from_directory(project_root, "document_normalizer_agent.html")


@app.route("/<path:filename>")
def serve_static(filename):
    target = project_root / filename
    if target.exists() and target.is_file():
        return send_from_directory(project_root, filename)
    return "404 Not Found", 404


@app.route("/api/agents/document-normalizer/engines", methods=["GET"])
def get_engines():
    return jsonify({"status": "success", "engines": document_normalizer_service.engine_status()})


@app.route("/api/agents/document-normalizer/normalize", methods=["POST"])
def normalize_document():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    try:
        result = document_normalizer_service.normalize_upload(
            file_storage=file,
            user_id=request.form.get("user_id"),
            preferred_engine=request.form.get("engine_preference", "auto"),
        )
        return jsonify(result)
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@app.route("/api/agents/document-normalizer/result/<job_id>/<kind>", methods=["GET"])
def get_result(job_id, kind):
    target = document_normalizer_service.result_file(job_id, kind)
    if not target:
        return jsonify({"error": "Result file not found"}), 404
    return send_file(target, as_attachment=True, download_name=target.name)


@app.route("/api/analytics/traffic-summary", methods=["GET"])
def traffic_summary():
    try:
        ensure_feed_access(request)
        days = int(request.args.get("days", "14"))
        days = max(1, min(days, 60))
        from datetime import datetime, timedelta

        since = datetime.utcnow() - timedelta(days=days - 1)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = fetch_analytics_rows(since.isoformat() + "Z")
        return jsonify(aggregate_traffic_summary(rows, days=days))
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except Exception as error:
        return jsonify({"error": str(error)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    app.run(host="0.0.0.0", port=port, debug=False)
