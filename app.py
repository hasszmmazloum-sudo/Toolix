import os
import uuid
import logging
import traceback
import io
from pathlib import Path
from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
import aiofiles
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg"]
ALLOWED_PDF_TYPES = ["application/pdf"]

def get_unique_filename(original_filename: str):
    """Generate unique filename"""
    ext = Path(original_filename).suffix
    return f"{uuid.uuid4().hex}{ext}"

def cleanup_file(file_path: str, delay: int = 60):
    """Delete file after delay"""
    import threading
    def remove_file():
        import time
        time.sleep(delay)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    threading.Thread(target=remove_file, daemon=True).start()

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/compress", response_class=HTMLResponse)
async def compress_page(request: Request):
    return templates.TemplateResponse("compress.html", {"request": request})

@app.post("/api/remove-bg")
async def remove_background(file: UploadFile = File(...)):
    try:
         from PIL import Image
import io

@app.post("/api/remove-bg")
async def remove_background(file: UploadFile = File(...)):
    try:
        from rembg import remove

        content = await file.read()

        image = Image.open(io.BytesIO(content))
        image.thumbnail((1000, 1000))

        temp_buffer = io.BytesIO()
        image.save(temp_buffer, format="PNG")
        resized_data = temp_buffer.getvalue()

        output_data = remove(resized_data)

        output_filename = f"nobg_{uuid.uuid4().hex}.png"
        output_path = os.path.join("outputs", output_filename)

        with open(output_path, "wb") as f:
            f.write(output_data)

        return FileResponse(
            output_path,
            media_type="image/png",
            filename="removed-background.png"
        )

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
        ...

@app.get("/image-to-pdf", response_class=HTMLResponse)
async def image_to_pdf_page(request: Request):
    return templates.TemplateResponse("image-to-pdf.html", {"request": request})

@app.get("/merge-pdf", response_class=HTMLResponse)
async def merge_pdf_page(request: Request):
    return templates.TemplateResponse("merge-pdf.html", {"request": request})

# Compression endpoint
@app.post("/compress-image")
async def compress_image(file: UploadFile = File(...)):
    try:
        logger.info(f"Compressing: {file.filename}")
        
        # Read file
        content = await file.read()
        
        # Check file size
        if len(content) > 5 * 1024 * 1024:
    raise HTTPException(status_code=400, detail="Image too large. Please upload a smaller image.")
        
        # Save input
        input_path = os.path.join("uploads", get_unique_filename(file.filename))
        with open(input_path, "wb") as f:
            f.write(content)
        
        # Compress
        output_filename = f"{uuid.uuid4().hex}_compressed.jpg"
        output_path = os.path.join("outputs", output_filename)
        
        image = Image.open(input_path)
        image = image.convert("RGB")
        
        # Adjust quality based on file size
        quality = 70
        if len(content) > 5 * 1024 * 1024:  # >5MB
            quality = 50
        elif len(content) > 2 * 1024 * 1024:  # >2MB
            quality = 60
            
        image.save(output_path, "JPEG", quality=quality, optimize=True)
        
        # Get sizes
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0
        
        # Cleanup
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

# Background Removal using rembg
@app.post("/api/remove-bg")
async def remove_background(file: UploadFile = File(...)):
    try:
        logger.info(f"Processing background removal for: {file.filename}")
        
        # Validate file type
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="File type not allowed. Please upload JPG or PNG images."
            )
        
        # Read file content
        content = await file.read()
        
        # Check file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds {MAX_FILE_SIZE // 1024 // 1024}MB limit"
            )
        
        # Remove background using rembg
        logger.info("Removing background with rembg...")
        output_data = remove(content)
        
        # Save output as PNG
        output_filename = f"nobg_{uuid.uuid4().hex}.png"
        output_path = os.path.join("outputs", output_filename)
        
        with open(output_path, "wb") as f:
            f.write(output_data)
        
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Failed to create output file")
        
        logger.info(f"Background removal completed. Output saved to: {output_path}")
        
        # Schedule cleanup
        cleanup_file(output_path, 60)
        
        # Return the file
        original_name = Path(file.filename).stem
        return FileResponse(
            path=output_path,
            media_type="image/png",
            filename=f"nobg_{original_name}.png"
        )
    
    except Exception as e:
        logger.error(f"Background removal error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Background removal failed: {str(e)}")

