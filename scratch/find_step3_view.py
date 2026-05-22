import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                if tc.get("name") == "view_file" and "Day17.html" in tc.get("args", {}).get("AbsolutePath", ""):
                    print(f"Step {step} has view_file for Day17.html")
                    # print start_line and end_line
                    print(tc.get("args"))
        except Exception as e:
            pass
