#!/bin/bash
# This script simulates the GitHub Actions workflow locally
# It assumes you have Python and required packages installed

echo "==== Simulating GitHub Actions Workflow ===="
echo "SentinelOne Data Collection"
echo

# Check if API token is set
if [ -z "$API_TOKEN" ] && [ -z "$SENTINEL_API_TOKEN" ]; then
  echo "❌ Error: API_TOKEN or SENTINEL_API_TOKEN environment variable is required"
  echo "Please set one of these environment variables first:"
  echo "  export API_TOKEN=your_token_here"
  echo "  OR"
  echo "  export SENTINEL_API_TOKEN=your_token_here"
  exit 1
fi

# Create output directory
OUTPUT_DIR="data_output"
mkdir -p "$OUTPUT_DIR"

# Check if specific endpoints were provided
if [ $# -gt 0 ]; then
  ENDPOINTS="$*"
  echo "Running with specific endpoints: $ENDPOINTS"
  python main.py --output "$OUTPUT_DIR" --endpoints $ENDPOINTS
else
  echo "Running with all endpoints"
  python main.py --output "$OUTPUT_DIR"
fi

# Show summary of collected files
echo
echo "==== Collection Results ===="
echo "CSV files generated:"
ls -lh "$OUTPUT_DIR"/*.csv 2>/dev/null || echo "No CSV files were generated"

echo
echo "Logs:"
ls -lh "$OUTPUT_DIR"/logs/*.log 2>/dev/null || echo "No log files were generated"

echo
echo "To view these results as if they were GitHub Actions artifacts,"
echo "open the CSV files in a spreadsheet application."
