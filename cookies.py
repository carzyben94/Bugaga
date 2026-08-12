# ============================================================
# КУКИ ДЛЯ X.COM (TWITTER) - АВТОРИЗОВАННАЯ СЕССИЯ
# ============================================================

COOKIES = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178649311604923115"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "gt",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "2087329533200384341"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178649311604923115"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178649311604923115"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "\"v1_VL5PDSWqcwv7LNBV75SiLA==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "0IZEFEXINZjUAkofClQ1wR5gAa1bbmp9faX0c3s2RNY-1786493439.08436-1.0.1.1-McoQi1ca0JO0PZiXPCNfeW1eArV2s6anfaj7Flk5YdlhrC9o3U9JTlgqUQeiAuvD14xtunnjl2pl23T_qWTewG0xZYTIQ8YyYMZ6uvR0bl.A27tDwc3bbfDA71nRj7eY"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "g_state",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "{\"i_l\":0,\"i_ll\":1786493441069,\"i_b\":\"GK5KqYSRaGCT7CvSxBv3wqY6m7ne53iSPqkYW+ROGIo\",\"i_e\":{\"enable_itp_optimization\":24},\"i_et\":1786493441069}"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "u%3D2067347503503052800"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "auth_token",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "cb1c77feeb34ba956e9a11395f16e2c40a8296b3"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "e769b9ab9eeae9ac8db6093626dbfea52ce3a5a0010cb4effe135bf6726b25ae60168ef75632bc6968843bee52b09ff318927e35a461014f564edebf8bb7199436c548cca8333728e28b98d882763b56"
    }
]

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_cookies_dict() -> dict:
    """Возвращает словарь {name: value} для всех кук"""
    return {c["name"]: c["value"] for c in COOKIES}

def get_cookies_for_domain(domain: str = ".x.com") -> list:
    """Возвращает куки для указанного домена"""
    return [c for c in COOKIES if domain in c.get("domain", "")]