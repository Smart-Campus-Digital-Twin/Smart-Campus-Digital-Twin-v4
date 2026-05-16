"""Patch the api-env secret with required API config values."""
import subprocess
import base64
import json

TOKEN = "bc9e661683cdd291830845f54875cf85f90cf937b5b191f4aba422bc61a8384b"

patches = {
    "INFLUXDB_TOKEN": TOKEN,
    "DATABASE_URL": "postgresql://campus:campus@postgres:5432/campus",
    "INFLUXDB_URL": "http://influxdb:8086",
    "INFLUXDB_ORG": "smart-campus",
    "INFLUXDB_BUCKET": "campus_sensors",
    "CORS_ORIGINS": '["http://localhost:3000","http://localhost:3001","http://campus.local","http://129.212.208.120","http://146.190.7.152"]',
}

encoded = {k: base64.b64encode(v.encode()).decode() for k, v in patches.items()}
patch = json.dumps({"data": encoded})

result = subprocess.run(
    ["kubectl", "patch", "secret", "api-env", "-n", "campus", "--patch", patch],
    capture_output=True, text=True
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)
