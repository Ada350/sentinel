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
    from dotenv import load_dotenv
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
else:
    # If no token provided, we could try to generate one using the API
    # POST https://your_management_url/web/api/v2.0/users/generate-api-token
    # This would require username/password authentication which is not recommended for automation
    # Instead, we'll just exit with an error
    print("❌ Error: API_TOKEN or SENTINEL_API_TOKEN environment variable is required")
    sys.exit(1)

# Get output dir and log level
OUTPUT_DIR = args.output or os.getenv("OUTPUT_DIR", "data_output")
LOG_LEVEL = args.log_level or os.getenv("LOG_LEVEL", "INFO")

# API request settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
TIMEOUT = 30  # seconds
REQUEST_DELAY = 1  # seconds - increased to help avoid rate limits
# Add rate limiting to comply with API documentation
RATE_LIMITS = {
    "agents": 25,  # 25 calls per second
    "threats": 25,  # 25 calls per second
    "cloud-detection/rules": 0.5,  # 30 calls per minute
    "threat-intelligence": 0.08,  # 5 calls per minute
    "default": 1  # 1 call per second for others
}

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
    
    # If any endpoints fail with 404, we might want to try a different API version
    # This is done by providing alternate endpoints, but we can also set up a fallback URL
    # Prioritize newer versions first, then try older ones
    fallback_versions = ["v2.1", "v2.0", "v2"]
    if api_version in fallback_versions:
        fallback_versions.remove(api_version)
    FALLBACK_URLS = [f"https://{region}.sentinelone.net/web/api/{v}" for v in fallback_versions]
    if FALLBACK_URLS:
        logger.info(f"Configured fallback API URLs if needed: {FALLBACK_URLS}")
    
    # Try to discover available API versions
    try:
        logger.info("Attempting to discover available API versions...")
        # Try to hit the base API without a version to see if it returns info
        discovery_url = f"https://{region}.sentinelone.net/web/api"
        discovery_response = requests.get(f"{discovery_url}/version", headers=HEADERS, timeout=TIMEOUT)
        if discovery_response.status_code == 200:
            version_info = discovery_response.json()
            logger.info(f"API version discovery successful: {version_info}")
            # Could parse this to update FALLBACK_URLS if needed
        else:
            logger.warning(f"API version discovery failed with status {discovery_response.status_code}")
    except Exception as e:
        logger.warning(f"Error during API version discovery: {e}")
else:
    logger.info(f"Using configured BASE_URL: {BASE_URL}")
    FALLBACK_URLS = []

# === API ENDPOINTS ===
# Dictionary of endpoints to fetch
ENDPOINTS = {
    "sites": {"endpoint": "/sites", "params": {"limit": 100}, "paginate": True},
    "policies": {"endpoint": "/policies", "params": {"limit": 100}, "alt_endpoints": ["/endpoint-policies", "/policy", "/settings/policies"], "paginate": True},
    "exclusions": {"endpoint": "/exclusions", "params": {"limit": 100}, "paginate": True},
    "deployments": {"endpoint": "/deployment-packs", "params": {"limit": 100}, "alt_endpoints": ["/install-packages", "/installer-packages", "/packages", "/sentinels/installer"], "paginate": True},
    "agents": {"endpoint": "/agents", "params": {"limit": 100}, "alt_endpoints": ["/sentinels"], "paginate": True, "rate_limit": 25},
    "rules": {"endpoint": "/rules", "params": {"limit": 100}, "alt_endpoints": ["/firewall/rules", "/network/rules", "/firewall-rules", "/settings/rules"], "paginate": True},
    "alerts": {"endpoint": "/alerts", "params": {"limit": 100}, "alt_endpoints": ["/threats", "/activities", "/detections"], "paginate": True, "rate_limit": 25},
    "api_tokens": {"endpoint": "/users/api-token-details", "params": None, "alt_endpoints": ["/api-tokens", "/system/api-tokens", "/rbac/api-tokens", "/settings/user/tokens"], "paginate": False}
}

