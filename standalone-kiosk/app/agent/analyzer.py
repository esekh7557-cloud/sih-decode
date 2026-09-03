import asyncio
import json
from pydantic import BaseModel
from typing import List

import os

try:
    from browser_use import Agent, Browser
    from langchain_openai import ChatOpenAI
    ChatOpenAI.provider = "openrouter"
except ImportError:
    # Will be available after pip install finishes
    pass


class FormFieldSchema(BaseModel):
    name: str
    type: str  # e.g., 'text', 'dropdown', 'file'
    required: bool
    description: str


class FormSchema(BaseModel):
    url: str
    fields: List[FormFieldSchema]
    required_documents: List[str]


async def analyze_form(url: str) -> FormSchema:
    """
    Uses a Multimodal CUA to navigate to the provided form URL,
    analyze the DOM and visual elements, and return a structured JSON schema
    of what information and documents are required to fill it.
    """
    
    # Initialize the LLM via OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY")
    model_name = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.0
    )
    
    # Define the extraction task
    task_prompt = f"""
    Navigate to the following URL: {url}
    This is an application form. Your task is NOT to fill it out.
    Your task is to analyze the form and extract its schema.
    
    Identify all the input fields, dropdowns, checkboxes, and file upload fields.
    For each field, determine its name, type, whether it is required, and a brief description.
    Also, compile a list of all required documents (e.g., 'Aadhar Card', 'Income Certificate').
    
    Return the result strictly as a JSON object that matches this structure:
    {{
        "url": "{url}",
        "fields": [
            {{"name": "Field Name", "type": "text|dropdown|file", "required": true|false, "description": "What this field asks for"}}
        ],
        "required_documents": ["Document 1", "Document 2"]
    }}
    """
    
    # Initialize the Browser and Agent
    browser = Browser()
    agent = Agent(
        task=task_prompt,
        llm=llm,
        browser=browser,
    )
    
    # Run the agent to extract the schema
    print(f"Starting form analysis for: {url}")
    result = await agent.run()
    
    await browser.close()
    
    # Extract the JSON from the final result
    # Assuming the agent returns the JSON string in its final step
    try:
        final_text = result.final_result()
        # Clean up Markdown JSON block if present
        if "```json" in final_text:
            final_text = final_text.split("```json")[1].split("```")[0].strip()
        
        schema_dict = json.loads(final_text)
        return FormSchema(**schema_dict)
    except Exception as e:
        print(f"Failed to parse agent output into JSON schema: {e}")
        print(f"Raw output: {result.final_result()}")
        return FormSchema(url=url, fields=[], required_documents=[])


if __name__ == "__main__":
    # Example usage
    sample_url = "https://example.com/sample-form" # Replace with actual form URL for testing
    schema = asyncio.run(analyze_form(sample_url))
    print(json.dumps(schema.model_dump(), indent=2))
