import subprocess, sys, time, os
from playwright.sync_api import sync_playwright

app_path = os.path.abspath("app.py")
proc = subprocess.Popen([sys.executable, app_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(3)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:8050/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Inspect date picker
        date_picker = page.locator("#dates")
        print("DatePicker count:", date_picker.count())
        if date_picker.count() > 0:
            outer_color = date_picker.evaluate("el => getComputedStyle(el).color")
            outer_bg = date_picker.evaluate("el => getComputedStyle(el).backgroundColor")
            print(f"Outer datepicker - color={outer_color}, bg={outer_bg}")
            
            inner_html = date_picker.inner_html()
            print("Inner HTML:", inner_html[:2000])
            
            text = date_picker.text_content()
            print("Text content:", repr(text[:500]))
            
            # Look at child elements
            children = date_picker.locator("div, span, input")
            print("Child count:", children.count())
            for i in range(min(children.count(), 20)):
                el = children.nth(i)
                tag = el.evaluate("el => el.tagName")
                cls = el.get_attribute("class") or ""
                color = el.evaluate("el => getComputedStyle(el).color")
                bg = el.evaluate("el => getComputedStyle(el).backgroundColor")
                txt = repr(el.text_content()[:80])
                print(f"  [{i}] {tag} class={cls[:60]} color={color} bg={bg} text={txt}")

        page.screenshot(path="dates_screenshot.png", full_page=True)
        print("Screenshot saved")
        browser.close()
finally:
    proc.terminate()
    proc.wait()
