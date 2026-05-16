#!/bin/bash
set -e

# InfluxDB initialization script. This runs automatically if mounted to /docker-entrypoint-initdb.d
echo "Initializing additional InfluxDB buckets..."

# Wait for InfluxDB to start accepting connections via CLI
influx ping

# Create campus_1m
influx bucket create -n campus_1m -o smart-campus -r 7d || echo "Bucket campus_1m may already exist"

# Create campus_1h
influx bucket create -n campus_1h -o smart-campus -r 30d || echo "Bucket campus_1h may already exist"

# Create campus_1d
influx bucket create -n campus_1d -o smart-campus -r 365d || echo "Bucket campus_1d may already exist"

echo "Additional buckets created."
