import sys
import os
import asyncio
from fastapi.encoders import jsonable_encoder

# Add web/backend first so backend imports resolve to web/backend
root_dir = os.path.abspath(os.path.dirname(__file__))
backend_dir = os.path.join(root_dir, "web", "backend")
sys.path.insert(0, backend_dir)
sys.path.insert(1, root_dir)

# Now we can import the routing functions
import web.backend.api.routes.detections as detections
from fastapi import UploadFile
import io

async def run_test():
    # Force detector to None to trigger fallback contour detection
    detections.detector = None
    
    # Read the test image using absolute path
    test_image_path = os.path.join(root_dir, "test_image.jpg")
    with open(test_image_path, "rb") as f:
        img_bytes = f.read()
    
    # Create a mock UploadFile
    upload_file = UploadFile(
        file=io.BytesIO(img_bytes),
        filename="test_image.jpg"
    )
    
    print("Running process_image with detector = None...")
    try:
        res = await detections.process_image(
            file=upload_file,
            org_id=None,
            gps_lat=39.9208,
            gps_lon=32.8541
        )
        print("Success! Response:")
        print(res)
        
        print("\nSerializing with jsonable_encoder...")
        encoded = jsonable_encoder(res)
        print("Serialization success!")
        print(encoded)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
