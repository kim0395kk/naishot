# app.py — AI 행정관 Pro (완세트)
# LAWGO(법제처 DRF) + NAVER(뉴스/웹/전문 블로그·카페) + Gemini→Groq + Supabase
# ✅ (1) API 호출 수 / 토큰 사용량 표시(가능한 범위)
# ✅ (2) NAVER 뉴스/웹/블로그/카페: "상황 관련성" 필터 + 블로그/카페 "전문성" 필터
# ✅ (3) LAWGO: 대표+연관 법령 3개 + JO(6자리) + 원문 클릭(HTML 링크)
# ✅ (4) 검색 결과 "틀 밖 튐" 방지: 구조화 파싱 + 카드 렌더
# ✅ (5) 옵션: LLM 정밀 리랭킹 토글(ON/OFF) (비용↑ 정확도↑)

import streamlit as st
import json
import re
import time
from datetime import datetime, timedelta
from html import escape

# ---------------------------
# Optional deps (안죽게)
# ---------------------------
try:
    import requests
except Exception:
    requests = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from supabase import create_client
except Exception:
    create_client = None


# =========================================================
# 1) Page & Style
# =========================================================
st.set_page_config(layout="wide", page_title="AI 행정관 Pro", page_icon="🏛️")

st.markdown(
    """
<style>
.stApp { background-color: #f3f4f6; }

.paper-sheet {
  background-color: white;
  width: 100%;
  max-width: 210mm;
  min-height: 297mm;
  padding: 25mm;
  margin: auto;
  box-shadow: 0 10px 30px rgba(0,0,0,0.1);
  font-family: 'Batang', serif;
  color: #111;
  line-height: 1.6;
  position: relative;
}

.doc-header { text-align: center; font-size: 22pt; font-weight: 900; margin-bottom: 30px; letter-spacing: 2px; }
.doc-info { display: flex; justify-content: space-between; font-size: 11pt; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; gap: 10px; flex-wrap: wrap;}
.doc-body { font-size: 12pt; text-align: justify; white-space: pre-line; }
.doc-footer { text-align: center; font-size: 20pt; font-weight: bold; margin-top: 80px; letter-spacing: 5px; }
.stamp { position: absolute; bottom: 85px; right: 80px; border: 3px solid #cc0000; color: #cc0000; padding: 5px 10px; font-size: 14pt; font-weight: bold; transform: rotate(-15deg); opacity: 0.8; border-radius: 5px; }

.agent-log { font-family: 'Consolas', monospace; font-size: 0.85rem; padding: 6px 12px; border-radius: 6px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.log-legal { background-color: #eff6ff; color: #1e40af; border-left: 4px solid #3b82f6; }
.log-search { background-color: #fff7ed; color: #c2410c; border-left: 4px solid #f97316; }
.log-strat { background-color: #f5f3ff; color: #6d28d9; border-left: 4px solid #8b5cf6; }
.log-calc { background-color: #f0fdf4; color: #166534; border-left: 4px solid #22c55e; }
.log-draft { background-color: #fef2f2; color: #991b1b; border-left: 4px solid #ef4444; }
.log-sys { background-color: #f3f4f6; color: #4b5563; border-left: 4px solid #9ca3af; }

.api-box { background: #ffffff; border: 1px solid #e5e7eb; padding: 14px; border-radius: 10px; }
.api-pill { display:inline-block; padding:4px 10px; border-radius:999px; font-size: 12px; margin-right:6px; margin-bottom:6px; border:1px solid #e5e7eb; background:#f9fafb; }
.api-ok { border-color:#bbf7d0; background:#f0fdf4; }
.api-bad { border-color:#fecaca; background:#fef2f2; }
.small-muted { color:#6b7280; font-size:12px; }

.item-card { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:12px 14px; margin-bottom:10px; }
.item-title { font-weight:700; }
.item-meta { color:#6b7280; font-size:12px; margin-top:4px; line-height:1.3; }
.item-desc { margin-top:8px; white-space:pre-line; }
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# 2) Helpers
# =========================================================
def mask_pii(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\b\d{2,3}-\d{3,4}-\d{4}\b", "OOO-OOOO-OOOO", text)
    text = re.sub(r"\b\d{6}-\d{7}\b", "OOOOOO-OOOOOOO", text)
    text = re.sub(r"\b\d{2,3}[가-힣]\d{4}\b", "OOO", text)
    return text


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<.*?>", "", s)
    s = s.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def safe_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return ""
    return u


def clamp(s: str, n: int = 300) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


# =========================================================
# 3) Meter / Trace (API 호출 수 + 토큰)
# =========================================================
class UsageMeter:
    def __init__(self):
        self.calls = {}
        self.tokens = {
            "gemini_prompt": 0,
            "gemini_output": 0,
            "gemini_total": 0,
            "groq_prompt": 0,
            "groq_output": 0,
            "groq_total": 0,
        }

    def inc_call(self, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1

    def add_gemini_tokens(self, prompt: int | None, output: int | None, total: int | None):
        if prompt is not None:
            self.tokens["gemini_prompt"] += int(prompt)
        if output is not None:
            self.tokens["gemini_output"] += int(output)
        if total is not None:
            self.tokens["gemini_total"] += int(total)
        else:
            if prompt is not None or output is not None:
                self.tokens["gemini_total"] += int((prompt or 0) + (output or 0))

    def add_groq_tokens(self, prompt: int | None, output: int | None, total: int | None):
        if prompt is not None:
            self.tokens["groq_prompt"] += int(prompt)
        if output is not None:
            self.tokens["groq_output"] += int(output)
        if total is not None:
            self.tokens["groq_total"] += int(total)
        else:
            if prompt is not None or output is not None:
                self.tokens["groq_total"] += int((prompt or 0) + (output or 0))


class Trace:
    def __init__(self):
        self.items = []
        self.meter = UsageMeter()

    def add(self, name, ok, detail="", tokens: dict | None = None):
        self.meter.inc_call(name)
        row = {"name": name, "ok": bool(ok), "detail": detail}
        if tokens:
            row["tokens"] = tokens
        self.items.append(row)

    def to_markdown(self):
        if not self.items:
            return "API 사용 내역이 없습니다."
        lines = ["| API | 성공 | 상세 | 토큰 |", "|---|---:|---|---|"]
        for it in self.items:
            tok = it.get("tokens")
            tok_str = ""
            if isinstance(tok, dict):
                p = tok.get("prompt")
                o = tok.get("output")
                t = tok.get("total")
                tok_str = f"p={p}, o={o}, t={t}"
            lines.append(f"| {it['name']} | {'✅' if it['ok'] else '❌'} | {it.get('detail','')} | {tok_str} |")
        return "\n".join(lines)

    def usage_summary(self) -> dict:
        return {"calls": self.meter.calls, "tokens": self.meter.tokens}


# =========================================================
# 4) Services
# =========================================================
class LLMService:
    """
    secrets:
      [general]
      GEMINI_API_KEY
      GROQ_API_KEY
      GROQ_MODEL
    """
    def __init__(self, trace: Trace):
        self.trace = trace
        g = st.secrets.get("general", {})
        self.gemini_key = g.get("GEMINI_API_KEY")
        self.groq_key = g.get("GROQ_API_KEY")
        self.groq_model = g.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.gemini_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

        self._gemini_ready = False
        if self.gemini_key and genai is not None:
            try:
                genai.configure(api_key=self.gemini_key)
                self._gemini_ready = True
                self.trace.add("Gemini.configure", True, "OK")
            except Exception as e:
                self.trace.add("Gemini.configure", False, f"{e}")
        else:
            self.trace.add("Gemini.configure", False, "No key or lib missing")

        self.groq_client = None
        if self.groq_key and Groq is not None:
            try:
                self.groq_client = Groq(api_key=self.groq_key)
                self.trace.add("Groq.init", True, f"model={self.groq_model}")
            except Exception as e:
                self.trace.add("Groq.init", False, f"{e}")
        else:
            self.trace.add("Groq.init", False, "No key or lib missing")

    @staticmethod
    def _extract_gemini_tokens(res) -> tuple[int | None, int | None, int | None]:
        try:
            um = getattr(res, "usage_metadata", None)
            if not um:
                return (None, None, None)
            total = getattr(um, "total_token_count", None)
            prompt = getattr(um, "prompt_token_count", None)
            output = getattr(um, "candidates_token_count", None)
            if output is None:
                output = getattr(um, "response_token_count", None)
            return (prompt, output, total)
        except Exception:
            return (None, None, None)

    def _try_gemini_text(self, prompt: str):
        if not self._gemini_ready:
            raise RuntimeError("Gemini not ready")
        last = None
        for m in self.gemini_models:
            try:
                model = genai.GenerativeModel(m)
                res = model.generate_content(prompt)
                p, o, t = self._extract_gemini_tokens(res)
                self.trace.meter.add_gemini_tokens(p, o, t)
                self.trace.add(
                    "Gemini.generate_content",
                    True,
                    f"model={m}",
                    tokens={"prompt": p, "output": o, "total": t},
                )
                return (res.text or "").strip()
            except Exception as e:
                last = e
                self.trace.add("Gemini.generate_content", False, f"model={m} err={type(e).__name__}")
        raise RuntimeError(last)

    def generate_text(self, prompt: str) -> str:
        try:
            return self._try_gemini_text(prompt)
        except Exception:
            pass

        if not self.groq_client:
            return "시스템 오류: LLM 연결 실패(Gemini/Groq 모두 불가)."
        try:
            completion = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            usage = getattr(completion, "usage", None)
            p = getattr(usage, "prompt_tokens", None) if usage else None
            o = getattr(usage, "completion_tokens", None) if usage else None
            t = getattr(usage, "total_tokens", None) if usage else None
            self.trace.meter.add_groq_tokens(p, o, t)
            self.trace.add(
                "Groq.chat.completions",
                True,
                f"model={self.groq_model}",
                tokens={"prompt": p, "output": o, "total": t},
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:
            self.trace.add("Groq.chat.completions", False, f"{type(e).__name__}: {e}")
            return "시스템 오류: Groq 호출 실패"

    def generate_json(self, prompt: str) -> dict | None:
        txt = self.generate_text(prompt + "\n\n반드시 JSON만 출력. 설명 금지.")
        try:
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if not m:
                return None
            return json.loads(m.group(0))
        except Exception:
            return None


class LawAPIService:
    """
    법제처 DRF
    secrets:
      [general]
      LAW_API_ID = OC
    """
    BASE_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
    BASE_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

    def __init__(self, trace: Trace):
        self.trace = trace
        g = st.secrets.get("general", {})
        self.oc = g.get("LAW_API_ID")
        if not self.oc:
            self.trace.add("LAWGO.init", False, "LAW_API_ID missing")

    def _get_json(self, url: str, params: dict, name: str, detail: str = ""):
        if requests is None:
            self.trace.add(name, False, "requests missing")
            return None
        if not self.oc:
            self.trace.add(name, False, "LAW_API_ID missing")
            return None
        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            self.trace.add(name, True, detail or f"endpoint={url.split('/')[-1]}")
            return data
        except Exception as e:
            self.trace.add(name, False, f"{type(e).__name__}: {e}")
            return None

    def search_law(self, query: str, display: int = 5) -> list[dict]:
        params = {"OC": self.oc, "target": "law", "type": "JSON", "query": query, "display": display, "page": 1}
        data = self._get_json(self.BASE_SEARCH, params, "LAWGO.lawSearch", "endpoint=lawSearch.do")
        if not isinstance(data, dict):
            return []

        candidates = []
        if isinstance(data.get("LawSearch"), dict) and isinstance(data["LawSearch"].get("law"), list):
            candidates = data["LawSearch"]["law"]
        elif isinstance(data.get("lawSearch"), dict) and isinstance(data["lawSearch"].get("law"), list):
            candidates = data["lawSearch"]["law"]
        else:
            for v in data.values():
                if isinstance(v, dict) and isinstance(v.get("law"), list):
                    candidates = v["law"]
                    break

        out = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            law_name = item.get("법령명한글") or item.get("법령명_한글") or item.get("법령명") or ""
            mst = item.get("법령일련번호") or item.get("MST") or item.get("lsi_seq")
            link = item.get("법령상세링크") or ""
            if link and link.startswith("/"):
                link = "https://www.law.go.kr" + link
            out.append({"law_name": str(law_name).strip(), "mst": str(mst) if mst else None, "link": str(link)})
        return [x for x in out if x["law_name"]]

    def fetch_article(self, mst: str, jo6: str | None):
        params = {"OC": self.oc, "target": "law", "type": "JSON", "MST": mst}
        if jo6:
            params["JO"] = jo6
        detail = f"endpoint=lawService.do MST={mst}" + (f" JO={jo6}" if jo6 else "")
        return self._get_json(self.BASE_SERVICE, params, "LAWGO.lawService", detail)

    @staticmethod
    def normalize_jo(jo_text: str) -> str | None:
        if not jo_text:
            return None
        s = jo_text.replace(" ", "")
        m = re.search(r"(\d+)\s*조(?:의\s*(\d+))?", s)
        if not m:
            return None
        n = int(m.group(1))
        k = int(m.group(2)) if m.group(2) else 0
        if n < 0 or n > 9999 or k < 0 or k > 99:
            return None
        return f"{n:04d}{k:02d}"

    @staticmethod
    def _extract_article_text(data: dict) -> str:
        if not isinstance(data, dict):
            return ""
        for key in ["조문내용", "joCntnt", "JO_CNTNT", "content", "Content"]:
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        # 일부 응답은 다른 구조로 올 수 있음 (최소한의 안전망)
        for v in data.values():
            if isinstance(v, str) and len(v) > 30 and "제" in v and "조" in v:
                return v.strip()
        return ""

    def get_related_laws_pack(self, situation: str, llm: LLMService, topk: int = 3):
        situation_m = mask_pii(situation)

        extract_prompt = f"""
너는 대한민국 행정 실무용 '법령 후보 추출기'다.
아래 상황에 연관된 법령 후보를 최대 6개 뽑아라.
각 후보는 법령명과 대표 조항(있으면)을 포함.

반드시 JSON만:
{{
  "candidates": [
    {{"law_name": "도로교통법", "article": "제32조"}},
    {{"law_name": "소방기본법", "article": ""}}
  ]
}}

상황: "{situation_m}"
"""
        guess = llm.generate_json(extract_prompt) or {}
        cand = guess.get("candidates") if isinstance(guess, dict) else None
        if not isinstance(cand, list):
            cand = []

        cleaned = []
        seen = set()
        for x in cand:
            if not isinstance(x, dict):
                continue
            ln = (x.get("law_name") or "").strip()
            ar = (x.get("article") or "").strip()
            if not ln or ln in seen:
                continue
            seen.add(ln)
            cleaned.append({"law_name": ln, "article": ar})
            if len(cleaned) >= 8:
                break

        # 부족하면 상황 키워드로 보강
        if len(cleaned) < topk:
            kw = re.sub(r"\s+", " ", situation_m).strip()[:40]
            kw_results = self.search_law(kw, display=10)
            for it in kw_results:
                ln = it["law_name"]
                if ln not in seen:
                    seen.add(ln)
                    cleaned.append({"law_name": ln, "article": ""})
                if len(cleaned) >= 8:
                    break

        picked = []
        picked_names = set()

        for c in cleaned:
            q = c["law_name"]
            ar = c["article"]
            sr = self.search_law(q, display=5)
            if not sr:
                continue
            best = sr[0]
            law_name = best.get("law_name") or q
            mst = best.get("mst")
            link = best.get("link", "")

            if not law_name or law_name in picked_names:
                continue
            picked_names.add(law_name)

            jo6 = self.normalize_jo(ar) if ar else None
            article_text = ""
            if mst:
                data = self.fetch_article(mst, jo6)
                article_text = self._extract_article_text(data)

            picked.append({"law_name": law_name, "article": ar, "jo6": jo6, "mst": mst, "link": link, "article_text": article_text})
            if len(picked) >= topk:
                break

        if not picked:
            picked = [{"law_name": "법령 API 검색 실패(결과 없음)", "article": "", "jo6": None, "mst": None, "link": "", "article_text": ""}]

        primary = picked[0]
        legal_basis_text = primary["law_name"] + (f" {primary['article']}" if primary.get("article") else "")
        return {"primary": primary, "related": picked, "legal_basis_text": legal_basis_text}


class NaverSearchService:
    """
    secrets:
      [naver]
      CLIENT_ID
      CLIENT_SECRET
    """
    BASE = "https://openapi.naver.com/v1/search"

    def __init__(self, trace: Trace):
        self.trace = trace
        n = st.secrets.get("naver", {})
        self.client_id = n.get("CLIENT_ID")
        self.client_secret = n.get("CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            self.trace.add("NAVER.init", False, "CLIENT_ID/SECRET missing")

    def _call(self, endpoint: str, query: str, display: int = 5, sort: str = "sim"):
        if requests is None:
            self.trace.add(f"NAVER.{endpoint}", False, "requests missing")
            return None
        if not self.client_id or not self.client_secret:
            self.trace.add(f"NAVER.{endpoint}", False, "CLIENT_ID/SECRET missing")
            return None

        url = f"{self.BASE}/{endpoint}.json"
        headers = {"X-Naver-Client-Id": self.client_id, "X-Naver-Client-Secret": self.client_secret}
        params = {"query": query, "display": display, "start": 1, "sort": sort}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            self.trace.add(f"NAVER.{endpoint}", True, f"display={display}")
            return r.json()
        except Exception as e:
            self.trace.add(f"NAVER.{endpoint}", False, f"{type(e).__name__}: {e}")
            return None

    # ---- 전문성(블로그/카페) ----
    _PRO_KEYWORDS = [
        "법령","시행령","시행규칙","조문","판례","행정심판","행정소송","과태료","처분","사전통지",
        "의견제출","이의신청","불복","유권해석","질의회신","고시","훈령","예규","지침","매뉴얼","가이드",
        "공공기관","지자체","공무원","법제처","국가법령정보","행정절차법","복지","수급","급여","조사"
    ]
    _NONPRO_KEYWORDS = ["후기","맛집","일상","여행","다이어트","브이로그","내돈내산","감성","연애","육아","리뷰"]

    @classmethod
    def _professional_score(cls, title: str, desc: str, link: str) -> int:
        t = (title or "") + " " + (desc or "")
        score = 0
        for k in cls._PRO_KEYWORDS:
            if k in t:
                score += 2
        if re.search(r"제?\s*\d+\s*조", t):
            score += 4
        if len(desc or "") >= 80:
            score += 1
        for k in cls._NONPRO_KEYWORDS:
            if k in t:
                score -= 4
        if re.search(r"[😂🤣😍😅]|ㅋㅋ|ㅎㅎ|ㅠㅠ", t):
            score -= 2
        if any(dom in (link or "") for dom in ["law.go.kr", "go.kr", "ac.kr", "moj.go.kr", "korea.kr"]):
            score += 3
        return score

    # ---- 관련성(전 소스 공통) ----
    @staticmethod
    def _make_relevance_terms(situation: str, laws_pack: dict) -> list[str]:
        base = re.findall(r"[가-힣A-Za-z0-9]{2,12}", situation or "")
        base = [w for w in base if w not in ["그리고","관련","문의","사항","대하여","대한","처리","요청","작성","안내","검토"]]

        rel = []
        for it in (laws_pack.get("related") or [])[:3]:
            nm = (it.get("law_name") or "")
            ar = (it.get("article") or "")
            rel += re.findall(r"[가-힣A-Za-z0-9]{2,12}", nm)
            rel += re.findall(r"[가-힣A-Za-z0-9]{2,12}", ar)

        terms = base + rel
        stop = set(["법","법령","제","조","등","관련","사항","기준","내용"])
        terms = [t for t in terms if t not in stop]

        uniq = []
        seen = set()
        for t in terms:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
            if len(uniq) >= 18:
                break
        return uniq

    @staticmethod
    def _relevance_score(title: str, desc: str, terms: list[str]) -> int:
        t = (title or "") + " " + (desc or "")
        score = 0
        for w in terms:
            if w and w in t:
                score += 3

        # "행정처분/과태료" 일반기사만 끼는 것 방지
        if ("과태료" in t or "행정처분" in t) and not any(
            x in t for x in ["복지","수급","급여","조사","사회보장","기초생활","생계","의료급여","주거급여","자격","신청"]
        ):
            score -= 6
        return score

    def _parse_items(self, data: dict, source: str) -> list[dict]:
        out = []
        if not data:
            return out
        for it in (data.get("items") or [])[:15]:
            title = normalize_text(it.get("title", ""))
            desc = normalize_text(it.get("description", "")) or normalize_text(it.get("snippet", ""))
            link = safe_url(it.get("link", "") or "")
            out.append({"source": source, "title": title or "(제목 없음)", "desc": clamp(desc, 320), "link": link})

        uniq, seen = [], set()
        for x in out:
            key = x.get("link") or (x["source"] + x["title"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(x)
        return uniq

    def search_precedents_parsed(self, situation: str, laws_pack: dict, enable_llm_rerank: bool = False, llm: LLMService | None = None) -> list[dict]:
        core = situation.strip()
        primary_law = (laws_pack.get("legal_basis_text") or "").strip()

        # ✅ 질의 강화: 대표법령 + 상황
        q_news = f"{core} {primary_law} 조사 기준"
        q_web  = f"{core} {primary_law} 조문 해설"
        q_blog = f"{core} {primary_law} 실무 해설"
        q_cafe = f"{core} {primary_law} 질의회신"

        news = self._call("news", q_news, display=8)
        webkr = self._call("webkr", q_web, display=8)
        blog = self._call("blog", q_blog, display=12)
        cafe = self._call("cafearticle", q_cafe, display=12)

        items = []
        items += self._parse_items(news, "news")
        items += self._parse_items(webkr, "webkr")
        items += self._parse_items(blog, "blog")
        items += self._parse_items(cafe, "cafe")

        terms = self._make_relevance_terms(core, laws_pack)

        scored = []
        for x in items:
            rel = self._relevance_score(x["title"], x["desc"], terms)
            pro = self._professional_score(x["title"], x["desc"], x["link"]) if x["source"] in ("blog", "cafe") else 0
            x2 = dict(x)
            x2["rel_score"] = rel
            x2["pro_score"] = pro
            scored.append(x2)

        filtered = []
        for x in scored:
            src = x["source"]
            if src in ("news", "webkr"):
                if x["rel_score"] >= 6:
                    filtered.append(x)
            else:
                if x["pro_score"] >= 6 and x["rel_score"] >= 6:
                    filtered.append(x)

        # ✅ (선택) LLM 정밀 리랭킹: 관련=1 / 무관=0
        if enable_llm_rerank and llm:
            keep = []
            for x in filtered[:12]:
                p = f"""
아래 검색결과가 '민원 상황'과 직접 관련이 있으면 1, 아니면 0만 출력.
인삿말 금지, 설명 금지.
민원: {core}
검색결과: {x['title']} / {x['desc']}
"""
                ans = (llm.generate_text(p) or "").strip()
                if ans.startswith("1"):
                    keep.append(x)
            filtered = keep

        filtered.sort(key=lambda z: (z.get("rel_score", 0) + (z.get("pro_score", 0) * 0.3)), reverse=True)

        # 소스별 상한(쏠림 방지)
        out = []
        caps = {"news": 5, "webkr": 5, "blog": 3, "cafe": 3}
        cnt = {k: 0 for k in caps}
        for x in filtered:
            s = x["source"]
            if s in caps and cnt[s] >= caps[s]:
                continue
            cnt[s] += 1
            out.append(x)

        return out


class DatabaseService:
    """
    secrets:
      [supabase]
      SUPABASE_URL
      SUPABASE_KEY
    """
    def __init__(self, trace: Trace):
        self.trace = trace
        self.is_active = False
        self.client = None

        if create_client is None:
            self.trace.add("Supabase.init", False, "supabase lib missing")
            return

        s = st.secrets.get("supabase", {})
        url = s.get("SUPABASE_URL")
        key = s.get("SUPABASE_KEY")
        if not url or not key:
            self.trace.add("Supabase.init", False, "URL/KEY missing")
            return
        try:
            self.client = create_client(url, key)
            self.is_active = True
            self.trace.add("Supabase.init", True, "connected")
        except Exception as e:
            self.trace.add("Supabase.init", False, f"{type(e).__name__}: {e}")

    def save_log(self, table: str, payload: dict):
        if not self.is_active or not self.client:
            return "DB 미연결 (저장 건너뜀)"
        try:
            self.client.table(table).insert(payload).execute()
            self.trace.add("Supabase.insert", True, f"table={table}")
            return "DB 저장 성공"
        except Exception as e:
            self.trace.add("Supabase.insert", False, f"{type(e).__name__}: {e}")
            return f"DB 저장 실패: {e}"


# =========================================================
# 5) Agents
# =========================================================
class LegalAgents:
    @staticmethod
    def strategist(llm: LLMService, situation: str, laws_pack: dict, precedent_items: list[dict]):
        legal_basis = laws_pack.get("legal_basis_text", "")
        related = laws_pack.get("related", []) or []
        primary = laws_pack.get("primary", {}) or {}

        rel_lines = []
        for i, it in enumerate(related[:3], 1):
            nm = it.get("law_name", "")
            ar = it.get("article", "")
            jo6 = it.get("jo6")
            mst = it.get("mst")
            rel_lines.append(f"{i}) {nm} {ar} (MST={mst}, JO={jo6})")
        rel_block = "\n".join(rel_lines) if rel_lines else "(없음)"

        brief = []
        for it in (precedent_items or [])[:8]:
            src = it.get("source")
            title = it.get("title")
            desc = it.get("desc")
            brief.append(f"- [{src}] {title}: {desc}")
        brief_block = "\n".join(brief) if brief else "(검색 결과 없음)"

        prompt = f"""
너는 행정 실무 '주무관'이다.

[출력 제약]
- 인삿말/자기소개/감사 문구 금지. 바로 본문 시작.
- 과도한 일반론 금지. 본 민원과 법령에 직접 연결된 문장만.
- 아래 3개 항목만, 마크다운으로.

[민원 상황]
{situation}

[대표 근거]
{legal_basis}

[대표 MST/JO]
MST={primary.get("mst")} / JO={primary.get("jo6")}

[연관 법령 3개]
{rel_block}

[유사 사례(네이버: 뉴스/웹 + 전문 블로그/카페만 + 관련성 필터)]
{brief_block}

1. **처리 방향**
2. **핵심 주의사항**
3. **예상 반발 및 대응**
"""
        return llm.generate_text(prompt)

    @staticmethod
    def clerk(llm: LLMService, situation: str, legal_basis: str):
        today = datetime.now()
        prompt = f"""
오늘: {today.strftime('%Y-%m-%d')}
상황: {situation}
법령(대표): {legal_basis}

행정처분 사전통지/이행명령 시 통상 부여하는
'이행/의견제출 기간'을 일수 숫자만 출력.
모르면 15.
"""
        days = 15
        try:
            res = llm.generate_text(prompt)
            days = int(re.sub(r"[^0-9]", "", res) or "15")
            if days <= 0:
                days = 15
        except Exception:
            days = 15

        deadline = today + timedelta(days=days)
        return {
            "today_str": today.strftime("%Y. %m. %d."),
            "deadline_str": deadline.strftime("%Y. %m. %d."),
            "days_added": days,
            "doc_num": f"행정-{today.strftime('%Y')}-{int(time.time())%1000:03d}호",
        }

    @staticmethod
    def drafter(llm: LLMService, situation: str, laws_pack: dict, meta_info: dict, strategy: str):
        situation = mask_pii(situation)
        primary = laws_pack.get("primary", {}) or {}
        related = laws_pack.get("related", []) or []

        rel_bullets = []
        for it in related[:3]:
            nm = it.get("law_name", "")
            ar = it.get("article", "")
            if nm:
                rel_bullets.append(f"- {nm} {ar}".strip())
        rel_text = "\n".join(rel_bullets) if rel_bullets else "- (연관 법령 확인 불가)"

        prompt = f"""
너는 행정기관의 서기다. 아래 정보로 완결된 공문서를 JSON으로 작성해라.

반드시 JSON만:
{{
  "title": "문서 제목",
  "receiver": "수신",
  "body_paragraphs": ["문단1", "문단2", "문단3"],
  "department_head": "발신 명의"
}}

[입력]
- 민원 상황: {situation}
- 대표 근거: {laws_pack.get("legal_basis_text","")}
- 대표 법령 MST/JO: MST={primary.get("mst")} / JO={primary.get("jo6")} (JO는 6자리)
- 대표 조문 내용(가능하면): {primary.get("article_text","")}
- 연관 법령(최대 3개):
{rel_text}
- 시행 일자: {meta_info['today_str']}
- 기한: {meta_info['deadline_str']} ({meta_info['days_added']}일)

[전략]
{strategy}

[작성 원칙]
- 본문 구조: [경위] -> [근거] -> [처분 내용] -> [권리구제 절차]
- 개인정보는 'OOO'로 마스킹
- 행정문서 톤: 건조/정중
"""
        doc = llm.generate_json(prompt)

        if not isinstance(doc, dict):
            doc = {
                "title": "공 문 서",
                "receiver": "수신자 참조",
                "body_paragraphs": [
                    "1. 귀하의 민원에 대하여 아래와 같이 검토 결과를 안내드립니다.",
                    f"2. 관련 근거(대표): {laws_pack.get('legal_basis_text','')}",
                    "3. 연관 법령(참고):\n" + rel_text,
                    f"4. (의견제출/이행) 기한: {meta_info['deadline_str']}까지",
                    "5. 기타 문의는 담당부서로 연락주시기 바랍니다.",
                ],
                "department_head": "행정기관장",
            }

        doc.setdefault("title", "공 문 서")
        doc.setdefault("receiver", "수신자 참조")
        doc.setdefault("body_paragraphs", [])
        doc.setdefault("department_head", "행정기관장")
        if isinstance(doc["body_paragraphs"], str):
            doc["body_paragraphs"] = [doc["body_paragraphs"]]

        return doc


# =========================================================
# 6) Rendering helpers
# =========================================================
def render_api_trace(trace_items):
    if not trace_items:
        st.info("API 사용 내역이 없습니다.")
        return
    pills = []
    for it in trace_items:
        cls = "api-pill api-ok" if it.get("ok") else "api-pill api-bad"
        name = escape(str(it.get("name", "")))
        detail = escape(str(it.get("detail", "")))
        tok = it.get("tokens")
        tok_str = ""
        if isinstance(tok, dict):
            tok_str = f" | tokens p={tok.get('prompt')}, o={tok.get('output')}, t={tok.get('total')}"
        pills.append(f"<span class='{cls}' title='{detail}{tok_str}'>{name}</span>")
    st.markdown(
        f"<div class='api-box'>{''.join(pills)}<div class='small-muted'>*pill hover/길게눌러 상세(토큰 포함)</div></div>",
        unsafe_allow_html=True,
    )


def render_usage_summary(usage: dict):
    calls = (usage or {}).get("calls", {}) or {}
    tokens = (usage or {}).get("tokens", {}) or {}

    st.markdown("#### 📞 API 호출 수")
    if calls:
        rows = [{"API": k, "Calls": v} for k, v in sorted(calls.items(), key=lambda x: (-x[1], x[0]))]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("호출 기록이 없습니다.")

    st.markdown("#### 🧾 토큰 사용량(가능한 범위)")
    t_rows = [
        {"Provider": "Gemini", "Prompt": tokens.get("gemini_prompt", 0), "Output": tokens.get("gemini_output", 0), "Total": tokens.get("gemini_total", 0)},
        {"Provider": "Groq", "Prompt": tokens.get("groq_prompt", 0), "Output": tokens.get("groq_output", 0), "Total": tokens.get("groq_total", 0)},
    ]
    st.dataframe(t_rows, use_container_width=True, hide_index=True)
    st.caption("※ Gemini 토큰은 라이브러리/응답 버전에 따라 미제공(None)일 수 있으며, 제공될 때만 합산됩니다.")


def law_link_from_meta(link: str, mst: str | None, jo6: str | None, oc: str | None) -> str:
    link = safe_url(link)
    if link:
        return link
    if not (mst and oc):
        return ""
    base = f"https://www.law.go.kr/DRF/lawService.do?OC={oc}&target=law&MST={mst}&type=HTML"
    if jo6:
        base += f"&JO={jo6}"
    return base


def render_laws_pack(laws_pack: dict):
    related = laws_pack.get("related", []) or []
    if not related:
        st.warning("법령 결과가 없습니다.")
        return

    g = st.secrets.get("general", {})
    oc = g.get("LAW_API_ID")

    st.markdown("**📜 대표 + 연관 법령 (최대 3개)**")
    for idx, it in enumerate(related[:3], 1):
        nm = it.get("law_name", "")
        ar = it.get("article", "")
        mst = it.get("mst")
        jo6 = it.get("jo6")
        link = it.get("link", "")

        full_url = law_link_from_meta(link, mst, jo6, oc)

        if full_url:
            st.markdown(f"### {idx}) [{escape(nm)} {escape(ar)}]({full_url})")
            st.link_button(f"🔗 원문 보기 - {idx}", full_url, use_container_width=True)
        else:
            st.markdown(f"### {idx}) {escape(nm)} {escape(ar)}")

        st.caption(f"MST: {mst} | JO(6자리): {jo6}")

        art = (it.get("article_text") or "").strip()
        if art:
            with st.expander(f"조문 내용(가능한 경우) - {idx}", expanded=False):
                st.info(art)
        else:
            st.caption("조문 내용은 JO/MST 매칭이 불완전하면 비어 있을 수 있습니다.")


def render_precedents(items: list[dict]):
    if not items:
        st.info("관련 검색 결과가 없습니다.")
        return

    def src_label(src: str) -> str:
        return {
            "news": "뉴스",
            "webkr": "웹문서",
            "blog": "블로그(전문+관련 필터)",
            "cafe": "카페(전문+관련 필터)",
        }.get(src, src or "검색")

    for it in items[:16]:
        src = it.get("source", "")
        title = it.get("title", "")
        desc = it.get("desc", "")
        link = safe_url(it.get("link", "") or "")
        rel = it.get("rel_score", None)
        pro = it.get("pro_score", None)

        st.markdown("<div class='item-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='item-title'>[{escape(src_label(src))}] {escape(title)}</div>", unsafe_allow_html=True)

        meta = []
        if isinstance(rel, int):
            meta.append(f"rel={rel}")
        if isinstance(pro, int) and src in ("blog", "cafe"):
            meta.append(f"pro={pro}")
        if meta:
            st.markdown(f"<div class='item-meta'>{escape(' | '.join(meta))}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='item-desc'>{escape(desc)}</div>", unsafe_allow_html=True)
        if link:
            st.link_button("열기", link, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# 7) Workflow
# =========================================================
def run_workflow(user_input: str, enable_llm_rerank: bool):
    trace = Trace()
    llm = LLMService(trace)
    law_api = LawAPIService(trace)
    naver = NaverSearchService(trace)
    db = DatabaseService(trace)

    log_placeholder = st.empty()
    logs = []

    def add_log(msg, style="sys"):
        logs.append(f"<div class='agent-log log-{style}'>{escape(msg)}</div>")
        log_placeholder.markdown("".join(logs), unsafe_allow_html=True)
        time.sleep(0.12)

    add_log("🔍 Phase 1: 법령 API(법제처)로 대표+연관 법령 3개 찾는 중...", "legal")
    laws_pack = law_api.get_related_laws_pack(user_input, llm, topk=3)
    add_log(f"📜 대표 근거: {laws_pack.get('legal_basis_text','')}", "legal")

    add_log("🔎 Phase 1b: 네이버 검색(뉴스/웹/블로그/카페) + 관련성/전문성 필터...", "search")
    precedent_items = naver.search_precedents_parsed(
        user_input,
        laws_pack,
        enable_llm_rerank=enable_llm_rerank,
        llm=llm if enable_llm_rerank else None
    )

    add_log("🧠 Phase 2: 업무 처리 방향 수립 중...", "strat")
    strategy = LegalAgents.strategist(llm, user_input, laws_pack, precedent_items)

    add_log("📅 Phase 3: 기한 산정 중...", "calc")
    meta_info = LegalAgents.clerk(llm, user_input, laws_pack.get("legal_basis_text", ""))

    add_log("✍️ Phase 3b: 공문서 작성 중...", "draft")
    doc_data = LegalAgents.drafter(llm, user_input, laws_pack, meta_info, strategy)

    add_log("💾 Phase 4: Supabase 저장 시도...", "sys")
    payload = {
        "situation": mask_pii(user_input),
        "law_name": laws_pack.get("legal_basis_text", ""),
        "summary": json.dumps(
            {
                "laws_pack": laws_pack,
                "precedent_items": precedent_items,
                "strategy": strategy,
                "document_content": doc_data,
                "api_trace": trace.items,
                "usage_summary": trace.usage_summary(),
                "rerank_enabled": bool(enable_llm_rerank),
            },
            ensure_ascii=False,
        ),
    }
    save_msg = db.save_log("law_reports", payload)

    add_log(f"✅ 완료: {save_msg}", "sys")
    time.sleep(0.35)
    log_placeholder.empty()

    return {
        "doc": doc_data,
        "meta": meta_info,
        "laws_pack": laws_pack,
        "precedent_items": precedent_items,
        "strategy": strategy,
        "save_msg": save_msg,
        "api_trace": trace.items,
        "api_trace_md": trace.to_markdown(),
        "usage_summary": trace.usage_summary(),
        "rerank_enabled": bool(enable_llm_rerank),
    }


# =========================================================
# 8) UI
# =========================================================
def main():
    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.title("🏢 AI 행정관 Pro")
        st.caption("LAWGO(법제처 DRF) + NAVER(뉴스/웹/전문 블로그·카페) + Gemini→Groq + Supabase")
        st.markdown("---")

        st.markdown("### 🗣️ 업무 지시")
        user_input = st.text_area(
            "업무 내용",
            height=150,
            placeholder="예시:\n- 소방차 전용구역 불법주차 과태료 안내문 작성\n- 무단방치차량 강제처리 절차 안내 공문 작성",
            label_visibility="collapsed",
        )

        enable_llm_rerank = st.toggle(
            "정밀 리랭킹(LLM로 검색결과 관련/무관 필터링) — 정확도↑ 비용↑",
            value=False
        )

        if st.button("⚡ 스마트 행정 처분 시작", type="primary", use_container_width=True):
            if not user_input.strip():
                st.warning("내용을 입력해주세요.")
            else:
                try:
                    with st.spinner("AI 에이전트 팀이 협업 중입니다..."):
                        st.session_state["workflow_result"] = run_workflow(user_input.strip(), enable_llm_rerank)
                except Exception as e:
                    st.error(f"시스템 오류 발생: {e}")

        if "workflow_result" in st.session_state:
            res = st.session_state["workflow_result"]
            st.markdown("---")

            if "성공" in (res.get("save_msg") or ""):
                st.success(f"✅ {res.get('save_msg')}")
            else:
                st.warning(res.get("save_msg", "DB 미연결"))

            with st.expander("📊 [표시] 호출 수 / 토큰 사용량", expanded=True):
                render_usage_summary(res.get("usage_summary", {}))

            with st.expander("🔌 [표시] 이번 업무에서 사용한 API (상세)", expanded=False):
                render_api_trace(res.get("api_trace", []))
                st.markdown(res.get("api_trace_md", ""))

            with st.expander("✅ [검토] 법령(법제처 API) — 제목 클릭=원문 보기", expanded=True):
                render_laws_pack(res.get("laws_pack", {}))

            with st.expander("🔎 [검토] 유사 사례(네이버) — 관련성/전문성 필터 적용", expanded=True):
                st.caption(f"정밀 리랭킹: {'ON' if res.get('rerank_enabled') else 'OFF'}")
                render_precedents(res.get("precedent_items", []))

            with st.expander("🧭 [방향] 업무 처리 가이드라인", expanded=True):
                st.markdown(res.get("strategy", ""))

    with col_right:
        if "workflow_result" in st.session_state:
            res = st.session_state["workflow_result"]
            doc = res.get("doc") or {}
            meta = res.get("meta") or {}

            paragraphs = doc.get("body_paragraphs", [])
            if isinstance(paragraphs, str):
                paragraphs = [paragraphs]

            html_content = f"""
<div class="paper-sheet">
  <div class="stamp">직인생략</div>
  <div class="doc-header">{escape(doc.get('title', '공 문 서'))}</div>
  <div class="doc-info">
    <span>문서번호: {escape(str(meta.get('doc_num','')))}</span>
    <span>시행일자: {escape(str(meta.get('today_str','')))}</span>
    <span>수신: {escape(doc.get('receiver', '수신자 참조'))}</span>
  </div>
  <hr style="border: 1px solid black; margin-bottom: 30px;">
  <div class="doc-body">
"""
            for p in paragraphs:
                html_content += f"<p style='margin-bottom: 15px;'>{escape(str(p))}</p>"

            html_content += f"""
  </div>
  <div class="doc-footer">{escape(doc.get('department_head', '행정기관장'))}</div>
</div>
"""
            st.markdown(html_content, unsafe_allow_html=True)
        else:
            st.markdown(
                """
<div style='text-align: center; padding: 100px; color: #aaa; background: white; border-radius: 10px; border: 2px dashed #ddd;'>
  <h3>📄 Document Preview</h3>
  <p>왼쪽에서 업무를 지시하면<br>완성된 공문서가 여기에 나타납니다.</p>
</div>
""",
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
