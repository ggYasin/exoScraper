
import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Capture logs
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"JS ERROR: {exc}"))

        page.goto("http://localhost:8000/index.html")
        page.evaluate("localStorage.clear()")
        page.reload()

        # Wait for table to load
        try:
            page.wait_for_selector("table.data-table tbody tr[data-idx]", timeout=5000)
        except Exception as e:
            print(f"Timeout waiting for table: {e}")
            page.screenshot(path="verification/error_state.png")
            return

        # Debug state
        state_debug = page.evaluate("JSON.stringify(state.tiers)")
        print(f"State tiers: {state_debug}")

        # 1. Verify Config Modal
        print("Opening Config Modal...")
        try:
            page.click("#btn-config-tiers", timeout=2000)
            time.sleep(1.0) # Animation
            page.screenshot(path="verification/config_modal.png")
            print("Captured config_modal.png")

            # Check if modal is visible
            if not page.is_visible("#config-modal"):
                print("ERROR: Config modal not visible after click")
            else:
                # Close modal
                page.click("#config-close")
                time.sleep(0.5)
        except Exception as e:
            print(f"Error interacting with config modal: {e}")

        # 2. Verify Comparison Feature
        print("Selecting laptops...")
        try:
            # Select first two rows
            rows = page.query_selector_all("tr[data-idx]")
            if len(rows) >= 2:
                # Checkbox selection
                page.evaluate("el => el.click()", rows[0].query_selector(".row-checkbox"))
                page.evaluate("el => el.click()", rows[1].query_selector(".row-checkbox"))

            time.sleep(0.5) # Bar slide up
            page.screenshot(path="verification/compare_bar.png")
            print("Captured compare_bar.png")

            # Open comparison
            print("Opening Comparison Modal...")
            page.click("#compare-view")
            time.sleep(1.0)
            page.screenshot(path="verification/comparison_view.png")
            print("Captured comparison_view.png")
        except Exception as e:
            print(f"Error interacting with comparison: {e}")

        browser.close()

if __name__ == "__main__":
    run()
