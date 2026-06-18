#!/bin/bash
# The visual feedback loop, one command: restart the (template) server with current code, record a
# lesson video WITH CAPTIONS, and tile frames across all scenes into one contact sheet to observe.
#   bash tools/observe.sh "how a volcano erupts" story  ->  build/sheet.jpg
set -e
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH" STORY_PROVIDER=template
TOPIC="${1:-how a volcano erupts}"
MODE="${2:-story}"
mkdir -p build
lsof -ti tcp:8001 | xargs kill -9 2>/dev/null || true
sleep 2
nohup uv run uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8001 >/tmp/srv8001.log 2>&1 &
for i in $(seq 1 25); do
  curl -s --max-time 2 http://127.0.0.1:8001/api/engine/status >/dev/null 2>&1 && break
  sleep 1
done
NODE_PATH=/tmp/pptr/node_modules node tools/record_lesson.js \
  --url http://127.0.0.1:8001 --topic "$TOPIC" --mode "$MODE" --style cartoon \
  --out build/lesson.mp4 --max 90000 2>&1 | tail -1
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 build/lesson.mp4)
STEP=$(awk "BEGIN{s=($DUR-0.6)/9; print (s<0.4?0.4:s)}")
ffmpeg -y -v error -i build/lesson.mp4 \
  -vf "fps=1/${STEP},scale=400:-1,tile=3x3:margin=6:padding=6:color=0x222222" \
  -frames:v 1 build/sheet.jpg
echo "OK: build/sheet.jpg  (video ${DUR}s)"
