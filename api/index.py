from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import os
import json

# --- Load telemetry data ---
data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "telemetry.json")

try:
    with open(data_path, "r") as f:
        data_list = json.load(f)
    df_full = pd.DataFrame(data_list)
    df_full["latency_ms"] = df_full["latency_ms"].astype(float)
    df_full["uptime_pct"] = df_full["uptime_pct"].astype(float)
except FileNotFoundError:
    print(f"ERROR: telemetry.json not found at {data_path}")
    df_full = None
except json.JSONDecodeError:
    print(f"ERROR: Failed to parse telemetry.json")
    df_full = None

# --- FastAPI app ---
app = FastAPI(title="eShopCo Latency Checker")

# --- Enable CORS for any origin ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # allow all origins
    allow_credentials=False,    # must be False with "*"
    allow_methods=["*"],        # allow all HTTP methods including OPTIONS
    allow_headers=["*"],        # allow all headers
)

# --- Pydantic request model ---
class MetricsRequest(BaseModel):
    regions: list[str]
    threshold_ms: int

# --- Metric calculation ---
def get_metrics_for_region(region_df: pd.DataFrame, threshold: int) -> dict:
    avg_latency = region_df["latency_ms"].mean()
    p95_latency = region_df["latency_ms"].quantile(0.95)
    breaches = (region_df["latency_ms"] > threshold).sum()
    avg_uptime = region_df["uptime_pct"].mean() / 100.0
    return {
        "avg_latency": round(avg_latency, 2),
        "p95_latency": round(p95_latency, 2),
        "avg_uptime": round(avg_uptime, 4),
        "breaches": int(breaches),
    }

# --- POST endpoint for metrics ---
@app.post("/")
async def get_region_metrics(request: MetricsRequest):
    if df_full is None:
        raise HTTPException(status_code=500, detail="Data loading failed. Check telemetry.json path.")

    results = {}
    for region in request.regions:
        region_df = df_full[df_full["region"] == region.lower()]
        if region_df.empty:
            results[region] = {"error": f"No data found for region '{region}'"}
            continue
        results[region] = get_metrics_for_region(region_df, request.threshold_ms)

    return results

# --- OPTIONS handler for preflight (optional but ensures dashboards work) ---
@app.options("/{rest_of_path:path}")
async def options_handler(rest_of_path: str, request: Request):
    return {}

# --- Root / health check endpoint ---
@app.get("/")
async def read_root():
    return {"status": "ok", "message": "Latency checker service is running."}
