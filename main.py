import requests
import pandas as pd
import os

# === CONFIGURATION ===
API_TOKEN = os.getenv("API_TOKEN")  # Loaded securely from .env or environment
BASE_URL = "https://usea1-012.sentinelone.net/web/api/v2.1"  # <-- Updated with your real console URL

HEADERS = {
    "Authorization": f"ApiToken {API_TOKEN}",
    "Content-Type": "application/json"
}

# === HELPER ===
def fetch(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json().get("data", [])

# === DATA COLLECTION ===
print("Fetching site structure...")
sites = fetch("/sites")

print("Fetching policies...")
policies = fetch("/policies")

print("Fetching exclusions...")
exclusions = fetch("/exclusions")

print("Fetching agent deployment packs...")
deployments = fetch("/deployment-packs")

print("Fetching agents (OS coverage, version info)...")
agents = fetch("/agents", params={"limit": 1000})

print("Fetching detection rules...")
rules = fetch("/rules")

print("Fetching alerts...")
alerts = fetch("/alerts", params={"limit": 100})

print("Fetching API tokens...")
api_tokens = fetch("/api-tokens")

# === OPTIONAL: convert to DataFrames for analysis/export ===
df_sites = pd.DataFrame(sites)
df_policies = pd.DataFrame(policies)
df_exclusions = pd.DataFrame(exclusions)
df_deployments = pd.DataFrame(deployments)
df_agents = pd.DataFrame(agents)
df_rules = pd.DataFrame(rules)
df_alerts = pd.DataFrame(alerts)
df_api_tokens = pd.DataFrame(api_tokens)

# === CSV EXPORT ===
df_sites.to_csv("sentinelone_sites.csv", index=False)
df_policies.to_csv("sentinelone_policies.csv", index=False)
df_exclusions.to_csv("sentinelone_exclusions.csv", index=False)
df_deployments.to_csv("sentinelone_deployments.csv", index=False)
df_agents.to_csv("sentinelone_agents.csv", index=False)
df_rules.to_csv("sentinelone_rules.csv", index=False)
df_alerts.to_csv("sentinelone_alerts.csv", index=False)
df_api_tokens.to_csv("sentinelone_api_tokens.csv", index=False)

print("✅ All data exported to CSV files.")