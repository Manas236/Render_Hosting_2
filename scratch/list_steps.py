import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step < 15:
                print(f"Step {step}: source={data.get('source')}, type={data.get('type')}, content_len={len(data.get('content') or '')}")
        except Exception as e:
            pass
