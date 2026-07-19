# browser-harness/agent-workspace/agent_helpers.py

"""Agent-editable browser helpers."""

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
