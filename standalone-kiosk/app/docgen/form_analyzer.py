import sys
import argparse
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

def analyze_form(port: int = 9222):
    print("=" * 60)
    print("  JanSeva AI -- Form Analyzer")
    print("=" * 60)
    print(f"\n[CONNECT] Connecting to Edge on port {port}...")
    
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    
    try:
        driver = webdriver.Edge(options=edge_options)
        
        # Make sure we are on the correct tab
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if "goaonline" in driver.current_url.lower() or "goa" in driver.title.lower():
                break
                
        print(f"   [OK] Connected! Current page: {driver.title}")
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Edge!")
        print(f"   Make sure you started Edge with:")
        print(f"   msedge.exe --remote-debugging-port={port} --user-data-dir=\"C:\\Users\\Vedant\\Desktop\\edge-debug-profile\"")
        sys.exit(1)

    print("\n[ANALYZE] Extracting form labels and inputs...\n")
    
    result = driver.execute_script("""
        const fields = [];
        const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea');
        
        for (const input of inputs) {
            // Skip hidden elements
            if (input.getBoundingClientRect().width === 0) continue;
            
            let labelText = '';
            
            // Strategy 1: Explicit 'for' attribute
            if (input.id) {
                const explicit = document.querySelector(`label[for="${input.id}"]`);
                if (explicit) labelText = explicit.innerText.trim();
            }
            
            // Strategy 2: Closest wrapping label
            if (!labelText) {
                const wrap = input.closest('label');
                if (wrap) {
                    // Remove the text of the input itself if any
                    let clone = wrap.cloneNode(true);
                    const innerInput = clone.querySelector('input, select, textarea');
                    if (innerInput) innerInput.remove();
                    labelText = clone.innerText.trim();
                }
            }
            
            // Strategy 3: Look at parent layout container
            if (!labelText) {
                let p = input.parentElement;
                // Stop traversing up if we hit a column, row, form-group, table cell, or the body
                while (p && p.tagName !== 'TD' && p.tagName !== 'TR' && p.tagName !== 'BODY' && p.tagName !== 'FORM' 
                       && !p.classList.contains('form-group') && !p.className.includes('col-')) {
                    p = p.parentElement;
                }
                
                if (p && p.tagName !== 'BODY' && p.tagName !== 'FORM') {
                    // Find the label inside this specific container
                    const labelEl = p.querySelector('label');
                    if (labelEl) {
                        labelText = labelEl.innerText.trim();
                    } else if (p.tagName === 'TR') {
                        // Fallback for tables without <label> tags
                        const firstTd = p.querySelector('td');
                        if (firstTd && firstTd !== input.closest('td')) {
                            labelText = firstTd.innerText.trim();
                        }
                    } else {
                        // Fallback: Just grab any bold text or span that acts as a label
                        const siblingLabel = p.querySelector('strong, span, h5, h6');
                        if (siblingLabel && siblingLabel.innerText.length > 2) {
                            labelText = siblingLabel.innerText.trim();
                        }
                    }
                }
            }
            
            // Strategy 4: Fallbacks
            if (!labelText) {
                labelText = input.placeholder || input.name || input.id || 'UNKNOWN_LABEL';
            }
            
            // Clean up label text
            labelText = labelText.replace(/\\*/g, '').replace(/:/g, '').trim();
            if (!labelText || labelText === 'UNKNOWN_LABEL') continue;

            const type = input.tagName.toLowerCase() === 'select' ? 'dropdown' : (input.type || 'text');
            const id = input.id || '';
            const name = input.name || '';
            
            let options = [];
            if (type === 'dropdown') {
                for (const opt of input.querySelectorAll('option')) {
                    if (opt.value && opt.value.trim() !== '') {
                        options.push(opt.innerText.trim() + " (" + opt.value + ")");
                    }
                }
            }
            
            fields.push({
                label: labelText,
                type: type,
                id: id,
                name: name,
                options: options
            });
        }
        return fields;
    """)

    if not result:
        print("No form fields found on the page!")
        return

    mapping_dict = "MAPPING = {\n"
    for f in result:
        dict_key = f['label'].lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '').replace('*', '').strip()
        while '__' in dict_key: dict_key = dict_key.replace('__', '_')
        if dict_key.endswith('_'): dict_key = dict_key[:-1]
        
        mapping_dict += f"    '{dict_key}': ['{f['label']}', 'Another variation'],  # Type: {f['type']}\n"
        if f['options']:
            mapping_dict += f"        # Dropdown Options: {', '.join(f['options'][:4])}"
            if len(f['options']) > 4: mapping_dict += " ..."
            mapping_dict += "\n"
    mapping_dict += "}\n"
    
    import os
    output_path = os.path.join(os.path.dirname(__file__), 'mappings', 'scraped_form.py')
    with open(output_path, 'w', encoding='utf-8') as f_out:
        f_out.write(mapping_dict)
    
    print("\n" + "=" * 60)
    print(f"SUCCESS! Found {len(result)} input fields.")
    print(f"The mapping has been automatically saved to:\n{output_path}")
    print("=" * 60)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    args = parser.parse_args()
    analyze_form(args.port)
