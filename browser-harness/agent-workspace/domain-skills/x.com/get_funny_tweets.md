
# Get Funny Tweets from X.com
## Description: Extract top liked tweets from the timeline which are likely to be funny or popular.
## Selectors:
- article[data-testid="tweet"]
- [data-testid="tweetText"]
- [data-testid="like"]

## Code:
tweets_data = js("""
const tweetContainers = document.querySelectorAll('article[data-testid="tweet"]');
let tweets = [];
tweetContainers.forEach((container, index) => {
    if (index >= 20) return; 
    const textElement = container.querySelector('[data-testid="tweetText"]');
    const likeCount = container.querySelector('[data-testid="like"]');
    let text = "";
    if (textElement) text = textElement.innerText;
    let likes = 0;
    if (likeCount) {
        const ariaLabel = likeCount.getAttribute('aria-label');
        if (ariaLabel) {
            const numStr = ariaLabel.replace(/[^0-9.]/g, '');
            likes = parseFloat(numStr) || 0;
        }
    }
    if (text) tweets.push({text: text, likes: likes});
});
tweets.sort((a, b) => b.likes - a.likes);
return tweets.slice(0, 5);
""")
print(tweets_data)
