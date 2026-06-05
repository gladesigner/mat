import json, sys
data = {r["id"]: r for r in json.load(open("oppskrifter.json"))}
ids = json.load(open("oversettelser/utvalg.json"))
n = int(sys.argv[1]); STR = 10
for i in ids[(n-1)*STR : n*STR]:
    r = data[i]
    print(f"### {i}")
    print("T:", r["title"])
    if r["description"]: print("D:", r["description"])
    print("I:", " | ".join(r["ingredients"]))
    print("S:", " ¶ ".join(r["instructions"]))
    print()
