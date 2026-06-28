import argparse
import asyncio
import json
import os
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Playwright is not installed. Please install it first:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)

PRIVACY_APPLE_URL = "https://privacy.apple.com"
DATA_EXPORT_SELECTOR = "request-copy-button, [data-test='request-copy'], button:has-text('Request a copy'), a:has-text('Request a copy'), a:has-text('请求获取数据拷贝'), a:has-text('获取数据副本')"
SELECT_ALL_SELECTOR = "select-all-checkbox, [data-test='select-all'], input[type='checkbox'][aria-label*='Select all'], input[type='checkbox'][aria-label*='全选']"
HEALTH_CHECKBOX_SELECTOR = "[data-test='health'], input[value='HEALTH'], input[type='checkbox']"
CONTINUE_BUTTON_SELECTOR = "button:has-text('Continue'), button:has-text('继续')"
SUBMIT_BUTTON_SELECTOR = "button:has-text('Submit'), button:has-text('提交')"
DOWNLOAD_LINK_SELECTOR = "a[href*='download'], a:has-text('Download'), a:has-text('下载')"
SIGN_IN_BUTTON_SELECTOR = "button:has-text('Sign In'), button:has-text('登录')"
APPLE_ID_INPUT = "input[type='text'], input[name='accountName'], input#account_name_text_field"
PASSWORD_INPUT = "input[type='password'], input[name='password'], input#password_text_field"
CONTINUE_SIGNIN_SELECTOR = "button:has-text('Continue'), button:has-text('继续'), button[id='sign-in']"

EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apple_health_export")


async def _wait_and_click(page, selector, timeout=15000, description="element"):
    try:
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=timeout)
        await el.click()
        return True
    except PlaywrightTimeout:
        print(f"  Timeout waiting for: {description} ({selector})")
        return False
    except Exception as e:
        print(f"  Error clicking {description}: {e}")
        return False


async def _fill_input(page, selector, value, timeout=10000, description="input"):
    try:
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=timeout)
        await el.fill(value)
        return True
    except PlaywrightTimeout:
        print(f"  Timeout waiting for: {description} ({selector})")
        return False
    except Exception as e:
        print(f"  Error filling {description}: {e}")
        return False


