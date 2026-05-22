import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step == 3:
                content = data.get("content", "")
                print(content[:2000])
                print("..." * 20)
                print(content[2000:4000])
        except Exception as e:
            pass
