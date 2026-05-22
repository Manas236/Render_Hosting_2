import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step in [253, 257]:
                tool_calls = data.get("tool_calls", [])
                for tc in tool_calls:
                    name = tc.get("name")
                    args = tc.get("args", {})
                    content = args.get("CodeContent") or args.get("ReplacementContent")
                    if content:
                        print(f"Step {step}: {name}")
                        print(content)
                        print("=" * 60)
        except Exception as e:
            pass
