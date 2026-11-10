import json
import tomllib
from datetime import datetime

with open("fleet.toml", "rb") as handle:
    settings = tomllib.load(handle)

print(settings["share_with"])     # ['GB', 'NO', 'DK']
print(settings["upload_window"])  # 22:30:00
print(settings["archive_mode"])   # 416
print(type(settings["commissioned"]).__name__)  # date
print("contact" in settings)      # False

danish = settings["recipient"][1]

print(danish["since"])            # 2026-04-15 08:00:00+02:00

try:
    json.dumps(settings)
except TypeError as error:
    print(error)  # Object of type time is not JSON serializable

print(json.dumps(danish["since"], default=str))  # "2026-04-15 08:00:00+02:00"

print(json.dumps(danish["since"], default=datetime.isoformat))
# "2026-04-15T08:00:00+02:00"
