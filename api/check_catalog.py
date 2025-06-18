import json

# Load JSON file
with open('./db/dso_catalog.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Basic checks
print(f"Total objects found: {len(data)}")
print("\nFirst 3 entries:\n")

for i, obj in enumerate(data[:3]):
    print(f"Entry {i+1}:")
    for key, value in obj.items():
        print(f"  {key}: {value}")
    print("-" * 40)

# Check for required keys and uniqueness of 'designation'
missing_keys = set()
designations = set()
duplicates = []

for obj in data:
    if 'designation' not in obj:
        missing_keys.add('designation')
    else:
        if obj['designation'] in designations:
            duplicates.append(obj['designation'])
        else:
            designations.add(obj['designation'])

if missing_keys:
    print("⚠️  Some objects are missing the 'designation' field.")
else:
    print("✅ All objects have a 'designation' field.")

if duplicates:
    print(f"⚠️  Duplicate designations found: {duplicates}")
else:
    print("✅ No duplicate designations found.")