# app.py
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
st.set_page_config(layout="wide", page_title="AI Bureau: The Legal Glass", page_icon="⚖️")

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
.doc-info { display: flex; justify-content: space-between; font-size: 11pt; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
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
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# 2) Helpers
# =========================================================
def _safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return cur


def mask_pii(text: str) -> str:
    if not text:
        return text
    # 전화번호/주민/차량번호 등 대충 마스킹
    text = re.sub(r"\b\d{2,3}-\d{3,4}-\d{4}\b", "OOO-OOOO-OOOO", text)
    text = re.sub(r"\b\d{6}-\d{7}\b", "OOOOOO-OOOOOOO", text)
    text = re.sub(r"\b\d{2,3}[가-힣]\d{4}\b", "OOO", text)  # 차량번호 단순
    return text


# =========================================================
# 3) Services
# =========================================================
class Trace:
    """API 사용 내역을 한 곳에 모으는 트레이서"""
    def __init__(self):
        self.items = []  # list[dict]

    def add(self, name, ok, detail="", extra=None):
        it = {"name": name, "ok": bool(ok), "detail": detail}
        if extra is not None:
            it["extra"] = extra
        self.items.append(it)

    def to_markdown(self):
        if not self.items:
            return "API 사용 내역이 없습니다."
        lines = ["| API | 성공 | 상세 |", "|---|---:|---|"]
        for it in self.items:
            lines.append(f"| {it['name']} | {'✅' if it['ok'] else '❌'} | {it.get('detail','')} |")
        return "\n".join(lines)


class LLMService:
    """
    Gemini(텍스트/JSON) -> 실패 시 Groq fallback
    """
    def __init__(self, trace: Trace):
        self.trace = trace

        g = st.secrets.get("general", {})
        self.gemini_key = g.get("GEMINI_API_KEY")
        self.groq_key = g.get("GROQ_API_KEY")
        self.groq_model = g.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.gemini_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ]

        self._gemini_ready = False
        if self.gemini_key and genai is not None:
            try:
                genai.configure(api_key=self.gemini_key)
                self._gemini_ready = True
                self.trace.add("Gemini.configure", True, "API Key configured")
            except Exception as e:
                self.trace.add("Gemini.configure", False, f"{e}")
                self._gemini_ready = False
        else:
            self.trace.add("Gemini.configure", False, "No key or library missing")

        self.groq_client = None
        if self.groq_key and Groq is not None:
            try:
                self.groq_client = Groq(api_key=self.groq_key)
                self.trace.add("Groq.init", True, f"model={self.groq_model}")
            except Exception as e:
                self.trace.add("Groq.init", False, f"{e}")
        else:
            self.trace.add("Groq.init", False, "No key or library missing")

    def _try_gemini_text(self, prompt: str):
        if not self._gemini_ready:
            raise RuntimeError("Gemini not ready")
        last_err = None
        for m in self.gemini_models:
            try:
                model = genai.GenerativeModel(m)
                res = model.generate_content(prompt)
                self.trace.add("Gemini.generate_content", True, f"model={m}")
                return res.text, m
            except Exception as e:
                last_err = e
                self.trace.add("Gemini.generate_content", False, f"model={m} err={type(e).__name__}")
                continue
        raise RuntimeError(f"All Gemini models failed: {last_err}")

    def generate_text(self, prompt: str) -> str:
        # Gemini 먼저
        try:
            text, _ = self._try_gemini_text(prompt)
            return text.strip()
        except Exception:
            pass

        # Groq fallback
        if not self.groq_client:
            return "시스템 오류: LLM 연결 실패(Gemini/Groq 모두 불가)."

        try:
            completion = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            self.trace.add("Groq.chat.completions", True, f"model={self.groq_model}")
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:
            self.trace.add("Groq.chat.completions", False, f"{e}")
            return "시스템 오류: Groq 호출 실패"

    def generate_json(self, prompt: str) -> dict | None:
        # JSON 강제 출력 (Gemini schema 모드 대신 안정적으로 파싱)
        txt = self.generate_text(prompt + "\n\n반드시 JSON만 출력하세요. 다른 문장 금지.")
        try:
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if not m:
                return None
            return json.loads(m.group(0))
        except Exception:
            return None


