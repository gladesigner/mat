import json, glob
data = json.load(open("oppskrifter.json"))
overs = {}
for f in sorted(glob.glob("oversettelser/batch*.json")):
    overs.update(json.load(open(f)))
n = 0
for r in data:
    o = overs.get(r["id"])
    if not o: continue
    r["original_language"] = r["language"]; r["language"] = "nb"
    r["title"] = o["t"]
    if o.get("d"): r["description"] = o["d"]
    r["ingredients"] = o["i"]; r["instructions"] = o["s"]
    n += 1
json.dump(data, open("oppskrifter.json","w"), ensure_ascii=False, indent=2)
with open("oppskrifter.js","w") as f:
    f.write("window.RECIPES = "); json.dump(data, f, ensure_ascii=False); f.write(";\n")
print(f"✓ {n} oversettelser flettet inn")
