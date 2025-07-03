# SentinelOne API Data Collector

A simple Python script to collect and export data from the SentinelOne API.

## Features

- Collects data from multiple SentinelOne API endpoints
- Converts API responses to Pandas DataFrames
- Exports data to CSV files
- Error handling with automatic retries
- Basic logging to file and console
- GitHub Actions integration for automated data collection

## Requirements

- Python 3.6+
- Required packages: requests, pandas

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The script uses environment variables for configuration:

- `API_TOKEN` or `SENTINEL_API_TOKEN` - Your SentinelOne API token (required)
- `BASE_URL` - SentinelOne API base URL (optional, default provided)
- `OUTPUT_DIR` - Directory for exported files (optional, default: "sentinelone_data")
- `LOG_LEVEL` - Logging level (optional, default: "INFO")

### Setting Up API Token

#### Local Development
Create a `.env` file with your API token:
```
API_TOKEN=your_token_here
```

#### GitHub Actions/Codespaces
Store your API token as a secret named `SENTINEL_API_TOKEN`.

## Usage

Run the script:

```bash
python main.py
```

## GitHub Actions Integration

This project includes GitHub Actions workflow for automated data collection:

### Workflow Features

- Runs daily (at 1 AM UTC by default)
- Can be triggered manually
- Uses securely stored API token from GitHub Secrets
- Generates and uploads CSV files as artifacts
- Stores logs for troubleshooting

### Setting Up GitHub Secrets

1. In your GitHub repository, go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Create a secret with name `SENTINEL_API_TOKEN` and your SentinelOne API token as the value

### Setting Up GitHub Codespaces Secrets

If you're using GitHub Codespaces for development:

1. Go to your GitHub account settings → **Codespaces**
2. Click on **Codespaces secrets**
3. Add a new secret with name `SENTINEL_API_TOKEN` and your API token as the value
4. Select which repositories can access this secret

### Manual Workflow Trigger

1. Go to the **Actions** tab in your GitHub repository
2. Select the **SentinelOne Data Collection** workflow
3. Click **Run workflow**

### Accessing the Data

After the workflow runs successfully:

1. Go to the completed workflow run
2. Scroll down to the **Artifacts** section
3. Download the **sentinelone-data** artifact to access the CSV files

## Output

The script creates a directory structure:

```
sentinelone_data/
├── sentinelone_sites.csv
├── sentinelone_policies.csv
├── sentinelone_exclusions.csv
├── sentinelone_deployments.csv
├── sentinelone_agents.csv
├── sentinelone_rules.csv
├── sentinelone_alerts.csv
├── sentinelone_api_tokens.csv
└── logs/
    └── sentinel_api_20250703_120000.log
```

## Error Handling

The application handles various error scenarios:

- API authentication failures
- Network connectivity issues
- Rate limiting
- Request timeouts
- Data processing errors

All errors are logged with detailed information for troubleshooting.

## License

MIT
