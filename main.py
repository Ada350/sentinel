import requests
import pandas as pd
import os
import logging
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError

try:
    from        # Fetch data from each endpoint
        for name, config in selected_endpoints.items():
            logger.info(f"Processing {name}...")
            alt_endpoints = config.get("alt_endpoints", None)
            data = fetch_with_retry(config["endpoint"], config["params"], alt_endpoints)
            collection_status[name] = len(data) > 0
            dataframes[name] = create_dataframe(data, name)v import load_dotenv
    # Load environment variables from .env file if it exists
    load_dotenv()
except ImportError:
    # dotenv is optional - only needed for local development
    pass

# === CONFIGURATION ===
# Parse command lines arguments
def parse_args():
    parser = argparse.ArgumentParser(description="SentinelOne API Data Collector")
    parser.add_argument("--output", type=str, 
                        help="Output directory for CSV files")
    parser.add_argument("--endpoints", nargs="+", 
                        help="Specific endpoints to fetch (space-separated)")
    parser.add_argument("--log-level", type=str, 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set logging level")
    return parser.parse_args()

# Get arguments
args = parse_args()

# API token can be loaded from multiple sources for flexibility
# - API_TOKEN environment variable (for local development)
# - SENTINEL_API_TOKEN environment variable (for GitHub/Codespaces)
API_TOKEN = os.getenv("API_TOKEN") or os.getenv("SENTINEL_API_TOKEN")
if API_TOKEN:
    # Strip any whitespace or newline characters that might be in the token
    API_TOKEN = API_TOKEN.strip()

# Get output dir and log level
OUTPUT_DIR = args.output or os.getenv("OUTPUT_DIR", "data_output")
LOG_LEVEL = args.log_level or os.getenv("LOG_LEVEL", "INFO")

# API request settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
TIMEOUT = 30  # seconds
REQUEST_DELAY = 0.5  # seconds

if not API_TOKEN:
    print("❌ Error: API_TOKEN or SENTINEL_API_TOKEN environment variable is required")
    sys.exit(1)

# === LOGGING SETUP ===
# Set up basic logging to file and console
log_dir = Path(OUTPUT_DIR) / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"sentinel_api_{timestamp}.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("sentinel-api")

# Set up headers for API requests
HEADERS = {
    "Authorization": f"ApiToken {API_TOKEN}",
    "Content-Type": "application/json"
}

# Determine BASE_URL with flexibility
BASE_URL = os.getenv("BASE_URL")
if not BASE_URL:
    # Default to usea1-012, but allow overriding
    region = os.getenv("SENTINEL_REGION", "usea1-012")
    api_version = os.getenv("API_VERSION", "v2.1")
    BASE_URL = f"https://{region}.sentinelone.net/web/api/{api_version}"
    logger.info(f"Using auto-configured BASE_URL: {BASE_URL}")

# === API ENDPOINTS ===
# Dictionary of endpoints to fetch
ENDPOINTS = {
    "sites": {"endpoint": "/sites", "params": None},
    "policies": {"endpoint": "/policies", "params": None, "alt_endpoints": ["/endpoint-policies"]},
    "exclusions": {"endpoint": "/exclusions", "params": None},
    "deployments": {"endpoint": "/deployment-packs", "params": None, "alt_endpoints": ["/install-packages", "/installer-packages"]},
    "agents": {"endpoint": "/agents", "params": {"limit": 1000}},
    "rules": {"endpoint": "/rules", "params": None, "alt_endpoints": ["/firewall/rules", "/network/rules"]},
    "alerts": {"endpoint": "/alerts", "params": {"limit": 100}, "alt_endpoints": ["/threats", "/activities"]},
    "api_tokens": {"endpoint": "/api-tokens", "params": None, "alt_endpoints": ["/users/api-token-details"]}
}

# === HELPER FUNCTIONS ===
def fetch_with_retry(endpoint, params=None, alt_endpoints=None):
    """Fetch data from API with retry logic"""
    # Try primary endpoint first
    url = f"{BASE_URL}{endpoint}"
    attempts = 0
    primary_failed = False
    
    while attempts < MAX_RETRIES:
        try:
            logger.info(f"Fetching data from {endpoint}")
            
            # Add delay to prevent rate limiting
            if attempts > 0:
                time.sleep(REQUEST_DELAY)
                
            response = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json().get("data", [])
            logger.info(f"Successfully fetched {len(data)} records from {endpoint}")
            return data
            
        except HTTPError as http_err:
            logger.error(f"HTTP error occurred when calling {endpoint}: {http_err}")
            if response.status_code == 401:
                logger.error("Authentication failed. Check your API token.")
                return []  # No point retrying auth failures
            elif response.status_code == 403:
                logger.error("Permission denied. Your API token may not have sufficient privileges.")
                return []  # No point retrying permission issues
            elif response.status_code == 429:
                logger.error("Rate limit exceeded. Retrying after delay.")
                # Continue to retry logic for rate limits
            elif response.status_code == 404 and alt_endpoints and attempts == MAX_RETRIES - 1:
                # If primary endpoint is 404 and we've tried enough times, mark it as failed
                # We'll try alternate endpoints after
                primary_failed = True
                logger.warning(f"Endpoint {endpoint} not found (404). Will try alternate endpoints.")
                break
            else:
                logger.error(f"HTTP error {response.status_code}. Retrying...")
        except (ConnectionError, Timeout) as err:
            logger.error(f"Connection error when calling {endpoint}: {err}")
        except Exception as e:
            logger.error(f"Unexpected error occurred when calling {endpoint}: {e}")
            return []  # Don't retry unexpected errors
            
        # Exponential backoff
        attempts += 1
        if attempts < MAX_RETRIES:
            wait_time = RETRY_DELAY * (2 ** (attempts - 1))
            logger.warning(f"Attempt {attempts} failed. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for {endpoint}")
    
    # If primary endpoint failed with 404 and we have alternates, try those
    if primary_failed and alt_endpoints:
        for alt_endpoint in alt_endpoints:
            logger.info(f"Trying alternate endpoint: {alt_endpoint}")
            alt_url = f"{BASE_URL}{alt_endpoint}"
            try:
                response = requests.get(alt_url, headers=HEADERS, params=params, timeout=TIMEOUT)
                response.raise_for_status()
                data = response.json().get("data", [])
                logger.info(f"Successfully fetched {len(data)} records from alternate endpoint {alt_endpoint}")
                return data
            except Exception as e:
                logger.warning(f"Alternate endpoint {alt_endpoint} also failed: {e}")
                continue
    
    return []  # Return empty list if all attempts fail

def create_dataframe(data, name):
    """Create DataFrame from API data"""
    try:
        if not data:
            logger.warning(f"No data available for {name}")
            return pd.DataFrame()
        
        # Special handling for the sites data which may have nested structures
        if name == "sites":
            # First attempt to normalize nested data
            try:
                # Clean and normalize the data before creating DataFrame
                # This helps with mixed dict/non-Series data
                flat_data = []
                for item in data:
                    # Create a flattened copy of each item
                    flat_item = {}
                    for key, value in item.items():
                        if isinstance(value, dict):
                            # Flatten nested dict with prefixed keys
                            for sub_key, sub_value in value.items():
                                flat_item[f"{key}_{sub_key}"] = sub_value
                        else:
                            flat_item[key] = value
                    flat_data.append(flat_item)
                
                df = pd.DataFrame(flat_data)
                logger.info(f"Created flattened DataFrame for {name} with {len(df)} rows")
                return df
            except Exception as inner_e:
                logger.warning(f"Flattening approach failed for {name}: {inner_e}. Trying alternative approach.")
                # Fall back to pandas normalization
                df = pd.json_normalize(data)
                logger.info(f"Created normalized DataFrame for {name} with {len(df)} rows")
                return df
        
        # Default approach for other endpoints
        df = pd.DataFrame(data)
        logger.info(f"Created DataFrame for {name} with {len(df)} rows")
        return df
    except Exception as e:
        logger.error(f"Error creating DataFrame for {name}: {e}")
        return pd.DataFrame()

def export_to_csv(df, filename):
    """Export DataFrame to CSV file"""
    try:
        if df.empty:
            logger.warning(f"DataFrame for {filename} is empty, skipping export")
            return False
            
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        df.to_csv(filename, index=False)
        logger.info(f"Exported {len(df)} rows to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error exporting to {filename}: {e}")
        return False

# === MAIN EXECUTION ===
def main():
    """Main function to collect and export SentinelOne data"""
    try:
        logger.info("Starting SentinelOne data collection")
        
        # Create output directory
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Track collection status and dataframes
        collection_status = {}
        dataframes = {}
        
        # Filter endpoints if specific ones are requested
        selected_endpoints = {}
        if args.endpoints:
            logger.info(f"Filtering for specific endpoints: {', '.join(args.endpoints)}")
            for endpoint in args.endpoints:
                if endpoint in ENDPOINTS:
                    selected_endpoints[endpoint] = ENDPOINTS[endpoint]
                else:
                    logger.warning(f"Unknown endpoint: {endpoint}")
        else:
            selected_endpoints = ENDPOINTS
            
        if not selected_endpoints:
            logger.error("No valid endpoints selected for collection")
            return 1
            
        # Fetch data from each endpoint
        for name, config in selected_endpoints.items():
            logger.info(f"Processing {name}...")
            data = fetch_with_retry(config["endpoint"], config["params"], config.get("alt_endpoints"))
            collection_status[name] = len(data) > 0
            dataframes[name] = create_dataframe(data, name)
        
        # Export data to CSV
        success_count = 0
        for name, df in dataframes.items():
            filename = os.path.join(OUTPUT_DIR, f"sentinelone_{name}.csv")
            if export_to_csv(df, filename):
                success_count += 1
        
        # Print summary
        logger.info(f"Completed with {success_count}/{len(ENDPOINTS)} datasets exported successfully")
        print("\n=== Collection Summary ===")
        for name, status in collection_status.items():
            status_icon = "✅" if status else "❌"
            print(f"{status_icon} {name.capitalize()}: {'Data collected' if status else 'No data collected'}")
            
        return 0
        
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
        print(f"❌ An error occurred: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())# Trigger workflow run
