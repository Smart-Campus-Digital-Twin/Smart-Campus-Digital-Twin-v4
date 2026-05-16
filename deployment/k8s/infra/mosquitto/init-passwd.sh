#!/bin/sh
# Creates the Mosquitto password file from environment variables.
# Runs once at container startup via Docker CMD override.
set -eu

PASSWD_FILE="/mosquitto/data/passwd"

if [ ! -f "$PASSWD_FILE" ]; then
    echo "Creating Mosquitto password file..."
    mosquitto_passwd -b -c "$PASSWD_FILE" "${MQTT_USERNAME}" "${MQTT_PASSWORD}"
    chmod 0640 "$PASSWD_FILE"
    chown root:mosquitto "$PASSWD_FILE" 2>/dev/null || chmod 0644 "$PASSWD_FILE"
    echo "Password file created."
else
    echo "Password file already exists — skipping creation."
fi

exec mosquitto -c /mosquitto/config/mosquitto.conf
