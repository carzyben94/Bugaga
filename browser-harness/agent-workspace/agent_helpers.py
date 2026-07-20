"""Agent-editable browser helpers.

Add task-specific browser primitives here. Core helpers from browser_harness.helpers
load this file when BH_AGENT_WORKSPACE points at this directory, or when this
repo's default agent-workspace exists.
"""

import sys
import os

# Добавляем путь к browser-harness
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    page_info,
    capture_screenshot,
    click_at_xy,
    type_text,
    press_key,
    scroll,
    js,
    cdp,
    ensure_real_tab,
)


def get_iphone_prices_de():
    """Получает цены на iPhone с apple.com/de"""
    new_tab("https://www.apple.com/de/shop/buy-iphone")
    wait_for_load()
    ensure_real_tab()
    
    prices = js("""
        const items = document.querySelectorAll('.price, [class*="price"]');
        Array.from(items).map(el => el.textContent.trim());
    """)
    return prices


def get_iphone_prices_mediamarkt():
    """Получает цены на iPhone с mediamarkt.de"""
    new_tab("https://www.mediamarkt.de/de/productlist/apple-iphone-15-3179635.html")
    wait_for_load()
    ensure_real_tab()
    
    prices = js("""
        const items = document.querySelectorAll('.price, .product-price, [class*="price"]');
        Array.from(items).map(el => el.textContent.trim());
    """)
    return prices


def search_agentlist(query):
    """Ищет навыки в AgentList по запросу"""
    import json
    import urllib.request
    
    url = f"https://agentlist.com/api/listings?q={query}&limit=10"
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
    
    results = []
    for item in data:
        results.append({
            "title": item.get("title"),
            "id": item.get("id"),
            "votes": item.get("vote_count"),
            "category": item.get("category"),
        })
    return results


def get_iphone_prices_idealo():
    """Получает цены на iPhone с idealo.de"""
    new_tab("https://www.idealo.de/preisvergleich/ProductCategory/3132F1125401.html")
    wait_for_load()
    ensure_real_tab()
    
    prices = js("""
        const items = document.querySelectorAll('.product-price-value, .product-price, .price');
        Array.from(items).slice(0, 10).map(el => el.textContent.trim());
    """)
    return prices


def get_tweets():
    tweets = js("""
    let tweets = [];
    const selectors = ['[data-testid="tweetText"]', 'article div[lang]', '[data-testid="cellInnerDiv"] div[lang]'];
    for (let sel of selectors) {
        document.querySelectorAll(sel).forEach(el => {
            if (el.innerText && el.innerText.trim() && !tweets.includes(el.innerText.trim())) {
                tweets.push(el.innerText.trim());
            }
        });
    }
    return tweets.slice(0, 20);
    """)
    print(f"Found {len(tweets)} tweets")
    return tweets

