import streamlit as st
import io
import time
import html
import requests
import xml.etree.ElementTree as ET
from PIL import Image

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
    from supabase import create_client
except Exception:
    create_client = None

try:
    from smolagents import CodeAgent, Tool
except Exception:
    CodeAgent = None
    Tool = object  # fallback


# ==========================================
# 1. 화면 설정 및 스타일 (API 시각화 포함)
# ==========================================
st.set_page_config(layout="wide", page_title="AI 행정관: AMP System", page_icon="🏛️")

st.markdown(
    """
<style>
    .stApp { background-color: #f8f9fa; }

    /* 실시간 API 로그 박스 스타일 */
    .log-box {
        padding: 12px; border-radius: 6px; margin-bottom: 8px;
        font-family: 'Consolas', monospace; font-size: 0.9em;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        animation: fadeIn 0.3s ease-in-out;
        white-space: pre-wrap;
        line-height: 1.45;
    }
    .log-law   { background-color: #eff6ff; border-left: 5px solid #3b82f6; color: #1e3a8a; }
    .log-naver { background-color: #f0fdf4; border-left: 5px solid #22c55e; color: #14532d; }
    .log-db    { background-color: #fef2f2; border-left: 5px solid #ef4444; color: #7f1d1d; }
    .log-brain { background-color: #f3f4f6; border-left: 5px solid #6b7280; color: #1f2937; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

    .result-card {
        background: white;
        padding: 26px;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
</style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# Utils
# ==========================================
def _safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        try:
            cur = cur[k]
        except Exception:
            return default
    return cur


def log_box(kind: str, msg: str):
    css = {
        "law": "log-box log-law",
        "naver": "log-box log-naver",
        "db": "log-box log-db",
        "brain": "log-box log-brain",
    }.get(kind, "log-box log-brain")
    st.markdown(f"<div class='{css}'>{html.escape(msg)}</div>", unsafe_allow_html=True)


def have_secret(path_a, path_b=None):
    try:
        if path_b is None:
            return path_a in st.secrets
        return path_a in st.secrets and path_b in st.secrets[path_a]
    except Exception:
        return False


# ==========================================
# 2. 엔진 어댑터 (Groq & Gemini)
# ==========================================
class GroqAdapter:
    """
    smolagents CodeAgent가 model을 호출하는 방식이 환경/버전별로 조금 달라서
    아래처럼 "문자열 프롬프트" / "messages 리스트" 둘 다 처리하도록 만든 어댑터.
    """

    def __init__(self):
        if Groq is None:
            raise RuntimeError("groq 패키지가 설치되어 있지 않습니다. requirements.txt에 groq 추가 필요")

        key = _safe_get(st.secrets, "general", "GROQ_API_KEY")
        if not key:
            raise RuntimeError("st.secrets['general']['GROQ_API_KEY'] 가 없습니다.")

        self.client = Groq(api_key=key)
        self.model = "llama-3.3-70b-versatile"

    def _chat(self, messages, stop_sequences=None, temperature=0.1):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stop=stop_sequences,
            temperature=temperature,
        )
        return completion.choices[0].message.content

    def __call__(self, *args, **kwargs):
        """
        - (messages, stop_sequences=...) 형태
        - (prompt_str) 형태
        둘 다 지원
        """
        stop_sequences = kwargs.get("stop_sequences") or kwargs.get("stop")
        temperature = kwargs.get("temperature", 0.1)

        try:
            # Case 1) messages 형태로 들어오는 경우
            if args and isinstance(args[0], list):
                return self._chat(args[0], stop_sequences=stop_sequences, temperature=temperature)

            # Case 2) 문자열 prompt로 들어오는 경우
            if args and isinstance(args[0], str):
                prompt = args[0]
                messages = [
                    {"role": "system", "content": "You are a helpful assistant for Korean public administration."},
                    {"role": "user", "content": prompt},
                ]
                return self._chat(messages, stop_sequences=stop_sequences, temperature=temperature)

            # Case 3) kwargs에 messages가 있을 수도 있음
            messages = kwargs.get("messages")
            if isinstance(messages, list):
                return self._chat(messages, stop_sequences=stop_sequences, temperature=temperature)

            return "Error: GroqAdapter 호출 형식을 인식하지 못했습니다."
        except Exception as e:
            return f"Error: {e}"


def analyze_image_gemini(image_bytes: bytes) -> str:
    """Gemini 1.5 Flash로 이미지 분석 (없으면 자동 비활성화)"""
    if genai is None:
        return "이미지 분석 비활성화: google-generativeai 미설치"

    api_key = _safe_get(st.secrets, "general", "GEMINI_API_KEY")
    if not api_key:
        return "이미지 분석 비활성화: GEMINI_API_KEY 미설정"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        img = Image.open(io.BytesIO(image_bytes))
        log_box("brain", "👁️ [Vision] Gemini가 현장 사진을 정밀 분석 중...")

        resp = model.generate_content(
            [
                "다음 이미지(공문서/현장사진)의 내용을 한국어로 매우 상세히 텍스트로 서술하시오. "
                "숫자, 주소, 날짜, 문서번호, 기관명, 표/도장/직인 표기까지 가능한 한 그대로 추출하시오.",
                img,
            ]
        )
        return getattr(resp, "text", "") or "이미지 분석 결과가 비어있습니다."
    except Exception as e:
        return f"이미지 분석 실패: {e}"


# ==========================================
# 3. 도구 (Tools) - API 호출 시각화 적용
# ==========================================
# smolagents 없으면 Tool 기반 자체 실행이 불가능하므로 사전에 막아줌
if CodeAgent is None:
    st.error("smolagents가 설치되어 있지 않습니다. requirements.txt에 smolagents를 추가하세요.")
    st.stop()


class OfficialLawApiTool(Tool):
    name = "search_law_api"
    description = "국가법령정보센터 API를 호출하여 법령 원문(검색 결과)을 조회합니다."
    inputs = {"query": {"type": "string", "description": "검색할 법령명 (예: 도로교통법)"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            return "검색어가 비어있습니다."

        log_box("law", f"🏛️ [Analyst] 국가법령정보센터 조회: '{q}'")

        api_id = _safe_get(st.secrets, "general", "LAW_API_ID")
        if not api_id:
            return "LAW_API_ID 미설정(st.secrets['general']['LAW_API_ID'])"

        url = "https://www.law.go.kr/DRF/lawSearch.do"
        params = {
            "OC": api_id,
            "target": "law",
            "type": "XML",
            "query": q,
            "display": 3,
        }

        try:
            resp = requests.get(url, params=params, timeout=12)
            resp.raise_for_status()

            # law.go.kr XML이 가끔 인코딩/형식이 특이할 수 있어 방어
            content = resp.content
            try:
                root = ET.fromstring(content)
            except Exception:
                # 혹시 EUC-KR 같은 인코딩 이슈가 있으면 재시도
                text = resp.text
                root = ET.fromstring(text.encode("utf-8", errors="ignore"))

            laws = []
            for item in root.findall(".//law"):
                name_el = item.find("lawNm")
                link_el = item.find("lawDetailLink")
                name = name_el.text.strip() if (name_el is not None and name_el.text) else "법령명 불명"
                link = link_el.text.strip() if (link_el is not None and link_el.text) else ""
                tail = (link[-18:] if link else "")
                laws.append(f"- {name} (Link: ...{tail})")

            log_box("law", f"↳ 법령 데이터 수신 완료 ({len(laws)}건)")
            return "\n".join(laws) if laws else "검색 결과 없음"
        except Exception as e:
            return f"API 오류: {e}"


class NaverSearchTool(Tool):
    name = "search_naver"
    description = "네이버 검색(뉴스/블로그)을 통해 유사 사례/해석을 찾습니다."
    inputs = {"query": {"type": "string", "description": "검색어"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            return "검색어가 비어있습니다."

        log_box("naver", f"🌱 [Manager] 네이버 검색 API 호출: '{q}'")

        client_id = _safe_get(st.secrets, "naver", "CLIENT_ID")
        client_secret = _safe_get(st.secrets, "naver", "CLIENT_SECRET")
        if not client_id or not client_secret:
            return "네이버 API 키 미설정(st.secrets['naver']['CLIENT_ID'/'CLIENT_SECRET'])"

        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }

        res_txt = []
        # 1) 뉴스
        try:
            news = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers=headers,
                params={"query": q, "display": 1, "sort": "date"},
                timeout=12,
            ).json()
            items = news.get("items") or []
            if items:
                res_txt.append(f"[뉴스] {items[0].get('title','').replace('<b>','').replace('</b>','')}")
        except Exception as e:
            res_txt.append(f"[뉴스] 오류: {e}")

        # 2) 블로그
        try:
            blog = requests.get(
                "https://openapi.naver.com/v1/search/blog.json",
                headers=headers,
                params={"query": q + " 판례 행정해석", "display": 1, "sort": "date"},
                timeout=12,
            ).json()
            items = blog.get("items") or []
            if items:
                res_txt.append(f"[블로그] {items[0].get('title','').replace('<b>','').replace('</b>','')}")
        except Exception as e:
            res_txt.append(f"[블로그] 오류: {e}")

        log_box("naver", "↳ 여론/사례 데이터 수신 완료")
        out = "\n".join([x for x in res_txt if x.strip()])
        return out if out else "결과 없음"


class DBTool(Tool):
    name = "save_record"
    description = "처리 결과를 Supabase DB에 저장합니다."
    inputs = {"summary": {"type": "string", "description": "저장할 내용"}}
    output_type = "string"

    def forward(self, summary: str) -> str:
        log_box("db", "💾 [Practitioner] Supabase DB 저장 시도...")

        if create_client is None:
            return "DB 저장 스킵: supabase 패키지 미설치"

        supa_url = _safe_get(st.secrets, "supabase", "SUPABASE_URL")
        supa_key = _safe_get(st.secrets, "supabase", "SUPABASE_KEY")
        if not supa_url or not supa_key:
            return "DB 저장 스킵: SUPABASE_URL/KEY 미설정"

        try:
            sb = create_client(supa_url, supa_key)

            text = (summary or "").strip()
            if not text:
                return "저장 스킵: summary가 비어있음"

            # 테이블명은 네가 쓰던 그대로
            sb.table("law_reports").insert({"summary": text}).execute()
            st.toast("DB 저장 성공!", icon="✅")
            return "저장 성공"
        except Exception as e:
            return f"저장 실패: {e}"


# ==========================================
# 4. 메인 실행 로직 (AMP 프롬프트)
# ==========================================
def main():
    st.title("🏛️ AI 행정관 Pro (AMP Edition)")
    st.caption("실시간 API 호출 시각화: 국가법령(Blue) / 네이버(Green) / DB(Red)")

    # 환경 점검 배너(조용히)
    with st.expander("⚙️ 런타임 체크(문제 생길 때만 열기)", expanded=False):
        st.write(
            {
                "groq_installed": Groq is not None,
                "gemini_installed": genai is not None,
                "supabase_installed": create_client is not None,
                "smolagents_installed": CodeAgent is not None,
                "GROQ_API_KEY": bool(_safe_get(st.secrets, "general", "GROQ_API_KEY")),
                "GEMINI_API_KEY": bool(_safe_get(st.secrets, "general", "GEMINI_API_KEY")),
                "LAW_API_ID": bool(_safe_get(st.secrets, "general", "LAW_API_ID")),
                "NAVER_KEYS": bool(_safe_get(st.secrets, "naver", "CLIENT_ID")) and bool(_safe_get(st.secrets, "naver", "CLIENT_SECRET")),
                "SUPABASE_KEYS": bool(_safe_get(st.secrets, "supabase", "SUPABASE_URL")) and bool(_safe_get(st.secrets, "supabase", "SUPABASE_KEY")),
            }
        )

    col1, col2 = st.columns([1, 1.1])

    with col1:
        st.subheader("📝 민원 접수")
        uploaded_file = st.file_uploader("증빙 서류/사진", type=["jpg", "png", "jpeg"])
        user_input = st.text_area("민원 내용", height=150, placeholder="내용을 입력하세요.")

        if st.button("🚀 업무 처리 시작", type="primary", use_container_width=True):
            if not user_input and not uploaded_file:
                st.warning("내용을 입력해주세요.")
                st.stop()

            # API 로그가 찍힐 컨테이너
            with st.status("🔄 AI 에이전트 팀이 협업 중입니다...", expanded=True) as status:
                # 1) Vision
                vision_res = ""
                if uploaded_file is not None:
                    vision_res = analyze_image_gemini(uploaded_file.getvalue())
                else:
                    vision_res = "첨부 이미지 없음"

                st.markdown("---")
                st.markdown("**🧠 Groq (Llama 3)가 AMP 프로토콜을 가동합니다.**")

                # AMP 시스템 프롬프트
                prompt = f"""
당신은 '행정관 팀 리더'입니다. 아래 민원을 3단계(AMP)로 처리하고,
각 단계에서 지정된 도구를 최소 1회 이상 반드시 사용하십시오.

[민원]
{user_input}

[사진분석(있으면)]
{vision_res}

[Step 1: Analyst (법률가)]
- 'search_law_api' 도구로 관련 법령을 조회하시오.
- 민원 사실관계에 비추어 위법/적법/불명확을 구분하시오.
- 판단 근거(조문/요지)를 간단히 제시하시오.

[Step 2: Manager (행정가)]
- 'search_naver' 도구로 유사 사례(판례/행정해석/보도 등)를 찾아 요지를 정리하시오.
- 가능한 조치(계도, 과태료, 행정처분, 타부서 이첩)를 옵션으로 제시하고,
  현장 실무 기준으로 '가장 합리적인 1안'을 선택하시오.

[Step 3: Practitioner (주무관)]
- 최종 결과물을 아래 중 민원 성격에 맞게 하나 작성하시오:
  1) 처분사전통지서(초안) 또는 2) 민원 답변서(공문 톤)
