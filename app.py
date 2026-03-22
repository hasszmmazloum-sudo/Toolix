import os
import uuid
import logging
import traceback
import io
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from pypdf import PdfReader, PdfWriter
import aiofiles

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create directories
for dir_name in ["uploads", "outputs", "temp"]:
    Path(dir_name).mkdir(exist_ok=True)

app = FastAPI(title="Toolix - All-in-One Online Tools")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Configuration
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg"]
ALLOWED_PDF_TYPES = ["application/pdf"]


def get_unique_filename(original_filename: str) -> str:
    ext = Path(original_filename).suffix
    return f"{uuid.uuid4().hex}{ext}"


def cleanup_file(file_path: str, delay: int = 60):
    import threading
    import time

    def remove_file():
        time.sleep(delay)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    threading.Thread(target=remove_file, daemon=True).start()


# Pages
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/compress", response_class=HTMLResponse)
async def compress_page(request: Request):
    return templates.TemplateResponse("compress.html", {"request": request})


@app.get("/remove-bg", response_class=HTMLResponse)
async def remove_bg_page(request: Request):
    return templates.TemplateResponse("remove-bg.html", {"request": request})


@app.get("/image-to-pdf", response_class=HTMLResponse)
async def image_to_pdf_page(request: Request):
    return templates.TemplateResponse("image-to-pdf.html", {"request": request})


@app.get("/merge-pdf", response_class=HTMLResponse)
async def merge_pdf_page(request: Request):
    return templates.TemplateResponse("merge-pdf.html", {"request": request})


# Compress image
@app.post("/compress-image")
async def compress_image(file: UploadFile = File(...)):
    try:
        logger.info(f"Compressing: {file.filename}")

        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Please upload JPG or PNG image")

        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large. Please upload a smaller image.")

        input_path = os.path.join("uploads", get_unique_filename(file.filename))
        with open(input_path, "wb") as f:
            f.write(content)

        output_filename = f"{uuid.uuid4().hex}_compressed.jpg"
        output_path = os.path.join("outputs", output_filename)

        image = Image.open(input_path)
        image = image.convert("RGB")

        quality = 70
        if len(content) > 2 * 1024 * 1024:
            quality = 60

        image.save(output_path, "JPEG", quality=quality, optimize=True)

        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0

        cleanup_file(input_path)
        cleanup_file(output_path)

        return JSONResponse({
            "success": True,
            "filename": output_filename,
            "download_url": f"/download/{output_filename}",
            "original_size_mb": round(original_size / (1024 * 1024), 2),
            "compressed_size_mb": round(compressed_size / (1024 * 1024), 2),
            "compression_ratio": ratio
        })

    except Exception as e:
        logger.error(f"Compression error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# Remove background
@app.post("/api/remove-bg")
async def remove_background(file: UploadFile = File(...)):
    raise HTTPException(
        status_code=503,
        detail="خارج الخدمة حاليا"
    )


# Image to PDF
@app.post("/api/image-to-pdf")
async def convert_images_to_pdf(files: List[UploadFile] = File(...)):
    try:
        logger.info(f"Converting {len(files)} images to PDF")

        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")

        if len(files) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 images allowed")

        images = []
        temp_files = []

        for idx, file in enumerate(files):
            logger.info(f"Processing image {idx + 1}: {file.filename}")

            if file.content_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail=f"File {file.filename}: type not allowed")

            content = await file.read()

            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds size limit")

            temp_path = os.path.join("uploads", get_unique_filename(file.filename))
            with open(temp_path, "wb") as f:
                f.write(content)
            temp_files.append(temp_path)

            img = Image.open(temp_path)

            if img.mode == "RGBA":
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
                img = rgb_img
            elif img.mode != "RGB":
                img = img.convert("RGB")

            images.append(img)

        if not images:
            raise HTTPException(status_code=400, detail="No valid images to convert")

        output_filename = f"images_{uuid.uuid4().hex}.pdf"
        output_path = os.path.join("outputs", output_filename)

        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:] if len(images) > 1 else [],
            resolution=100.0,
            optimize=True
        )

        for temp_path in temp_files:
            cleanup_file(temp_path)
        cleanup_file(output_path)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="converted_images.pdf"
        )

    except Exception as e:
        logger.error(f"Image to PDF error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


# Merge PDFs
@app.post("/api/merge-pdf")
async def merge_pdfs(files: List[UploadFile] = File(...)):
    try:
        logger.info(f"Merging {len(files)} PDFs")

        if len(files) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 PDF files to merge")

        if len(files) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 PDF files allowed")

        writer = PdfWriter()
        temp_files = []

        for idx, file in enumerate(files):
            logger.info(f"Processing PDF {idx + 1}: {file.filename}")

            if file.content_type not in ALLOWED_PDF_TYPES:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is not a valid PDF")

            content = await file.read()

            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds size limit")

            if len(content) == 0:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")

            if not content.startswith(b"%PDF"):
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is not a valid PDF")

            filepath = os.path.join("uploads", get_unique_filename(file.filename))
            with open(filepath, "wb") as f:
                f.write(content)

            temp_files.append(filepath)

            try:
                reader = PdfReader(filepath)
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid PDF file: {file.filename} - {str(e)}")

        if len(writer.pages) == 0:
            raise HTTPException(status_code=400, detail="No pages found in the uploaded PDFs")

        output_filename = f"merged_{uuid.uuid4().hex}.pdf"
        output_path = os.path.join("outputs", output_filename)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        for temp_path in temp_files:
            cleanup_file(temp_path)
        cleanup_file(output_path)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="merged_files.pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Merge PDF error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"PDF merge failed: {str(e)}")


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("outputs", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename, media_type="application/octet-stream")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("ads.txt")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)