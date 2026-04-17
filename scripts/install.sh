#!/usr/bin/env bash
# OpenSpeakers — one-line installer (delegates to setup-openspeakers.sh)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/scripts/install.sh | bash
#
# For the full interactive setup script (recommended):
#   curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main/setup-openspeakers.sh | bash
#
set -euo pipefail

REPO="https://raw.githubusercontent.com/davidamacey/OpenSpeakers/main"

echo "Downloading OpenSpeakers setup script..."
curl -fsSL "$REPO/setup-openspeakers.sh" | bash
