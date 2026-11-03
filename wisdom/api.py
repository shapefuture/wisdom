"""Loopback HTTP adapter with explicit host, origin, content and CSRF boundaries."""
from __future__ import annotations
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit,parse_qs,unquote
from . import __version__
from .access import allowed,references
from .errors import FoundryError,ValidationError,NotFound,PermissionDenied
from .exports import export_bundle,markdown,argdown

WEB=Path(__file__).parent/"web"
MAX_BODY=2_000_000

class FoundryServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,address,app):
        self.app=app
        self.csrf_token=secrets.token_urlsafe(32)
        super().__init__(address,Handler)
        port=self.server_address[1]
        self.allowed_hosts={f"127.0.0.1:{port}",f"localhost:{port}",f"[::1]:{port}"}

class Handler(BaseHTTPRequestHandler):
    server_version="WisdomFoundry/"+__version__
    protocol_version="HTTP/1.1"
    def log_message(self,format,*args):
        # Keep request bodies, queries, source text and credentials out of default logs.
        return
    @property
    def app(self):return self.server.app

    def _send(self,status,data,content_type="application/json; charset=utf-8",filename=None):
        if isinstance(data,(dict,list)):
            body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        elif isinstance(data,str):body=data.encode()
        else:body=data
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Cross-Origin-Resource-Policy","same-origin")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header("Content-Disposition",'attachment; filename="'+filename+'"')
        self.end_headers()
        self.wfile.write(body)

    def _boundary(self,mutation=False):
        if self.headers.get("Host") not in self.server.allowed_hosts:
            raise PermissionDenied("Unrecognized Host header.")
        origin=self.headers.get("Origin")
        expected="http://"+self.headers.get("Host","")
        if origin and origin!=expected:raise PermissionDenied("Cross-origin access is disabled.")
        if self.headers.get("Sec-Fetch-Site")=="cross-site":raise PermissionDenied("Cross-site access is disabled.")
        if mutation:
            if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
                raise ValidationError("Mutations require application/json.")
            token=self.headers.get("X-CSRF-Token","")
            if not secrets.compare_digest(token,self.server.csrf_token):
                raise PermissionDenied("A local session CSRF token is required.")

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValidationError("Chunked request bodies are not supported.")
        try:length=int(self.headers.get("Content-Length","0"))
        except ValueError:raise ValidationError("Invalid Content-Length.") from None
        if length<0 or length>MAX_BODY:raise ValidationError("Request body exceeds 2 MB.")
        try:
            value=json.loads(self.rfile.read(length),parse_constant=lambda x:(_ for _ in ()).throw(ValueError()))
        except (ValueError,UnicodeDecodeError):
            raise ValidationError("Request body must contain valid finite JSON.") from None
        if not isinstance(value,dict):raise ValidationError("JSON body must be an object.")
        return value

    def _visible(self,record):
        if allowed(self.app.store,record):return record
        if record["kind"]=="source":
            d=record["data"]
            return {**record,"data":{k:v for k,v in d.items() if k not in {"text","original_text"}},
                    "restricted":True}
        raise NotFound("Record unavailable under current source permissions.")

    def _eligible_payload(self,payload):
        def scan(value):
            if isinstance(value,dict):
                for rid in references(value):
                    rec=self.app.store.get(rid)
                    if not allowed(self.app.store,rec):
                        raise PermissionDenied("A referenced source is restricted, expired, or unavailable.")
                for child in value.values():scan(child)
            elif isinstance(value,list):
                for child in value:scan(child)
        scan(payload)

    def do_GET(self):
        try:
            self._boundary()
            split=urlsplit(self.path); path=unquote(split.path)
            query={k:v[-1] for k,v in parse_qs(split.query).items()}
            if path=="/api/session":
                return self._send(200,{"csrf_token":self.server.csrf_token,"mode":"local_single_user"})
            if path=="/api/dashboard":
                recs=self.app.store.list()
                counts=Counter(r["kind"] for r in recs if r["kind"]=="source" or allowed(self.app.store,r))
                return self._send(200,{"counts":dict(counts),"provider":self.app.provider.name if self.app.provider else "offline (exact-source drafts)",
                    "mode":"advisory_only","external_actions_enabled":False,
                    "review_debt":sum(r["kind"]=="claim" and r["data"].get("review_status")=="unreviewed" for r in recs),
                    "ledger":self.app.store.verify_ledger(),"version":__version__,"empirical_gates":"pending independent evaluation"})
            if path=="/api/records":
                records=[]
                for r in self.app.store.list(query.get("kind")):
                    try:records.append(self._visible(r))
                    except NotFound:pass
                return self._send(200,{"records":records})
            if path.startswith("/api/records/"):
                rid=path.removeprefix("/api/records/")
                # Check current permissions before exposing an older revision.
                self._visible(self.app.store.get(rid))
                return self._send(200,self._visible(self.app.store.get(rid,int(query["version"]) if "version" in query else None)))
            if path.startswith("/api/history/"):
                rid=path.removeprefix("/api/history/")
                self._visible(self.app.store.get(rid))
                return self._send(200,{"records":[self._visible(r) for r in self.app.store.history(rid)]})
            if path.startswith("/api/sources/") and path.endswith("/coverage"):
                rid=path.split("/")[-2]; self._visible(self.app.store.get(rid))
                return self._send(200,self.app.ingest.coverage(rid))
            if path.startswith("/api/spans/") and path.endswith("/verify"):
                rid=path.split("/")[-2]
                self._visible(self.app.store.get(rid))
                return self._send(200,self.app.evidence.verify_span(rid))
            if path=="/api/events":return self._send(200,{"events":self.app.store.events()})
            if path=="/api/audit":return self._send(200,self.app.watchdog.audit())
            if path=="/api/search":
                return self._send(200,{"records":self.app.retrieval.search(query.get("q",""),query.get("lens","fusion"),int(query.get("limit","20")))})
            if path.startswith("/api/lineage/"):
                return self._send(200,self.app.retrieval.lineage(path.removeprefix("/api/lineage/")))
            if path=="/api/export":
                bundle=export_bundle(self.app.store);fmt=query.get("format","json")
                if fmt=="json":return self._send(200,bundle,filename="wisdom-export.json")
                if fmt=="markdown":return self._send(200,markdown(bundle),"text/markdown; charset=utf-8","wisdom-export.md")
                if fmt=="argdown":return self._send(200,argdown(bundle),"text/plain; charset=utf-8","wisdom-export.argdown")
                raise ValidationError("Unknown export format.")
            static={"/":WEB/"index.html","/index.html":WEB/"index.html",
                    "/wisdom/web/index.html":WEB/"index.html","/wisdom/web/app.js":WEB/"app.js",
                    "/wisdom/web/style.css":WEB/"style.css","/app.js":WEB/"app.js","/style.css":WEB/"style.css"}
            if path in static:
                content_type={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}[static[path].suffix]
                return self._send(200,static[path].read_bytes(),content_type)
            raise NotFound("Route not found.")
        except FoundryError as exc:self._send(exc.status,{"error":str(exc),"code":type(exc).__name__})
        except (ValueError,TypeError,KeyError) as exc:self._send(400,{"error":"Invalid request parameter.","code":"ValidationError"})
        except Exception:self._send(500,{"error":"Internal error; inspect local validation and audit records.","code":"InternalError"})

    def do_POST(self):
        try:
            self._boundary(mutation=True)
            payload=self._body()
            path=unquote(urlsplit(self.path).path)
            self._eligible_payload(payload)
            result=self._mutate(path,payload)
            self._send(200,result)
        except FoundryError as exc:
            self.close_connection=True
            self._send(exc.status,{"error":str(exc),"code":type(exc).__name__})
        except (ValueError,TypeError,KeyError):
            self.close_connection=True
            self._send(400,{"error":"Invalid request parameter.","code":"ValidationError"})
        except Exception:
            self.close_connection=True
            self._send(500,{"error":"Internal error; inspect local validation and audit records.","code":"InternalError"})

    def _mutate(self,path,p):
        app=self.app
        direct={"/api/sources":app.ingest.ingest,"/api/theories":app.theory.build,"/api/mechanisms":app.theory.mechanism,
                "/api/problems":app.invention.problem,"/api/decisions":app.decisions.create,"/api/voi":app.decisions.voi,
                "/api/predictions":app.lab.predict,"/api/experiments":app.lab.experiment,"/api/outcomes":app.lab.observe,
                "/api/skills":app.lab.skill,"/api/triggers":app.memory.trigger,"/api/trace":app.memory.trace,
                "/api/goals":app.memory.goal,"/api/context":app.retrieval.compile,"/api/route":app.workflows.route}
        direct['/api/annotations']=app.annotations.record
        if path in direct:return direct[path](p)
        parts=path.strip("/").split("/")
        if len(parts)==4 and parts[0]=="api":
            kind,rid,action=parts[1:]
            self._visible(app.store.get(rid))
            functions={
                ("sources","analyze"):lambda:app.evidence.analyze(rid),
                ("sources","delete"):lambda:self._delete(rid,p),
                ("claims","review"):lambda:app.evidence.review(rid,p),
                ("problems","forge"):lambda:app.invention.forge(rid,p),
                ("ideas","red-team"):lambda:app.invention.red_team(rid),
                ("decisions","approve"):lambda:app.decisions.approve(rid,p),
                ("skills","promote"):lambda:app.lab.promote(rid,p),
                ("jobs","retry"):lambda:app.workflows.retry(rid),
                ("mechanisms","discover"):lambda:app.invention.discover(rid,p)}
            if (kind,action) in functions:return functions[(kind,action)]()
        if path.startswith("/api/learning/"):return app.lab.learn(path.removeprefix("/api/learning/"))
        if path=="/api/triggers/evaluate":return app.memory.evaluate(p.get("signals",{}),p.get("budget",3))
        if path=="/api/jobs":return app.workflows.run(p.get("operation"),p.get("payload",{}),p.get("idempotency_key"))
        if path=="/api/assess":return app.governor.assess(p["record_id"],p.get("purpose","research"),p.get("stakes","low"))
        raise NotFound("Route not found.")

    def _delete(self,rid,p):
        if p.get("confirm") is not True:raise PermissionDenied("Explicit confirmation is required to delete this source and its derivatives.")
        return self.app.store.purge_source(rid,p.get("reason","User-requested deletion"))