async def _handle_apple_signin(page, apple_id, password):
    print("  Navigating to Apple sign-in...")

    await page.goto(PRIVACY_APPLE_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    sign_in_handle = await page.evaluate("""
        () => {
            const btns = document.querySelectorAll('button, a');
            for (const btn of btns) {
                const text = btn.textContent || '';
                if (text.includes('Sign In') || text.includes('登录') || text.includes('Sign in')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }
    """)

    if not sign_in_handle:
        try:
            await page.click("button:has-text('Sign In'), a:has-text('Sign In')", timeout=5000)
        except Exception:
            pass

    await page.wait_for_timeout(2000)

    print("  Entering Apple ID...")
    apple_id_filled = await _fill_input(
        page, APPLE_ID_INPUT, apple_id, description="Apple ID input"
    )
    if not apple_id_filled:
        print("  Could not find Apple ID input field. Please check the page.")
        print("  The page URL is:", page.url)
        return False

    await _wait_and_click(page, CONTINUE_SIGNIN_SELECTOR, description="Continue after Apple ID")

    await page.wait_for_timeout(2000)

    print("  Entering password...")
    pwd_filled = await _fill_input(
        page, PASSWORD_INPUT, password, description="Password input"
    )
    if not pwd_filled:
        print("  Could not find password input field.")
        return False

    await _wait_and_click(page, CONTINUE_SIGNIN_SELECTOR, description="Sign in button")

    print("  Waiting for 2FA verification...")
    print("  >>> Please check your Apple device and approve the sign-in request <<<")
    print("  >>> You have 120 seconds to complete 2FA <<<")

    try:
        await page.wait_for_url("**/account**", timeout=120000)
    except PlaywrightTimeout:
        try:
            await page.wait_for_url("**/privacy**", timeout=5000)
        except PlaywrightTimeout:
            current_url = page.url
            if "privacy.apple.com" in current_url:
                pass
            else:
                print(f"  Sign-in may have failed. Current URL: {current_url}")
                return False

    await page.wait_for_timeout(3000)
    print("  Sign-in successful!")
    return True


async def _request_data_copy(page, data_categories=None):
    print("  Looking for 'Request a copy of your data' option...")

    await page.wait_for_timeout(3000)

    request_copy_found = False
    for selector in [
        "a:has-text('Request a copy')",
        "a:has-text('请求获取数据拷贝')",
        "a:has-text('获取数据副本')",
        "button:has-text('Request a copy')",
        "[data-test='request-copy']",
    ]:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=3000):
                await el.click()
                request_copy_found = True
                print("  Clicked 'Request a copy' link")
                break
        except Exception:
            continue

    if not request_copy_found:
        request_copy_found = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a, button');
                for (const link of links) {
                    const text = (link.textContent || '').toLowerCase();
                    if (text.includes('request a copy') || text.includes('获取数据副本') || text.includes('请求获取数据拷贝')) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }
        """)

    if not request_copy_found:
        print("  Could not find 'Request a copy' option on the page.")
        print("  You may need to navigate to it manually.")
        print("  Current URL:", page.url)
        return False

    await page.wait_for_timeout(5000)

    print("  Selecting data categories...")

    select_all_clicked = False
    for selector in [
        "input[type='checkbox'][aria-label*='Select all']",
        "input[type='checkbox'][aria-label*='全选']",
        "[data-test='select-all']",
        "label:has-text('Select all') input",
        "label:has-text('全选') input",
    ]:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=3000):
                if not await el.is_checked():
                    await el.check()
                select_all_clicked = True
                print("  Selected all data categories")
                break
        except Exception:
            continue

    if not select_all_clicked:
        print("  Select All not found, trying to select Health data specifically...")
        health_selected = False
        for selector in [
            "input[type='checkbox'][value='HEALTH']",
            "label:has-text('Health') input",
            "label:has-text('健康') input",
            "[data-test='health']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    if not await el.is_checked():
                        await el.check()
                    health_selected = True
                    print("  Selected Health data category")
                    break
            except Exception:
                continue

        if not health_selected:
            print("  Could not find Health checkbox. Attempting to select all via JavaScript...")
            health_selected = await page.evaluate("""
                () => {
                    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
                    let found = false;
                    for (const cb of checkboxes) {
                        const label = (cb.closest('label') || cb.parentElement || {}).textContent || '';
                        if (label.toLowerCase().includes('health') || label.includes('健康') || cb.value === 'HEALTH') {
                            if (!cb.checked) cb.click();
                            found = true;
                        }
                    }
                    if (!found) {
                        for (const cb of checkboxes) {
                            if (!cb.checked) cb.click();
                        }
                        found = true;
                    }
                    return found;
                }
            """)

    await page.wait_for_timeout(2000)

    print("  Clicking Continue...")
    continue_clicked = False
    for selector in [
        "button:has-text('Continue')",
        "button:has-text('继续')",
        "[data-test='continue']",
    ]:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=3000):
                await el.click()
                continue_clicked = True
                break
        except Exception:
            continue

    if not continue_clicked:
        print("  Could not find Continue button.")
        return False

    await page.wait_for_timeout(3000)

    print("  Clicking Submit...")
    submit_clicked = False
    for selector in [
        "button:has-text('Submit')",
        "button:has-text('提交')",
        "[data-test='submit']",
    ]:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=3000):
                await el.click()
                submit_clicked = True
                break
        except Exception:
            continue

    if not submit_clicked:
        print("  Could not find Submit button.")
        return False

    await page.wait_for_timeout(3000)
    print("  Data copy request submitted successfully!")
    print("  Apple will prepare your data. This typically takes 1-7 days.")
    print("  You will receive an email notification when it's ready to download.")
    return True


async def _download_available_data(page, download_dir):
    print("  Checking for available downloads...")

    await page.goto(PRIVACY_APPLE_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(5000)

    download_links = await page.evaluate("""
        () => {
            const links = document.querySelectorAll('a');
            const result = [];
            for (const link of links) {
                const text = (link.textContent || '').toLowerCase();
                if (text.includes('download') || text.includes('下载')) {
                    result.push({
                        text: link.textContent.trim(),
                        href: link.href
                    });
                }
            }
            return result;
        }
    """)

    if not download_links:
        print("  No available downloads found at this time.")
        print("  Your data may still be being prepared by Apple.")
        return []

    downloaded = []
    for link_info in download_links:
        print(f"  Found download: {link_info['text']}")

    async with page.expect_download(timeout=300000) as download_info:
        for link_info in download_links:
            try:
                await page.click(f"a[href='{link_info['href']}']", timeout=10000)
                download = await download_info.value
                save_path = os.path.join(download_dir, download.suggested_filename)
                await download.save_as(save_path)
                downloaded.append(save_path)
                print(f"  Downloaded: {save_path}")
                break
            except Exception as e:
                print(f"  Download failed: {e}")
                continue

    return downloaded


async def _run_interactive_mode(page):
    print("\n  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  Interactive Mode - Browser is open for manual control  ║")
    print("  ╠══════════════════════════════════════════════════════════╣")
    print("  ║  The browser is paused. You can:                        ║")
    print("  ║  1. Complete sign-in manually if 2FA is needed          ║")
    print("  ║  2. Navigate to 'Request a copy of your data'          ║")
    print("  ║  3. Select Health data and submit the request           ║")
    print("  ║  4. Download any available data archives                ║")
    print("  ║                                                         ║")
    print("  ║  When finished, press Enter in this terminal to close   ║")
    print("  ╚══════════════════════════════════════════════════════════╝\n")

    await asyncio.get_event_loop().run_in_executor(None, input, "  Press Enter when you're done with the browser...")

    current_url = page.url
    print(f"\n  Final URL: {current_url}")


async def run_export(apple_id=None, password=None, headless=False, download_only=False, interactive=True, download_dir=None):
    if download_dir is None:
        download_dir = EXPORT_DIR

    os.makedirs(download_dir, exist_ok=True)

    print("\n  ══════════════════════════════════════════════════════")
    print("  Apple Health Data Web Export (privacy.apple.com)")
    print("  ══════════════════════════════════════════════════════\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True,
        )

        page = await context.new_page()

        try:
            if download_only:
                print("  Mode: Download only (checking for available data)")
                if apple_id and password:
                    signed_in = await _handle_apple_signin(page, apple_id, password)
                    if not signed_in and not interactive:
                        print("  Sign-in failed and interactive mode is disabled.")
                        return
                downloaded = await _download_available_data(page, download_dir)
                if downloaded:
                    print(f"\n  Downloaded {len(downloaded)} file(s) to: {download_dir}")
                    for f in downloaded:
                        print(f"    - {f}")
            elif apple_id and password:
                print("  Mode: Automated sign-in + data request")
                print(f"  Apple ID: {apple_id[:3]}***{apple_id[-3:] if len(apple_id) > 6 else '***'}")

                signed_in = await _handle_apple_signin(page, apple_id, password)
                if not signed_in:
                    if interactive:
                        print("  Automated sign-in failed. Switching to interactive mode...")
                        await _run_interactive_mode(page)
                    else:
                        print("  Sign-in failed. Use --interactive to complete manually.")
                    return

                await _request_data_copy(page)

                downloaded = await _download_available_data(page, download_dir)
                if downloaded:
                    print(f"\n  Downloaded {len(downloaded)} file(s) to: {download_dir}")

                if interactive:
                    await _run_interactive_mode(page)
            else:
                print("  Mode: Interactive (no credentials provided)")
                print("  Opening browser to privacy.apple.com...")
                print("  Please sign in and request your data copy manually.\n")

                await page.goto(PRIVACY_APPLE_URL, wait_until="domcontentloaded", timeout=30000)

                await _run_interactive_mode(page)

        except Exception as e:
            print(f"\n  Error: {e}")
            if interactive:
                print("  Switching to interactive mode so you can continue manually...")
                await _run_interactive_mode(page)
        finally:
            await browser.close()

    print("\n  ══════════════════════════════════════════════════════")
    print("  Session complete")
    print("  ══════════════════════════════════════════════════════")
    print(f"\n  Download directory: {download_dir}")
    print("\n  Next steps:")
    print("  1. If you submitted a data request, wait for Apple's email (1-7 days)")
    print("  2. When the data is ready, re-run this script with --download-only")
    print("  3. Then sync to running_page with:")
    print(f"     python run_page/apple_health_sync.py {download_dir}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Export Apple Health data from privacy.apple.com using browser automation"
    )
    parser.add_argument(
        "--apple-id",
        default=os.environ.get("APPLE_ID", ""),
        help="Your Apple ID email address (or set APPLE_ID env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("APPLE_PASSWORD", ""),
        help="Your Apple ID password (or set APPLE_PASSWORD env var)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only check for and download available data (don't submit new request)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive mode (exit on errors instead of pausing)",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help=f"Directory to save downloaded files (default: {EXPORT_DIR})",
    )

    args = parser.parse_args()

    apple_id = args.apple_id
    password = args.password

    asyncio.run(
        run_export(
            apple_id=apple_id if apple_id else None,
            password=password if password else None,
            headless=args.headless,
            download_only=args.download_only,
            interactive=not args.non_interactive,
            download_dir=args.download_dir,
        )
    )


if __name__ == "__main__":
    main()