- 마지막에 'save_record' 도구로 요약(핵심 근거/조치/기한)을 저장하시오.

[출력 형식]
- Step 1/2/3을 명확한 제목으로 구분
- 최종 문서는 바로 복사해 공문에 붙일 수 있게 작성
"""

                # Agent Setup
                try:
                    model = GroqAdapter()
                except Exception as e:
                    status.update(label="❌ 모델 초기화 실패", state="error", expanded=True)
                    st.error(str(e))
                    st.stop()

                tools = [OfficialLawApiTool(), NaverSearchTool(), DBTool()]

                # [핵심] add_base_tools=False (DuckDuckGo 끄기)
                agent = CodeAgent(tools=tools, model=model, add_base_tools=False)

                try:
                    result = agent.run(prompt)
                    st.session_state["result"] = result
                    status.update(label="✅ 업무 처리 완료!", state="complete", expanded=False)
                except Exception as e:
                    status.update(label="❌ 실행 중 오류", state="error", expanded=True)
                    st.error(f"실행 중 오류: {e}")

    with col2:
        st.subheader("📄 최종 결과 보고서")
        if "result" in st.session_state and st.session_state["result"]:
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            # 결과는 기본적으로 마크다운으로 보여주는 게 제일 안전/호환 좋음
            st.markdown(st.session_state["result"])
            st.markdown("</div>", unsafe_allow_html=True)
            st.success("모든 절차가 법적/행정적 검토를 거쳐 완료되었습니다.")
        else:
            st.info("왼쪽에서 실행하면 API 호출 과정과 결과가 여기에 표시됩니다.")


if __name__ == "__main__":
    main()
