from PIL import Image

path = r"c:\Users\Admin\Desktop\Project Pandora\uploaded_images\Swara Sawant (2) (1).jfif"
try:
    with Image.open(path) as img:
        width, height = img.size
        print(f"Image dimensions: {width}x{height}")
        # Sample pixels from top, bottom, left, right borders
        print("Top border pixels (y=0, x=0, w/4, w/2, 3w/4, w-1):")
        for x in [0, width//4, width//2, 3*width//4, width-1]:
            print(f"  x={x}, y=0: {img.getpixel((x, 0))}")
            
        print("Bottom border pixels (y=h-1, x=0, w/4, w/2, 3w/4, w-1):")
        for x in [0, width//4, width//2, 3*width//4, width-1]:
            print(f"  x={x}, y={height-1}: {img.getpixel((x, height-1))}")
            
        print("Left border pixels (x=0, y=0, h/4, h/2, 3h/4, h-1):")
        for y in [0, height//4, height//2, 3*height//4, height-1]:
            print(f"  x=0, y={y}: {img.getpixel((0, y))}")

except Exception as e:
    print(f"Failed: {e}")