# Image to PDF endpoint
@app.post("/api/image-to-pdf")
async def convert_images_to_pdf(files: List[UploadFile] = File(...)):
    """Convert images to single PDF"""
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
            
            # Validate file type
            if file.content_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail=f"File {file.filename}: type not allowed")
            
            # Read file content
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds size limit")
            
            # Save temporarily
            temp_path = os.path.join("uploads", get_unique_filename(file.filename))
            with open(temp_path, 'wb') as f:
                f.write(content)
            temp_files.append(temp_path)
            
            # Open and convert image
            img = Image.open(temp_path)
            
            # Convert to RGB
            if img.mode == 'RGBA':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
                img = rgb_img
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            images.append(img)
        
        if not images:
            raise HTTPException(status_code=400, detail="No valid images to convert")
        
        # Create PDF
        output_filename = f"images_{uuid.uuid4().hex}.pdf"
        output_path = os.path.join("outputs", output_filename)
        
        # Save as PDF
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:] if len(images) > 1 else [],
            resolution=100.0,
            optimize=True
        )
        
        logger.info(f"PDF created successfully: {output_path}")
        
        # Cleanup
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

# Merge PDF endpoint
# Merge PDF endpoint with better error handling
@app.post("/api/merge-pdf")
async def merge_pdfs(files: List[UploadFile] = File(...)):
    """Merge multiple PDFs with improved error handling"""
    try:
        from pypdf import PdfReader, PdfWriter
        
        logger.info(f"Merging {len(files)} PDFs")
        
        if len(files) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 PDF files to merge")
        
        if len(files) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 PDF files allowed")
        
        writer = PdfWriter()
        temp_files = []
        valid_pdfs = []
        
        for idx, file in enumerate(files):
            logger.info(f"Processing PDF {idx + 1}: {file.filename}")
            
            # Validate file type
            if file.content_type not in ALLOWED_PDF_TYPES:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is not a valid PDF (wrong content type)")
            
            # Read file content
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {MAX_FILE_SIZE // 1024 // 1024}MB limit")
            
            # Check if file is empty
            if len(content) == 0:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")
            
            # Check PDF header
            if not content.startswith(b'%PDF'):
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' does not appear to be a valid PDF (missing PDF header)")
            
            # Save file
            filename = get_unique_filename(file.filename)
            filepath = os.path.join("uploads", filename)
            
            with open(filepath, 'wb') as f:
                f.write(content)
            
            temp_files.append(filepath)
            
            # Try to read PDF
            try:
                reader = PdfReader(filepath)
                
                # Check if PDF has any pages
                if len(reader.pages) == 0:
                    logger.warning(f"PDF '{file.filename}' has no pages")
                    continue
                
                # Add pages to writer
                for page in reader.pages:
                    writer.add_page(page)
                
                valid_pdfs.append(file.filename)
                logger.info(f"Successfully added {len(reader.pages)} pages from '{file.filename}'")
                
            except Exception as e:
                logger.error(f"Error reading PDF '{file.filename}': {str(e)}")
                # Clean up this file
                try:
                    os.remove(filepath)
                except:
                    pass
                raise HTTPException(status_code=400, detail=f"Invalid PDF file: {file.filename} - {str(e)}")
        
        # Check if we have any valid PDFs
        if len(valid_pdfs) == 0:
            raise HTTPException(status_code=400, detail="No valid PDF files with pages found")
        
        if len(writer.pages) == 0:
            raise HTTPException(status_code=400, detail="No pages found in the uploaded PDFs")
        
        # Save merged PDF
        output_filename = f"merged_{uuid.uuid4().hex}.pdf"
        output_path = os.path.join("outputs", output_filename)
        
        try:
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            # Verify the merged file was created
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("Merged PDF file is empty or was not created")
            
            logger.info(f"Merged PDF created successfully: {output_path} with {len(writer.pages)} pages from {len(valid_pdfs)} files")
            
        except Exception as e:
            logger.error(f"Error writing merged PDF: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating merged PDF: {str(e)}")
        
        # Schedule cleanup
        for temp_path in temp_files:
            cleanup_file(temp_path)
        cleanup_file(output_path)
        
        # Return the merged file
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
    """Download processed file"""
    file_path = os.path.join("outputs", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename, media_type="application/octet-stream")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

    from fastapi.responses import FileResponse

@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("ads.txt")