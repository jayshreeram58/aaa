"""
Course Wallah Bypass Service Runner
Starts the standalone REST API & Web UI server.
"""

import os
import sys

if __name__ == "__main__":
    from bypass_service.server import run_server
    port = int(os.environ.get("BYPASS_PORT", os.environ.get("PORT", 5055)))
    run_server(host="0.0.0.0", port=port)
