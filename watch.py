"""11/22 제주→김포 15~20시 출발 직항에 2명 좌석이 나오면 텔레그램으로 알린다 (구글 항공편 기준)."""
import datetime, json, os, re, sys, urllib.parse, urllib.request
from playwright.sync_api import sync_playwright

ORIGIN, DEST, DATE, ADULTS = "CJU", "GMP", "2026-11-22", 2
WINDOW = os.environ.get("WINDOW", "15:00-20:00").split("-")  # 출발 시각 범위(현지 시각)
STATE = "state.json"
URL = "https://www.google.com/travel/flights?" + urllib.parse.urlencode(
    {"q": f"Flights from {ORIGIN} to {DEST} on {DATE} one way {ADULTS} adults", "hl": "en", "gl": "kr", "curr": "KRW"})
# 예: "From 266000 South Korean won. Nonstop flight with Jin Air. Leaves Jeju International Airport at 1:50 PM on ..."
ROW = re.compile(r"^From ([\d,]+) South Korean won\. Nonstop flight with (.+?)\. Leaves .+? at (\d{1,2}:\d{2} [AP]M) on")


def fetch():
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("CHANNEL") or None)
        for _ in range(3):  # 가끔 목록이 안 뜨는 때가 있어 다시 시도
            pg = b.new_page(locale="en-US")
            try:
                pg.goto(URL, timeout=60000)
                pg.wait_for_selector("li [aria-label*=' Leaves ']", timeout=45000)
            except Exception:
                pg.close()
                continue
            pg.wait_for_timeout(3000)  # 목록이 다 채워질 때까지
            more = pg.get_by_role("button", name="more flights")
            if more.count():
                more.first.click()
                pg.wait_for_timeout(3000)
            break
        labels = pg.locator("li [aria-label]").evaluate_all("els => els.map(e => e.getAttribute('aria-label'))") if not pg.is_closed() else []
        b.close()
    if not any(" Leaves " in l for l in labels):
        sys.exit("항공편 목록을 못 읽음 (구글이 막았거나 화면 구조가 바뀜)")  # 실패로 끝나 GitHub가 메일을 보냄
    found = {}
    for l in labels:
        m = ROW.match(l)
        if m:
            t = datetime.datetime.strptime(m[3], "%I:%M %p").strftime("%H:%M")
            if WINDOW[0] <= t <= WINDOW[1]:
                found[f"{t} {m[2]}"] = int(m[1].replace(",", ""))
    return found


def notify(text):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[DRY RUN]", text)
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)


def main():
    if datetime.date.today().isoformat() > DATE:
        return print("날짜 지남, 종료")
    found = fetch()
    print("범위 안 좌석:", found or "없음")
    old = set(json.load(open(STATE)) if os.path.exists(STATE) else [])
    new = sorted(k for k in found if k not in old)
    if new:
        lines = [f"- {k}  {found[k]:,}원({ADULTS}명)" for k in new]
        notify(f"✈ {DATE[5:]} 제주→김포 {WINDOW[0]}~{WINDOW[1]} 좌석 나옴\n" + "\n".join(lines) + f"\n\n{URL}")
    json.dump(sorted(found), open(STATE, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
