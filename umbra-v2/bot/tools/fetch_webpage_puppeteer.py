"""
Webpage fetching tool using Puppeteer (via Node.js subprocess).

Replaces Letta's built-in fetch_webpage (which uses Exa/trafilatura) for
self-hosted deployments. Uses Puppeteer for JavaScript-rendered pages.

Requires: Node.js and puppeteer installed globally or in the tool's environment.
    npm install -g puppeteer
"""

import os
import json
import subprocess
import tempfile
from typing import Optional
from pydantic import BaseModel, Field


class FetchWebpagePuppeteerArgs(BaseModel):
    url: str = Field(description="The URL to fetch")
    max_length: int = Field(
        default=10000,
        ge=100,
        le=50000,
        description="Maximum characters of content to return",
    )


# Node.js script for Puppeteer-based page fetching
_PUPPETEER_SCRIPT = r"""
const puppeteer = require('puppeteer');

(async () => {
    const url = process.argv[2];
    const maxLen = parseInt(process.argv[3] || '10000');

    let browser;
    try {
        browser = await puppeteer.launch({
            headless: 'new',
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
        });
        const page = await browser.newPage();
        await page.setUserAgent('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36');

        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });

        // Extract page content
        const result = await page.evaluate(() => {
            // Remove scripts, styles, nav, footer, etc.
            const remove = document.querySelectorAll(
                'script, style, nav, footer, header, iframe, noscript, .cookie-banner, .ad, [role="banner"], [role="navigation"]'
            );
            remove.forEach(el => el.remove());

            const title = document.title || '';
            const body = document.body;
            if (!body) return JSON.stringify({ title, content: '' });

            // Get text content, preserving structure
            function getText(node, depth = 0) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.trim();
                    return text ? text + ' ' : '';
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return '';

                const tag = node.tagName.toLowerCase();
                const block = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                               'li', 'tr', 'blockquote', 'pre', 'article', 'section'].includes(tag);

                let prefix = '';
                if (['h1','h2','h3','h4','h5','h6'].includes(tag)) {
                    prefix = '#'.repeat(parseInt(tag[1])) + ' ';
                } else if (tag === 'li') {
                    prefix = '- ';
                }

                let text = '';
                for (const child of node.childNodes) {
                    text += getText(child, depth + 1);
                }

                if (block && text.trim()) {
                    return '\n' + prefix + text.trim() + '\n';
                }
                return text;
            }

            const content = getText(body)
                .replace(/\n{3,}/g, '\n\n')
                .trim();

            return JSON.stringify({ title, content });
        });

        const parsed = JSON.parse(result);
        if (parsed.content.length > maxLen) {
            parsed.content = parsed.content.substring(0, maxLen) + '\n\n[Content truncated]';
        }
        console.log(JSON.stringify(parsed));
    } catch (err) {
        console.log(JSON.stringify({ error: err.message }));
    } finally {
        if (browser) await browser.close();
    }
})();
"""


def fetch_webpage_puppeteer(
    url: str,
    max_length: int = 10000,
) -> str:
    """
    Fetch a webpage and convert it to readable text using Puppeteer.

    Renders JavaScript-heavy pages and extracts clean text content.
    Useful for fetching modern web pages that require JS rendering.

    Args:
        url: The URL of the webpage to fetch.
        max_length: Maximum characters of content to return. Defaults to 10000.

    Returns:
        The webpage content as clean text with the page title.
    """
    # Write the script to a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(_PUPPETEER_SCRIPT)
        script_path = f.name

    try:
        result = subprocess.run(
            ["node", script_path, url, str(max_length)],
            capture_output=True,
            text=True,
            timeout=45,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Puppeteer failed: {stderr[:500]}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("Puppeteer returned no output")

        data = json.loads(output)
        if "error" in data:
            raise RuntimeError(f"Puppeteer error: {data['error']}")

        title = data.get("title", "")
        content = data.get("content", "")

        if title:
            return f"# {title}\n\n{content}"
        return content

    finally:
        os.unlink(script_path)
