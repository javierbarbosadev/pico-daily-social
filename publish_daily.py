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
        
    print(f"Launching Playwright mobile capture for: {url} (Target Answer: {target_char})")
    os.makedirs("raw_video", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        context = browser.new_context(
            viewport={"width": 430, "height": 932},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            record_video_dir="raw_video/",
            record_video_size={"width": 430, "height": 932}
        )
        page = context.new_page()
        
        # 1. Navigate and load
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 2. Inject mobile layout styling
        page.add_style_tag(content="""
            header, nav, [class*="header"], [class*="navbar"], button:has-text("Check Answer"), [class*="hint"] { 
                display: none !important; 
            }

            body {
                background-color: #F8FAFC !important;
                padding-top: 90px !important;
                padding-left: 16px !important;
                padding-right: 16px !important;
                overflow: hidden !important;
            }

            #pico-reel-hook {
                position: fixed;
                top: 16px;
                left: 16px;
                right: 16px;
                background: #0F172A;
                color: #FFFFFF;
                padding: 14px 18px;
                border-radius: 14px;
                font-size: 16px;
                font-weight: 700;
                text-align: center;
                box-shadow: 0 10px 25px rgba(0,0,0,0.18);
                z-index: 99999;
            }

            #pico-timer-wrapper {
                width: 100%;
                height: 6px;
                background: #334155;
                border-radius: 3px;
                margin-top: 10px;
                overflow: hidden;
            }

            #pico-timer-bar {
                height: 100%;
                background: #10B981;
                width: 100%;
                animation: picoCountdown 3.5s linear forwards;
            }

            @keyframes picoCountdown {
                from { width: 100%; background: #10B981; }
                50%  { background: #F59E0B; }
                to   { width: 0%; background: #EF4444; }
            }

            .pico-highlight-correct {
                background-color: #10B981 !important;
                color: #FFFFFF !important;
                border: 3px solid #059669 !important;
                transform: scale(1.03) !important;
                transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
                box-shadow: 0 0 20px rgba(16, 185, 129, 0.5) !important;
            }
            .pico-highlight-correct * {
                color: #FFFFFF !important;
            }

            #pico-cta-overlay {
                position: fixed;
                bottom: -260px;
                left: 16px;
                right: 16px;
                background: #FFFFFF;
                border-radius: 20px;
                border-top: 5px solid #10B981;
                box-shadow: 0 -15px 40px rgba(0,0,0,0.2);
                padding: 22px 18px;
                text-align: center;
                transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
                z-index: 100000;
            }
            #pico-cta-overlay.active {
                transform: translateY(-275px) !important;
            }
        """)

        # 3. Add DOM overlays and animations
        page.evaluate(f"""() => {{
            const banner = document.createElement('div');
            banner.id = 'pico-reel-hook';
            banner.innerHTML = `
                <div>⏱️ Can your Year 5 child solve this?</div>
                <div id="pico-timer-wrapper"><div id="pico-timer-bar"></div></div>
            `;
            document.body.prepend(banner);

            const cta = document.createElement('div');
            cta.id = 'pico-cta-overlay';
            cta.innerHTML = `
                <div style="font-size: 18px; font-weight: 800; color: #0F172A; margin-bottom: 4px;">PicoLearn 11+ Practice</div>
                <div style="font-size: 13px; color: #475569; margin-bottom: 14px;">Adaptive 11+ prep that builds exam confidence.</div>
                <div style="display: inline-block; background: #10B981; color: #fff; font-size: 13px; font-weight: 700; padding: 10px 20px; border-radius: 10px;">
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

    # 4. Generate ticking countdown and success chime using clean ffmpeg filtergraph
    print("Generating ticking audio and rendering final MP4...")

    filter_complex = (
        # Video scaling and centering on 1080x1920 canvas
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xF8FAFC[v];"
        
        # Audio track 1: Crisp clock ticks every 0.5s from 0s to 3.5s
        "sine=f=1200:d=3.5,"
        "volume=enable='between(mod(t,0.5),0,0.04)':volume=1.0:eval=frame,"
        "volume=enable='not(between(mod(t,0.5),0,0.04))':volume=0.0:eval=frame[clicks];"
        
        # Audio track 2: Success bell chime from 3.5s to 6.5s
        "sine=f=880:d=3.0,"
        "volume='exp(-1.5*(t-0))':eval=frame,"
        "adelay=3500|3500[bell];"
        
        # Mix clicks and chime together
        "[clicks][bell]amix=inputs=2:dropout_transition=0:normalize=0[a]"
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
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        output_mp4
    ]
    subprocess.run(ffmpeg_cmd, check=True)
    print("Reel with audio rendered successfully.")
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
    # Wait 8s for CDN edge warm-up
    time.sleep(8)
    return url

def publish_reel_to_instagram(video_url: str, caption: str):
    base_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}"

    # 1. Create Media Container
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

    # 2. Poll Container Status until Meta transcoding is FINISHED
    print("Polling Meta for Reel transcoding completion...")
    status_url = f"https://graph.facebook.com/v21.0/{container_id}"
    params = {
        "fields": "status_code,status",
        "access_token": ACCESS_TOKEN
    }

    max_attempts = 24  # Poll up to 2 minutes (24 * 5s)
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

    # 3. Publish Live
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

    # Normalise headers for safe column lookup
    headers = [str(h).strip().lower() for h in sheet.row_values(1)]
    status_col = headers.index("status") + 1 if "status" in headers else 6

    for idx, row in enumerate(records, start=2):
        # Normalise dictionary keys to lowercase with underscores
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

            # Update row status to POSTED
            sheet.update_cell(idx, status_col, "POSTED")
            print(f"Row {idx} updated to POSTED.")
            break

if __name__ == "__main__":
    main()
