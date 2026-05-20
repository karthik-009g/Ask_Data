import json
import urllib.request

url = "http://localhost:8000/openapi.json"
route = "/api/v1/admin/employees/{employee_id}/permissions"

with urllib.request.urlopen(url, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))

paths = data.get("paths", {})
print("HAS_ROUTE", route in paths)
if route in paths:
    print("ROUTE_METHODS", sorted(paths[route].keys()))
