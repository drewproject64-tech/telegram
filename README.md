# Telegram Ads → ChatGPT MCP Connector

Dedicated connector service for the official Telegram Ads advertiser API.

## Architecture
ChatGPT → MCP → Render → Telegram Ads API

## Deploy
Build: `pip install -r requirements.txt`
Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`

Required Render environment variables:
- TELEGRAM_ADS_TOKEN
- MCP_API_KEY
- ENABLE_WRITES=false

Never commit API credentials.

MCP endpoint: `/mcp`
Health: `/health`
