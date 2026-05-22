out_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\scratch\original_Day17.html"
with open(out_path, "r", encoding="utf-8") as f:
    lines = f.readlines()
    for idx, l in enumerate(lines):
        if "WEATHER" in l.upper() or "FORECAST" in l.upper():
            print("Line number:", idx+1)
            start = max(0, idx-5)
            end = min(len(lines), idx+60)
            print("".join(lines[start:end]))
            print("="*60)
