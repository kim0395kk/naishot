# civil_engineering/rag_system.py
"""
토목직 특화 RAG (Retrieval-Augmented Generation) 시스템
"""

import os
import json
import pickle
from typing import List, Dict, Optional, Tuple
import numpy as np

# 벡터 임베딩 (Optional)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available")

# 벡터 DB (Optional)
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss not available")


class CivilEngineeringRAG:
    """
    토목직 산업단지 전문 RAG 시스템
    """
    
    def __init__(self, 
                 complexes_data: List[Dict],
                 embedding_model: str = "distiluse-base-multilingual-cased-v2",
                 vector_db_path: str = "data/vector_db"):
        """
        초기화
        
        Args:
            complexes_data: 파싱된 산업단지 데이터 리스트
            embedding_model: 임베딩 모델명
            vector_db_path: 벡터 DB 저장 경로
        """
        self.complexes_data = complexes_data
        self.vector_db_path = vector_db_path
        self.chunks = []
        self.embeddings = None
        self.index = None
        self.model_name = embedding_model
        
        # 임베딩 모델 로드
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer(embedding_model)
            except Exception as e:
                print(f"Failed to load sentence-transformer: {e}")
                self.embedding_model = None
        else:
            self.embedding_model = None
            print("(!) 임베딩 모델 없음 - 키워드 검색만 사용")
        
        # 데이터 준비
        self._prepare_chunks()
        
        # 벡터 DB 로드 또는 생성
        if os.path.exists(f"{vector_db_path}/index.faiss"):
            self._load_index()
        else:
            self._build_index()
    
    def _prepare_chunks(self):
        """청크 생성"""
        from civil_engineering.data_parser import create_search_chunks
        
        for complex_data in self.complexes_data:
            chunks = create_search_chunks(complex_data)
            self.chunks.extend(chunks)
        
        print(f"(+) {len(self.chunks)}개 청크 생성 완료")
    
    def _build_index(self):
        """벡터 인덱스 구축"""
        if not self.embedding_model:
            print("(!) 임베딩 모델 없음 - 인덱스 구축 스킵")
            return
        
        print("(*) 벡터 인덱스 구축 중...")
        
        try:
            # 텍스트 임베딩 생성
            texts = [chunk['text'] for chunk in self.chunks]
            self.embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
            
            # FAISS 인덱스 생성
            if FAISS_AVAILABLE:
                dimension = self.embeddings.shape[1]
                self.index = faiss.IndexFlatL2(dimension)
                self.index.add(self.embeddings.astype('float32'))
                
                # 저장
                os.makedirs(self.vector_db_path, exist_ok=True)
                faiss.write_index(self.index, f"{self.vector_db_path}/index.faiss")
                
                with open(f"{self.vector_db_path}/chunks.pkl", "wb") as f:
                    pickle.dump(self.chunks, f)
                
                print(f"(+) 벡터 인덱스 저장 완료: {self.vector_db_path}")
            else:
                print("(!) FAISS 없음 - 인덱스 저장 스킵")
        except Exception as e:
            print(f"(!) 인덱스 구축 중 오류: {e}")
    
    def _load_index(self):
        """저장된 인덱스 로드"""
        if not FAISS_AVAILABLE:
            return
        
        try:
            self.index = faiss.read_index(f"{self.vector_db_path}/index.faiss")
            
            with open(f"{self.vector_db_path}/chunks.pkl", "rb") as f:
                self.chunks = pickle.load(f)
            
            print(f"(+) 벡터 인덱스 로드 완료: {len(self.chunks)}개 청크")
        except Exception as e:
            print(f"(!) 인덱스 로드 실패 (재구축 시도): {e}")
            self._build_index()
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        """
        쿼리에 대한 관련 청크 검색
        
        Args:
            query: 검색 질문
            top_k: 반환할 상위 결과 개수
        
        Returns:
            [(청크, 유사도 점수), ...] 리스트
        """
        
        # 벡터 검색 (임베딩 모델 있을 때)
        if self.embedding_model and self.index:
            try:
                query_embedding = self.embedding_model.encode([query])
                distances, indices = self.index.search(query_embedding.astype('float32'), top_k)
                
                results = []
                for i, idx in enumerate(indices[0]):
                    if idx < len(self.chunks) and idx >= 0:
                        chunk = self.chunks[idx]
                        score = 1 / (1 + distances[0][i])  # 거리를 유사도로 변환
                        results.append((chunk, score))
                
                return results
            except Exception as e:
                print(f"Vector search failed: {e}")
                return self._keyword_search(query, top_k)
        
        # Fallback: 키워드 검색
        else:
            return self._keyword_search(query, top_k)
    
    def _keyword_search(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        """키워드 기반 검색 (Fallback)"""
        keywords = query.split()
        
        scored_chunks = []
        for chunk in self.chunks:
            score = sum(1 for kw in keywords if kw in chunk['text'])
            if score > 0:
                scored_chunks.append((chunk, score))
        
        # 점수 순 정렬
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        # 점수 정규화
        max_score = scored_chunks[0][1] if scored_chunks else 1
        normalized = [(chunk, score / max_score) for chunk, score in scored_chunks[:top_k]]
        
        return normalized
    
    def answer_question(self, question: str, llm_service, top_k: int = 3) -> Dict:
        """
        질문에 대한 답변 생성 (RAG)
        
        Args:
            question: 사용자 질문
            llm_service: LLM 서비스 인스턴스 (generate_text 메서드 보유)
            top_k: 컨텍스트로 사용할 청크 수
        
        Returns:
            {
                "answer": "답변 텍스트",
                "sources": ["출처1", "출처2"],
                "confidence": 0.0~1.0
            }
        """
        
        # 1. 관련 청크 검색
        search_results = self.search(question, top_k)
        
        if not search_results:
            # 검색 결과가 없으면 LLM 지식으로 답변 시도 (단, 경고 메시지 포함)
            print(f"(!) 검색 결과 없음 -> LLM 일반 지식 활용: {question}")
            
            fallback_prompt = f"""
당신은 토목 행정 전문가입니다. 
사용자의 질문에 대해 당신이 가진 일반적인 토목/행정 지식을 바탕으로 친절하게 답변해 주세요.

[중요 제약사항]
답변의 맨 앞부분에 반드시 다음 경고 문구를 포함해야 합니다.
"⚠️ **내부 규정이나 매뉴얼에서 관련 내용을 찾을 수 없습니다.** 아래 내용은 일반적인 토목 지식에 기반한 답변이므로, 정확한 업무 처리를 위해서는 반드시 관련 규정을 별도로 확인하시기 바랍니다."

[질문]
{question}
"""
            # LLM 호출
            try:
                llm_answer = llm_service.generate_text(fallback_prompt)
            except Exception as e:
                llm_answer = "죄송합니다. 관련 정보를 찾을 수 없으며, 일반 지식 답변 생성 중 오류가 발생했습니다."
                print(f"(!) LLM Fallback Error: {e}")

            return {
                "answer": llm_answer,
                "sources": ["⚠️ 일반 지식 (내부 문서 없음)"],
                "confidence": 0.1,
                "raw_chunks": []
            }
        
        # 2. 컨텍스트 구성
        context_parts = []
        sources = []
        
        for chunk, score in search_results:
            # 메타데이터 기반 출처 표시 (산업단지 vs 업무매뉴얼)
            if chunk.get('metadata', {}).get('type') == 'manual':
                source_name = f"{chunk['complex_name']} (매뉴얼)"
            else:
                source_name = f"{chunk['complex_name']} ({chunk.get('type', 'general')})"
            
            context_parts.append(f"[{source_name}]\n{chunk['text']}")
            sources.append(source_name)
        
        context = "\n\n---\n\n".join(context_parts)
        
        # 3. LLM에 질문
        prompt = f"""
당신은 토목 행정 전문가입니다. 다음 [참고 자료]를 바탕으로 공무원의 질문에 답변하세요.

[참고 자료]
{context}

[질문]
{question}


[참고 자료]
{context}

[질문]
{question}

[답변 규칙]
- 참고 자료에 있는 정보만 사용
- 구체적인 숫자, 날짜, 명칭 정확히 인용
- 없는 정보는 "자료에 없음"이라고 명시
- 간결하고 명확하게 답변
- 한국어로 답변

답변:
"""
        
        try:
            # llm_service가 generate_text 메서드를 가지고 있다고 가정
            answer = llm_service.generate_text(prompt)
            
            # 평균 신뢰도 계산
            avg_confidence = sum(score for _, score in search_results) / len(search_results)
            
            return {
                "answer": answer,
                "sources": list(set(sources)),  # 중복 제거
                "confidence": avg_confidence,
                "raw_chunks": [chunk for chunk, _ in search_results]
            }
            
        except Exception as e:
            return {
                "answer": f"답변 생성 중 오류: {str(e)}",
                "sources": sources,
                "confidence": 0.0,
                "raw_chunks": []
            }


# ===== 편의 함수 =====

def load_rag_system(data_path: str = "data/parsed_complexes.json",
                    vector_db_path: str = "data/vector_db") -> Optional[CivilEngineeringRAG]:
    """
    RAG 시스템 로드
    
    Args:
        data_path: 파싱된 데이터 JSON 경로
        vector_db_path: 벡터 DB 경로
    
    Returns:
        CivilEngineeringRAG 인스턴스 또는 None
    """
    
    try:
        # 1. JSON 데이터 로드 시도
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                complexes_data = json.load(f)
        else:
            # JSON 없으면 MD 파일들 찾아서 파싱
            import glob
            from civil_engineering.data_parser import parse_all_md_files
            
            # llm_ready_docs 폴더 사용
            md_files = glob.glob(r"c:\Users\Mr Kim\Desktop\chungsim\llm_ready_docs\*.md")
            if not md_files:
                # 상대 경로 fallback
                md_files = glob.glob("llm_ready_docs/*.md")
            
            if not md_files:
                print("(!) MD 파일을 찾을 수 없습니다.")
                return None
                
            print(f"(+) MD 파일 {len(md_files)}개 파싱 시작...")
            complexes_data = parse_all_md_files(md_files)
            
            # 파싱 결과 저장 (캐싱)
            os.makedirs(os.path.dirname(data_path), exist_ok=True)
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(complexes_data, f, ensure_ascii=False, indent=2)
            print("(+) 파싱 데이터 캐싱 완료")
        
        # 2. RAG 시스템 초기화
        rag = CivilEngineeringRAG(complexes_data, vector_db_path=vector_db_path)
        
        return rag
        
    except Exception as e:
        print(f"(!) RAG 시스템 로드 실패: {e}")
        import traceback
        traceback.print_exc()
        return None
