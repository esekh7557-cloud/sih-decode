import json
import asyncio
from playwright.async_api import async_playwright

async def analyze_form(url: str):
    """
    Navigates to the given URL and analyzes the DOM to extract a form schema.
    It identifies inputs, selects, textareas, and associates them with labels.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        page = await browser.new_page()
        
        print(f"[FormAnalyzer] Navigating to {url}...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            print("[FormAnalyzer] Waiting 10 seconds so you can see the form...")
            await page.wait_for_timeout(10000)

        except Exception as e:
            print(f"[FormAnalyzer] Failed to load page: {e}")
            await browser.close()
            return {"error": str(e)}

        print("[FormAnalyzer] Taking screenshot...")
        await page.screenshot(path="form_screenshot.png")

        print("[FormAnalyzer] Extracting form elements...")
        
        # Inject JavaScript to analyze the form in the browser context
        schema = await page.evaluate('''() => {
            const results = [];
            const elements = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]), select, textarea');
            
            elements.forEach((el, index) => {
                const id = el.id || '';
                const name = el.name || '';
                const type = el.tagName.toLowerCase() === 'input' ? el.type : el.tagName.toLowerCase();
                
                // Try to find the associated label
                let label = '';
                if (id) {
                    const labelEl = document.querySelector(`label[for="${id}"]`);
                    if (labelEl) label = labelEl.innerText.trim();
                }
                
                // Fallback: look for a wrapper label
                if (!label) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) label = parentLabel.innerText.trim();
                }
                
                // Fallback: use aria-label or placeholder
                if (!label) label = el.getAttribute('aria-label') || '';
                if (!label) label = el.getAttribute('placeholder') || '';
                if (!label) label = name || id; // Last resort
                
                const fieldData = {
                    selector: id ? `#${id}` : (name ? `[name="${name}"]` : ''),
                    id: id,
                    name: name,
                    type: type,
                    label: label
                };
                
                // If it's a select dropdown, get the options
                if (type === 'select') {
                    const options = Array.from(el.options).map(opt => ({
                        value: opt.value,
                        text: opt.innerText.trim()
                    }));
                    fieldData.options = options;
                }
                
                // Only push if we have a valid selector to target it later
                if (fieldData.selector) {
                    results.push(fieldData);
                }
            });
            
            return results;
        }''')
        
        await browser.close()
        
        return {
            "url": url,
            "fields_found": len(schema),
            "schema": schema
        }

if __name__ == "__main__":
    # Test script usage
    async def main():
        url = input("Enter a URL to analyze: ")
        if url:
            result = await analyze_form(url)
            print(json.dumps(result, indent=2))
            
    asyncio.run(main())
