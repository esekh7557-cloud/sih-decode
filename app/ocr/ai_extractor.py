"""AI-Powered Document Data Extractor.

Extracts structured data from uploaded document images (Aadhaar, PAN, Ration Card,
Income Certificate, etc.) using OpenRouter Vision LLMs. Returns ONLY the factual
information extracted by the AI with no hallucinated or assumed values.
"""
from __future__ import annotations

import os
import json
import base64
import io
from pathlib import Path
from typing import Any, Dict, List, Union
import re
import httpx
from PIL import Image

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a precision OCR and document information extraction AI for the JanSeva portal.
Analyze the provided document image(s) and any conversation history. Your goal is to extract factual information and fill the following required schema:

{
  "applying_for": Self,
  "purpose": null,
  "residence_period": null,
  "title": null,
  "name": null,
  "place_of_birth": null,
  "dob": null,
  "gender": null,
  "marital_status": null,
  "guardian_relation": null,
  "father_name": null,  
  "mobile": null,
  "email": null,
  "occupation": null, 
  "caste_category": null,
  "address": null,
  "locality": null,
  "district": null,
  "taluka": null,
  "village": null,
  "pincode": null,
  "family_size": null,
  "earning_members": null,
  "children_count": null,
  "previous_certificate": No,
  "immovable_property": No, 
  "property_value": 0,
  "other_income": 0,
  "part_no": null,
  "serial_no": null,
  "electoral_year": null,
  "constituency": null,
  "ration_card": null,
  "property_details": null,
  "id_proof_type": null, 
  "id_proof_no": null,   
  "certify": "yes"
}

Extraction Guidelines:
1. Extract ONLY information that is explicitly readable in the image or provided by the user in the conversation history.
2. DO NOT invent, guess, or provide placeholder values.
3. If ANY fields are missing and cannot be extracted from the images or conversation history, you MUST ask the user for them.
   Return a JSON object like this: {"action": "ask", "questions": ["Question 1", "Question 2", ...]}
   You MUST include a separate question in the array for EVERY single field that is still missing. Do not limit the number of questions.
4. If ALL fields are found and nothing is missing, return a JSON object with just the extracted key-value pairs. 
5. Do NOT include markdown fences, explanations, or any placeholder keys.
"""


def _prepare_image_url(image_input: Union[str, bytes, Path, Image.Image], max_dimension: int = 1200) -> str:
    """Ensure image is properly compressed and formatted as a Data URI."""
    if isinstance(image_input, Image.Image):
        img = image_input.copy()
    elif isinstance(image_input, (str, Path)) and os.path.isfile(str(image_input)):
        img = Image.open(str(image_input))
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, str):
        if image_input.startswith("data:image/"):
            # Already a Data URI, return as-is
            return image_input
        elif image_input.startswith("http://") or image_input.startswith("https://"):
            return image_input
        else:
            # Raw base64 string
            raw_bytes = base64.b64decode(image_input.split(",")[-1])
            img = Image.open(io.BytesIO(raw_bytes))
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    # Downscale if image is too large
    if max(img.size) > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # Convert to RGB if in RGBA or other modes
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"


async def extract_data_from_images(
    images: List[Union[str, bytes, Path, Image.Image]],
    model: str | None = None,
    api_key: str | None = None,
    chat_history: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Extracts factual information from one or more document images using Vision AI.
    
    Returns a dictionary containing:
      - "success": bool
      - "extracted_fields": dict of keys and values detected by AI
      - "model_used": model ID that produced the result
      - "raw_output": raw text returned by the model
    """
    if not images and not chat_history:
        return {
            "success": False,
            "error": "No images or chat history provided",
            "extracted_fields": {},
            "model_used": None
        }

    key = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return {
            "success": False,
            "error": "Missing OPENROUTER_API_KEY in environment or arguments",
            "extracted_fields": {},
            "model_used": None
        }

    # Format messages
    messages: List[Dict[str, Any]] = []
    
    # First message: System prompt + Images
    first_content: List[Dict[str, Any]] = [{"type": "text", "text": SYSTEM_PROMPT}]
    for img in images:
        try:
            img_url = _prepare_image_url(img)
            first_content.append({"type": "image_url", "image_url": {"url": img_url}})
        except Exception as e:
            print(f"[AIExtractor] Error preparing image: {e}")
            
    messages.append({"role": "user", "content": first_content})
    
    # Append chat history
    if chat_history:
        for msg in chat_history:
            messages.append(msg)

    preferred_model = model or os.getenv("OPENROUTER_MODEL", "dots-studio/dots-3-note-preview:free").strip()
    candidate_models = [
        preferred_model,
        "dots-studio/dots-3-note-preview:free",
        "minimax/minimax-m3:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "google/gemma-4-26b-a4b-it:free"
    ]
    # Remove duplicates preserving order
    seen = set()
    models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    last_error = None
    for target_model in models:
        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.0
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    OPENROUTER_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "HTTP-Referer": "https://janseva.ai",
                        "X-Title": "JanSeva Document Extractor"
                    },
                    json=payload
                )

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    continue

                resp_data = resp.json()
                raw_text = resp_data["choices"][0]["message"]["content"].strip()

                # Clean markdown blocks if present
                clean_text = raw_text
                if clean_text.startswith("```"):
                    lines = clean_text.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_text = "\n".join(lines).strip()

                start = clean_text.find("{")
                end = clean_text.rfind("}")
                if start != -1 and end != -1 and start < end:
                    parsed_json = json.loads(clean_text[start : end + 1])
                else:
                    parsed_json = json.loads(clean_text)

                # Filter out null, empty or placeholder values
                filtered_fields = {
                    k: v for k, v in parsed_json.items()
                    if v is not None and str(v).strip() != "" and str(v).lower() not in ("null", "none", "n/a", "unknown")
                }

                # Auto-normalize Aadhaar and ID Proof fields
                # Check if a 12-digit number is mistakenly mapped to mobile
                if "mobile" in filtered_fields:
                    digits = re.sub(r"\D", "", str(filtered_fields["mobile"]))
                    if len(digits) == 12 and "aadhaar_number" not in filtered_fields:
                        filtered_fields["aadhaar_number"] = str(filtered_fields.pop("mobile"))

                if "aadhaar_number" in filtered_fields:
                    digits = re.sub(r"\D", "", str(filtered_fields["aadhaar_number"]))
                    if "id_proof_no" not in filtered_fields:
                        filtered_fields["id_proof_no"] = digits
                    if "id_proof_type" not in filtered_fields:
                        filtered_fields["id_proof_type"] = "Aadhaar Card"

                return {
                    "success": True,
                    "extracted_fields": filtered_fields,
                    "fields_count": len(filtered_fields),
                    "model_used": target_model,
                    "raw_output": raw_text
                }

        except Exception as e:
            last_error = str(e)
            continue

    return {
        "success": False,
        "error": f"Extraction failed on all models. Last error: {last_error}",
        "extracted_fields": {},
        "model_used": None
    }


def extract_sync(
    images: List[Union[str, bytes, Path, Image.Image]],
    model: str | None = None,
    api_key: str | None = None
) -> Dict[str, Any]:
    """Synchronous wrapper for extract_data_from_images."""
    import asyncio
    return asyncio.run(extract_data_from_images(images, model=model, api_key=api_key))
