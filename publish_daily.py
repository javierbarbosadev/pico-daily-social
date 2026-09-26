import os
import json
import time
import subprocess
import requests
import cloudinary
import cloudinary.uploader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# 1. Environment Configurations
GCP_KEY = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
IG_USER_ID = os.getenv("IG_USER_ID")
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

def record_reel_video(url: str, correct_letter: str, output_mp4: str = "daily_reel.mp4") -> str:
    target_char = str(correct_letter).strip().upper()
    if target_char not in ["A", "B", "C", "D"]:
        target_char = "B"
        
    print(f"Launching Playwright 9:16 capture for: {url} (Target Answer: {target_char})")
    os.makedirs("raw_video", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(
            viewport={"width": 540, "height": 960},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            record_video_dir="raw_video/",
            record_video_size={"width": 540, "height": 960}
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 1. Clean out unwanted header, nav, topic bars, and action buttons
        page.evaluate("""() => {
            // Remove navigation and headers
            document.querySelectorAll('header, nav').forEach(el => el.remove());

            // Remove hint/check buttons
            document.querySelectorAll('button, a').forEach(btn => {
                const txt = (btn.innerText || '').trim().toLowerCase();
                if (txt.includes('hint') || txt.includes('check answer')) {
                    btn.remove();
                }
            });

            // Remove Topic / Difficulty meta bars
            document.querySelectorAll('div, p, span').forEach(el => {
                const txt = (el.innerText || '').trim().toUpperCase();
                if (txt.includes('TOPIC:') || txt.includes('DIFFICULTY')) {
                    el.remove();
                }
            });
        }""")

        # 2. Inject styles: reset parent margins to 0 auto and remove left gutters
        page.add_style_tag(content="""
            html, body {
                width: 540px !important;
                height: 960px !important;
                background-color: #FAF8F5 !important;
                margin: 0 !important;
                padding: 44px 20px 20px 20px !important;
                box-sizing: border-box !important;
                overflow: hidden !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                display: flex !important;
                flex-direction: column !important;
                justify-content: flex-start !important;
                align-items: center !important;
            }

            /* Strip out unwanted elements */
            header, nav, [class*="hint"], [class*="topic"], [class*="difficulty"], [class*="progress"] {
                display: none !important;
            }

            /* Neutralise any parent width constraints or asymmetrical left margins */
            #root, #__next, main, [class*="container"], [class*="max-w"], body > div:not(#pico-reel-hook):not(#pico-solve-prompt):not(#pico-cta-overlay) {
                width: 100% !important;
                max-width: 100% !important;
                margin-left: 0 !important;
                margin-right: 0 !important;
                padding-left: 0 !important;
                padding-right: 0 !important;
                box-sizing: border-box !important;
                display: flex !important;
                flex-direction: column !important;
                align-items: stretch !important;
            }

            /* 1. Hook Banner */
            #pico-reel-hook {
                width: 100% !important;
                background: #0F172A !important;
                color: #FFFFFF !important;
                padding: 14px 16px !important;
                border-radius: 16px !important;
                font-size: 17px !important;
                font-weight: 800 !important;
                text-align: center !important;
                box-shadow: 0 10px 25px rgba(0,0,0,0.18) !important;
                box-sizing: border-box !important;
                margin-bottom: 20px !important;
                flex-shrink: 0 !important;
                z-index: 100 !important;
            }

            #pico-timer-wrapper {
                width: 100% !important;
                height: 6px !important;
                background: #334155 !important;
                border-radius: 3px !important;
                margin-top: 10px !important;
                overflow: hidden !important;
            }

            #pico-timer-bar {
                height: 100% !important;
                background: #10B981 !important;
                width: 100% !important;
                animation: picoCountdown 3.5s linear forwards !important;
            }

            @keyframes picoCountdown {
                from { width: 100%; background: #10B981; }
                50%  { background: #F59E0B; }
                to   { width: 0%; background: #EF4444; }
            }

            /* Question Card styling */
            h1, h2, h3, [class*="question-text"], p {
                font-size: 20px !important;
                line-height: 1.35 !important;
                font-weight: 800 !important;
                color: #0F172A !important;
                margin: 0 0 16px 0 !important;
                text-align: center !important;
            }

            /* Single-column answers */
            [class*="grid"], [class*="options-container"] {
                display: flex !important;
                flex-direction: column !important;
                gap: 10px !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }

            button, [class*="option-card"], [class*="choice"] {
                width: 100% !important;
                min-height: 52px !important;
                padding: 8px 16px !important;
                font-size: 18px !important;
                font-weight: 700 !important;
                border-radius: 12px !important;
                border: 2px solid #E2E8F0 !important;
                background: #FFFFFF !important;
                box-shadow: 0 2px 6px rgba(0,0,0,0.04) !important;
                display: flex !important;
                align-items: center !important;
                box-sizing: border-box !important;
            }

            /* Highlight correct answer */
            .pico-highlight-correct {
                background-color: #10B981 !important;
                color: #FFFFFF !important;
                border-color: #059669 !important;
                transform: scale(1.02) !important;
                transition: all 0.3s ease-out !important;
                box-shadow: 0 0 20px rgba(16, 185, 129, 0.45) !important;
            }
            .pico-highlight-correct * {
                color: #FFFFFF !important;
            }

            /* 3. Hold prompt pill: shifted to bottom 165px to clear the username line cleanly */
            #pico-solve-prompt {
                position: fixed !important;
                bottom: 165px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                background: #0F172A !important;
                color: #FFFFFF !important;
                padding: 10px 22px !important;
                border-radius: 9999px !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                text-align: center !important;
                white-space: nowrap !important;
                box-shadow: 0 8px 20px rgba(0,0,0,0.25) !important;
                z-index: 9999 !important;
            }

            /* 4. Sliding CTA overlay */
            #pico-cta-overlay {
                position: fixed !important;
                bottom: -320px !important;
                left: 20px !important;
                right: 20px !important;
                background: #FFFFFF !important;
                border-radius: 24px !important;
                border-top: 6px solid #10B981 !important;
                box-shadow: 0 -15px 45px rgba(0,0,0,0.25) !important;
                padding: 24px !important;
                text-align: center !important;
                transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1) !important;
                z-index: 1000000 !important;
            }
            #pico-cta-overlay.active {
                transform: translateY(-460px) !important;
            }
        """)

        # 3. Inject elements
        page.evaluate(f"""() => {{
            const banner = document.createElement('div');
            banner.id = 'pico-reel-hook';
            banner.innerHTML = `
                <div>⏱️ Can your Year 5 child solve this?</div>
                <div id="pico-timer-wrapper"><div id="pico-timer-bar"></div></div>
            `;
            document.body.prepend(banner);

            const prompt = document.createElement('div');
            prompt.id = 'pico-solve-prompt';
            prompt.innerText = '👆 Hold screen to pause • Answer below 👇';
            document.body.appendChild(prompt);

            const cta = document.createElement('div');
            cta.id = 'pico-cta-overlay';
            cta.innerHTML = `
                <div style="font-size: 20px; font-weight: 800; color: #0F172A; margin-bottom: 4px;">PicoLearn 11+ Practice</div>
                <div style="font-size: 14px; color: #475569; margin-bottom: 14px;">Adaptive 11+ prep that builds exam confidence.</div>
                <div style="display: inline-block; background: #10B981; color: #fff; font-size: 14px; font-weight: 700; padding: 10px 22px; border-radius: 12px;">
                    Try free at picolearn.co.uk
                </div>
            `;
            document.body.appendChild(cta);

            setTimeout(() => {{
                const target = "{target_char}";
                const all = Array.from(document.querySelectorAll('div, button, li, label'));
                const match = all.find(el => {{
                    const t = (el.innerText || '').trim();
                    return (t === target || t.startsWith(target + ' ') || t.startsWith(target + '\\n')) &&
                           el.children.length <= 3 && el.offsetHeight > 25 && el.offsetHeight < 120;
                }});
                if (match) {{
                    const card = match.closest('button') || match.closest('[class*="option"]') || match.parentElement;
                    card.classList.add('pico-highlight-correct');
                }}
            }}, 3500);

            setTimeout(() => {{
                cta.classList.add('active');
            }}, 5500);
        }}""")

        page.wait_for_timeout(7000)

        video_path = page.video.path()
        context.close()
        browser.close()

    print(f"Raw capture saved: {video_path}")

    # 4. ffmpeg upscale to 1080x1920
    audio_track = "assets/audio.mp3"
    print("Encoding final full-bleed 1080x1920 MP4...")

    if os.path.exists(audio_track):
        filter_complex = (
            "[0:v]scale=1080:1920[v];"
            "[1:a]aloop=loop=-1:size=2e+09,atrim=0:7,volume=0.4[music];"
            "sine=f=880:d=2.5,volume='exp(-1.5*t)':eval=frame,adelay=3500|3500[bell];"
            "[music][bell]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-sseof", "-7.0",
            "-i", video_path,
            "-i", audio_track,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.0",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k",
            "-t", "7.0",
            output_mp4
        ]
    else:
        filter_complex = (
            "[0:v]scale=1080:1920[v];"
            "sine=f=880:d=2.5,volume='exp(-1.5*t)':eval=frame,adelay=3500|3500[a]"
        )
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-sseof", "-7.0",
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.0",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k",
            "-t", "7.0",
            output_mp4
        ]

    subprocess.run(ffmpeg_cmd, check=True)
    print("Reel ready for Instagram.")
    return output_mp4


def upload_video_to_cdn(video_path: str) -> str:
    print("Uploading MP4 Reel to Cloudinary...")
    res = cloudinary.uploader.upload(
        video_path,
        folder="picolearn_reels",
        resource_type="video",
        overwrite=True,
        invalidate=True
    )
    url = res["secure_url"]
    print(f"Video hosted: {url}")
    time.sleep(8)
    return url


def publish_reel_to_instagram(video_url: str, caption: str):
    base_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}"

    print("Creating Reel media container on Instagram...")
    container_payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(f"{base_url}/media", data=container_payload).json()
    if "id" not in res:
        raise RuntimeError(f"Reel container creation failed: {res}")

    container_id = res["id"]
    print(f"Reel Container created. ID: {container_id}")

    print("Polling Meta for Reel transcoding completion...")
    status_url = f"https://graph.facebook.com/v21.0/{container_id}"
    params = {
        "fields": "status_code,status",
        "access_token": ACCESS_TOKEN
    }

    max_attempts = 24
    is_ready = False

    for attempt in range(1, max_attempts + 1):
        time.sleep(5)
        status_res = requests.get(status_url, params=params).json()
        status_code = status_res.get("status_code")
        print(f"[{attempt}/{max_attempts}] Meta Reel Status: {status_code}")

        if status_code == "FINISHED":
            is_ready = True
            break
        elif status_code == "ERROR":
            raise RuntimeError(f"Meta failed to process Reel video: {status_res}")
        elif status_code == "EXPIRED":
            raise RuntimeError(f"Meta Reel container expired before publishing: {status_res}")

    if not is_ready:
        raise TimeoutError("Meta timed out processing the Reel video after 2 minutes.")

    print("Publishing Reel to feed...")
    publish_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    pub_res = requests.post(f"{base_url}/media_publish", data=publish_payload).json()

    if "id" not in pub_res:
        raise RuntimeError(f"Publish failed: {pub_res}")

    print(f"Success! Reel live on @pico11plus. Live ID: {pub_res['id']}")


