import json

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step = data.get("step_index")
            if step in [752, 754, 756, 772, 774, 778]:
                print(f"Step {step}: type={data.get('type')}")
                content = data.get("content", "")
                if content:
                    print(f"  Content length: {len(content)}")
                    # Find 'WEATHER' in content case-insensitive
                    idx = content.upper().find("WEATHER")
                    if idx != -1:
                        print(f"  Found WEATHER at index {idx}")
                        # Print 300 chars around it
                        print(content[max(0, idx-50):min(len(content), idx+500)])
                        print("="*60)
        except Exception as e:
            pass
