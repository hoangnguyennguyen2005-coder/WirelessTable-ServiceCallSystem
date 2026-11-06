"""Start built local application (no global installation/Docker required)."""
import argparse
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['simulation', 'hardware'], default=os.getenv('PBL_MODE', 'simulation'))
parser.add_argument('--port', type=int, default=8000)
args = parser.parse_args()
os.chdir(root)
os.environ['PBL_MODE'] = args.mode
sys.path.insert(0, str(root / 'backend'))
import uvicorn  # noqa: E402
print(f'PBL4 {args.mode}: http://127.0.0.1:{args.port} (loopback only)')
uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, proxy_headers=False)
