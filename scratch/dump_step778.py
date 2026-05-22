import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("step_index") == 778:
                content = data.get("content", "")
                with open("scratch/step778_view.html", "w", encoding="utf-8") as out:
                    out.write(content)
                print("Successfully wrote step 778 content to scratch/step778_view.html")
                break
        except Exception as e:
            pass
