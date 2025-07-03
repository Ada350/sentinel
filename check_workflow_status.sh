#!/bin/bash

# Make this script executable with: chmod +x check_workflow_status.sh

# Get the GitHub repository from the remote URL
REPO_URL=$(git config --get remote.origin.url)
REPO_PATH=$(echo $REPO_URL | sed -n 's/.*github.com[:\/]\(.*\)\.git/\1/p')

if [ -z "$REPO_PATH" ]; then
  REPO_PATH=$(echo $REPO_URL | sed -n 's/.*github.com[:\/]\(.*\)/\1/p')
fi

if [ -z "$REPO_PATH" ]; then
  echo "Error: Could not determine GitHub repository path from remote URL: $REPO_URL"
  exit 1
fi

echo "Repository: $REPO_PATH"

# Get the workflow runs
echo "Fetching workflow runs..."
WORKFLOW_RUNS=$(curl -s -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/$REPO_PATH/actions/runs?per_page=5")

# Parse the JSON response to get the workflow runs
echo "Recent workflow runs:"
echo "--------------------"
echo "$WORKFLOW_RUNS" | jq -r '.workflow_runs[] | "\(.id) | \(.name) | \(.status) | \(.conclusion) | \(.created_at) | \(.html_url)"' | \
  while read -r line; do
    IFS="|" read -r id name status conclusion created_at url <<< "$line"
    echo "ID: $id"
    echo "Name: $name"
    echo "Status: $status"
    echo "Conclusion: $conclusion"
    echo "Created: $created_at"
    echo "URL: $url"
    echo "--------------------"
  done

# If jq is not available, suggest installing it
if [ $? -ne 0 ]; then
  echo "Error: jq command not found. Please install jq to parse JSON:"
  echo "sudo apt-get install jq  # For Debian/Ubuntu"
  echo "sudo yum install jq      # For CentOS/RHEL"
  echo "brew install jq          # For macOS"
fi
