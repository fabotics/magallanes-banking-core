"""Check the MCP endpoint of a running instance with the MCP SDK's own client.

Usage:
    python scripts/mcp_check.py --base-url http://localhost:8000

It connects to `/mcp` over Streamable HTTP, lists the tools and calls
`lookup_merchant` with the tax ID of the seeded restaurant. The key is sent
as a bearer token, the way an agent platform would send it. Exits with code 1
if anything is not as expected. Reads BANK_API_KEY from the environment or `.env`.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

# Make `app` importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

GOLDEN_PATH_TAX_ID = "66871234-7"
EXPECTED_TRADE_NAME = "Restaurante El Mirador"


async def check(base_url: str, api_key: str) -> bool:
    """Run the three checks against `<base_url>/mcp` and print one line for each."""
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    transport = streamable_http_client(f"{base_url}/mcp", http_client=http_client)
    async with Client(transport) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        print(f"mcp: tools listed                  {tools}")

        found = await client.call_tool("lookup_merchant", {"tax_id": GOLDEN_PATH_TAX_ID})
        merchant = found.structured_content or {}
        print(f"mcp: lookup_merchant {GOLDEN_PATH_TAX_ID}    {merchant}")

        unknown = await client.call_tool("lookup_merchant", {"tax_id": "11111111-1"})
        not_found = unknown.structured_content or {}
        print(f"mcp: lookup_merchant unknown       {not_found}")

    return (
        tools == ["lookup_merchant"]
        and merchant.get("trade_name") == EXPECTED_TRADE_NAME
        and not found.is_error
        and not_found.get("found") is False
        and not unknown.is_error
    )


def main() -> None:
    """Parse the arguments, run the check and set the exit code."""
    parser = argparse.ArgumentParser(description="MCP check for a running banking core.")
    parser.add_argument("--base-url", required=True, help="for example http://localhost:8000")
    args = parser.parse_args()

    api_key = get_settings().bank_api_key
    if not api_key:
        sys.exit("BANK_API_KEY is not set in the environment or in .env")
    ok = asyncio.run(check(args.base_url.rstrip("/"), api_key))
    print("mcp check ok" if ok else "mcp check FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
