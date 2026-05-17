"""
stdio Transport Layer
======================
Provides stdio-based MCP transport for compatibility with Glama's
automated testing infrastructure and stdio-based MCP clients.

Reads JSON-RPC messages from stdin, routes through the same tool
registry as the HTTP server, and writes responses to stdout.

The existing HTTP server (main.py --serve) is unchanged and continues
to serve real agent traffic. This file is only used when stdio
transport is needed (e.g. Glama's build system, Claude Desktop).

Usage:
  python stdio_server.py

MCP clients connect by spawning this process and communicating
via stdin/stdout.
"""

import asyncio
import json
import logging
import os
import sys

# Suppress all logging to stdout — MCP stdio transport uses stdout
# for protocol messages only
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
log = logging.getLogger("stdio")

# Add parent directory to path if running from subdirectory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def handle_request(request: dict, registry) -> dict:
    """Route a single MCP JSON-RPC request and return a response."""
    req_id  = request.get("id")
    method  = request.get("method", "")
    params  = request.get("params") or {}

    try:
        # initialize handshake
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "Scientific Tools MCP Server",
                        "version": "1.0.0",
                    },
                },
            }

        # tools/list
        if method == "tools/list":
            tools = [t.to_mcp_schema() for t in registry.list_all()]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": tools,
                    "disclaimer": (
                        "Data from third-party APIs. Provided as is without warranty. "
                        "Not for clinical, legal, or safety-critical use. "
                        "Terms: https://mcp-site.com/terms"
                    ),
                },
            }

        # tools/call
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}

            tool = registry.get(tool_name)
            if not tool:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}",
                    },
                }

            # Execute tool
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(arguments)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: tool.handler(arguments)
                )

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result, indent=2)}
                    ],
                    "isError": False,
                },
            }

        # notifications (no response needed)
        if method.startswith("notifications/"):
            return None

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    except Exception as exc:
        log.error("Handler error for %s: %s", method, exc)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(exc)}",
            },
        }


async def run_stdio():
    """Main stdio loop — reads from stdin, writes to stdout."""

    # Bootstrap tool registry
    from server import ToolRegistry
    from tools.literature_search import register as reg_lit
    from tools.compound_lookup    import register as reg_chem
    from tools.gpu_spot_prices    import register as reg_gpu
    from tools.patent_search      import register as reg_patent
    from tools.scientific_data    import register as reg_scidata
    from tools.analytics          import register as reg_analytics

    registry = ToolRegistry()
    reg_lit(registry)
    reg_chem(registry)
    reg_gpu(registry)
    reg_patent(registry)
    reg_scidata(registry)
    reg_analytics(registry)

    log.info("stdio server ready — %d tools", registry.count())

    # Read line by line from stdin
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(
        writer_transport, writer_protocol, reader, loop
    )

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            line = line.decode("utf-8").strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                _write(writer_transport, response)
                continue

            response = await handle_request(request, registry)

            # Notifications return None — no response needed
            if response is not None:
                _write(writer_transport, response)

        except asyncio.IncompleteReadError:
            break
        except Exception as exc:
            log.error("stdio loop error: %s", exc)
            break


def _write(transport, data: dict) -> None:
    """Write a JSON-RPC response to stdout, newline-delimited."""
    line = json.dumps(data, separators=(",", ":")) + "\n"
    transport.write(line.encode("utf-8"))


def main():
    try:
        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
