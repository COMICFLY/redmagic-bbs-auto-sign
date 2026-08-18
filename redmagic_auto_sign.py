#!/usr/bin/env python3
"""RedMagic community auto sign-in helper."""

from __future__ import annotations

import argparse
import gzip
import http.client
import json
import os
import re
import secrets
import string
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlencode


BBS_API = "https://api-bbs.redmagic.com"

DEFAULT_H5_VERSION = "3.0.0"
DEFAULT_H5_UA = (
    "Mozilla/5.0 (Linux; Android 15; NX769J Build/AQ3A.240812.002; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/150.0.7871.181 Mobile Safari/537.36/zealer/5.2.5"
)
DEFAULT_PUSH_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
BOUNDARY_CHARS = string.ascii_letters + string.digits


class RedMagicError(RuntimeError):
    pass


@dataclass
class Account:
    name: str
    access_token: Optional[str] = None


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


def now_ms() -> str:
    return str(int(time.time() * 1000))


def random_webkit_boundary() -> str:
    suffix = "".join(secrets.choice(BOUNDARY_CHARS) for _ in range(16))
    return "----WebKitFormBoundary" + suffix


def split_values(raw: str) -> List[str]:
    if not raw:
        return []
    values = []
    for item in re.split(r"[\n,;]+", raw):
        item = item.strip()
        if item:
            values.append(item)
    return values


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return value[:2] + "***"
    return value[:6] + "***" + value[-4:]


def add_github_mask(value: Optional[str]) -> None:
    if value and os.getenv("GITHUB_ACTIONS"):
        print(f"::add-mask::{value}")


