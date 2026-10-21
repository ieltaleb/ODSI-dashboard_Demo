import subprocess, sys, time, os
from playwright.sync_api import sync_playwright

proc = subprocess.Popen([sys.executable, 'app.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(3)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8050/', wait_until='networkidle')
    page.wait_for_timeout(3000)
    selectors = ['#dates', '#dates input', '#dates div', '.DatePickerRange', '.DateInput']
    for sel in selectors:
        els = page.locator(sel)
        print(f'Selector {sel}: count={els.count()}')
        for i in range(min(els.count(), 5)):
            el = els.nth(i)
            tag = el.evaluate('el => el.tagName')
            cls = el.get_attribute('class') or ''
            color = el.evaluate('el => getComputedStyle(el).color')
            bg = el.evaluate('el => getComputedStyle(el).backgroundColor')
            print(f'  [{i}] {tag} class={cls[:70]} color={color} bg={bg}')
    # Also dump all elements inside .controls
    controls = page.locator('.controls')
    if controls.count() > 0:
        print("\n--- All elements inside .controls ---")
        all_el = controls.locator('*')
        print('Total children:', all_el.count())
        for i in range(all_el.count()):
            el = all_el.nth(i)
            tag = el.evaluate('el => el.tagName')
            el_id = el.get_attribute('id') or ''
            cls = el.get_attribute('class') or ''
            color = el.evaluate('el => getComputedStyle(el).color')
            bg = el.evaluate('el => getComputedStyle(el).backgroundColor')
            print(f'  [{i}] {tag} id={el_id} class={cls[:60]} color={color} bg={bg}')
    browser.close()
proc.terminate()
proc.wait()
