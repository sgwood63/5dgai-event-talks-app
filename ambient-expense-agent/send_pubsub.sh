#!/bin/bash

# send_pubsub.sh
# Sends a JSON expense payload to the local Pub/Sub endpoint.

PORT=${PORT:-8080}
URL="http://localhost:${PORT}/pubsub"

# Check if input is from stdin (pipe) or passed as a file/argument
if [ -t 0 ]; then
  # stdin is a terminal, check arguments
  if [ -n "$1" ]; then
    if [ -f "$1" ]; then
      # Read from file path
      JSON_INPUT=$(cat "$1")
    else
      # Treat argument as raw JSON string
      JSON_INPUT="$1"
    fi
  else
    echo "Usage:"
    echo "  $0 '<json_string>'"
    echo "  $0 <path_to_json_file>"
    echo "  echo '<json_string>' | $0"
    exit 1
  fi
else
  # Read from stdin pipe
  JSON_INPUT=$(cat)
fi

# Validate that the input is non-empty
if [ -z "$JSON_INPUT" ]; then
  echo "Error: Input JSON is empty."
  exit 1
fi

# Base64 encode the JSON input without newlines
DATA_B64=$(echo -n "$JSON_INPUT" | base64 | tr -d '\n')

# Generate a unique message ID (using uuidgen on Mac, fallback to date stamp)
MSG_ID=$(uuidgen 2>/dev/null || echo "msg-$(date +%s)")

# Construct the Pub/Sub envelope JSON
ENVELOPE=$(cat <<EOF
{
  "message": {
    "data": "$DATA_B64",
    "messageId": "$MSG_ID"
  },
  "subscription": "projects/my-project/subscriptions/test-sub"
}
EOF
)

# Send the payload to the pubsub endpoint
curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$ENVELOPE"
echo "" # Ensure trailing newline in terminal output
