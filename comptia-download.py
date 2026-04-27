#!/usr/bin/env python3
"""
comptia-download.py — Download CompTIA CertMaster course modules as PDFs (+ videos).

Usage:
    python comptia-download.py <course_url> -u EMAIL [-p PASSWORD] [-o DIR]

Requires:
    pip install playwright yt-dlp
    playwright install chromium

Notes:
    - Defaults to showing the browser window so you can handle SSO/2FA manually.
    - Use --headless for unattended runs after confirming login works.
    - Only use this for content you have legitimately purchased/licensed.
"""

import argparse
import asyncio
import getpass
import re
import subprocess
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
except ImportError:
    sys.exit("Missing dependency: pip install playwright && playwright install chromium")

# Matches "1.0 Title", "1.2.3 Some Topic", "2.0", etc.
SECTION_RE = re.compile(r'^(\d+(?:\.\d+)*)[.\s]+(.+)')

# Delay between page loads (seconds) — be polite to the server
DEFAULT_DELAY = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize(name: str) -> str:
    """Strip characters that are unsafe in file/directory names."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', name)
    return name.strip().rstrip('.')


def depth_from_number(num: str) -> int:
    """'1.2.3' → 3"""
    return len(num.split('.'))


def build_breadcrumbs(items: list[dict]) -> list[list[str]]:
    """
    Given a flat list of {number, label} dicts (in outline order),
    build the ancestor path for each item.

    E.g., "1.1.1 Topic" → ["1.0 Chapter", "1.1 Section", "1.1.1 Topic"]
    """
    label_by_prefix: dict[str, str] = {it["number"]: it["label"] for it in items}

    breadcrumbs = []
    for item in items:
        parts = item["number"].split(".")
        crumb = []
        for i in range(1, len(parts) + 1):
            prefix = ".".join(parts[:i])
            if prefix in label_by_prefix:
                crumb.append(label_by_prefix[prefix])
            else:
                # Try "N.0" for top-level chapters listed as "1.0 Title"
                zero = f"{parts[0]}.0" if i == 1 else None
                if zero and zero in label_by_prefix:
                    crumb.append(label_by_prefix[zero])
                else:
                    crumb.append(f"{prefix} ?")
        breadcrumbs.append(crumb)

    return breadcrumbs


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def do_login(page: Page, email: str, password: str) -> None:
    print("Logging in…")
    await page.wait_for_load_state("networkidle")

    for sel in [
        'input[type="email"]', 'input[name="email"]', '#email',
        '#username', 'input[placeholder*="mail" i]', 'input[name="user"]',
    ]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.fill(email)
            break

    for sel in ['input[type="password"]', '#password', 'input[name="password"]']:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.fill(password)
            break

    for sel in [
        'button[type="submit"]', 'input[type="submit"]',
        'button:text-is("Sign in")', 'button:text-is("Log in")',
        'button:text-is("Login")', 'button:text-is("Continue")',
        'button:has-text("Sign")', 'button:has-text("Log")',
    ]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click()
            break

    await page.wait_for_load_state("networkidle")
    print(f"  → {page.url}")


# ---------------------------------------------------------------------------
# Outline discovery
# ---------------------------------------------------------------------------

async def click_outline_tab(page: Page) -> bool:
    """Find and click the 'Outline' link/tab. Returns True if found."""
    for sel in [
        'a:text-is("Outline")', 'button:text-is("Outline")',
        'a:text("Outline")',    'button:text("Outline")',
        '[aria-label="Outline"]', '[data-tab="outline"]',
        'a[href*="outline"]',
    ]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click()
            await page.wait_for_load_state("networkidle")
            return True
    return False


async def collect_outline_items(page: Page) -> list[dict]:
    """
    Scan the page for elements whose visible text starts with a section number
    (e.g. "1.0 Chapter", "1.1.2 Topic"). Returns them in DOM order.
    """
    # Try to narrow the search to an outline/sidebar container first
    container = None
    for sel in [
        ".course-outline", ".lesson-outline", "#outline",
        "[class*='outline' i]", "[class*='sidebar' i]", "[class*='toc' i]",
        "aside", ".course-nav", ".course-sidebar", "nav",
    ]:
        el = await page.query_selector(sel)
        if el:
            text = await el.inner_text()
            if SECTION_RE.search(text):
                container = el
                break

    scope = container if container else page

    candidates = await scope.query_selector_all(
        "a, button, [role='treeitem'], [role='option'], [role='menuitem'], "
        "[role='link'], li, span[tabindex], div[tabindex], div[class*='item' i], "
        "div[class*='lesson' i], div[class*='module' i], div[class*='topic' i]"
    )

    items = []
    seen: set[str] = set()
    for el in candidates:
        try:
            raw = (await el.inner_text()).strip()
        except Exception:
            continue
        first_line = raw.split("\n")[0].strip()
        m = SECTION_RE.match(first_line)
        if not m:
            continue
        number = m.group(1)
        title = m.group(2).strip()
        label = f"{number} {title}"
        if label in seen:
            continue
        seen.add(label)
        items.append({
            "number": number,
            "title": title,
            "label": label,
            "depth": depth_from_number(number),
        })

    return items


# ---------------------------------------------------------------------------
# Video detection & download
# ---------------------------------------------------------------------------

async def detect_video_urls(page: Page) -> list[str]:
    urls = []

    # HTML5 <video>
    for sel in ["video[src]", "video source[src]"]:
        for el in await page.query_selector_all(sel):
            src = await el.get_attribute("src")
            if src:
                urls.append(src)

    # Iframes (YouTube, Vimeo, Kaltura, Brightcove, etc.)
    for el in await page.query_selector_all("iframe[src]"):
        src = (await el.get_attribute("src")) or ""
        if any(k in src for k in ("youtube", "vimeo", "kaltura", "brightcove", "player", "video")):
            urls.append(src)

    return urls


def try_yt_dlp(video_url: str, output_base: Path) -> bool:
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-playlist", "-o", str(output_base) + ".%(ext)s", video_url],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return True
        print(f"      yt-dlp error: {result.stderr.strip()[:200]}")
    except FileNotFoundError:
        print("      yt-dlp not found — pip install yt-dlp")
    except subprocess.TimeoutExpired:
        print("      yt-dlp timed out")
    return False


# ---------------------------------------------------------------------------
# PDF saving
# ---------------------------------------------------------------------------

async def save_pdf(page: Page, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    await page.pdf(
        path=str(pdf_path),
        format="A4",
        print_background=True,
        margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"},
    )


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

async def find_and_click(page: Page, label: str) -> bool:
    """Re-find an outline item by its label text and click it. Returns True on success."""
    candidates = await page.query_selector_all(
        "a, button, [role='treeitem'], [role='option'], [role='menuitem'], "
        "[role='link'], li, span[tabindex], div[tabindex], div[class*='item' i], "
        "div[class*='lesson' i], div[class*='module' i], div[class*='topic' i]"
    )
    for el in candidates:
        try:
            raw = (await el.inner_text()).strip().split("\n")[0].strip()
            m = SECTION_RE.match(raw)
            if m and f"{m.group(1)} {m.group(2).strip()}" == label:
                await el.scroll_into_view_if_needed()
                await el.click()
                await page.wait_for_load_state("networkidle")
                return True
        except Exception:
            continue
    return False


async def process_all(
    page: Page,
    items: list[dict],
    breadcrumbs: list[list[str]],
    outline_url: str,
    output_dir: Path,
    delay: float,
) -> None:
    total = len(items)
    for idx, (item, crumb) in enumerate(zip(items, breadcrumbs), 1):
        label = item["label"]
        print(f"\n[{idx}/{total}] {label}")

        # Build output paths
        parts = [sanitize(p) for p in crumb]
        rel = Path(*parts)
        pdf_path = output_dir / rel.with_suffix(".pdf")
        base_path = output_dir / rel  # used for video filename (no extension)

        if pdf_path.exists():
            print("  already saved — skipping")
            continue

        # Make sure the outline is still visible; if not, reload it
        outline_items_present = await page.query_selector(
            f"*:text-is('{label[:40]}')"
        ) if label else None
        if not outline_items_present:
            print("  reloading outline…")
            await page.goto(outline_url, wait_until="networkidle")
            await asyncio.sleep(delay)

        # Find and click the item
        ok = await find_and_click(page, label)
        if not ok:
            print(f"  [warn] element not found — skipping")
            await page.goto(outline_url, wait_until="networkidle")
            await asyncio.sleep(delay)
            continue

        await asyncio.sleep(delay)

        # Download videos
        video_urls = await detect_video_urls(page)
        for v_idx, v_url in enumerate(video_urls):
            suffix = f"_{v_idx + 1}" if len(video_urls) > 1 else ""
            vpath = base_path.parent / (base_path.name + suffix)
            print(f"  downloading video from {v_url[:80]}…")
            ok_v = try_yt_dlp(v_url, vpath)
            if ok_v:
                print("  [video] saved")
            else:
                print("  [video] download failed — skipping")

        # Save PDF
        print("  saving PDF…")
        try:
            await save_pdf(page, pdf_path)
            print(f"  [pdf] {pdf_path}")
        except Exception as exc:
            print(f"  [pdf error] {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Download CompTIA CertMaster course modules as PDFs (+ videos).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python comptia-download.py https://certmaster.comptia.org/courses/123 -u me@email.com
  python comptia-download.py <url> -u me@email.com -p secret -o ~/Downloads/sec-plus
  python comptia-download.py <url> -u me@email.com --headless
        """,
    )
    parser.add_argument("course_url", help="Course page URL on comptia.org / certmaster.comptia.org")
    parser.add_argument("-u", "--user", required=True, help="Login email/username")
    parser.add_argument("-p", "--password", help="Login password (prompted if omitted)")
    parser.add_argument("-o", "--output", default="comptia-course", help="Output directory (default: comptia-course)")
    parser.add_argument("--headless", action="store_true", help="Run browser headlessly (no window)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Seconds between page loads (default: {DEFAULT_DELAY})")
    parser.add_argument("--skip-confirm", action="store_true", help="Skip the outline preview confirmation")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # Navigate to course — may redirect to login
        print(f"Opening: {args.course_url}")
        await page.goto(args.course_url, wait_until="networkidle")

        if any(k in page.url for k in ("login", "signin", "auth", "sso")):
            await do_login(page, args.user, password)
            await page.goto(args.course_url, wait_until="networkidle")

        # Find the Outline tab
        print("Looking for Outline tab…")
        found = await click_outline_tab(page)
        if not found:
            print("[warn] Outline tab not found — using current page as-is")

        outline_url = page.url
        print(f"Outline URL: {outline_url}")

        # Collect outline items
        print("Collecting outline items…")
        items = await collect_outline_items(page)

        if not items:
            print(
                "\n[error] No numbered items found in the outline.\n"
                "Tips:\n"
                "  • Run without --headless so you can see the page.\n"
                "  • Make sure you are logged in and on the correct course page.\n"
                "  • The outline may load lazily — try scrolling/expanding it first."
            )
            await browser.close()
            sys.exit(1)

        breadcrumbs = build_breadcrumbs(items)

        # Preview
        print(f"\nFound {len(items)} items:")
        for it, crumb in zip(items, breadcrumbs):
            indent = "  " * (it["depth"] - 1)
            print(f"  {indent}{it['label']}")

        if not args.skip_confirm:
            ans = input("\nProceed with download? [Y/n]: ").strip().lower()
            if ans == "n":
                print("Aborted.")
                await browser.close()
                sys.exit(0)

        # Run
        await process_all(page, items, breadcrumbs, outline_url, output_dir, args.delay)

        await browser.close()
        print(f"\nDone. Files saved to: {output_dir.resolve()}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
