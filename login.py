import re
import time
import logging
import requests
from urllib3.util import Retry

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FlexSMSLogin")

class FlexSMSClient:
    """
    Flex SMS Portal Authentication & Client
    Extracted from apibeld project.
    Handles math captcha solving, session management, and login.
    """
    def __init__(self, base_url="http://168.119.13.175/ints", username="Atiar59_FD", password="Atiar5942@#", proxy=None):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.proxy = proxy
        self.session = None
        self.is_logged_in = False
        self.ajax_url = None
        self._init_session()

    def _init_session(self):
        """Initializes requests session with retry strategy and browser headers."""
        if hasattr(self, 'session') and self.session:
            try:
                self.session.close()
            except Exception:
                pass

        self.session = requests.Session()

        if self.proxy:
            self.session.proxies = {
                'http': self.proxy,
                'https': self.proxy
            }

        retry_strategy = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=retry_strategy
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        })

    def solve_captcha(self, html_text):
        """
        Extracts and solves simple math captchas like:
        'What is 7 + 10 = ?' or 'What is 15 - 5 = ?'
        """
        # Match standard math patterns: X + Y, X - Y, X * Y
        match = re.search(r'What is\s+(\d+)\s*([+\-*])\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
        if match:
            n1 = int(match.group(1))
            op = match.group(2)
            n2 = int(match.group(3))
            if op == '+':
                return n1 + n2
            elif op == '-':
                return n1 - n2
            elif op == '*':
                return n1 * n2

        # Fallback regex for alternative formatting
        match_simple = re.search(r'(\d+)\s*([+\-*])\s*(\d+)\s*=\s*\?', html_text)
        if match_simple:
            n1 = int(match_simple.group(1))
            op = match_simple.group(2)
            n2 = int(match_simple.group(3))
            if op == '+':
                return n1 + n2
            elif op == '-':
                return n1 - n2
            elif op == '*':
                return n1 * n2

        return None

    def login(self, max_retries=3):
        """
        Performs full login:
        1. Loads login page
        2. Solves arithmetic captcha
        3. Posts credentials to /signin
        4. Verifies login status & extracts session info
        """
        login_page_url = f"{self.base_url}/login"
        signin_url = f"{self.base_url}/signin"

        logger.info(f"Connecting to {login_page_url} for user '{self.username}'...")

        for attempt in range(1, max_retries + 1):
            try:
                # 1. Fetch login page
                r = self.session.get(login_page_url, timeout=(5.0, 10.0))

                if r.status_code == 429:
                    logger.warning(f"Rate limited (429) on attempt {attempt}. Waiting before retry...")
                    time.sleep(1.0)
                    self._init_session()
                    continue

                if r.status_code != 200:
                    logger.error(f"Failed to load login page. HTTP Status: {r.status_code}")
                    time.sleep(0.5)
                    continue

                # 2. Extract and solve math captcha
                captcha_ans = self.solve_captcha(r.text)
                if captcha_ans is None:
                    logger.warning(f"[Attempt {attempt}] Could not parse math captcha from login page.")
                    time.sleep(0.5)
                    continue

                logger.info(f"[Attempt {attempt}] Captcha solved: {captcha_ans}")

                # 3. Post signin request
                payload = {
                    'username': self.username,
                    'password': self.password,
                    'capt': captcha_ans
                }

                r_post = self.session.post(
                    signin_url,
                    data=payload,
                    timeout=(5.0, 10.0),
                    allow_redirects=True
                )

                # Check if redirected to SMSDashboard or login successful
                if "SMSDashboard" in r_post.url or "dashboard" in r_post.text.lower() or r_post.status_code == 200:
                    logger.info("Successfully signed in! Checking report endpoint...")

                    # 4. Optional: Extract Ajax report endpoint
                    reports_url = f"{self.base_url}/agent/FailedSMSReports"
                    r_rep = self.session.get(reports_url, timeout=(5.0, 10.0))
                    if r_rep.status_code == 200:
                        ajax_match = re.search(r'sAjaxSource":\s*"([^"]+)"', r_rep.text)
                        if ajax_match:
                            self.ajax_url = f"{self.base_url}/agent/{ajax_match.group(1)}"
                            logger.info(f"Ajax endpoint extracted: {self.ajax_url}")

                    self.is_logged_in = True
                    logger.info(f"✅ Login successful for {self.username}!")
                    return True
                else:
                    logger.warning(f"Login failed (URL: {r_post.url}, Status: {r_post.status_code})")
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"Exception during login attempt {attempt}: {e}")
                time.sleep(0.5)

        self.is_logged_in = False
        logger.error(f"❌ Login failed after {max_retries} attempts.")
        return False


if __name__ == "__main__":
    client = FlexSMSClient()
    success = client.login()
    if success:
        print("\n=== LOGIN SUCCESSFUL ===")
        print(f"Session Cookies: {client.session.cookies.get_dict()}")
        if client.ajax_url:
            print(f"Ajax Endpoint: {client.ajax_url}")
    else:
        print("\n=== LOGIN FAILED ===")
