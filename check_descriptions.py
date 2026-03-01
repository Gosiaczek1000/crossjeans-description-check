import re
import csv
import json
import os
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


CATEGORY_URLS = [
    "https://crossjeans.pl/on/jeansy-meskie/slim?limit=0",
    "https://crossjeans.pl/on/jeansy-meskie/regular?limit=0",
]

MIN_LEN = 130
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DescriptionChecker/1.0; +https://github.com/)",
}


def norm_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s


def is_probably_product_url(url: str) -> bool:
    """
    Heurystyka (bez znajomości dokładnej struktury strony):
    - musi być na crossjeans.pl
    - ścieżka nie może wyglądać jak kategoria (bez cyfr zwykle)
    - bardzo często produkty mają w URL ciągi cyfr i myślników
    """
    try:
        p = urlparse(url)
    except Exception:
        return False

    if "crossjeans.pl" not in p.netloc:
        return False

    path = p.path.lower()

    # Odfiltruj oczywiste nie-produkty
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".svg", ".css", ".js", ".pdf")):
        return False

    # Musi być w sekcji męskiej /on/ (bo Twoje linki są /on/…)
    if not path.startswith("/on/"):
        return False

    # Heurystyka: produkt zwykle ma liczby w URL
    if re.search(r"\d{3,}", path):
        return True

    return False


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def extract_product_links_from_category(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue

        full = urljoin(base_url, href)
        # usuń fragmenty typu #…
        full = full.split("#", 1)[0]

        if is_probably_product_url(full):
            links.add(full)

    return sorted(links)


def extract_description_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # 1) Meta og:description
    og = soup.select_one('meta[property="og:description"]')
    if og and og.get("content"):
        txt = norm_text(og["content"])
        if txt:
            return txt

    # 2) Meta description
    md = soup.select_one('meta[name="description"]')
    if md and md.get("content"):
        txt = norm_text(md["content"])
        if txt:
            return txt

    # 3) Najczęstsze miejsca w HTML (różne sklepy mają różnie)
    candidates = [
        '[itemprop="description"]',
        "#description",
        ".description",
        ".product-description",
        ".product__description",
        ".tabs-content",
    ]
    for sel in candidates:
        el = soup.select_one(sel)
        if el:
            txt = norm_text(el.get_text(" ", strip=True))
            if txt:
                return txt

    # 4) JSON-LD Product (czasem opis jest tam)
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        # data może być dict albo lista
        blocks = data if isinstance(data, list) else [data]
        for b in blocks:
            if isinstance(b, dict) and (b.get("@type") == "Product" or "Product" in str(b.get("@type", ""))):
                desc = b.get("description", "")
                desc = norm_text(desc)
                if desc:
                    return desc

    return ""


def main() -> int:
    os.makedirs("outputs", exist_ok=True)

    all_product_links = set()

    print("KROK 1: Zbieram linki produktów z kategorii…")
    for cat in CATEGORY_URLS:
        try:
            html = fetch(cat)
        except Exception as e:
            print(f"  ERROR: Nie mogę pobrać kategorii: {cat}\n  {e}")
            continue

        links = extract_product_links_from_category(html, cat)
        print(f"  {cat} -> znaleziono linków (kandydatów): {len(links)}")
        for l in links:
            all_product_links.add(l)

    product_links = sorted(all_product_links)
    print(f"\nKROK 2: Łącznie unikalnych linków produktów: {len(product_links)}")

    results = []
    missing_or_short = []

    print("\nKROK 3: Sprawdzam opisy na stronach produktów…")
    for i, url in enumerate(product_links, start=1):
        try:
            html = fetch(url)
            desc = extract_description_from_html(html)
            desc_len = len(desc)

            if desc_len == 0:
                status = "MISSING"
            elif desc_len < MIN_LEN:
                status = f"SHORT<{MIN_LEN}"
            else:
                status = "OK"

            row = {
                "url": url,
                "status": status,
                "desc_len": desc_len,
                "description_preview": desc[:180],
            }
            results.append(row)

            if status != "OK":
                missing_or_short.append(row)

            if i % 25 == 0:
                print(f"  ...sprawdzone {i}/{len(product_links)}")

        except Exception as e:
            row = {
                "url": url,
                "status": "ERROR",
                "desc_len": 0,
                "description_preview": "",
            }
            results.append(row)
            missing_or_short.append(row)
            print(f"  ERROR na {url}: {e}")

    # CSV
    csv_path = "outputs/report.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "status", "desc_len", "description_preview"])
        w.writeheader()
        w.writerows(results)

    # Markdown (czytelny wykaz problemów)
    md_path = "outputs/report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Raport: brak opisu / opis < 130 znaków\n\n")
        f.write(f"- Liczba produktów: **{len(product_links)}**\n")
        f.write(f"- Problemy (MISSING / SHORT / ERROR): **{len(missing_or_short)}**\n\n")

        if not missing_or_short:
            f.write("✅ Brak problemów – wszystkie opisy mają co najmniej 130 znaków.\n")
        else:
            f.write("## Lista problemów\n\n")
            for r in missing_or_short:
                f.write(f"- **{r['status']}** ({r['desc_len']} znaków) → {r['url']}\n")

    # GitHub Actions: podsumowanie i “outputy”
    fail_count = len(missing_or_short)
    summary = (
        f"Produkty: {len(product_links)}\n"
        f"Problemy (MISSING/SHORT/ERROR): {fail_count}\n"
        f"Raport: outputs/report.md oraz outputs/report.csv\n"
    )
    print("\nPODSUMOWANIE\n" + summary)

    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with open(github_summary, "a", encoding="utf-8") as f:
            f.write("## Wynik kontroli opisów\n\n")
            f.write(f"- Produkty: **{len(product_links)}**\n")
            f.write(f"- Problemy (MISSING/SHORT/ERROR): **{fail_count}**\n")
            f.write("\nRaport jest w artifact: `outputs/report.md`, `outputs/report.csv`.\n")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"fail_count={fail_count}\n")

    # Nie “psuj” akcji – zostaw 0, żeby zawsze był artifact do pobrania
    return 0


if __name__ == "__main__":
    sys.exit(main())
