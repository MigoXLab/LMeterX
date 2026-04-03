# ⚡ lmeterx-web-loadtest

LMeterX Web Load Test Skill. Enter a webpage URL to automatically analyze the page's APIs, perform connectivity pre-checks, and batch-create load testing tasks.

## Quick Start

### 1. Environment Variable Configuration

The script comes with the following built-in default values ​​and can be run directly. If you wish to override these defaults, you can set variables with the same names via environment variables or the `.openclaw/.env` file:

| Variable | Default Value | Description |
|------|--------|------|
| `LMETERX_BASE_URL` | `http://localhost:8080` | LMeterX Backend Address |
| `LMETERX_AUTH_TOKEN` | `localhost_lmeterx` | Service Token: Binds to an Agent User |


### 2. Run

```bash
# Basic Usage
python scripts/run.py --url "https://example.com"

# Custom Parameters
python scripts/run.py \
  --url "https://example.com" \
  --concurrent-users 80 \
  --duration 600 \
  --spawn-rate 80
```

## Parameter Description

| Parameter | Default Value | Description |
|------|--------|------|
| `--url` | (Required) | Target Page URL |
| `--concurrent-users` | 10 | concurrent users (1-5000) |
| `--duration` | 300 | duration/s |
| `--spawn-rate` | 10| spawn rate |

## Security Guidelines

- **Whitelist Mechanism:** Only calls to 3 specific interfaces are permitted; requests to any other paths will be blocked.
- **Token Override:** If you wish to use a custom Token, you can override the default by setting the environment variable `LMETERX_AUTH_TOKEN`.
- **Concurrency Limit:** The maximum limit for concurrent users is set to 5,000 to prevent accidental misuse.
