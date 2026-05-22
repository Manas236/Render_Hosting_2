out_path = r"C:\Users\Admin\.gemini\antigravity\brain\879187dc-52c8-457b-892c-3084992961da\scratch\original_Day17.html"
with open(out_path, "r", encoding="utf-8") as f:
    content = f.read()
    print("Total file length:", len(content))
    # search for keywords
    keywords = ["weather", "forecast", "mumbai", "celcius", "high", "low", "temp"]
    for kw in keywords:
        pos = content.lower().find(kw)
        if pos != -1:
            print(f"Keyword '{kw}' found at position {pos}")
            # print snippet of 200 chars around position
            start = max(0, pos-100)
            end = min(len(content), pos+200)
            print(f"Snippet: {repr(content[start:end])}")
            print("-" * 50)
