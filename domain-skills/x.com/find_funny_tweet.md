
# Find Funny Tweet on X.com
## Description: Navigate to X.com, load tweets, and identify a potentially funny tweet based on keywords or fallback to the first available tweet.
## Selectors:
- [data-testid="tweetText"]
- article div[lang]
- [data-testid="cellInnerDiv"] div[lang]

## Code:
# 1. new_tab("https://x.com")
# 2. wait_for_load()
# 3. time.sleep(5)
# 4. Use js() to extract tweets:
tweets_js = """
let tweets = [];
const selectors = ['[data-testid="tweetText"]', 'article div[lang]', '[data-testid="cellInnerDiv"] div[lang]'];
for (let sel of selectors) {
    document.querySelectorAll(sel).forEach(el => {
        const text = el.innerText.trim();
        if (text.length > 20 && !tweets.includes(text)) {
            tweets.push(text);
        }
    });
}
return tweets.slice(0, 10);
"""
tweets = js(tweets_js)
# 5. Filter for humor (😂, LOL, funny) or pick first one.
# 6. capture_screenshot("tweet_found.png")
