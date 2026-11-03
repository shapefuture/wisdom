"""Command-line research, intake, audit, export and local workbench."""
import argparse
import json
from pathlib import Path
import sys
from .composition import Application
from .api import FoundryServer
from .exports import export_bundle,markdown,argdown
from .errors import FoundryError

def main(argv=None):
    parser=argparse.ArgumentParser(prog="wisdom",description="Wisdom Foundry local research workbench")
    parser.add_argument("--db",default=".wisdom/foundry.db",help="Canonical SQLite database")
    parser.add_argument("--raw-dir",default=".wisdom/raw",help="Content-addressed originals")
    sub=parser.add_subparsers(dest="command",required=True)
    serve=sub.add_parser("serve");serve.add_argument("--port",type=int,default=8787)
    ingest=sub.add_parser("ingest");ingest.add_argument("file");ingest.add_argument("--title");ingest.add_argument("--uri",default="")
    ingest.add_argument("--format",choices=["text","srt","vtt"]);ingest.add_argument("--family",default="")
    ingest.add_argument("--license",default="user-provided");ingest.add_argument("--private",action="store_true")
    ingest.add_argument("--allow-export",action="store_true");ingest.add_argument("--allow-model",action="store_true")
    ingest.add_argument("--rights-confirmed",action="store_true",required=True)
    analyze=sub.add_parser("analyze");analyze.add_argument("source_id")
    search=sub.add_parser("search");search.add_argument("query");search.add_argument("--lens",default="fusion")
    context=sub.add_parser("context");context.add_argument("question");context.add_argument("--budget",type=int,default=2000)
    get=sub.add_parser("get");get.add_argument("record_id");get.add_argument("--version",type=int)
    export=sub.add_parser("export");export.add_argument("--format",choices=["json","markdown","argdown"],default="json");export.add_argument("--out")
    sub.add_parser("audit");sub.add_parser("status")
    delete=sub.add_parser("delete-source");delete.add_argument("source_id");delete.add_argument("--reason",required=True);delete.add_argument("--confirm",action="store_true",required=True)
    call=sub.add_parser("call",help="Run a typed local operation with a JSON object file")
    call.add_argument("operation",choices=["annotation","theory","mechanism","problem","forge","decision","approve","prediction","experiment","outcome","learn","skill","promote","goal","trace","trigger","evaluate","route"])
    call.add_argument("json_file")
    args=parser.parse_args(argv)
    app=None
    try:
        app=Application(args.db,raw_dir=args.raw_dir,configured_provider=True)
        if args.command=="serve":
            server=FoundryServer(("127.0.0.1",args.port),app)
            print(f"Wisdom Foundry: http://127.0.0.1:{server.server_address[1]} — local single-user advisory workspace",flush=True)
            try:server.serve_forever()
            except KeyboardInterrupt:pass
            finally:server.server_close()
            return 0
        if args.command=="ingest":
            file=Path(args.file);fmt=args.format or (file.suffix[1:] if file.suffix.lower() in {".srt",".vtt"} else "text")
            result=app.ingest.ingest({"title":args.title or file.stem,"uri":args.uri,"text":file.read_text(encoding="utf-8-sig"),"format":fmt,
                  "source_family":args.family,"rights":{"allowed":True,"license":args.license,"private":args.private,
                  "allow_export":args.allow_export,"allow_model":args.allow_model}})
        elif args.command=="analyze":result=app.evidence.analyze(args.source_id)
        elif args.command=="search":result=app.retrieval.search(args.query,args.lens)
        elif args.command=="context":result=app.retrieval.compile({"question":args.question,"budget":args.budget})
        elif args.command=="get":result=app.store.get(args.record_id,args.version)
        elif args.command=="audit":result=app.watchdog.audit()
        elif args.command=="status":
            from collections import Counter
            result={"counts":dict(Counter(r["kind"] for r in app.store.list())),"provider":app.provider.name if app.provider else "offline",
                    "ledger":app.store.verify_ledger(),"external_actions_enabled":False}
        elif args.command=="delete-source":result=app.store.purge_source(args.source_id,args.reason)
        elif args.command=="call":
            payload=json.loads(Path(args.json_file).read_text())
            if not isinstance(payload,dict):raise ValueError("Operation JSON must be an object.")
            ops={"annotation":app.annotations.record,"theory":app.theory.build,"mechanism":app.theory.mechanism,"problem":app.invention.problem,
                 "forge":lambda p:app.invention.forge(p["problem_id"],p),"decision":app.decisions.create,
                 "approve":lambda p:app.decisions.approve(p["decision_id"],p),"prediction":app.lab.predict,
                 "experiment":app.lab.experiment,"outcome":app.lab.observe,"learn":lambda p:app.lab.learn(p["prediction_id"]),
                 "skill":app.lab.skill,"promote":lambda p:app.lab.promote(p["skill_id"],p),"goal":app.memory.goal,
                 "trace":app.memory.trace,"trigger":app.memory.trigger,"evaluate":lambda p:app.memory.evaluate(p["signals"],p.get("budget",3)),
                 "route":app.workflows.route}
            result=ops[args.operation](payload)
        else:
            bundle=export_bundle(app.store)
            text=json.dumps(bundle,ensure_ascii=False,indent=2) if args.format=="json" else markdown(bundle) if args.format=="markdown" else argdown(bundle)
            if args.out:
                Path(args.out).write_text(text,encoding="utf-8")
                print(args.out)
            else:print(text)
            return 0
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (FoundryError,OSError,ValueError,KeyError) as exc:
        print(f"Error: {exc}",file=sys.stderr);return 1
    finally:
        if app is not None:app.close()

if __name__=="__main__":raise SystemExit(main())

