import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                name = tc.get("name")
                args = tc.get("args", {})
                target = args.get("TargetFile") or args.get("Target")
                if target and "Day17.html" in target:
                    content = args.get("CodeContent") or args.get("ReplacementContent")
                    if content and "WEATHER" in content.upper():
                        print(f"Step {data.get('step_index')}: {name}")
                        print("Content length:", len(content))
                        # Let's search for the weather block in the content
                        lines = content.splitlines()
                        for i, l in enumerate(lines):
                            if "WEATHER FORECAST" in l:
                                start = max(0, i-5)
                                end = min(len(lines), i+40)
                                print("\n".join(lines[start:end]))
                                print("="*50)
                                break
        except Exception as e:
            pass
