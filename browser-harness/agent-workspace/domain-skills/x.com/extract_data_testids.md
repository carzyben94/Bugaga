
To extract all data-testid attributes from x.com:
1. Navigate to https://x.com
2. Wait for page load (wait_for_load() + time.sleep(5))
3. Use js() with querySelectorAll('[data-testid]') to extract all testids
4. Parse the JSON response to get unique values