class HttpClient:
    def __init__(self) -> None:
        self.timeout = env_float("REDMAGIC_TIMEOUT", 20.0)
        self.retries = max(0, env_int("REDMAGIC_RETRIES", 2))

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Tuple[int, str]:
        headers = dict(headers or {})
        if body is not None and "Content-Length" not in headers:
            headers["Content-Length"] = str(len(body))

        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(url, data=body, headers=headers, method=method)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    text = self._decode_body(raw, response.headers)
                    return int(response.status), text
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                text = self._decode_body(raw, exc.headers)
                if int(exc.code) in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                return int(exc.code), text
            except (
                urllib.error.URLError,
                TimeoutError,
                http.client.RemoteDisconnected,
                ConnectionResetError,
            ) as exc:
                if attempt < self.retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise RedMagicError(f"{method} {url} failed: {exc}") from exc
        raise RedMagicError(f"{method} {url} failed after retries")

    @staticmethod
    def _decode_body(raw: bytes, headers: Any) -> str:
        encoding = ""
        if headers:
            encoding = str(headers.get("Content-Encoding") or "").lower()
        if "gzip" in encoding and raw:
            raw = gzip.decompress(raw)
        charset = "utf-8"
        if headers and hasattr(headers, "get_content_charset"):
            charset = headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace")

    def post_form(
        self,
        url: str,
        headers: Dict[str, str],
        data: Dict[str, Any],
        multipart: bool = False,
    ) -> Tuple[int, str]:
        headers = dict(headers)
        if multipart:
            boundary = random_webkit_boundary()
            body = encode_multipart(data, boundary)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            body = urlencode({key: str(value) for key, value in data.items()}).encode("utf-8")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        return self.request("POST", url, headers=headers, body=body)

    def post_json(self, url: str, payload: Dict[str, Any]) -> Tuple[int, str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self.request(
            "POST",
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )

    def get(self, url: str, params: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
        if params:
            separator = "&" if "?" in url else "?"
            url = url + separator + urlencode(params)
        return self.request("GET", url, headers={}, body=None)


def encode_multipart(data: Dict[str, Any], boundary: str) -> bytes:
    parts = []
    for key, value in data.items():
        parts.append(f"--{boundary}\r\n")
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n')
        parts.append(f"{value}\r\n")
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode("utf-8")


def build_session() -> HttpClient:
    return HttpClient()


def decode_response(status_code: int, text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        snippet = text[:400].replace("\n", " ")
        raise RedMagicError(
            f"HTTP {status_code}, response is not JSON: {snippet}"
        ) from exc
    if status_code >= 400:
        raise RedMagicError(f"HTTP {status_code}: {data}")
    if not isinstance(data, dict):
        raise RedMagicError(f"Unexpected JSON payload: {data!r}")
    return data


def post_form(
    session: HttpClient,
    url: str,
    headers: Dict[str, str],
    data: Dict[str, Any],
    multipart: bool = False,
) -> Dict[str, Any]:
    status_code, text = session.post_form(url, headers=headers, data=data, multipart=multipart)
    return decode_response(status_code, text)


def bbs_headers(access_token: str) -> Dict[str, str]:
    h5_version = env("REDMAGIC_H5_VERSION", DEFAULT_H5_VERSION)
    return {
        "sec-ch-ua-platform": '"Android"',
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Android WebView";v="150"',
        "accessToken": access_token,
        "sec-ch-ua-mobile": "?1",
        "vesioncode": h5_version,
        "User-Agent": env("REDMAGIC_H5_UA", DEFAULT_H5_UA),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://apph5-bbs.redmagic.com",
        "X-Requested-With": "cn.nubia.bbs",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://apph5-bbs.redmagic.com/",
        "Accept-Language": env("REDMAGIC_ACCEPT_LANGUAGE", "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"),
    }


def parse_account_item(item: Any, index: int) -> Account:
    if isinstance(item, str):
        return Account(name=f"account-{index}", access_token=item.strip())
    if not isinstance(item, dict):
        raise RedMagicError(f"REDMAGIC_ACCOUNTS item #{index} must be an object or token string")

    token = (
        item.get("access_token")
        or item.get("accessToken")
        or item.get("token")
        or item.get("REDMAGIC_ACCESS_TOKEN")
    )
    if not token:
        raise RedMagicError(
            f"REDMAGIC_ACCOUNTS item #{index} is missing access_token/accessToken/token"
        )
    return Account(
        name=str(item.get("name") or f"account-{index}"),
        access_token=str(token).strip() if token else None,
    )


def load_accounts() -> List[Account]:
    accounts: List[Account] = []
    raw_accounts = os.getenv("REDMAGIC_ACCOUNTS", "").strip()
    if raw_accounts:
        try:
            parsed = json.loads(raw_accounts)
        except json.JSONDecodeError as exc:
            raise RedMagicError("REDMAGIC_ACCOUNTS must be valid JSON") from exc
        if isinstance(parsed, dict):
            parsed = [dict(value, name=key) if isinstance(value, dict) else {"name": key, "access_token": value} for key, value in parsed.items()]
        if not isinstance(parsed, list):
            raise RedMagicError("REDMAGIC_ACCOUNTS must be a JSON list or object")
        accounts.extend(parse_account_item(item, i + 1) for i, item in enumerate(parsed))

    for index, token in enumerate(split_values(os.getenv("REDMAGIC_ACCESS_TOKENS", "")), start=1):
        accounts.append(Account(name=f"token-{index}", access_token=token))

    single_token = env("REDMAGIC_ACCESS_TOKEN")
    if single_token:
        accounts.append(Account(name=env("REDMAGIC_ACCOUNT_NAME", "default"), access_token=single_token))

    deduped: List[Account] = []
    seen = set()
    for account in accounts:
        key = (account.name, account.access_token)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(account)
    return deduped


class RedMagicClient:
    def __init__(self, session: HttpClient) -> None:
        self.session = session

    def access_token_for(self, account: Account) -> str:
        if not account.access_token:
            raise RedMagicError(f"{account.name}: accessToken is required")
        add_github_mask(account.access_token)
        return account.access_token

    def home_index(self, token: str) -> Dict[str, Any]:
        return post_form(
            self.session,
            f"{BBS_API}/points/home/index",
            bbs_headers(token),
            {"pageSize": env("REDMAGIC_HOME_PAGE_SIZE", "4"), "v": now_ms()},
            multipart=True,
        )

    def sign_in(self, token: str) -> Dict[str, Any]:
        return post_form(
            self.session,
            f"{BBS_API}/points/home/pointsRegister",
            bbs_headers(token),
            {"v": now_ms()},
            multipart=True,
        )

    def open_box(self, token: str) -> Dict[str, Any]:
        return post_form(
            self.session,
            f"{BBS_API}/points/home/openbox",
            bbs_headers(token),
            {"v": now_ms()},
            multipart=True,
        )

    def claim_energy(self, token: str, energy_id: str) -> Dict[str, Any]:
        return post_form(
            self.session,
            f"{BBS_API}/points/home/havingenergy",
            bbs_headers(token),
            {"energyId": energy_id, "v": now_ms()},
            multipart=True,
        )

    def launch_prize(self, token: str) -> Dict[str, Any]:
        return post_form(
            self.session,
            f"{BBS_API}/points/prize/launch",
            bbs_headers(token),
            {
                "template_id": env("REDMAGIC_PRIZE_TEMPLATE_ID", "1"),
                "aid": env("REDMAGIC_PRIZE_AID", "0"),
                "v": now_ms(),
            },
            multipart=True,
        )


def ok_status(payload: Dict[str, Any]) -> bool:
    status = payload.get("status")
    return status in (None, 0, 200, "0", "200", True)


def payload_msg(payload: Dict[str, Any]) -> str:
    return str(payload.get("msg") or payload.get("message") or payload)


def format_home(payload: Dict[str, Any]) -> List[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    user = data.get("userInfo") if isinstance(data.get("userInfo"), dict) else {}
    lines = []
    nickname = user.get("nickname") or user.get("uid") or "unknown"
    score = user.get("score")
    energy = user.get("energy")
    lines.append(f"Home: {nickname} | score={score} | energy={energy}")
    next_open = data.get("nextOpenTime")
    if next_open:
        lines.append(f"Box nextOpenTime={next_open}")
    return lines


def registration_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    register = data.get("registerData")
    return register if isinstance(register, dict) else {}


def signed_state(payload: Dict[str, Any]) -> Optional[bool]:
    value = registration_data(payload).get("isRegister")
    if value in (1, "1", True):
        return True
    if value in (0, "0", False):
        return False
    return None


def ensure_signed(
    client: RedMagicClient,
    token: str,
    home_payload: Dict[str, Any],
) -> Tuple[List[str], Dict[str, Any], bool]:
    register = registration_data(home_payload)
    state = signed_state(home_payload)
    if state is True:
        message = register.get("txt") or "already signed"
        return [f"Sign: already signed, {message}"], home_payload, True
    if state is None:
        return [f"Sign: failed, unexpected isRegister={register.get('isRegister')!r}"], home_payload, False

    sign = client.sign_in(token)
    if not ok_status(sign):
        return [f"Sign: failed, {payload_msg(sign)}"], home_payload, False

    verified_home = client.home_index(token)
    if not ok_status(verified_home):
        return [f"Sign: request succeeded but verification failed, {payload_msg(verified_home)}"], home_payload, False
    if signed_state(verified_home) is not True:
        value = registration_data(verified_home).get("isRegister")
        return [f"Sign: request succeeded but isRegister={value!r}"], verified_home, False

    verified_register = registration_data(verified_home)
    sign_data = sign.get("data") if isinstance(sign.get("data"), dict) else {}
    details = []
    reward = verified_register.get("todayEnergy") or register.get("todayEnergy")
    if reward not in (None, ""):
        details.append(f"reward={reward}")
    continue_days = sign_data.get("continueDays")
    if continue_days not in (None, ""):
        details.append(f"continueDays={continue_days}")
    suffix = ", " + ", ".join(details) if details else ""
    return [f"Sign: completed{suffix}"], verified_home, True


def should_open_box(home_payload: Dict[str, Any]) -> Tuple[bool, str]:
    data = home_payload.get("data") if isinstance(home_payload.get("data"), dict) else {}
    waiting = data.get("boxWaitingOpen")
    next_open = data.get("nextOpenTime")
    if waiting in (1, "1", True):
        return True, "boxWaitingOpen=1"
    if next_open in (0, "0", None, ""):
        return True, "nextOpenTime is empty"
    try:
        next_open_int = int(next_open)
        if next_open_int <= int(time.time()):
            return True, "nextOpenTime reached"
        return False, f"next box at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_open_int))}"
    except (TypeError, ValueError):
        return False, f"unexpected nextOpenTime={next_open!r}"


def open_and_claim_box(client: RedMagicClient, token: str) -> Tuple[str, bool]:
    box = client.open_box(token)
    if not ok_status(box):
        return f"Box: failed, {payload_msg(box)}", False

    data = box.get("data") if isinstance(box.get("data"), dict) else {}
    reward = f"+{data.get('energy', '?')} energy"
    next_open = data.get("nextOpenTime", "-")
    energy_id = data.get("energyId")
    if energy_id in (None, ""):
        return (
            f"Box: opened, {reward}, but claim was not confirmed: "
            f"openbox returned no energyId, nextOpenTime={next_open}"
        ), False

    claim = client.claim_energy(token, str(energy_id))
    if not ok_status(claim):
        return (
            f"Box: opened, {reward}, but claim failed: {payload_msg(claim)}, "
            f"nextOpenTime={next_open}"
        ), False
    return f"Box: claimed, {reward}, nextOpenTime={next_open}", True


def run_tasks_for_account(
    client: RedMagicClient,
    account: Account,
    dry_run: bool = False,
) -> Tuple[List[str], bool]:
    lines = [f"## {account.name}"]
    token = client.access_token_for(account)
    lines.append(f"Token: {mask(token)}")

    if dry_run:
        lines.append("Dry run: token configured; daily tasks skipped.")
        return lines, True

    home = client.home_index(token)
    if not ok_status(home):
        raise RedMagicError(f"{account.name}: home/index failed: {payload_msg(home)}")
    sign_lines, home, sign_ok = ensure_signed(client, token, home)
    lines.extend(format_home(home))
    lines.extend(sign_lines)

    if env_bool("REDMAGIC_ENABLE_BOX", True):
        openable, reason = should_open_box(home)
        if openable:
            box_line, _ = open_and_claim_box(client, token)
            lines.append(box_line)
        else:
            lines.append(f"Box: skipped, {reason}")

    if env_bool("REDMAGIC_ENABLE_LOTTERY", True):
        times = max(0, env_int("REDMAGIC_LOTTERY_TIMES", 10))
        delay = max(0.0, env_float("REDMAGIC_LOTTERY_DELAY", 1.5))
        for index in range(1, times + 1):
            prize = client.launch_prize(token)
            if not ok_status(prize):
                lines.append(f"Lottery #{index}: stopped, {payload_msg(prize)}")
                break
            data = prize.get("data") if isinstance(prize.get("data"), dict) else {}
            desc = data.get("prize_desc") or data.get("title") or payload_msg(prize)
            surplus = data.get("surplus_num")
            lines.append(f"Lottery #{index}: {desc}, surplus={surplus}")
            if surplus in (0, "0"):
                break
            if index != times and delay:
                time.sleep(delay)

    return lines, sign_ok


def run_box_for_account(client: RedMagicClient, account: Account) -> Tuple[List[str], bool, bool]:
    lines = [f"## {account.name}"]
    token = client.access_token_for(account)
    lines.append(f"Token: {mask(token)}")

    home = client.home_index(token)
    if not ok_status(home):
        raise RedMagicError(f"{account.name}: home/index failed: {payload_msg(home)}")
    lines.extend(format_home(home))

    openable, reason = should_open_box(home)
    if not openable:
        lines.append(f"Box: skipped, {reason}")
        return lines, False, True

    box_line, claimed = open_and_claim_box(client, token)
    lines.append(box_line)
    return lines, claimed, claimed


def send_notification(session: HttpClient, title: str, content: str) -> List[str]:
    if env_bool("REDMAGIC_PUSH_DISABLED", False):
        return ["push disabled"]

    results: List[str] = []

    pushplus_token = env("PUSHPLUS_TOKEN") or env("PUSH_PLUS_TOKEN")
    if pushplus_token:
        url = "https://www.pushplus.plus/send"
        payload = {
            "token": pushplus_token,
            "title": title,
            "content": content,
            "template": env("PUSHPLUS_TEMPLATE", "markdown"),
        }
        try:
            status_code, _ = session.post_json(url, payload)
            results.append(f"PushPlus: HTTP {status_code}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"PushPlus: {exc}")

    serverchan_key = env("SCT_KEY") or env("SERVERCHAN_SENDKEY")
    if serverchan_key:
        try:
            url = serverchan_url(serverchan_key)
            status_code, response_text = session.post_form(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": env("REDMAGIC_PUSH_UA", DEFAULT_PUSH_UA),
                },
                data={"title": title, "desp": content},
            )
            results.append(
                f"ServerChan: {format_push_response(status_code, response_text, serverchan_key)}"
            )
        except Exception as exc:  # noqa: BLE001
            results.append(f"ServerChan: {exc}")

    bark_base = env("BARK_URL")
    bark_key = env("BARK_KEY")
    if bark_base or bark_key:
        base = bark_base.rstrip("/") if bark_base else f"https://api.day.app/{bark_key}"
        url = f"{base}/{quote(title, safe='')}/{quote(content[:1800], safe='')}"
        try:
            status_code, _ = session.get(url, params={"group": "RedMagic"})
            results.append(f"Bark: HTTP {status_code}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"Bark: {exc}")

    tg_token = env("TG_BOT_TOKEN") or env("TELEGRAM_BOT_TOKEN")
    tg_user = env("TG_USER_ID") or env("TELEGRAM_CHAT_ID")
    if tg_token and tg_user:
        url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        payload = {
            "chat_id": tg_user,
            "text": f"{title}\n\n{content}",
            "link_preview_options": json.dumps({"is_disabled": True}),
        }
        try:
            status_code, _ = session.post_form(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=payload,
            )
            results.append(f"Telegram: HTTP {status_code}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"Telegram: {exc}")

    webhook_url = env("REDMAGIC_WEBHOOK_URL")
    if webhook_url:
        try:
            status_code, _ = session.post_json(
                webhook_url,
                {"title": title, "content": content, "source": "redmagic-auto-sign"},
            )
            results.append(f"Webhook: HTTP {status_code}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"Webhook: {exc}")

    return results or ["no push channel configured"]


def serverchan_url(sendkey: str) -> str:
    if "://" in sendkey or "/" in sendkey:
        raise RedMagicError("ServerChan SendKey must contain the key only, not the API URL")
    match = re.match(r"^sctp(\d+)t", sendkey, re.IGNORECASE)
    if sendkey.lower().startswith("sctp") and not match:
        raise RedMagicError("Invalid ServerChan3 SendKey format")
    if match:
        return f"https://{match.group(1)}.push.ft07.com/send/{sendkey}.send"
    return f"https://sctapi.ftqq.com/{sendkey}.send"


def format_push_response(status_code: int, text: str, secret: str = "") -> str:
    details: List[str] = []
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        snippet = re.sub(r"\s+", " ", text or "").strip()[:200]
        if snippet:
            details.append(snippet)
    else:
        if isinstance(payload, dict):
            if payload.get("code") is not None:
                details.append(f"code {payload['code']}")
            message = next(
                (
                    str(payload[key]).strip()
                    for key in ("info", "message", "error", "msg")
                    if payload.get(key) not in (None, "")
                ),
                "",
            )
            if message:
                details.append(message)

    result = f"HTTP {status_code}"
    if details:
        result += ", " + ", ".join(details)
    if secret:
        result = result.replace(secret, "***").replace(quote(secret, safe=""), "***")
    return result


def run_daily(client: RedMagicClient, accounts: List[Account], dry_run: bool) -> Tuple[str, bool]:
    if not accounts:
        raise RedMagicError("No account configured. Set REDMAGIC_ACCESS_TOKENS or REDMAGIC_ACCESS_TOKEN.")
    all_lines: List[str] = ["# RedMagic Auto Sign"]
    ok = True
    for account in accounts:
        try:
            lines, account_ok = run_tasks_for_account(client, account, dry_run=dry_run)
            all_lines.extend(lines)
            ok = ok and account_ok
        except Exception as exc:  # noqa: BLE001
            ok = False
            all_lines.append(f"## {account.name}")
            all_lines.append(f"Failed: {exc}")
            if env_bool("REDMAGIC_DEBUG", False):
                all_lines.append("```")
                all_lines.append(traceback.format_exc())
                all_lines.append("```")
    return "\n".join(all_lines), ok


def run_box_only(client: RedMagicClient, accounts: List[Account]) -> Tuple[str, bool, bool]:
    if not accounts:
        raise RedMagicError("No account configured. Set REDMAGIC_ACCESS_TOKENS or REDMAGIC_ACCESS_TOKEN.")
    all_lines: List[str] = ["# RedMagic Box"]
    ok = True
    claimed = False
    for account in accounts:
        try:
            lines, account_claimed, account_ok = run_box_for_account(client, account)
            all_lines.extend(lines)
            claimed = claimed or account_claimed
            ok = ok and account_ok
        except Exception as exc:  # noqa: BLE001
            ok = False
            all_lines.append(f"## {account.name}")
            all_lines.append(f"Failed: {exc}")
            if env_bool("REDMAGIC_DEBUG", False):
                all_lines.append("```")
                all_lines.append(traceback.format_exc())
                all_lines.append("```")
    if not claimed:
        all_lines.append("No box claimed in this run.")
    return "\n".join(all_lines), ok, claimed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RedMagic community auto sign-in")
    parser.add_argument("--box-only", action="store_true", help="check/open treasure box only")
    parser.add_argument("--dry-run", action="store_true", help="validate token config but skip daily tasks")
    parser.add_argument("--no-push", action="store_true", help="do not send push notification")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    session = build_session()
    client = RedMagicClient(session)
    accounts = load_accounts()

    box_only = args.box_only or env_bool("REDMAGIC_BOX_ONLY", False)
    dry_run = args.dry_run or env_bool("REDMAGIC_DRY_RUN", False)
    no_push = args.no_push or env_bool("REDMAGIC_PUSH_DISABLED", False)
    box_claimed = False

    try:
        if box_only:
            report, ok, box_claimed = run_box_only(client, accounts)
            title = "RedMagic Box"
        else:
            report, ok = run_daily(client, accounts, dry_run=dry_run)
            title = "RedMagic Auto Sign"
    except Exception as exc:  # noqa: BLE001
        ok = False
        failed_title = "RedMagic Box" if box_only else "RedMagic Auto Sign"
        report = f"# {failed_title}\nFailed: {exc}"
        if env_bool("REDMAGIC_DEBUG", False):
            report += "\n```\n" + traceback.format_exc() + "\n```"
        title = f"{failed_title} Failed"

    print(report)

    if box_only and ok and env_bool("REDMAGIC_BOX_PUSH_ONLY_OPENED", True) and not box_claimed:
        no_push = True

    if not no_push:
        push_results = send_notification(session, title, report)
        print("\n# Push")
        for result in push_results:
            print(result)

    if ok:
        return 0
    return 1 if env_bool("REDMAGIC_FAIL_ON_ERROR", True) else 0


if __name__ == "__main__":
    sys.exit(main())
