# -*- coding: utf-8 -*-
import os
import re
import time
import logging
import requests
from urllib3.util import Retry

from config import extract_otp, get_country_info

logger = logging.getLogger("SMSClient")

class FlexSMSClient:
    def __init__(self, username="Atiar59_FD", password="Atiar5942@#", base_url="http://168.119.13.175/ints", worker_id="Tab-1", proxy=None):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self.proxy = proxy
        self.session = None
        self.is_logged_in = False
        self.ajax_url = None
        self.echo_counter = 0
        self.last_query_time = 0.0
        self.last_response_time = 0.0
        self.rate_limited_until = 0.0
        self.consecutive_errors = 0
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
            total=1,
            backoff_factor=0.2,
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
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        })

    def solve_captcha(self, html_text):
        """Extracts and calculates simple math captchas."""
        m = re.search(r'What is\s+(\d+)\s*([+\-*])\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
        if m:
            n1, op, n2 = int(m.group(1)), m.group(2), int(m.group(3))
            if op == '+': return n1 + n2
            if op == '-': return n1 - n2
            if op == '*': return n1 * n2

        m_simple = re.search(r'(\d+)\s*([+\-*])\s*(\d+)\s*=\s*\?', html_text)
        if m_simple:
            n1, op, n2 = int(m_simple.group(1)), m_simple.group(2), int(m_simple.group(3))
            if op == '+': return n1 + n2
            if op == '-': return n1 - n2
            if op == '*': return n1 * n2

        return None

    def login(self, max_retries=3):
        """Authenticates with the portal and extracts the private sAjaxSource URL."""
        login_page_url = f"{self.base_url}/login"
        signin_url = f"{self.base_url}/signin"
        reports_url = f"{self.base_url}/agent/FailedSMSReports"

        logger.info(f"[{self.worker_id}] Connecting to {login_page_url} for user '{self.username}'...")

        for attempt in range(1, max_retries + 1):
            try:
                r = self.session.get(login_page_url, timeout=(1.5, 3.0))

                if r.status_code == 429:
                    logger.warning(f"[{self.worker_id}] Rate limited (429) on attempt {attempt}.")
                    time.sleep(0.5)
                    self._init_session()
                    continue

                if r.status_code != 200:
                    time.sleep(0.2)
                    continue

                captcha_ans = self.solve_captcha(r.text)
                if captcha_ans is None:
                    time.sleep(0.2)
                    continue

                payload = {
                    'username': self.username,
                    'password': self.password,
                    'capt': captcha_ans
                }

                r_post = self.session.post(
                    signin_url,
                    data=payload,
                    timeout=(1.5, 3.0),
                    allow_redirects=True
                )

                if "SMSDashboard" in r_post.url or "dashboard" in r_post.text.lower() or r_post.status_code == 200:
                    r_rep = self.session.get(reports_url, timeout=(1.5, 3.0))
                    if r_rep.status_code == 200:
                        ajax_match = re.search(r'sAjaxSource":\s*"([^"]+)"', r_rep.text)
                        if ajax_match:
                            self.ajax_url = f"{self.base_url}/agent/{ajax_match.group(1)}"
                            self.is_logged_in = True
                            self.rate_limited_until = 0.0
                            self.consecutive_errors = 0
                            logger.info(f"[{self.worker_id}] Login successful for {self.username}! Ajax URL: {self.ajax_url}")
                            return True

                time.sleep(0.2)

            except Exception as e:
                logger.error(f"[{self.worker_id}] Login error on attempt {attempt}: {e}")
                time.sleep(0.2)

        self.is_logged_in = False
        return False

    def fetch_records(self, keyword="Telegram", display_length=10):
        """
        Ultra-fast query with display_length=10.
        Limits MySQL execution time to <200ms.
        """
        now = time.time()
        if self.rate_limited_until > now:
            return None

        if not self.is_logged_in or not self.ajax_url:
            if not self.login():
                return None

        self.echo_counter += 1
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Referer': f"{self.base_url}/agent/FailedSMSReports",
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }

        params = {
            'sEcho': str(self.echo_counter),
            'iDisplayStart': '0',
            'iDisplayLength': str(display_length),
            'iSortingCols': '1',
            'iSortCol_0': '0',
            'sSortDir_0': 'desc',
            'bSortable_0': 'true',
            'bSearchable_0': 'true',
            'bSearchable_1': 'true',
            'bSearchable_2': 'true',
            'bSearchable_3': 'true',
            'bSearchable_4': 'true',
            'sSearch': keyword.strip() if keyword else '',
            '_': str(int(now * 1000))
        }

        try:
            t0 = time.time()
            res = self.session.get(self.ajax_url, params=params, headers=headers, timeout=(1.5, 3.0))
            self.last_response_time = time.time() - t0
            self.last_query_time = time.time()

            if res.status_code == 429:
                self.rate_limited_until = time.time() + 1.2
                return None

            if res.status_code != 200 or "Direct Script Access Not Allowed" in res.text or "<!DOCTYPE html>" in res.text:
                self.is_logged_in = False
                self.ajax_url = None
                return None

            data = res.json()
            raw_rows = data.get('aaData', [])
            records = []

            for row in raw_rows:
                if len(row) < 4:
                    continue
                num_str = str(row[1]).strip()
                cli_str = str(row[2]).strip()
                msg_str = str(row[3]).strip()

                if not num_str or not msg_str:
                    continue

                clean_digits = re.sub(r'[^0-9]', '', num_str)
                if len(clean_digits) < 5:
                    continue

                country_name, iso_code, flag_emoji, calling_code = get_country_info(clean_digits)
                otp_code = extract_otp(msg_str, cli=cli_str)

                records.append({
                    'time': str(row[0]).strip(),
                    'number': num_str,
                    'cli': cli_str,
                    'message': msg_str,
                    'otp': otp_code,
                    'country': country_name,
                    'iso': iso_code,
                    'flag': flag_emoji,
                    'calling_code': calling_code,
                    'cause': str(row[4]).strip() if len(row) > 4 else ""
                })

            self.consecutive_errors = 0
            return records

        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors >= 3:
                self.is_logged_in = False
                self.ajax_url = None
                self._init_session()
            self.rate_limited_until = time.time() + 0.5
            return None
