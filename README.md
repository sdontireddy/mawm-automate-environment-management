# MAWM Environment Management Automation

Python-based automation tool for creating and managing Manhattan WMS environments through sequential API execution.

## Features

- Sequential API execution with dependency handling
- **Header-based environment selection** (Location, Organization headers)
- Single API URL for all environments (DEV, QA,Stage )
- Comprehensive error handling and retry logic
- Detailed logging and monitoring
- Secure credential management
- Rollback capabilities on failure
- Clone configuration between environments

## Project Structure

```
mawm-environment-mgmt-automation/
├── config/
│   ├── environments.yaml           # ALL environments configured here (unified)
│   │                               # Single URL with variant headers
│   └── api_sequences.yaml          # API call sequences
├── src/
│   ├── api_client.py               # API client with custom headers support
│   ├── orchestrator.py             # Main orchestration engine
│   ├── config_loader.py            # Configuration management
│   ├── dual_env_client.py          # Dual environment (source/dest) client
│   └── utils/
│       ├── logger.py               # Logging setup
│       ├── validators.py           # Input validation
│       └── oauth_handler.py        # OAuth 2.0 token management
├── logs/                           # Log files
├── .env.example                    # Environment variables template
├── requirements.txt                # Python dependencies
└── main.py                         # Entry point
```

## Setup

1. **Create virtual environment:**

   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   copy .env.example .env
   # Edit .env with your credentials
   ```

## Usage

### Create a new environment:

```bash
python main.py --action create --env dev
```

### Clone from Golden environment:

```bash
# Clone using default golden environment
python main.py --action clone --env dev

# Clone from specific source environment
python main.py --action clone --env qa --source-env golden

# Dry run to see what would be cloned
python main.py --action clone --env dev --dry-run
```

### Validate existing environment:

```bash
python main.py --action validate --env qa
```

### Dry run (no actual API calls):

```bash
python main.py --action create --env dev --dry-run
```

## Configuration

### Single Unified Configuration

All environments use the **same API base URL** with **different headers** to distinguish environments:

**config/environments.yaml:**

```yaml
base_url: "https://{{clientID}}.sce.manh.com"

environments:
  dev:
    name: "DeV"
    custom_headers:
      Location: "DEV"
      Organization: "DEV"

  qa:
    name: "QA"
    custom_headers:
      Location: "QA"
      Organization: "QA"

  : name: ""
    custom_headers:
      Location: ""
      Organization: ""
```

The framework automatically routes API calls based on these headers!

### API Sequences

Edit `config/api_sequences.yaml` to define:

- API call sequences
- Dependencies between calls
- Validation rules
- Clone operations (source → destination)

## Logging

Logs are stored in `logs/` directory:

- `automation_{timestamp}.log` - Detailed logs
- `errors_{timestamp}.log` - Error-only logs

## Security

- Never commit `.env` file
- Use secure credential storage (Azure Key Vault, etc.)
- Rotate API keys regularly
