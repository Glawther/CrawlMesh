import random
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class BrowserProfile:
    label: str
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str
    accept_language: str


PROFILES: List[BrowserProfile] = [
    BrowserProfile(
        label="Chrome 131.0 / Windows 10 x64",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    ),
    BrowserProfile(
        label="Chrome 131.0 / macOS Sonoma",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
        accept_language="pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    ),
    BrowserProfile(
        label="Firefox 132.0 / Linux x86_64",
        user_agent="Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
        sec_ch_ua="",
        sec_ch_ua_platform='"Linux"',
        sec_ch_ua_mobile="?0",
        accept_language="pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
    ),
    BrowserProfile(
        label="Edge 131.0 / Windows 11 x64",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        sec_ch_ua='"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        accept_language="pt-BR,pt;q=0.9,en;q=0.8",
    ),
]


class FingerprintRotator:
    """Generates coherent browser header sets to avoid anti-bot heuristics."""

    def __init__(self) -> None:
        self._index = 0

    def next_profile(self, randomize: bool = True) -> BrowserProfile:
        if randomize:
            return random.choice(PROFILES)
        profile = PROFILES[self._index % len(PROFILES)]
        self._index += 1
        return profile

    def build_headers(
        self, referer: str = "https://www.google.com.br/", randomize: bool = True
    ) -> tuple[Dict[str, str], str]:
        profile = self.next_profile(randomize=randomize)
        headers: Dict[str, str] = {
            "User-Agent": profile.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": profile.accept_language,
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Referer": referer,
        }
        if profile.sec_ch_ua:
            headers["Sec-Ch-Ua"] = profile.sec_ch_ua
            headers["Sec-Ch-Ua-Mobile"] = profile.sec_ch_ua_mobile
            headers["Sec-Ch-Ua-Platform"] = profile.sec_ch_ua_platform
        return headers, profile.label


fingerprint_rotator = FingerprintRotator()
