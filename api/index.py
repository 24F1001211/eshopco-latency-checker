from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import os
import json


# --- Load Data ---
# Try finding the file by stepping up one directory from the script's location
# to the /vercel/output/ root, and then descending into the 'api' directory.
data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "telemetry.json")



try:
    # Load the JSON data
    with open(data_path, 'r') as f:
        data_list = json.load(f)
    
    # Use pandas to load the entire dataset once when the server starts
    df_full = pd.DataFrame(data_list)
    
    # Ensure numerical columns are correctly typed
    df_full['latency_ms'] = df_full['latency_ms'].astype(float)
    df_full['uptime_pct'] = df_full['uptime_pct'].astype(float)
    
except FileNotFoundError:
    print(f"ERROR: telemetry.json not found at {data_path}")
    df_full = None
except json.JSONDecodeError:
    print(f"ERROR: Failed to parse telemetry.json")
    df_full = None
    
# --- FastAPI App Initialization & CORS ---
app = FastAPI(title="eShopCo Latency Checker")

# Corrected CORS Configuration
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # allow all domains
    allow_credentials=False,  # must be False with "*"
    allow_methods=["*"],      # allow all HTTP methods
    allow_headers=["*"],      # allow all headers
)


# --- Pydantic Request Model ---
class MetricsRequest(BaseModel):
    """Defines the expected JSON body for the POST request."""
    regions: list[str]
    threshold_ms: int

# --- Core Metric Calculation Logic ---
def get_metrics_for_region(region_df: pd.DataFrame, threshold: int) -> dict:
    """Calculates all required metrics for a given DataFrame (single region)."""
    
    # 1. Latency Metrics
    avg_latency = region_df['latency_ms'].mean()
    p95_latency = region_df['latency_ms'].quantile(0.95)
    
    # 2. Breaches (Count where latency > threshold)
    breaches = (region_df['latency_ms'] > threshold).sum()
    
    # 3. Average Uptime
    # The requirement is 'avg_uptime' (mean), so we use the mean of the percentage column,
    # and divide by 100.0 to convert to the required fractional format.
    avg_uptime = region_df['uptime_pct'].mean() / 100.0 
    
    return {
        # Format values as required
        "avg_latency": round(avg_latency, 2),
        "p95_latency": round(p95_latency, 2),
        "avg_uptime": round(avg_uptime, 4), # Use 4 decimal places for a fraction
        "breaches": int(breaches)
    }

# --- Vercel Endpoint ---
@app.post("/")
def get_region_metrics(request: MetricsRequest):
    """
    Accepts regions and a threshold, and returns per-region performance metrics.
    """
    if df_full is None:
        raise HTTPException(status_code=500, detail="Data loading failed. Check telemetry.json path.")

    results = {}
    
    # Iterate over the requested regions
    for region in request.regions:
        # Filter the full DataFrame to get only the data for the current region
        region_df = df_full[df_full['region'] == region.lower()]
        
        if region_df.empty:
            results[region] = {"error": f"No data found for region '{region}'"}
            continue
            
        metrics = get_metrics_for_region(region_df, request.threshold_ms)
        results[region] = metrics
        
    return results

# --- Optional: Root/Health Check Endpoint ---
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Latency checker service is running."}
