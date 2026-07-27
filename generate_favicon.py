from PIL import Image
import os
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_favicon.py <source_image>")
        sys.exit(1)
        
    source_img = sys.argv[1]
    out_dir = "ui/public"
    
    img = Image.open(source_img)
    # Ensure image is in RGBA mode
    img = img.convert("RGBA")
    
    # 1. favicon.ico (usually contains 16x16 and 32x32, sometimes 48x48)
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
    img.save(os.path.join(out_dir, "favicon.ico"), sizes=icon_sizes)
    
    # 2. favicon-32x32.png
    img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
    img_32.save(os.path.join(out_dir, "favicon-32x32.png"))
    
    # 3. favicon-16x16.png
    img_16 = img.resize((16, 16), Image.Resampling.LANCZOS)
    img_16.save(os.path.join(out_dir, "favicon-16x16.png"))
    
    # 4. apple-touch-icon.png (180x180)
    img_180 = img.resize((180, 180), Image.Resampling.LANCZOS)
    # Background for apple touch icon should ideally not be transparent, but let's keep it as is.
    # We can add a white background if needed, but RGBA is okay for now.
    img_180.save(os.path.join(out_dir, "apple-touch-icon.png"))
    
    print("Successfully generated all favicons!")

if __name__ == "__main__":
    main()
