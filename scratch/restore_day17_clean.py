import json
import re

log_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\.system_generated\logs\transcript.jsonl"
recovered = None
max_len = 0
best_step = -1

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "VIEW_FILE":
                content = data.get("content", "")
                if "Day17.html" in content:
                    print(f"VIEW_FILE step {data.get('step_index')} has length {len(content)}")
                    if len(content) > max_len:
                        max_len = len(content)
                        recovered = content
                        best_step = data.get('step_index')
        except Exception as e:
            print("Error parsing line:", e)

if recovered:
    print(f"Recovering from step {best_step} with length {max_len}")
    lines = recovered.splitlines()
    cleaned_html_lines = []
    start_parsing = False
    for l in lines:
        if "1: <!" in l or re.match(r'^\s*1:\s*<html', l) or re.match(r'^\s*1:\s*<!DOCTYPE', l):
            start_parsing = True
        if start_parsing:
            m = re.match(r'^\s*\d+:\s?(.*)', l)
            if m:
                cleaned_html_lines.append(m.group(1))
            else:
                cleaned_html_lines.append(l)
            
    recovered_html = "\n".join(cleaned_html_lines)
    print(f"Recovered HTML has {len(cleaned_html_lines)} lines")
    with open("scratch/recovered_Day17.html", "w", encoding="utf-8") as out:
        out.write(recovered_html)
    print("Wrote clean recovered HTML to scratch/recovered_Day17.html")
else:
    print("Could not recover clean HTML")