class LawAPIService:
    """
    법제처 국가법령정보(DRF) 사용:
    - 목록/검색: http://www.law.go.kr/DRF/lawSearch.do?target=law&type=JSON&query=...
    - 본문:     http://www.law.go.kr/DRF/lawService.do?target=law&type=JSON&MST=...&JO=...
    """
    BASE_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
    BASE_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

    def __init__(self, trace: Trace):
        self.trace = trace
        g = st.secrets.get("general", {})
        self.oc = g.get("LAW_API_ID")  # OC
        if not self.oc:
            self.trace.add("LAWGO.init", False, "LAW_API_ID(OC) missing")

    def _get_json(self, url: str, params: dict, name: str):
        if requests is None:
            self.trace.add(name, False, "requests missing")
            return None
        if not self.oc:
            self.trace.add(name, False, "LAW_API_ID(OC) missing")
            return None

        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            self.trace.add(name, True, f"endpoint={url.split('/')[-1]}")
            return data
        except Exception as e:
            self.trace.add(name, False, f"{type(e).__name__}: {e}")
            return None

    def search_law(self, query: str, display: int = 5):
        params = {
            "OC": self.oc,
            "target": "law",
            "type": "JSON",
            "query": query,
            "display": display,
            "page": 1,
        }
        data = self._get_json(self.BASE_SEARCH, params, "LAWGO.lawSearch")
        # 응답 포맷이 일정치 않을 수 있어 최대한 유연하게
        # 보통: {"LawSearch":{"law":[{...}, ...], "totalCnt":...}}
        if not data:
            return []

        # 가능한 경로들
        candidates = []
        for path in [
            ("LawSearch", "law"),
            ("lawSearch", "law"),
            ("Law",),
        ]:
            cur = _safe_get(data, *path, default=None)
            if isinstance(cur, list):
                candidates = cur
                break
        # 혹시 dict 안에 law 키만 있는 구조
        if not candidates:
            for v in data.values():
                if isinstance(v, dict) and isinstance(v.get("law"), list):
                    candidates = v["law"]
                    break

        results = []
        for item in candidates or []:
            if not isinstance(item, dict):
                continue
            law_name = item.get("법령명한글") or item.get("법령명_한글") or item.get("법령명") or ""
            law_id = item.get("법령ID") or item.get("법령ID") or item.get("ID")
            mst = item.get("법령일련번호") or item.get("MST") or item.get("lsi_seq")
            link = item.get("법령상세링크") or item.get("법령상세링크") or ""
            results.append(
                {
                    "law_name": str(law_name),
                    "law_id": str(law_id) if law_id is not None else None,
                    "mst": str(mst) if mst is not None else None,
                    "link": str(link),
                    "raw": item,
                }
            )
        return results

    def fetch_article(self, mst: str, jo6: str | None = None):
        # JO: 6자리 (조번호4 + 가지번호2) 예: 2조=000200, 10조의2=001002
        params = {
            "OC": self.oc,
            "target": "law",
            "type": "JSON",
            "MST": mst,
        }
        if jo6:
            params["JO"] = jo6

        data = self._get_json(self.BASE_SERVICE, params, "LAWGO.lawService")
        return data

    @staticmethod
    def normalize_jo(jo_text: str) -> str | None:
        """
        '제32조' / '32조' / '제10조의2' -> 6자리 JO로 변환
        규칙:
        - N조 -> N을 4자리로, 가지번호는 00
        - N조의K -> N 4자리 + K 2자리
        """
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

    def get_best_law_and_article(self, situation: str, llm_service: LLMService):
        """
        1) LLM으로 '법령명' + '조항' 후보를 뽑고
        2) lawSearch로 법령을 확정
        3) 가능하면 lawService로 해당 조문 내용까지 끌어옴
        """
        situation = mask_pii(situation)

        extract_prompt = f"""
너는 대한민국 행정 실무용 키워드 추출기다.
아래 민원/업무 상황에서 적용 가능성이 높은 '법령명'과 '조항'을 한 개만 추정해라.

반드시 JSON만 출력:
{{
  "law_name_guess": "예: 자동차관리법",
  "article_guess": "예: 제26조"  // 없으면 빈 문자열
}}

상황: "{situation}"
"""
        guess = llm_service.generate_json(extract_prompt) or {}
        law_name_guess = (guess.get("law_name_guess") or "").strip()
        article_guess = (guess.get("article_guess") or "").strip()

        # 1차: 법령명으로 검색
        results = self.search_law(law_name_guess or situation[:30])
        if not results:
            # 2차: 상황 키워드로 검색(짧게)
            kw = re.sub(r"\s+", " ", situation).strip()[:40]
            results = self.search_law(kw)

        if not results:
            return {
                "law_basis_text": "법령 API 검색 실패(검색 결과 없음)",
                "law_article_text": "",
                "law_meta": {},
            }

        best = results[0]
        mst = best.get("mst")
        law_name = best.get("law_name") or law_name_guess or "법령명 불명"

        jo6 = self.normalize_jo(article_guess) if article_guess else None

        article_text = ""
        law_basis_text = law_name
        if article_guess:
            law_basis_text = f"{law_name} {article_guess}"

        # 조문까지 가능한 경우: MST가 있어야 안정적
        law_meta = {"law_name": law_name, "mst": mst, "law_id": best.get("law_id"), "link": best.get("link")}
        if mst:
            data = self.fetch_article(mst, jo6=jo6)
            # 응답 구조가 복잡할 수 있으니 조문내용 key를 넓게 탐색
            # 흔히: 조문내용 / 조문제목 / 항내용 / 호내용 등이 들어감
            if isinstance(data, dict):
                # 후보 키들
                candidates = []
                for k in ["조문내용", "joCntnt", "조문내용_"]:
                    v = data.get(k)
                    if isinstance(v, str) and v.strip():
                        candidates.append(v.strip())
                # 깊은 구조 탐색(대충)
                if not candidates:
                    txt = json.dumps(data, ensure_ascii=False)
                    m = re.search(r'"조문내용"\s*:\s*"([^"]+)"', txt)
                    if m:
                        candidates.append(m.group(1))

                if candidates:
                    article_text = candidates[0]

        return {
            "law_basis_text": law_basis_text,
            "law_article_text": article_text,
            "law_meta": law_meta,
        }


