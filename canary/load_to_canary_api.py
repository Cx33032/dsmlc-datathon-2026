"""Load the Canary tags straight into a local Canary Historian through the Store and Forward REST write API.

Same tags as export_to_canary.py (it builds them), but no CSV Collector is needed: values go to Store and
Forward on https://localhost:55293, which forwards them to the Historian into dataset "Strathcona".

Needs a Canary API token with write access (Canary Admin > Identity > API Tokens). It is read from the
CANARY_API_TOKEN environment variable or from canary/.api_token (git-ignored) and never printed.

  python canary/load_to_canary_api.py --start 2026-10-01 --areas Winter      # small test first
  python canary/load_to_canary_api.py                                        # 2026 YTD, all areas
  python canary/load_to_canary_api.py --start 2025-01-01                     # full test period
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import urllib3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from export_to_canary import build_frame, to_lines  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # local self-signed certificate
CHUNK = 100_000   # values per storeData call
TZ = "-06:00"     # Saskatchewan time, UTC-6 all year (no daylight saving); the API needs an explicit offset


def api_token() -> str:
    tok = os.environ.get("CANARY_API_TOKEN") or os.environ.get("CANARY_TOKEN") or (
        (HERE / ".api_token").read_text().strip()
                                                 if (HERE / ".api_token").exists() else "")
    if not tok:
        sys.exit("No Canary API token: set CANARY_API_TOKEN or put it in canary/.api_token")
    return tok


class Sender:
    def __init__(self, url: str, historian: str, client_id: str):
        self.url, self.historian, self.client_id = url.rstrip("/"), historian, client_id
        self.s = requests.Session()
        self.s.verify = False   # only ever used against the local Store and Forward service
        self.token = None

    def _post(self, path: str, body: dict) -> dict:
        r = self.s.post(f"{self.url}/api/v1/{path}", json=body, timeout=300)
        try:
            out = r.json()
        except ValueError:
            raise RuntimeError(f"{path}: HTTP {r.status_code} {r.text[:200]}")
        if out.get("statusCode") not in (None, "Good"):
            errs = out.get("errors") or []
            raise RuntimeError(f"{path}: {len(errs)} error(s), first: {errs[:3]}")
        return out

    def open(self, tok: str):
        settings = {"clientTimeout": 300000, "autoCreateDatasets": True, "autoWriteNoData": False,
                    "insertReplaceData": True}
        body = {"historians": [self.historian], "clientId": self.client_id, "settings": settings}
        try:
            self.token = self._post("getSessionToken", {**body, "apiToken": tok})["sessionToken"]
        except RuntimeError:
            user = self._post("getUserToken", {"apiToken": tok})["userToken"]
            self.token = self._post("getSessionToken", {**body, "userToken": user})["sessionToken"]

    def store(self, tvqs: dict):
        self._post("storeData", {"sessionToken": self.token, "tvqs": tvqs})

    def close(self):
        if self.token:
            try:
                self._post("revokeSessionToken", {"sessionToken": self.token})
            finally:
                self.token = None


def batches(lines: pd.DataFrame, dataset: str):
    """Yield {"Dataset.Area.UWI.Measure": [[ts, value, quality], ...]} dicts of about CHUNK values each."""
    lines = lines.sort_values(["tag", "ts"])
    out, n = {}, 0
    for tag, g in lines.groupby("tag", sort=False):
        out[f"{dataset}.{tag}"] = [[t + TZ, float(v), int(q)] for t, v, q in zip(g["ts"], g["value"], g["quality"])]
        n += len(g)
        if n >= CHUNK:
            yield out, n
            out, n = {}, 0
    if out:
        yield out, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end")
    ap.add_argument("--areas", nargs="*")
    ap.add_argument("--dataset", default="Strathcona")
    ap.add_argument("--url", default="https://localhost:55293")
    ap.add_argument("--historian", default="localhost")
    ap.add_argument("--dry-run", action="store_true", help="build the values and stop before sending")
    a = ap.parse_args()

    t0 = time.time()
    lines = to_lines(build_frame(a.start, a.end, a.areas))
    print(f"built {len(lines):,} values on {lines['tag'].nunique():,} tags in {time.time() - t0:.0f}s")
    if a.dry_run:
        return
    snd = Sender(a.url, a.historian, "dsmlc_datathon_loader")
    snd.open(api_token())
    sent = 0
    try:
        for tvqs, n in batches(lines, a.dataset):
            snd.store(tvqs)
            sent += n
            print(f"  sent {sent:,} / {len(lines):,}", flush=True)
    finally:
        snd.close()
    print(f"done: {sent:,} values into dataset {a.dataset} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
