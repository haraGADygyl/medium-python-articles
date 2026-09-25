"""The snippets the article shows, run end to end."""
import yaml

fleet_yaml = """\
# Export settings for the north-east harbour buoys.
fleet: north-east
share_with: [GB, NO, DK]      # met offices that receive the feed
upload_window: 22:30          # UTC, after the evening poll
firmware: 1.10
archive_mode: 0640
compress: on
station_code: 07031
commissioned: 2026-02-11
contact: null
"""

settings = yaml.safe_load(fleet_yaml)
print(settings["share_with"])     # ['GB', False, 'DK']
print(settings["upload_window"])  # 1350
print(settings["firmware"])       # 1.1
print(settings["archive_mode"])   # 416
print(settings["station_code"])   # 3609
print(type(settings["commissioned"]))  # <class 'datetime.date'>

quoted = yaml.safe_load('share_with: ["GB", "NO", "DK"]\nfirmware: "1.10"\n')
print(quoted)  # {'share_with': ['GB', 'NO', 'DK'], 'firmware': '1.10'}
