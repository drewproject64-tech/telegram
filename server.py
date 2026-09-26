import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastmcp import FastMCP
from telead import Client, InputAdTargetChannels

load_dotenv()

TELEGRAM_ADS_TOKEN = os.getenv("TELEGRAM_ADS_TOKEN", "").strip()
MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()
ENABLE_WRITES = os.getenv("ENABLE_WRITES", "false").lower() == "true"

if not TELEGRAM_ADS_TOKEN:
    raise RuntimeError("TELEGRAM_ADS_TOKEN is required")

mcp = FastMCP("Telegram Ads")
app = FastAPI(title="Telegram Ads ChatGPT MCP", version="1.0.0")


def api_client() -> Client:
    return Client(TELEGRAM_ADS_TOKEN)


def require_writes() -> None:
    if not ENABLE_WRITES:
        raise RuntimeError(
            "Write operations are disabled. Set ENABLE_WRITES=true in Render after testing."
        )


def dump(value: Any) -> Any:
    fn = getattr(value, "model_dump", None)
    return fn() if callable(fn) else value


@mcp.tool()
def get_account() -> dict[str, Any]:
    """Get the current Telegram Ads advertiser account information."""
    with api_client() as c:
        return dump(c.get_current_account())


@mcp.tool()
def list_ads(status: str | None = None) -> list[dict[str, Any]]:
    """List Telegram Ads, optionally filtered by status."""
    with api_client() as c:
        ads = []
        for ad in c.iter_ads():
            data = dump(ad)
            if status and str(data.get("status", "")).lower() != status.lower():
                continue
            ads.append(data)
        return ads


@mcp.tool()
def get_ad_stats(ad_id: str, period: str = "day") -> dict[str, Any]:
    """Get statistics for a Telegram ad. Supported periods depend on Telegram's API."""
    with api_client() as c:
        return dump(c.get_ad_stats(ad_id, period=period))


@mcp.tool()
def validate_ad_copy(text: str, destination: str) -> dict[str, Any]:
    """Check common Telegram Ads copy and destination issues before submission."""
    problems: list[str] = []
    warnings: list[str] = []

    if len(text) > 160:
        problems.append(f"Text is {len(text)} characters; Telegram Ads allows up to 160.")
    if "\n" in text or "\r" in text:
        problems.append("Ad text contains a line break.")
    if re.search(r"https?://(?!t\.me/)", text, re.I):
        problems.append("External URLs should not be used in the ad text.")
    if not re.match(r"^(https://)?t\.me/[A-Za-z0-9_+/?=&.-]+$", destination):
        warnings.append("Destination is not a standard t.me Telegram destination.")
    if re.search(r"[!?]{4,}", text):
        warnings.append("Review excessive punctuation.")
    if re.search(r"\b(guaranteed|guarantee|risk[- ]free|100% profit|double your money)\b", text, re.I):
        warnings.append("Potentially absolute or misleading claim detected.")
    if re.search(r"\b(profit|profits|investment|returns|trading signals)\b", text, re.I):
        warnings.append("Financial/promotional language detected; review Telegram's current policies.")

    return {
        "ok": not problems,
        "character_count": len(text),
        "problems": problems,
        "warnings": warnings,
        "destination": destination,
    }


@mcp.tool()
def create_ad(
    title: str,
    text: str,
    promote_url: str,
    cpm: float,
    initial_budget: float,
    target_channels: list[str],
) -> dict[str, Any]:
    """Create a Telegram ad. Requires ENABLE_WRITES=true."""
    require_writes()
    validation = validate_ad_copy(text, promote_url)
    if not validation["ok"]:
        return {"created": False, "validation": validation}

    with api_client() as c:
        ad = c.create_ad(
            title=title,
            text=text,
            promote_url=promote_url,
            cpm=cpm,
            placement="channel_post",
            target=InputAdTargetChannels(channel_ids=target_channels),
            initial_budget=initial_budget,
        )
        return {"created": True, "ad": dump(ad)}


@mcp.tool()
def pause_ad(ad_id: str) -> dict[str, Any]:
    """Pause a Telegram ad. Requires ENABLE_WRITES=true."""
    require_writes()
    with api_client() as c:
        return {"success": True, "result": dump(c.pause_ad(ad_id))}


@mcp.tool()
def update_ad(
    ad_id: str,
    title: str | None = None,
    text: str | None = None,
    promote_url: str | None = None,
    cpm: float | None = None,
    budget: float | None = None,
) -> dict[str, Any]:
    """Update a Telegram ad. Requires ENABLE_WRITES=true."""
    require_writes()

    if text is not None:
        validation = validate_ad_copy(text, promote_url or "")
        if not validation["ok"]:
            return {"updated": False, "validation": validation}

    kwargs: dict[str, Any] = {}
    if title is not None:
        kwargs["title"] = title
    if text is not None:
        kwargs["text"] = text
    if promote_url is not None:
        kwargs["promote_url"] = promote_url
    if cpm is not None:
        kwargs["cpm"] = cpm
    if budget is not None:
        kwargs["budget"] = budget

    with api_client() as c:
        return {"updated": True, "result": dump(c.update_ad(ad_id, **kwargs))}


@app.get("/health")
def health():
    return {
        "ok": True,
        "telegram_ads_configured": bool(TELEGRAM_ADS_TOKEN),
        "writes_enabled": ENABLE_WRITES,
    }


@app.middleware("http")
async def protect_http(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    if MCP_API_KEY and request.headers.get("x-mcp-api-key") != MCP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid MCP API key")

    return await call_next(request)


mcp_app = mcp.http_app(path="/mcp")
app.mount("/", mcp_app)