# === HELPER FUNCTIONS ===
def fetch_with_retry(endpoint, params=None, alt_endpoints=None, paginate=False, rate_limit=None):
    """Fetch data from API with retry logic and pagination support"""
    # Determine rate limit for this endpoint
    if rate_limit is None:
        # Check if any part of the endpoint matches a key in RATE_LIMITS
        for key, limit in RATE_LIMITS.items():
            if key in endpoint:
                rate_limit = limit
                break
        # If no match, use default
        if rate_limit is None:
            rate_limit = RATE_LIMITS.get("default", 1)
    
    # Calculate sleep time based on rate limit (in seconds)
    sleep_time = 1.0 / rate_limit if rate_limit > 0 else 1
    logger.debug(f"Using rate limit of {rate_limit} requests/second (sleep time: {sleep_time:.3f}s)")
    
    # Try primary endpoint first
    url = f"{BASE_URL}{endpoint}"
    attempts = 0
    primary_failed = False
    all_data = []
    
    # For pagination
    next_cursor = None
    page_count = 0
    max_pages = 100  # Safety limit
    
    # If paginating, we'll loop until no more pages
    while True:
        if page_count >= max_pages:
            logger.warning(f"Reached maximum page count ({max_pages}) for {endpoint}. Some data may be missing.")
            break
            
        page_count += 1
        current_params = params.copy() if params else {}
        
        # Add cursor if we're paginating and have a next cursor
        if paginate and next_cursor:
            current_params['cursor'] = next_cursor
            
        attempts = 0
        while attempts < MAX_RETRIES:
            try:
                if page_count == 1:
                    logger.info(f"Fetching data from {endpoint}")
                else:
                    logger.info(f"Fetching page {page_count} from {endpoint}")
                
                # Add delay to prevent rate limiting
                if attempts > 0 or page_count > 1:
                    time.sleep(max(sleep_time, REQUEST_DELAY))
                    
                response = requests.get(url, headers=HEADERS, params=current_params, timeout=TIMEOUT)
                response.raise_for_status()
                
                response_data = response.json()
                data = response_data.get("data", [])
                all_data.extend(data)
                
                if page_count == 1:
                    logger.info(f"Successfully fetched {len(data)} records from {endpoint}")
                else:
                    logger.info(f"Successfully fetched {len(data)} records from {endpoint} (page {page_count})")
                
                # Check for pagination info
                if paginate:
                    pagination = response_data.get("pagination", {})
                    next_cursor = pagination.get("nextCursor")
                    total_items = pagination.get("totalItems", 0)
                    
                    if next_cursor:
                        logger.debug(f"Found next cursor for {endpoint}, continuing pagination")
                    else:
                        logger.debug(f"No more pages for {endpoint}")
                        break
                else:
                    # Not paginating, we're done
                    break
                    
                # Break out of retry loop
                break
                
            except HTTPError as http_err:
                logger.error(f"HTTP error occurred when calling {endpoint}: {http_err}")
                if response.status_code == 401:
                    logger.error("Authentication failed. Check your API token.")
                    return []  # No point retrying auth failures
                elif response.status_code == 403:
                    logger.error("Permission denied. Your API token may not have sufficient privileges.")
                    return []  # No point retrying permission issues
                elif response.status_code == 429:
                    logger.error("Rate limit exceeded. Retrying after longer delay.")
                    sleep_time *= 2  # Double the sleep time
                elif response.status_code == 404 and alt_endpoints and attempts == MAX_RETRIES - 1 and page_count == 1:
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
                return all_data  # Don't retry unexpected errors
                
            # Exponential backoff
            attempts += 1
            if attempts < MAX_RETRIES:
                wait_time = RETRY_DELAY * (2 ** (attempts - 1))
                logger.warning(f"Attempt {attempts} failed. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for {endpoint}")
                
        # If we're not paginating or there are no more pages, exit the pagination loop
        if not paginate or not next_cursor or primary_failed:
            break
    
    # If we got some data already, return it
    if all_data:
        return all_data
        
    # If primary endpoint failed with 404 and we have alternates, try those
    if primary_failed and alt_endpoints:
        for alt_endpoint in alt_endpoints:
            logger.info(f"Trying alternate endpoint: {alt_endpoint}")
            alt_url = f"{BASE_URL}{alt_endpoint}"
            try:
                # Use the same pagination approach for alternate endpoints
                alt_all_data = []
                alt_next_cursor = None
                alt_page_count = 0
                
                while True:
                    if alt_page_count >= max_pages:
                        logger.warning(f"Reached maximum page count ({max_pages}) for {alt_endpoint}. Some data may be missing.")
                        break
                        
                    alt_page_count += 1
                    alt_current_params = params.copy() if params else {}
                    
                    # Add cursor if we're paginating and have a next cursor
                    if paginate and alt_next_cursor:
                        alt_current_params['cursor'] = alt_next_cursor
                
                    # Apply rate limiting
                    if alt_page_count > 1:
                        time.sleep(sleep_time)
                
                    response = requests.get(alt_url, headers=HEADERS, params=alt_current_params, timeout=TIMEOUT)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    data = response_data.get("data", [])
                    alt_all_data.extend(data)
                    
                    if alt_page_count == 1:
                        logger.info(f"Successfully fetched {len(data)} records from alternate endpoint {alt_endpoint}")
                    else:
                        logger.info(f"Successfully fetched {len(data)} records from alternate endpoint {alt_endpoint} (page {alt_page_count})")
                    
                    # Check for pagination info
                    if paginate:
                        pagination = response_data.get("pagination", {})
                        alt_next_cursor = pagination.get("nextCursor")
                        
                        if alt_next_cursor:
                            logger.debug(f"Found next cursor for {alt_endpoint}, continuing pagination")
                        else:
                            logger.debug(f"No more pages for {alt_endpoint}")
                            break
                    else:
                        # Not paginating, we're done
                        break
                
                return alt_all_data
            except Exception as e:
                logger.warning(f"Alternate endpoint {alt_endpoint} also failed: {e}")
                continue
    
    # If all alternate endpoints failed and we have fallback URLs, try the primary endpoint with each fallback URL
    if primary_failed and 'FALLBACK_URLS' in globals() and FALLBACK_URLS:
        logger.info(f"Trying fallback API versions")
        for fallback_url in FALLBACK_URLS:
            fallback_full_url = f"{fallback_url}{endpoint}"
            logger.info(f"Trying fallback URL: {fallback_full_url}")
            try:
                # Use the same pagination approach for fallback URLs
                fallback_all_data = []
                fallback_next_cursor = None
                fallback_page_count = 0
                
                while True:
                    if fallback_page_count >= max_pages:
                        logger.warning(f"Reached maximum page count ({max_pages}) for {fallback_full_url}. Some data may be missing.")
                        break
                        
                    fallback_page_count += 1
                    fallback_current_params = params.copy() if params else {}
                    
                    # Add cursor if we're paginating and have a next cursor
                    if paginate and fallback_next_cursor:
                        fallback_current_params['cursor'] = fallback_next_cursor
                
                    # Apply rate limiting
                    if fallback_page_count > 1:
                        time.sleep(sleep_time)
                
                    response = requests.get(fallback_full_url, headers=HEADERS, params=fallback_current_params, timeout=TIMEOUT)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    data = response_data.get("data", [])
                    fallback_all_data.extend(data)
                    
                    if fallback_page_count == 1:
                        logger.info(f"Successfully fetched {len(data)} records from fallback URL {fallback_full_url}")
                    else:
                        logger.info(f"Successfully fetched {len(data)} records from fallback URL {fallback_full_url} (page {fallback_page_count})")
                    
                    # Check for pagination info
                    if paginate:
                        pagination = response_data.get("pagination", {})
                        fallback_next_cursor = pagination.get("nextCursor")
                        
                        if fallback_next_cursor:
                            logger.debug(f"Found next cursor for {fallback_full_url}, continuing pagination")
                        else:
                            logger.debug(f"No more pages for {fallback_full_url}")
                            break
                    else:
                        # Not paginating, we're done
                        break
                
                return fallback_all_data
            except Exception as e:
                logger.warning(f"Fallback URL {fallback_full_url} also failed: {e}")
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
            try:
                # First check if the data is a list of objects
                if not isinstance(data, list):
                    logger.warning(f"Expected list for {name} but got {type(data)}. Converting to list.")
                    if isinstance(data, dict):
                        data = [data]
                    else:
                        # If it's a string or other type, wrap in a list with a single dict
                        data = [{"data": data}]
                
                # Clean and normalize the data before creating DataFrame
                flat_data = []
                for item in data:
                    # Skip if not a dict
                    if not isinstance(item, dict):
                        logger.warning(f"Skipping non-dict item in {name}: {type(item)}")
                        continue
                        
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
                
                if flat_data:
                    df = pd.DataFrame(flat_data)
                    logger.info(f"Created flattened DataFrame for {name} with {len(df)} rows")
                    return df
                else:
                    # If no valid items were found, fall back to json_normalize
                    logger.warning(f"No valid items found for {name} using flattening approach. Trying normalization.")
                    raise ValueError("No valid items found")
                    
            except Exception as inner_e:
                logger.warning(f"Flattening approach failed for {name}: {inner_e}. Trying alternative approach.")
                # Fall back to pandas normalization
                try:
                    df = pd.json_normalize(data)
                    logger.info(f"Created normalized DataFrame for {name} with {len(df)} rows")
                    return df
                except Exception as norm_e:
                    logger.warning(f"Normalization failed for {name}: {norm_e}. Trying simple approach.")
                    # If normalization fails, try simple approach
                    if isinstance(data, list) and all(isinstance(item, str) for item in data):
                        df = pd.DataFrame({"name": data})
                        logger.info(f"Created simple DataFrame for {name} with {len(df)} rows")
                        return df
                    else:
                        # Last resort - try converting to strings
                        df = pd.DataFrame([{"data": str(d)} for d in data])
                        logger.info(f"Created fallback DataFrame for {name} with {len(df)} rows")
                        return df
        
        # Default approach for other endpoints
        try:
            df = pd.DataFrame(data)
            logger.info(f"Created DataFrame for {name} with {len(df)} rows")
            return df
        except Exception as df_e:
            logger.warning(f"Standard DataFrame creation failed for {name}: {df_e}. Trying normalization.")
            try:
                df = pd.json_normalize(data)
                logger.info(f"Created normalized DataFrame for {name} with {len(df)} rows")
                return df
            except Exception as norm_e:
                logger.warning(f"All DataFrame creation methods failed for {name}. Creating empty DataFrame.")
                return pd.DataFrame()
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
            paginate = config.get("paginate", False)
            rate_limit = config.get("rate_limit", None)
            data = fetch_with_retry(
                config["endpoint"], 
                config["params"], 
                config.get("alt_endpoints"),
                paginate=paginate,
                rate_limit=rate_limit
            )
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
    sys.exit(main())
