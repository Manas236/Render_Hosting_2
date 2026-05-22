import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
out_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\scratch\original_Day17.html"

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step == 3:
                content = data.get("content", "")
                with open(out_path, "w", encoding="utf-8") as out:
                    out.write(content)
                print("Successfully wrote original Day17.html content to:", out_path)
                break
        except Exception as e:
            print("Error:", e)