def main():
    if not GCP_KEY:
        raise ValueError("Missing GCP_SERVICE_ACCOUNT_KEY secret.")

    creds_dict = json.loads(GCP_KEY)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open("PicoLearn Social Queue").sheet1
    records = sheet.get_all_records()

    if not records:
        print("No records found in Google Sheet.")
        return

    headers = [str(h).strip().lower() for h in sheet.row_values(1)]
    status_col = headers.index("status") + 1 if "status" in headers else 6

    for idx, row in enumerate(records, start=2):
        clean_row = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}

        if str(clean_row.get("status", "")).strip().upper() == "READY":
            url = (
                clean_row.get("target_url")
                or clean_row.get("preview_url")
                or clean_row.get("url")
                or clean_row.get("question_url")
                or clean_row.get("link")
            )

            if not url or not str(url).strip().startswith("http"):
                print(f"Skipping row {idx}: URL is missing or invalid. Columns found: {list(clean_row.keys())}")
                continue

            caption = (
                clean_row.get("caption")
                or "Can your child solve this daily 11+ challenge? Drop your answer below! 👇 #11plus #11plusprep #grammarschool"
            )

            correct_answer = (
                clean_row.get("answer")
                or clean_row.get("correct_answer")
                or clean_row.get("correct_option")
                or "B"
            )

            print(f"Processing Reel row {idx} with URL: {url} (Answer: {correct_answer})")
            mp4_file = record_reel_video(str(url).strip(), correct_letter=str(correct_answer).strip())
            video_cdn_url = upload_video_to_cdn(mp4_file)
            publish_reel_to_instagram(video_cdn_url, caption)

            sheet.update_cell(idx, status_col, "POSTED")
            print(f"Row {idx} updated to POSTED.")
            break


if __name__ == "__main__":
    main()
