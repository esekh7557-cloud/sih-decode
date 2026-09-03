import asyncio
import os
from typing import Dict, Any

try:
    from browser_use import Agent, Browser
    from langchain_openai import ChatOpenAI
    ChatOpenAI.provider = "openrouter"
except ImportError:
    pass

async def execute_form_fill(url: str, data: Dict[str, Any]) -> str:
    """
    Uses a Computer-Use Agent to navigate to the URL and fill out the form
    using the provided structured data.
    
    Args:
        url (str): The target form URL.
        data (Dict[str, Any]): A dictionary of field names and their values to fill.
                               Includes paths to files for upload fields.
                               
    Returns:
        str: Result of the execution or confirmation message.
    """
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    model_name = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.0
    )
    
    # We construct a detailed prompt instructing the agent on exactly what to fill
    data_str = "\n".join([f"- {k}: {v}" for k, v in data.items()])
    
    task_prompt = f"""
    Navigate to the following URL: {url}
    Your task is to fill out the form on this page using the provided data.
    
    Data to use:
    {data_str}
    
    Instructions:
    1. Look for the corresponding input fields, dropdowns, and file upload buttons for each data item.
    2. Type the text for text fields.
    3. Select the correct option for dropdowns.
    4. For any file uploads, provide the absolute path given in the data.
    5. Once all fields are filled, click the 'Submit' or 'Save' button.
    6. Return a summary of what was filled and if the submission was successful.
    """
    
    # Launch browser in non-headless mode if you want to watch it, or headless=True for production
    # Browser-use defaults to non-headless usually, which is good for debugging CUA
    browser = Browser()
    
    agent = Agent(
        task=task_prompt,
        llm=llm,
        browser=browser,
    )
    
    print(f"Starting execution for: {url}")
    result = await agent.run()
    
    await browser.close()
    
    return result.final_result()

if __name__ == "__main__":
    # Example usage
    sample_url = "https://example.com/sample-form"
    sample_data = {
        "First Name": "John",
        "Last Name": "Doe",
        "Aadhar Card": os.path.abspath("scans/sample_session/aadhar.png") # Example path
    }
    # result = asyncio.run(execute_form_fill(sample_url, sample_data))
    # print(result)
