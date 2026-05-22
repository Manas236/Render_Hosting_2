import os
from PIL import Image

uploaded_dir = r"c:\Users\Admin\Desktop\Project Pandora\uploaded_images"
files = [
    "FW19_AFC_Ranveer_Singh_Stills_Shot_1_0210.webp",
    "FW19_AFC_Ranveer_Singh_Stills_Shot_3_1203.webp",
    "Swara Sawant (2) (1).jfif"
]

for filename in os.listdir(uploaded_dir):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.jfif')):
        path = os.path.join(uploaded_dir, filename)
        try:
            with Image.open(path) as img:
                print(f"File: {filename} | Format: {img.format} | Size: {img.size} | Mode: {img.mode}")
        except Exception as e:
            print(f"Failed to open {filename}: {e}")
