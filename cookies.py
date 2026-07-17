# ---------- КУКИ ДЛЯ X.COM ----------
X_COOKIES = [
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "__cuid", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "lang", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "ru"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "dnt", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "1"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id_marketing", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id_ads", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "personalization_id", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "twid", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "u%3D2067347503503052800"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "auth_token", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "ct0", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "__cf_bm", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "KFaKAqD6gO1ZhCG6Eng0A2oPJccRx5Yjs2LnNaZIUDs-1784022753.029898-1.0.1.1-NIpFLkCP7hAPgu0V_JbWmriYyaVYe7B5rrbuxMtSTicUxDV0MYrhlTiAdVxPlMbIKnf4TLZNw53wRWfRpoodX0Ys6UaRcP2oXJjXWiYMwXp2i4tTOSYKYcLnRL41ius7"}
]

SITE_COOKIES = {"x.com": X_COOKIES, "twitter.com": X_COOKIES}

def get_cookies_for_url(url):
    for domain, cookies in SITE_COOKIES.items():
        if domain in url.lower():
            return cookies
    return []