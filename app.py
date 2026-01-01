import streamlit as st
import io
import time
import re
import html
import requests
import xml.etree.ElementTree as ET
from PIL import Image

# =========================
# Optional imports (안죽게)
# =========================
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from supabase import create_client
except Exception:
    create_client = None


# ==========================================
# 1) Page & Style
# ==========================================
st.set_page_config(layout="wide", page_title="AI 행정관: AMP System", page_icon="🏛️")

st.markdown(
    """
<style>
    .stApp { background-color: #f8f9fa; }

    .log-box {
        padding: 12px; border-radius: 6px; margin-bottom: 8px;
        font-family: 'Consolas', monospace; font-size: 0.92em;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        animation: fadeIn 0.2s ease-in-out;
        white-space: pre-wrap;
        line-height: 1.45;
    }
    .log-law   { background-color: #eff6ff; border-left: 5px solid #3b82f6; color: #1e3a8a; }
    .log-naver { background-color: #f0fdf4; border-left: 5px solid #22c55e; color: #14532d; }
    .log-db    { background-color: #fef2f2; border-left: 5px solid #ef4444; color: #7f1d1d; }
    .log-brain { background-color: #f3f4f6; border-left: 5px solid #6b7280; color: #111827; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px);} to { opacity: 1; transform: translateY(0);} }

    .result-card {
        background: white;
        padding: 26px;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    .small-muted { color:#6b7280; font-size:0.9em; }
</style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# 2) Utils
# ==========================================
def log_box(kind: str, msg: str):
    css = {
        "law": "log-box log-law",
        "naver": "log-box log-naver",
        "db": "log-box log-db",
        "brain": "log-box log-brain",
    }.get(kind, "log-box log-brain")
    st.markdown(f"<div class='{css}'>{html.escape(msg)}</div>", unsafe_allow_html=True)


def sget(*path, default=None):
    """st.secrets safe getter: sget("general","GROQ_API_KEY")"""
    cur = st.secrets
    try:
        for p in path:
            cur = cur[p]
        return cur
    except Exception:
        return default


def clean_html_tags(text: str) -> str:
    if not text:
        return ""
    # 네이버 API title에 <b>가 들어오니 제거
    return re.sub(r"</?b>", "", text)


# ==========================================
# 3) External Calls (LAW / NAVER / VISION / DB)
# ==========================================
def call_law_api(query: str, display: int = 5) -> dict:
    """
    국가법령정보센터 DRF lawSearch 호출
    반환: {"items":[{"name":..,"link":..},...], "raw": "..."} 형태
    """
    q = (query or "").strip()
    if not q:
        return {"items": [], "raw": "검색어가 비어있습니다."}

    api_id = sget("general", "LAW_API_ID")
    if not api_id:
        return {"items": [], "raw": "LAW_API_ID 미설정(st.secrets['general']['LAW_API_ID'])"}

    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": api_id,
        "target": "law",
        "type": "XML",
        "query": q,
        "display": int(display),
    }

    log_box("law", f"🏛️ [Step1-LAW] 국가법령정보센터 조회: '{q}'")
    try:
        resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()

        # XML 파싱 (가끔 인코딩 문제 방어)
        content = resp.content
        try:
            root = ET.fromstring(content)
        except Exception:
            root = ET.fromstring(resp.text.encode("utf-8", errors="ignore"))

        items = []
        for law in root.findall(".//law"):
            nm = law.findtext("lawNm") or ""
            link = law.findtext("lawDetailLink") or ""
            nm = nm.strip()
            link = link.strip()
            if nm:
                items.append({"name": nm, "link": link})

        log_box("law", f"↳ 수신 완료: {len(items)}건")
        raw = "\n".join([f"- {it['name']} ({it['link'][-24:] if it['link'] else ''})" for it in items]) or "검색 결과 없음"
        return {"items": items, "raw": raw}

    except Exception as e:
        return {"items": [], "raw": f"API 오류: {e}"}


def call_naver_search(query: str) -> dict:
    """
    네이버 검색 API (뉴스 1건 + 블로그 1건)
    반환: {"news": {...}|None, "blog": {...}|None, "raw":"..."}
    """
    q = (query or "").strip()
    if not q:
        return {"news": None, "blog": None, "raw": "검색어가 비어있습니다."}

    cid = sget("naver", "CLIENT_ID")
    csec = sget("naver", "CLIENT_SECRET")
    if not cid or not csec:
        return {"news": None, "blog": None, "raw": "네이버 API 키 미설정(naver.CLIENT_ID / CLIENT_SECRET)"}

    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}

    log_box("naver", f"🌱 [Step2-NAVER] 네이버 검색 호출: '{q}'")

    out_lines = []
    news_item = None
    blog_item = None

    try:
        news = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers=headers,
            params={"query": q, "display": 1, "sort": "date"},
            timeout=12,
        ).json()
        items = news.get("items") or []
        if items:
            it = items[0]
            news_item = {
                "title": clean_html_tags(it.get("title", "")),
                "link": it.get("link", ""),
                "description": clean_html_tags(it.get("description", "")),
                "pubDate": it.get("pubDate", ""),
            }
            out_lines.append(f"[뉴스] {news_item['title']}")

    except Exception as e:
        out_lines.append(f"[뉴스] 오류: {e}")

    try:
        blog = requests.get(
            "https://openapi.naver.com/v1/search/blog.json",
            headers=headers,
            params={"query": q + " 판례 행정해석", "display": 1, "sort": "date"},
            timeout=12,
        ).json()
        items = blog.get("items") or []
        if items:
            it = items[0]
            blog_item = {
                "title": clean_html_tags(it.get("title", "")),
                "link": it.get("link", ""),
                "description": clean_html_tags(it.get("description", "")),
                "postdate": it.get("postdate", ""),
            }
            out_lines.append(f"[블로그] {blog_item['title']}")

    except Exception as e:
        out_lines.append(f"[블로그] 오류: {e}")

    log_box("naver", "↳ 수신 완료")
    raw = "\n".join(out_lines) if out_lines else "결과 없음"
    return {"news": news_item, "blog": blog_item, "raw": raw}


def analyze_image_gemini(image_bytes: bytes) -> str:
    """
    Gemini Vision (있으면 사용, 없으면 OFF)
    """
    if genai is None:
        return "이미지 분석 OFF: google-generativeai 미설치"

    gkey = sget("general", "GEMINI_API_KEY")
    if not gkey:
        return "이미지 분석 OFF: GEMINI_API_KEY 미설정"

    try:
        genai.configure(api_key=gkey)
        model = genai.GenerativeModel("gemini-1.5-flash")
        img = Image.open(io.BytesIO(image_bytes))

        log_box("brain", "👁️ [Vision] Gemini가 첨부 이미지를 분석 중...")

        resp = model.generate_content(
            [
                "다음 이미지(공문/현장사진)의 내용을 한국어로 상세히 텍스트화 하시오. "
                "문서번호/기관명/주소/날짜/표/직인 관련 표기까지 최대한 원문 형태로.",
                img,
            ]
        )
        return getattr(resp, "text", "") or "이미지 분석 결과가 비어있습니다."
    except Exception as e:
        return f"이미지 분석 실패: {e}"


def save_to_supabase(summary: str) -> str:
    """
    Supabase law_reports 테이블에 저장
    """
    log_box("db", "💾 [DB] Supabase 저장 시도...")

    if create_client is None:
        return "DB 저장 스킵: supabase 패키지 미설치"

    url = sget("supabase", "SUPABASE_URL")
    key = sget("supabase", "SUPABASE_KEY")
    if not url or not key:
        return "DB 저장 스킵: SUPABASE_URL/KEY 미설정"

    text = (summary or "").strip()
    if not text:
        return "DB 저장 스킵: summary가 비어있음"

    try:
        sb = create_client(url, key)
        sb.table("law_reports").insert({"summary": text}).execute()
        st.toast("DB 저장 성공!", icon="✅")
        return "저장 성공"
    except Exception as e:
        return f"저장 실패: {e}"


# ==========================================
# 4) Groq LLM (문서 생성 전용)
# ==========================================
def groq_generate(prompt: str, temperature: float = 0.15) -> str:
    if Groq is None:
        return "LLM 오류: groq 패키지 미설치"

    gkey = sget("general", "GROQ_API_KEY")
    if not gkey:
        return "LLM 오류: GROQ_API_KEY 미설정"

    client = Groq(api_key=gkey)
    model = sget("general", "GROQ_MODEL", default="llama-3.3-70b-versatile")

    log_box("brain", f"🧠 [LLM] Groq 생성 호출 (model={model})")

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "너는 한국 지방행정 실무 + 행정법 + 공문서 작성 전문가다. 과장 없이 근거 중심으로 작성한다."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"LLM 오류: {e}"


# ==========================================
# 5) AMP Orchestrator (DDG 0% 직접 통제)
# ==========================================
def run_amp(mw_text: str, vision_text: str, law_query: str, naver_query: str, doc_type: str) -> str:
    """
    Step1: call_law_api
    Step2: call_naver_search
    Step3: groq_generate(최종 문서)
    + DB 저장(요약)
    """
    # Step1 (법령)
    law_res = call_law_api(law_query, display=5)
    law_raw = law_res["raw"]

    # Step2 (사례/여론)
    naver_res = call_naver_search(naver_query)
    naver_raw = naver_res["raw"]

    # Step3 (최종 문서 생성)
    # doc_type: "답변서" or "처분사전통지서"
    draft_instruction = {
        "답변서": "민원 답변 공문(국문) 형식으로 작성하라. 서두 인사→사안 판단→법적 근거→조치 가능/불가 및 안내→문의처 순으로.",
        "처분사전통지서": "처분사전통지서(초안) 형식으로 작성하라. 처분의 원인이 되는 사실, 법적 근거, 예정 처분 내용, 의견제출 기한/방법을 포함하라.",
    }.get(doc_type, "민원 답변 공문 형식으로 작성하라.")

    prompt = f"""
[입력-민원]
{mw_text}

[입력-사진 분석(있으면)]
{vision_text}

[Step1 결과-법령 API]
{law_raw}

[Step2 결과-네이버 검색]
{naver_raw}

[작성 지시]
- 위 Step1/2 결과를 근거로 사실관계를 정리하고, 실무적으로 가능한 조치만 제시하라.
- 근거 없는 단정 금지. 불명확하면 '추가 확인 필요'로 표시.
- {draft_instruction}

[출력 형식]
## Step 1: Analyst (법률 검토)
- 적용 가능 법령 후보
- 위법/적법/불명확 판단 및 이유

## Step 2: Manager (사례/해석)
- 유사 사례 요지(뉴스/블로그)
- 행정 조치 옵션(1안/2안/3안)과 추천 1안

## Step 3: Practitioner (최종 문서)
- 최종 문서 전문(복붙 가능)

## DB 저장용 요약(5줄)
- 핵심 근거/조치/기한/안내처
"""
    final_text = groq_generate(prompt, temperature=0.15)

    # DB 저장(요약만)
    summary = extract_db_summary(final_text)
    db_msg = save_to_supabase(summary)
    log_box("db", f"↳ {db_msg}")

    return final_text


def extract_db_summary(final_text: str) -> str:
    """
    'DB 저장용 요약(5줄)' 섹션이 있으면 그 부분을 저장.
    없으면 앞부분 일부를 저장.
    """
    if not final_text:
        return ""
    m = re.search(r"##\s*DB\s*저장용\s*요약.*?\n(.+)$", final_text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        tail = m.group(1).strip()
        # 너무 길면 컷
        return tail[:1800]
    return final_text.strip()[:1800]


# ==========================================
# 6) UI
# ==========================================
def main():
    st.title("🏛️ AI 행정관 Pro (AMP System) — DDG ZERO")
    st.caption("법령 API(Blue) / 네이버(Green) / DB(Red) / LLM&Vision(Gray)")

    with st.expander("⚙️ 런타임 체크(문제 생길 때만)", expanded=False):
        st.write(
            {
                "groq_installed": Groq is not None,
                "gemini_installed": genai is not None,
                "supabase_installed": create_client is not None,
                "GROQ_API_KEY": bool(sget("general", "GROQ_API_KEY")),
                "GEMINI_API_KEY": bool(sget("general", "GEMINI_API_KEY")),
                "LAW_API_ID": bool(sget("general", "LAW_API_ID")),
                "NAVER_KEYS": bool(sget("naver", "CLIENT_ID")) and bool(sget("naver", "CLIENT_SECRET")),
                "SUPABASE_KEYS": bool(sget("supabase", "SUPABASE_URL")) and bool(sget("supabase", "SUPABASE_KEY")),
            }
        )

    col1, col2 = st.columns([1, 1.1])

    with col1:
        st.subheader("📝 민원 접수")

        uploaded_file = st.file_uploader("증빙 서류/사진", type=["jpg", "png", "jpeg"])
        mw_text = st.text_area("민원 내용", height=170, placeholder="내용을 입력하세요.")

        st.markdown("### 🔎 검색 키워드(직접 통제)")
        st.caption("에이전트가 마음대로 검색어를 바꾸지 못하게, 여기서 사람이 키워드를 고정합니다.")

        law_query = st.text_input("법령 검색어(국가법령 API)", value="자동차관리법")
        naver_query = st.text_input("네이버 검색어(사례/해석)", value="자동차관리법 무단방치 과태료 행정처분")

        doc_type = st.radio("최종 산출물", ["답변서", "처분사전통지서"], horizontal=True)

        st.markdown("<div class='small-muted'>※ Gemini Vision / Supabase는 키가 없으면 자동으로 OFF/스킵됩니다.</div>", unsafe_allow_html=True)

        if st.button("🚀 AMP 실행", type="primary", use_container_width=True):
            if not mw_text and not uploaded_file:
                st.warning("민원 내용 또는 첨부파일 중 하나는 필요합니다.")
                st.stop()

            with st.status("🔄 AMP 3단계 처리 중...", expanded=True) as status:
                vision_text = "첨부 이미지 없음"
                if uploaded_file is not None:
                    vision_text = analyze_image_gemini(uploaded_file.getvalue())

                # 실제 AMP 실행
                result = run_amp(
                    mw_text=mw_text,
                    vision_text=vision_text,
                    law_query=law_query,
                    naver_query=naver_query,
                    doc_type=doc_type,
                )

                st.session_state["result"] = result
                status.update(label="✅ 완료", state="complete", expanded=False)

    with col2:
        st.subheader("📄 최종 결과")
        if st.session_state.get("result"):
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            st.markdown(st.session_state["result"])
            st.markdown("</div>", unsafe_allow_html=True)
            st.success("완료")
        else:
            st.info("왼쪽에서 실행하면 결과가 여기에 표시됩니다.")


if __name__ == "__main__":
    main()
