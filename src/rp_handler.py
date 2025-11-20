import os
import json
import uuid
import runpod
import base64
import requests
import boto3
from botocore.client import Config
from ComfyUI_API_Wrapper import ComfyUI_API_Wrapper

# --- Global Constants & Initialization ---
COMFYUI_URL = "http://127.0.0.1:8188"
client_id = str(uuid.uuid4())
output_path = "/root/comfy/ComfyUI/output"
api = ComfyUI_API_Wrapper(COMFYUI_URL, client_id, output_path)

# Load the workflow template at startup
WORKFLOW_TEMPLATE_PATH = "/root/workflow_api.json"
try:
    with open(WORKFLOW_TEMPLATE_PATH, 'r') as f:
        WORKFLOW_TEMPLATE = json.load(f)
    print(f"Successfully loaded workflow template from {WORKFLOW_TEMPLATE_PATH}")
except Exception as e:
    print(f"Error loading workflow template: {e}")
    WORKFLOW_TEMPLATE = None

# --- RunPod Handler ---
def handler(job):
    job_input = job.get('input', {})

    # 1. Prepare Workflow
    # Use the loaded template as a base, or accept a full workflow override
    if job_input.get('workflow'):
        workflow = job_input['workflow']
    elif WORKFLOW_TEMPLATE:
        workflow = json.loads(json.dumps(WORKFLOW_TEMPLATE)) # Deep copy
    else:
        return {"error": "No workflow provided and no template found."}

    # 2. Inject Inputs (Text-to-Image)
    # Positive Prompt (Node 6)
    if 'prompt' in job_input:
        prompt_text = job_input['prompt']
        if "6" in workflow and "inputs" in workflow["6"]:
             workflow["6"]["inputs"]["text"] = prompt_text
        else:
             print("Warning: Node 6 (Positive Prompt) not found in workflow, skipping prompt injection.")

    # Negative Prompt (Node 7) - Optional
    if 'negative_prompt' in job_input:
        neg_prompt_text = job_input['negative_prompt']
        if "7" in workflow and "inputs" in workflow["7"]:
             workflow["7"]["inputs"]["text"] = neg_prompt_text

    # Seed (Node 94 or 75) - Optional
    # If user provides seed, we update the Seed Generator (Node 94) or Sampler (Node 75)
    if 'seed' in job_input:
        seed_val = int(job_input['seed'])
        # Try Node 94 (Seed Generator) first
        if "94" in workflow and "inputs" in workflow["94"]:
             # Usually widget_values but API format uses inputs if connected, or custom node specific.
             # Comfy-image-saver's Seed Generator likely uses 'seed' in inputs for API.
             workflow["94"]["inputs"]["seed"] = seed_val
        # Fallback to Sampler (Node 75) if it has a seed input
        elif "75" in workflow and "inputs" in workflow["75"]:
             workflow["75"]["inputs"]["seed"] = seed_val

    # 3. Find Output Node (SaveImage)
    output_node_id = None
    for node_id, node_data in workflow.items():
        if node_data.get("class_type") == "SaveImage":
            output_node_id = node_id
            break

    if not output_node_id:
        return {"error": "Workflow must contain a 'SaveImage' node."}

    try:
        # 4. Execute Workflow
        output_data = api.queue_prompt_and_get_images(workflow, output_node_id)
        if not output_data:
             return {"error": "Execution timed out or generated no output."}

        # 5. Upload to R2/S3
        s3_client = boto3.client(
            's3',
            endpoint_url=os.environ.get('R2_ENDPOINT_URL'),
            aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
            config=Config(signature_version='s3v4')
        )

        bucket_name = os.environ.get('R2_BUCKET_NAME')
        public_url_base = os.environ.get('R2_PUBLIC_URL')

        image_urls = []
        for image_info in output_data:
            filename = image_info.get("filename")
            if filename:
                image_bytes = api.get_image(filename, image_info.get("subfolder"), image_info.get("type"))

                unique_filename = f"{uuid.uuid4()}_{filename}"

                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=unique_filename,
                    Body=image_bytes,
                    ContentType='image/png'
                )

                image_url = f"{public_url_base}/{unique_filename}"
                image_urls.append(image_url)

        return {"images": image_urls}

    except Exception as e:
        import traceback
        print(f"Handler Error: {e}")
        traceback.print_exc()
        return {"error": f"Error processing request: {str(e)}"}

if __name__ == "__main__":
    print("ComfyUI Text-to-Image Worker Started")
    runpod.serverless.start({"handler": handler})
