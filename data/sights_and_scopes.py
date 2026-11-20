import json
import sys
import os
from decimal import Decimal
from helpers import resource_path
from data import load_data_file


SIGHTS = {}
SCOPES = {}
sights_filename = resource_path("sights.json")
scopes_filename = resource_path("scopes.json")

for name, attachment_data in load_data_file("sights.json").items():
    attachment_data["decay"] = Decimal(attachment_data["decay"])
    SIGHTS[name] = attachment_data

for name, attachment_data in load_data_file("scopes.json").items():
    attachment_data["decay"] = Decimal(attachment_data["decay"])
    SCOPES[name] = attachment_data


FIELDS = ("name", "type", "decay", "ammo")

if __name__ == "__main__":

    file_type = ("sights", "scopes")

    for i, fn in enumerate(sys.argv[1:]):

        file_data = {}
        with open(fn, 'r') as f:
            header = True
            for line in f.readlines():
                if header:
                    header = False
                    continue
                try:
                    data = dict(zip(FIELDS, line.split(";")))
                    data["decay"] = Decimal(data["decay"] if data["decay"].strip() else "0.0") / Decimal(100.0)
                    data["ammo"] = int(data["ammo"] if data["ammo"].strip() else 0)

                    file_data[data["name"]] = {
                        "type": data["type"],
                        "decay": str(data["decay"]),
                        "ammo": data["ammo"]
                    }

                except:
                    raise
                    print(line)
                    break

        if file_data:
            output = open(f"{file_type[i]}.json", 'w')
            output.write(json.dumps(file_data, indent=2, sort_keys=True))
