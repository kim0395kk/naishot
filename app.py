# app.py — AI 행정관 Pro (API 사용 내역 표시 + 완전 방어형 완세트)
import streamlit as st
import json
import re
import time
from datetime import datetime, timedelta
from html import escape as html_escape

# =========================
# Optional imports (안죽게)
# =========================
try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from serpapi import GoogleSearch
except Exception:
    GoogleSearch = None

try:
    from supabase import create_client
except Exception:
    create_client = None

# ==========================================
# 1) Page Config & Styles
# ==========================================
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

.badge-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
  margin-bottom: 8px;
}
.badge-sub { font-size: 0.85rem; color: #6b7280; margin-top: 2px; }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2) Helpers
# ==========================================
def sget(*keys, default=None):
    """
    sget("general","GEMINI_API_KEY") 처럼 안전 접근
    """
    cur = st.secrets
    try:
        for k in keys:
            cur = cur[k]
        return cur
    except Exception:
        return default

def api_card(title: str, ok: bool, subtitle: str = "") -> str:
    icon = "✅" if ok else "⛔"
    dim = "" if ok else "opacity:0.7;"
    sub = f"<div class='badge-sub'>{html_escape(subtitle)}</div>" if subtitle else ""
    return f"<div class='badge-card' style='{dim}'><div><b>{icon} {html_escape(title)}</b></div>{sub}</div>"

# ==========================================
# 3) Infrastructure Layer (Services)
# ==========================================
class LLMService:
    """
    ✅ Patch:
    - generate_text / generate_json 이 결과 + trace 반환
      trace = {"provider":"gemini|groq|none", "model":"...", "ok":bool, "error":"..."}
    """
    def __init__(self):
        self.gemini_key = sget("general", "GEMINI_API_KEY", default=None)
        self.groq_key = sget("general", "GROQ_API_KEY", default=None)

        self.gemini_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ]

        self.gemini_ok = False
        if self.gemini_key and genai is not None:
            try:
                genai.configure(api_key=self.gemini_key)
                self.gemini_ok = True
            except Exception:
                self.gemini_ok = False

        self.groq_client = None
        if self.groq_key and Groq is not None:
            try:
                self.groq_client = Groq(api_key=self.groq_key)
            except Exception:
                self.groq_client = None

    def _trace(self, provider="none", model=None, ok=False, error=None):
        return {"provider": provider, "model": model, "ok": ok, "error": str(error) if error else None}

    def _try_gemini_text(self, prompt: str):
        if not self.gemini_ok:
            raise RuntimeError("Gemini not available")

        last_err = None
        for model_name in self.gemini_models:
            try:
                model = genai.GenerativeModel(model_name)
                res = model.generate_content(prompt)
                text = (res.text or "").strip()
                if not text:
                    raise RuntimeError("Empty response")
                return text, self._trace(provider="gemini", model=model_name, ok=True)
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(last_err)

    def _try_groq_text(self, prompt: str):
        if not self.groq_client:
            raise RuntimeError("Groq not available")
        try:
            completion = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = (completion.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("Empty response")
            return text, self._trace(provider="groq", model="llama-3.3-70b-versatile", ok=True)
        except Exception as e:
            raise RuntimeError(e)

    def generate_text(self, prompt: str):
        # 1) Gemini
        gemini_err = None
        try:
            text, trace = self._try_gemini_text(prompt)
            return text, trace
        except Exception as e_g:
            gemini_err = e_g

        # 2) Groq fallback
        groq_err = None
        try:
            text, trace = self._try_groq_text(prompt)
            return text, trace
        except Exception as e_r:
            groq_err = e_r

        trace = self._trace(provider="none", model=None, ok=False, error=f"Gemini:{gemini_err} | Groq:{groq_err}")
        return "시스템 오류: AI 모델 연결 실패", trace

    def generate_json(self, prompt: str):
        text, trace = self.generate_text(prompt + "\n\n반드시 JSON만 출력하세요. 설명 금지.")
        obj = None
        try:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                obj = json.loads(m.group(0))
        except Exception:
            obj = None

        if obj is None:
            trace = {**trace, "ok": False, "error": (trace.get("error") or "") + " | JSON parse failed"}
        return obj, trace, text

class SearchService:
    """SerpApi(GoogleSearch) Wrapper"""
    def __init__(self):
        self.api_key = sget("general", "SERPAPI_KEY", default=None)

    def search_precedents(self, query: str) -> str:
        if not self.api_key:
            return "⚠️ SERPAPI_KEY 미설정: 유사 사례 검색 생략"
        if GoogleSearch is None:
            return "⚠️ serpapi 패키지 미설치: 유사 사례 검색 생략(requirements.txt 확인)"

        try:
            search_query = f"{query} 행정처분 판례 사례 민원 답변"
            params = {"engine": "google", "q": search_query, "api_key": self.api_key, "num": 3, "hl": "ko", "gl": "kr"}
            search = GoogleSearch(params)
            results = (search.get_dict() or {}).get("organic_results", []) or []
            if not results:
                return "관련된 유사 사례 검색 결과가 없습니다."

            summary = []
            for item in results:
                title = item.get("title", "제목 없음")
                snippet = item.get("snippet", "내용 없음")
                link = item.get("link", "#")
                summary.append(f"- **[{title}]({link})**: {snippet}")
            return "\n".join(summary)
        except Exception as e:
            return f"검색 중 오류 발생: {e}"

class DatabaseService:
    """Supabase Persistence Layer"""
    def __init__(self):
        self.is_active = False
        self.client = None

        if create_client is None:
            return

        url = sget("supabase", "SUPABASE_URL", default=None)
        key = sget("supabase", "SUPABASE_KEY", default=None)
        if not url or not key:
            return

        try:
            self.client = create_client(url, key)
            self.is_active = True
        except Exception:
            self.is_active = False
            self.client = None

    def save_log(self, user_input, legal_basis, strategy, doc_data):
        if not self.is_active:
            return "DB 미연결 (저장 건너뜀)"
        try:
            final_summary_content = {"strategy": strategy, "document_content": doc_data}
            data = {
                "situation": user_input,
                "law_name": legal_basis,
                "summary": json.dumps(final_summary_content, ensure_ascii=False),
            }
            self.client.table("law_reports").insert(data).execute()
            return "DB 저장 성공"
        except Exception as e:
            return f"DB 저장 실패: {e}"

# 싱글톤
llm_service = LLMService()
search_service = SearchService()
db_service = DatabaseService()

# ==========================================
# 4) Domain Layer (Agents)
# ==========================================
class LegalAgents:
    @staticmethod
    def researcher(situation: str):
        prompt = f"""
상황: "{situation}"

위 상황에 적용할 가장 정확한 '법령명'과 '관련 조항'을 하나만 찾으시오.
반드시 현행 대한민국 법령이어야 하며, 조항 번호까지 명시하세요.
예: 도로교통법 제32조(정차 및 주차의 금지)

[출력 형식]
- 법령명: ...
- 조항: ...
- 한 줄 요지: ...
"""
        text, trace = llm_service.generate_text(prompt)
        return text.strip(), trace

    @staticmethod
    def strategist(situation: str, legal_basis: str, search_results: str):
        prompt = f"""
[민원 상황]
{situation}

[법적 근거]
{legal_basis}

[유사 사례/판례]
{search_results}

위 정보를 종합하여 처리 전략을 마크다운으로 작성:
1. 처리 방향
2. 핵심 주의사항
3. 예상 반발 및 대응
"""
        text, trace = llm_service.generate_text(prompt)
        return text.strip(), trace

    @staticmethod
    def clerk(situation: str, legal_basis: str):
        today = datetime.now()
        prompt = f"""
오늘: {today.strftime('%Y-%m-%d')}
상황: {situation}
법령: {legal_basis}

행정처분 사전통지/이행명령 시 통상 부여하는 의견제출/이행기간 '일수'만 숫자로.
모르면 15.
"""
        text, trace = llm_service.generate_text(prompt)

        days = 15
        try:
            n = re.sub(r"[^0-9]", "", text)
            if n:
                days = max(1, min(60, int(n)))
        except Exception:
            days = 15

        deadline = today + timedelta(days=days)
        meta = {
            "today_str": today.strftime("%Y. %m. %d."),
            "deadline_str": deadline.strftime("%Y. %m. %d."),
            "days_added": days,
            "doc_num": f"행정-{today.strftime('%Y')}-{int(time.time())%1000:03d}호",
        }
        return meta, trace

    @staticmethod
    def drafter(situation: str, legal_basis: str, meta_info: dict, strategy: str, dept: str, officer: str):
        dept = (dept or "OOO과").strip()
        officer = (officer or "OOO").strip()

        prompt = f"""
너는 행정기관 문서 작성자다. 아래 정보를 바탕으로 '완결된 공문서'를 JSON으로 작성하라.
설명 금지. JSON만.

[입력]
- 민원 상황: {situation}
- 법적 근거: {legal_basis}
- 시행일자: {meta_info['today_str']}
- 기한: {meta_info['deadline_str']} ({meta_info['days_added']}일)
- 부서명: {dept}
- 담당자: {officer}

[전략]
{strategy}

[작성 원칙]
- 본문 구조: [경위] -> [근거] -> [처분/조치 내용] -> [권리구제/안내]
- 개인정보(이름/번호)는 반드시 OOO 마스킹
- 문서 톤: 정중/건조한 행정문
- receiver가 불명확하면 합리적으로 추론

[JSON 스키마]
{{
  "title": "공문서 제목",
  "receiver": "수신인",
  "body_paragraphs": ["문단1", "문단2", "..."],
  "department_head": "발신 명의(예: 충주시장 또는 OOO과장 등)"
}}
"""
        obj, trace, raw = llm_service.generate_json(prompt)

        # 안전장치: JSON 실패 시 최소 문서 생성
        if not isinstance(obj, dict):
            obj = {
                "title": "공 문 서",
                "receiver": "수신자 참조",
                "body_paragraphs": [
                    "1. 귀하의 민원에 감사드립니다.",
                    f"2. 본 건은 다음 법령에 따라 검토되었습니다: {legal_basis}",
                    "3. 관련 규정 및 현장 여건을 종합하여 필요한 조치를 진행하겠습니다.",
                    f"4. (의견제출/이행) 기한: {meta_info['deadline_str']}까지",
                    "5. 기타 문의는 담당부서로 연락주시기 바랍니다.",
                ],
                "department_head": "행정기관장",
            }

        # 필수키 보정
        obj.setdefault("title", "공 문 서")
        obj.setdefault("receiver", "수신자 참조")
        obj.setdefault("body_paragraphs", [])
        obj.setdefault("department_head", "행정기관장")
        if isinstance(obj["body_paragraphs"], str):
            obj["body_paragraphs"] = [obj["body_paragraphs"]]

        # 표시용 메타도 박아두기
        obj["_dept"] = dept
        obj["_officer"] = officer

        return obj, trace

# ==========================================
# 5) Workflow (API 사용 내역 100% 기록)
# ==========================================
def run_workflow(user_input: str, dept: str = None, officer: str = None):
    dept = (dept or st.session_state.get("dept") or "OOO과").strip()
    officer = (officer or st.session_state.get("officer") or "OOO").strip()

    log_placeholder = st.empty()
    logs = []

    api_usage = {
        "llm_calls": [],  # 단계별 LLM 호출 기록 (정확)
        "serpapi": {"used": False, "error": None},
        "supabase": {"used": False, "error": None},
    }

    def add_log(msg, style="sys"):
        logs.append(f"<div class='agent-log log-{style}'>{html_escape(msg)}</div>")
        log_placeholder.markdown("".join(logs), unsafe_allow_html=True)
        time.sleep(0.2)

    # Phase 1: Research
    add_log("🔍 Phase 1: 법령 리서치 중...", "legal")
    legal_basis, trace1 = LegalAgents.researcher(user_input)
    api_usage["llm_calls"].append({"step": "researcher", **trace1})
    add_log(f"📜 법적 근거 도출 완료 ({trace1.get('provider')} / {trace1.get('model')})", "legal")

    add_log("🌍 Phase 1-2: 유사사례 검색 중...", "search")
    search_results = search_service.search_precedents(user_input)
    if ("미설정" not in search_results) and ("미설치" not in search_results) and ("오류" not in search_results):
        api_usage["serpapi"]["used"] = True
    else:
        api_usage["serpapi"]["error"] = search_results

    # Phase 2: Strategy
    add_log("🧠 Phase 2: 처리 전략 수립 중...", "strat")
    strategy, trace2 = LegalAgents.strategist(user_input, legal_basis, search_results)
    api_usage["llm_calls"].append({"step": "strategist", **trace2})
    add_log(f"🧭 전략 수립 완료 ({trace2.get('provider')} / {trace2.get('model')})", "strat")

    # Phase 3: Deadline + Draft
    add_log("📅 Phase 3: 기한 산정 중...", "calc")
    meta_info, trace3 = LegalAgents.clerk(user_input, legal_basis)
    api_usage["llm_calls"].append({"step": "clerk", **trace3})
    add_log(f"📌 기한 산정 완료 ({trace3.get('provider')} / {trace3.get('model')})", "calc")

    add_log("✍️ Phase 3-2: 공문서 작성 중...", "draft")
    doc_data, trace4 = LegalAgents.drafter(user_input, legal_basis, meta_info, strategy, dept, officer)
    api_usage["llm_calls"].append({"step": "drafter", **trace4})
    add_log(f"🧾 공문서 작성 완료 ({trace4.get('provider')} / {trace4.get('model')})", "draft")

    # Phase 4: Save
    add_log("💾 Phase 4: DB 저장 중...", "sys")
    save_result = db_service.save_log(user_input, legal_basis, strategy, doc_data)
    if "DB 저장 성공" in save_result:
        api_usage["supabase"]["used"] = True
    else:
        api_usage["supabase"]["error"] = save_result

    add_log(f"✅ 완료: {save_result}", "sys")
    time.sleep(0.6)
    log_placeholder.empty()

    return {
        "doc": doc_data,
        "meta": meta_info,
        "law": legal_basis,
        "search": search_results,
        "strategy": strategy,
        "save_msg": save_result,
        "api_usage": api_usage,
    }

# ==========================================
# 6) UI Helpers
# ==========================================
def render_api_usage(usage: dict):
    llm_calls = usage.get("llm_calls", [])
    serp = usage.get("serpapi", {})
    supa = usage.get("supabase", {})

    st.markdown("### 🔌 이번 업무 처리에서 사용된 API")

    # LLM calls
    if llm_calls:
        for c in llm_calls:
            ok = bool(c.get("ok"))
            step = c.get("step", "llm")
            provider = c.get("provider", "none")
            model = c.get("model", "")
            err = c.get("error", "")
            subtitle = f"{step}: {provider} / {model}" + (f" | error: {err}" if (not ok and err) else "")
            st.markdown(api_card("LLM 호출", ok, subtitle), unsafe_allow_html=True)
    else:
        st.markdown(api_card("LLM 호출", False, "호출 기록 없음"), unsafe_allow_html=True)

    # SerpApi
    if serp.get("used"):
        st.markdown(api_card("SerpApi (Google Search)", True, "유사사례 검색 수행"), unsafe_allow_html=True)
    else:
        st.markdown(api_card("SerpApi (Google Search)", False, serp.get("error") or "미사용"), unsafe_allow_html=True)

    # Supabase
    if supa.get("used"):
        st.markdown(api_card("Supabase (DB)", True, "로그 저장 완료"), unsafe_allow_html=True)
    else:
        st.markdown(api_card("Supabase (DB)", False, supa.get("error") or "미사용"), unsafe_allow_html=True)

# ==========================================
# 7) Presentation Layer (Main)
# ==========================================
def main():
    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.title("🏢 AI 행정관 Pro")
        st.caption("Gemini + Groq + Search + Strategy + DB + API Trace")
        st.markdown("---")

        st.markdown("### 🧾 기본 정보")
        dept = st.text_input("부서(과)명", value=st.session_state.get("dept", "차량민원과"))
        officer = st.text_input("담당자(주무관)", value=st.session_state.get("officer", "OOO"))
        st.session_state["dept"] = dept
        st.session_state["officer"] = officer

        st.markdown("### 🗣️ 업무 지시")
        user_input = st.text_area(
            "업무 내용",
            height=150,
            placeholder="예시:\n- 아파트 단지 내 소방차 전용구역 불법 주차 차량에 대한 조치(계도/과태료) 안내문 초안 작성",
            label_visibility="collapsed",
        )

        if st.button("⚡ 스마트 행정 처분 시작", type="primary", use_container_width=True):
            if not user_input.strip():
                st.warning("내용을 입력해주세요.")
            else:
                try:
                    with st.spinner("AI 에이전트 팀이 협업 중입니다..."):
                        st.session_state["workflow_result"] = run_workflow(
                            user_input=user_input.strip(),
                            dept=dept.strip(),
                            officer=officer.strip(),
                        )
                except Exception as e:
                    st.error(f"시스템 오류 발생: {e}")

        if "workflow_result" in st.session_state:
            res = st.session_state["workflow_result"]

            st.markdown("---")

            # DB 결과
            if "성공" in (res.get("save_msg") or ""):
                st.success(f"✅ {res.get('save_msg')}")
            else:
                st.error(f"❌ {res.get('save_msg')}")

            # API 사용 내역 표시 (요청사항)
            render_api_usage(res.get("api_usage", {}))

            # 법령/검색
            with st.expander("✅ [검토] 법령 및 유사 사례 확인", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**📜 적용 법령**")
                    st.code(res.get("law", ""), language="text")
                with c2:
                    st.markdown("**🌍 유사 사례**")
                    st.info(res.get("search", ""))

            # 전략
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

            # HTML은 왼쪽 끝에 붙여서(렌더 안정)
            html_parts = []
            html_parts.append('<div class="paper-sheet">')
            html_parts.append('<div class="stamp">직인생략</div>')
            html_parts.append(f'<div class="doc-header">{html_escape(str(doc.get("title","공 문 서")))}</div>')
            html_parts.append('<div class="doc-info">')
            html_parts.append(f'<span>문서번호: {html_escape(str(meta.get("doc_num","")))}</span>')
            html_parts.append(f'<span>시행일자: {html_escape(str(meta.get("today_str","")))}</span>')
            html_parts.append(f'<span>수신: {html_escape(str(doc.get("receiver","수신자 참조")))}</span>')
            html_parts.append(f'<span>부서: {html_escape(str(doc.get("_dept", st.session_state.get("dept",""))))}</span>')
            html_parts.append(f'<span>담당: {html_escape(str(doc.get("_officer", st.session_state.get("officer",""))))}</span>')
            html_parts.append("</div>")
            html_parts.append('<hr style="border: 1px solid black; margin-bottom: 30px;">')
            html_parts.append('<div class="doc-body">')
            for p in paragraphs:
                html_parts.append(f"<p style='margin-bottom: 15px;'>{html_escape(str(p))}</p>")
            html_parts.append("</div>")
            html_parts.append(f'<div class="doc-footer">{html_escape(str(doc.get("department_head","행정기관장")))}</div>')
            html_parts.append("</div>")

            st.markdown("".join(html_parts), unsafe_allow_html=True)

        else:
            st.markdown(
                """
<div style="text-align:center; padding:100px; color:#aaa; background:white; border-radius:10px; border:2px dashed #ddd;">
  <h3>📄 Document Preview</h3>
  <p>왼쪽에서 업무를 지시하면<br>완성된 공문서가 여기에 나타납니다.</p>
</div>
""",
                unsafe_allow_html=True,
            )

if __name__ == "__main__":
    main()
