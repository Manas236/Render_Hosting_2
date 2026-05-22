import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step == 3:
                print("Keys:", list(data.keys()))
                print("Status:", data.get("status"))
                print("Tool Calls:", json.dumps(data.get("tool_calls"), indent=2)[:500])
                # Check for output or response
                for k, v in data.items():
                    if k not in ["content", "tool_calls"]:
                        print(f"{k}: {str(v)[:100]}")
        except Exception as e:
            pass
