import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step in [3, 4, 5]:
                print(f"Step {step} source={data.get('source')} type={data.get('type')}")
                content = data.get("content", "")
                if "WEATHER" in content.upper() or "FORECAST" in content.upper() or "RNI" in content.upper():
                    print("Found relevant content!")
                    lines = content.splitlines()
                    for idx, l in enumerate(lines):
                        if "WEATHER" in l.upper() or "FORECAST" in l.upper():
                            start = max(0, idx-5)
                            end = min(len(lines), idx+30)
                            print("\n".join(lines[start:end]))
                            break
        except Exception as e:
            pass
