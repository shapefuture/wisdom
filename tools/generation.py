#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from wisdom.generation import manifest
p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args()
result=manifest(ROOT)
if args.write:
    out=ROOT/"generations"/(result["generation_id"].split(":")[1]+".json")
    out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,indent=2)+"\n")
    print(out)
else:print(json.dumps(result,indent=2))

