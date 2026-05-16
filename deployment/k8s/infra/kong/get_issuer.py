import json, sys

d = json.load(open("/tmp/realm.json"))
ts = d["token-service"]
print(ts[: ts.index("/protocol/openid-connect")])
