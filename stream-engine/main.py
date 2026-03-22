import os
import subprocess
import threading
import time
import re
import base64
import urllib.request
import zmq
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Whitelist the specific frontend domain to resolve the CORS preflight issue
CORS(app, resources={r"/*": {"origins": "https://magnificent-nature-production-085b.up.railway.app"}})

# --- ENGINE ASSETS & CONFIG ---
OVERLAY_FILE = "live_overlay.png"
AUDIO_PIPE = "/tmp/live_audio.fifo"
SILENCE_FILE = "fallback_silence.mp3"
ZMQ_PORT = "5555"

dj_state = {
    "active_audio_url": None,
    "streaming": False
}

# 1. GENERATE ENGINE ASSETS & FALLBACKS ON BOOT
def setup_environment():
    if not os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "wb") as f:
            f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
    
    if not os.path.exists(AUDIO_PIPE):
        os.mkfifo(AUDIO_PIPE)

    if not os.path.exists(SILENCE_FILE):
        print("🔊 Generating Fault-Tolerant Audio Fallback...")
        os.system(f"ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t 1 -q:a 9 {SILENCE_FILE} > /dev/null 2>&1")

setup_environment()

# 2. FAULT-TOLERANT BACKGROUND DJ THREAD
def audio_dj_worker():
    while True:
        if dj_state["streaming"]:
            try:
                # Open pipe ONCE.
                with open(AUDIO_PIPE, 'wb') as pipe:
                    while dj_state["streaming"]:
                        current_url = dj_state["active_audio_url"]
                        if current_url:
                            try:
                                req = urllib.request.Request(current_url, headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(req, timeout=5) as response:
                                    while dj_state["active_audio_url"] == current_url and dj_state["streaming"]:
                                        chunk = response.read(8192)
                                        if not chunk: 
                                            break # End of track, break to loop it instantly
                                        pipe.write(chunk)
                            except Exception as e:
                                print(f"🎵 DJ Buffer/URL Error: {e}")
                                with open(SILENCE_FILE, "rb") as f:
                                    pipe.write(f.read())
                                time.sleep(1)
                        else:
                            # No track assigned, pour silence to keep FFmpeg alive
                            with open(SILENCE_FILE, "rb") as f:
                                pipe.write(f.read())
                            time.sleep(1)
            except Exception as e:
                print(f"Pipe Connection Error: {e}")
                time.sleep(1)
        else:
            time.sleep(1)

threading.Thread(target=audio_dj_worker, daemon=True).start()

# 3. ZMQ FADER MESSENGER
def send_zmq_command(target, command):
    try:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
        socket.setsockopt(zmq.RCVTIMEO, 1000) 
        socket.send_string(f"{target} {command}")
        socket.recv() 
        socket.close()
    except Exception as e:
        print(f"ZMQ Fader Error: {e}")

# --- API CONTROL BOARD ---

@app.route('/update_overlay', methods=['POST'])
def update_overlay():
    overlay_base64 = request.json.get('overlay_base64')
    if overlay_base64:
        try:
            img_data = base64.b64decode(overlay_base64.split(',')[-1])
            temp_file = f"{OVERLAY_FILE}.tmp"
            with open(temp_file, 'wb') as f:
                f.write(img_data)
            # Atomic swap ensures FFmpeg never reads a half-written file
            os.replace(temp_file, OVERLAY_FILE) 
            return jsonify({"message": "Overlay atomically updated!"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No image provided"}), 400

@app.route('/update_audio', methods=['POST'])
def update_audio():
    new_url = request.json.get('audio_url')
    dj_state["active_audio_url"] = new_url
    return jsonify({"message": f"DJ switched track to: {new_url}"}), 200

@app.route('/update_volume', methods=['POST'])
def update_volume():
    orig_vol = float(request.json.get('orig_vol', 1.0))
    bg_vol = float(request.json.get('bg_vol', 0.5))
    
    send_zmq_command("volume@vidvol", f"volume {orig_vol}")
    send_zmq_command("volume@bgvol", f"volume {bg_vol}")
    return jsonify({"message": "Volume faded live!"}), 200

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "status": "Online",
        "is_streaming": dj_state["streaming"],
        "active_audio": dj_state["active_audio_url"]
    })

# --- CORE BROADCAST MIXER ---

def run_pro_stream(source, destination, resolution, orig_vol, bg_vol):
    dj_state["streaming"] = True
    
    try:
        if 'x.com' in source or 'twitter.com' in source:
            source = subprocess.check_output(['yt-dlp', '-g', source]).decode('utf-8').strip()
        elif 'youtube.com/live/' in source:
            match = re.search(r'/live/([^?]+)', source)
            if match: source = f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception as e:
        print(f"Link Extraction Error: {e}")
        dj_state["streaming"] = False
        return

    print(f"🚨 CLOUD STUDIO LIVE: Booting IMMORTAL LOOP with Makkah TV={orig_vol}, Quran={bg_vol}")
    
    v_maxrate, v_bufsize = ("2500k", "5000k") 
    streamlink_qual = "720p,720p60,best" 

    proxy_arg = f"--http-proxy \"{os.environ.get('PROXY_URL', '')}\"" if os.environ.get('PROXY_URL', '') else ""
    user_agent = '--http-header "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"'
    
    cookie_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
    cookie_header = ""
    if os.path.exists(cookie_path):
        try:
            with open(cookie_path, 'r') as f:
                cookies = [f"{p.split()[5]}={p.split()[6].strip()}" for p in f if not p.startswith('#') and p.strip() and len(p.split()) >= 7]
            if cookies: cookie_header = '--http-header "Cookie=' + '; '.join(cookies) + '"'
        except: pass

    # 🚀 THE IMMORTAL LOOP: Keeps the stream alive for 6 months!
    while dj_state["streaming"]:
        print("▶️ Starting/Restarting FFmpeg Broadcast Engine...")
        
        # 🚨 THE FIX IS HERE: Added '-re' right after '-y' to force real-time 1x speed!
        ffmpeg_cmd = (
            f"streamlink --loglevel info --stdout {proxy_arg} {user_agent} {cookie_header} \"{source}\" {streamlink_qual} | "
            f"ffmpeg -y -re -fflags +genpts -i pipe:0 "
            f"-i {AUDIO_PIPE} "
            f"-f image2 -loop 1 -framerate 5 -i {OVERLAY_FILE} "
            f"-filter_complex \"[0:v]scale=1280:720[base_vid];"
            f"[base_vid][2:v]overlay=0:0[outv];"
            f"[0:a]volume@vidvol={orig_vol}[orig_a];"
            f"[1:a]volume@bgvol={bg_vol}[bg_a];"
            f"[orig_a][bg_a]amix=inputs=2:duration=first:normalize=0,azmq[outa]\" "
            f"-map \"[outv]\" -map \"[outa]\" "
            f"-c:v libx264 -preset superfast -b:v {v_maxrate} -minrate {v_maxrate} -maxrate {v_maxrate} -bufsize {v_bufsize} "
            f"-r 25 -pix_fmt yuv420p -g 50 -keyint_min 50 -sc_threshold 0 "
            f"-c:a aac -b:a 128k -ar 44100 -flvflags no_duration_filesize -f flv \"{destination}\""
        )

        try:
            subprocess.run(ffmpeg_cmd, shell=True)
            
            if dj_state["streaming"]:
                print("⚠️ Source dropped or FFmpeg crashed. Reconnecting in 5 seconds...")
                time.sleep(5)
                
        except Exception as e:
            print(f"Broadcast Error: {e}")
            time.sleep(5)

    print("⏹️ Broadcast safely terminated by user.")
    try:
        fd = os.open(AUDIO_PIPE, os.O_RDONLY | os.O_NONBLOCK)
        os.close(fd)
    except Exception: 
        pass

@app.route('/start_stream', methods=['POST'])
def start_stream():
    data = request.json
    source_url = data.get('source_url')
    rtmp_url = data.get('rtmp_url')
    resolution = data.get('resolution', '720p')
    
    if not source_url or not rtmp_url:
        return jsonify({"error": "Missing source or RTMP URL"}), 400

    if dj_state["streaming"]:
        return jsonify({"error": "Stream is already running! Use sync endpoints to modify."}), 409

    dj_state["active_audio_url"] = data.get('custom_audio')
    
    orig_vol = float(data.get('orig_vol', 1.0))
    bg_vol = float(data.get('bg_vol', 0.5))

    overlay_base64 = data.get('overlay_base64')
    if overlay_base64:
        try:
            img_data = base64.b64decode(overlay_base64.split(',')[-1])
            temp_file = f"{OVERLAY_FILE}.tmp"
            with open(temp_file, 'wb') as f:
                f.write(img_data)
            os.replace(temp_file, OVERLAY_FILE)
        except Exception as e:
            print(f"Initial Overlay Error: {e}")

    threading.Thread(target=run_pro_stream, args=(source_url, rtmp_url, resolution, orig_vol, bg_vol)).start()
    return jsonify({"message": "Pro Studio Mixer booted successfully"}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
