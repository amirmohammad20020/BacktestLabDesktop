from PIL import Image
img = Image.open("logo.png").convert("RGBA")
img.save("app.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("app.ico ساخته شد")
