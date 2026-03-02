import re
import csv
import json
import os
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


CATEGORY_URLS = [
    "https://crossjeans.pl/ona/komplety-damskie?limit=0",
    "https://crossjeans.pl/ona/basic-damski?limit=0",
    "https://crossjeans.pl/ona/buty-damskie?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/longsleeve?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/swetry-damskie?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/sukienki-spodnice?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/kurtki-damskie-jeansowe?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/kurtki-damskie?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/bluzy-damskie?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/bluzki-i-koszule-damskie?limit=0",
    "https://crossjeans.pl/ona/odziez-damska/t-shirty-damskie?limit=0",
    "https://crossjeans.pl/ona/spodnie-damskie/spodnie-dresowe?limit=0",
    "https://crossjeans.pl/ona/spodnie-damskie/chino?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/boyfriend?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/mom-jeans?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/flare?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/wide-leg?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/straight?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/slim?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/skinny?limit=0",
    "https://crossjeans.pl/ona/jeansy-damskie/super-skinny?limit=0",
    "https://crossjeans.pl/on/basic-meski?limit=0",
    "https://crossjeans.pl/on/buty-meskie?limit=0",
    "https://crossjeans.pl/on/spodnie-meskie/spodnie-dresowe?limit=0",
    "https://crossjeans.pl/on/spodnie-meskie/spodnie-chino-meskie?limit=0",
    "https://crossjeans.pl/on/jeansy-meskie/slim?limit=0",
    "https://crossjeans.pl/on/jeansy-meskie/relaxed?limit=0",
    "https://crossjeans.pl/on/jeansy-meskie/regular?limit=0",
    "https://crossjeans.pl/on/odziez-meska/kurtki-meskie?limit=0",
    "https://crossjeans.pl/on/odziez-meska/bluzy-meskie?limit=0",
    "https://crossjeans.pl/on/odziez-meska/swetry-meskie?limit=0",
    "https://crossjeans.pl/on/odziez-meska/t-shirty-meskie?limit=0",
    "https://crossjeans.pl/on/odziez-meska/longsleeve?limit=0",
    "https://crossjeans.pl/on/odziez-meska/kurtki-meskie-jeansowe?limit=0",
    "https://crossjeans.pl/on/odziez-meska/koszule-meskie?limit=0",
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
    if not (path.startswith("/on/") or path.startswith("/ona/")):
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

    # Najpewniejsze miejsce na CrossJeans:
    # tekst między "Ilość" a "+ Więcej"
    full_text = soup.get_text("\n", strip=True)

    if "Ilość" in full_text and "+ Więcej" in full_text:
        after = full_text.split("Ilość", 1)[1]
        between = after.split("+ Więcej", 1)[0]

        lines = [norm_text(x) for x in between.split("\n")]
        lines = [x for x in lines if len(x) >= 20]

        # usuń wersję urwaną z "..."
        lines = [x for x in lines if not x.endswith("...")]

        if lines:
            return max(lines, key=len)

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