class NaverSearchService:
    """
    네이버 검색 API:
    - https://openapi.naver.com/v1/search/news.json
    - https://openapi.naver.com/v1/search/webkr.json
    """
    BASE = "https://openapi.naver.com/v1/search"

    def __init__(self, trace: Trace):
        self.trace = trace
        n = st.secrets.get("naver", {})
        self.client_id = n.get("CLIENT_ID")
        self.client_secret = n.get("CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            self.trace.add("NAVER.init", False, "CLIENT_ID/SECRET missing")

    def _call(self, endpoint: str, query: str, display: int = 3, sort: str = "sim"):
        if requests is None:
            self.trace.add(f"NAVER.{endpoint}", False, "requests missing")
            return None
        if not self.client_id or not self.client_secret:
            self.trace.add(f"NAVER.{endpoint}", False, "CLIENT_ID/SECRET missing")
            return None

        url = f"{self.BASE}/{endpoint}.json"
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {"query": query, "display": display, "start": 1, "sort": sort}

        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            self.trace.add(f"NAVER.{endpoint}", True, f"display={display}")
            return r.json()
        except Exception as e:
            self.trace.add(f"NAVER.{endpoint}", False, f"{type(e).__name__}: {e}")
            return None

    @staticmethod
    def _strip_html(s: str) -> str:
        return re.sub(r"<.*?>", "", s or "").strip()

    def search_precedents(self, situation: str) -> str:
        q1 = f"{situation} 행정처분"
        q2 = f"{situation} 과태료 기준"

        news = self._call("news", q1, display=3)
        webkr = self._call("webkr", q2, display=3)

        lines = []
        def add_items(data, label):
            if not data:
                return
            for it in (data.get("items") or [])[:3]:
                title = self._strip_html(it.get("title", ""))
                link = it.get("link", "")
                desc = self._strip_html(it.get("description", "")) or self._strip_html(it.get("snippet", ""))
                if title:
                    lines.append(f"- **[{label}] {title}**: {desc}\n  - {link}")

        add_items(news, "뉴스")
        add_items(webkr, "웹문서")

        return "\n".join(lines) if lines else "관련 검색 결과가 없습니다."


class DatabaseService:
    def __init__(self, trace: Trace):
        self.trace = trace
        self.is_active = False
        self.client = None

        if create_client is None:
            self.trace.add("Supabase.init", False, "supabase lib missing")
            return

        try:
            s = st.secrets.get("supabase", {})
            url = s.get("SUPABASE_URL")
            key = s.get("SUPABASE_KEY")
            if not url or not key:
                self.trace.add("Supabase.init", False, "URL/KEY missing")
                return
            self.client = create_client(url, key)
            self.is_active = True
            self.trace.add("Supabase.init", True, "connected")
        except Exception as e:
            self.trace.add("Supabase.init", False, f"{e}")
            self.is_active = False

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
# 4) Domain Agents
# =========================================================
class LegalAgents:
    @staticmethod
    def strategist(llm: LLMService, situation: str, legal_basis: str, law_article_text: str, search_results: str):
        prompt = f"""
너는 행정 실무 '주무관'이다. 아래 정보를 종합해 '업무 처리 방향'을 세워라.

[민원 상황]
{situation}

[법적 근거(확정)]
{legal_basis}

[관련 조문 내용(가능하면)]
{law_article_text}

[네이버 검색 결과(유사 사례)]
{search_results}

아래 3개 항목을 마크다운으로:
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
법령: {legal_basis}

위 상황에서 행정처분 사전통지/이행명령 시 통상적으로 부여하는
'이행/의견제출 기간' 일수만 숫자로 출력.
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
    def drafter(llm: LLMService, situation: str, legal_basis: str, law_article_text: str, meta_info: dict, strategy: str):
        situation = mask_pii(situation)

        prompt = f"""
너는 행정기관의 서기다. 아래 정보로 '완결된 공문서'를 JSON으로 작성해라.

반드시 JSON만 출력:
{{
  "title": "문서 제목",
  "receiver": "수신",
  "body_paragraphs": ["문단1", "문단2", "문단3"],
  "department_head": "발신 명의"
}}

[입력]
- 민원 상황: {situation}
- 법적 근거: {legal_basis}
- 관련 조문 내용(참고): {law_article_text}
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
        if not doc:
            # 최소 안전 폴백
            doc = {
                "title": "공 문 서",
                "receiver": "수신자 참조",
                "body_paragraphs": [
                    "1. 귀하의 민원에 대한 검토 결과를 다음과 같이 안내드립니다.",
                    f"2. 관련 근거: {legal_basis}",
                    f"3. 위 근거에 따라 필요한 행정절차를 진행할 예정입니다. 기한: {meta_info['deadline_str']}",
                ],
                "department_head": "행정기관장",
            }
        return doc


# =========================================================
# 5) Workflow
# =========================================================
def run_workflow(user_input: str):
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
        time.sleep(0.2)

    # Phase 1: Law API
    add_log("🔍 Phase 1: 법령 API(국가법령정보)로 근거 확인 중...", "legal")
    law_pack = law_api.get_best_law_and_article(user_input, llm)
    legal_basis = law_pack["law_basis_text"]
    law_article_text = law_pack.get("law_article_text", "")
    add_log(f"📜 법령 확정: {legal_basis}", "legal")

    # Phase 1b: Naver search
    add_log("🔎 Phase 1b: 네이버 검색 API로 유사사례 조회 중...", "search")
    search_results = naver.search_precedents(user_input)

    # Phase 2: Strategy
    add_log("🧠 Phase 2: 업무 처리 방향 수립 중...", "strat")
    strategy = LegalAgents.strategist(llm, user_input, legal_basis, law_article_text, search_results)

    # Phase 3: Meta & Draft
    add_log("📅 Phase 3: 기한 산정 중...", "calc")
    meta_info = LegalAgents.clerk(llm, user_input, legal_basis)

    add_log("✍️ Phase 3b: 공문서 작성 중...", "draft")
    doc_data = LegalAgents.drafter(llm, user_input, legal_basis, law_article_text, meta_info, strategy)

    # Phase 4: Save
    add_log("💾 Phase 4: Supabase 저장 시도...", "sys")
    payload = {
        "situation": mask_pii(user_input),
        "law_name": legal_basis,
        "summary": json.dumps(
            {
                "law_article_text": law_article_text,
                "strategy": strategy,
                "document_content": doc_data,
                "api_trace": trace.items,
            },
            ensure_ascii=False,
        ),
    }
    save_msg = db.save_log("law_reports", payload)

    add_log(f"✅ 완료: {save_msg}", "sys")
    time.sleep(0.6)
    log_placeholder.empty()

    return {
        "doc": doc_data,
        "meta": meta_info,
        "law": legal_basis,
        "law_article_text": law_article_text,
        "search": search_results,
        "strategy": strategy,
        "save_msg": save_msg,
        "api_trace": trace.items,
        "api_trace_md": trace.to_markdown(),
    }


# =========================================================
# 6) UI
# =========================================================
def render_api_trace(trace_items: list[dict]):
    if not trace_items:
        st.info("API 사용 내역이 없습니다.")
        return

    pills = []
    for it in trace_items:
        cls = "api-pill api-ok" if it.get("ok") else "api-pill api-bad"
        name = escape(str(it.get("name", "")))
        detail = escape(str(it.get("detail", "")))
        pills.append(f"<span class='{cls}' title='{detail}'>{name}</span>")

    st.markdown(f"<div class='api-box'>{''.join(pills)}<div class='small-muted'>*각 pill을 길게 누르거나 마우스 올리면 상세가 보입니다.</div></div>", unsafe_allow_html=True)


def main():
    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.title("🏢 AI 행정관 Pro (LawAPI + Naver)")
        st.caption("법령=국가법령정보 OpenAPI / 검색=네이버 Search API / LLM=Gemini→Groq / DB=Supabase")
        st.markdown("---")

        st.markdown("### 🗣️ 업무 지시")
        user_input = st.text_area(
            "업무 내용",
            height=150,
            placeholder="예시:\n- 무단방치차량 민원 접수 후, 강제처리 절차 안내 공문 작성\n- 차고지 외 주기위반 단속 관련 시정 요청 회신",
            label_visibility="collapsed",
        )

        if st.button("⚡ 스마트 행정 처분 시작", type="primary", use_container_width=True):
            if not user_input.strip():
                st.warning("내용을 입력해주세요.")
            else:
                try:
                    with st.spinner("AI 에이전트 팀이 협업 중입니다..."):
                        st.session_state["workflow_result"] = run_workflow(user_input)
                except Exception as e:
                    st.error(f"시스템 오류 발생: {e}")

        # Persisted results
        if "workflow_result" in st.session_state:
            res = st.session_state["workflow_result"]
            st.markdown("---")

            # DB save
            if "성공" in res.get("save_msg", ""):
                st.success(f"✅ {res['save_msg']}")
            else:
                st.warning(res.get("save_msg", "DB 미연결"))

            # API trace
            with st.expander("🔌 [표시] 이번 업무에서 사용한 API", expanded=True):
                render_api_trace(res.get("api_trace", []))
                st.markdown(res.get("api_trace_md", ""))

            # Law & Search
            with st.expander("✅ [검토] 법령(법제처 API) 및 유사 사례(네이버 API)", expanded=True):
                st.markdown("**📜 적용 법령(확정)**")
                st.code(res.get("law", ""), language="text")

                st.markdown("**📌 관련 조문 내용(가능한 경우)**")
                if res.get("law_article_text"):
                    st.info(res["law_article_text"])
                else:
                    st.caption("조문 내용은 MST/JO 확정이 안 되면 비어있을 수 있습니다(법령명+조항만 확정).")

                st.markdown("**🔎 유사 사례(네이버 검색 결과)**")
                st.markdown(res.get("search", "검색 결과 없음"))

            # Strategy
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
