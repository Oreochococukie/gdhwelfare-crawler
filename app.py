import streamlit as st
import subprocess
import sys
import pandas as pd
import time
from datetime import datetime, timedelta
import io

# ------------------------------------------------------
# [핵심] Streamlit Cloud에서 Playwright 브라우저 강제 설치
# ------------------------------------------------------
@st.cache_resource
def install_playwright_browser():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"❌ 설치 중 오류 발생: {e}")

install_playwright_browser()

from playwright.sync_api import sync_playwright

# ------------------------------------------------------
# 크롤링 로직
# ------------------------------------------------------

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%Y.%m.%d')
        except:
            return None

def scroll_to_bottom(page):
    """스크롤을 부드럽게 내려서 데이터 로딩 유도"""
    try:
        # 한 번에 확 내리지 않고 나눠서 내림 (데이터 로딩 트리거)
        for _ in range(3):
            page.keyboard.press("End")
            time.sleep(0.5)
    except:
        pass

def scrape_with_period(start_date, end_date, progress_bar):
    data = []
    # URL 뒤에 불필요한 파라미터 제거하고 pageIndex만 딱 바꿈
    base_url = "https://www.gdhwelfare.or.kr/community/PhotoList.do?pageIndex={}"
    page_index = 1
    max_pages = 50 # 안전을 위해 최대 페이지 제한 (필요시 늘리세요)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        # 모바일 뷰포트로 설정하면 리스트가 더 단순하게 나올 수 있음 (선택사항)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        try:
            while page_index <= max_pages:
                progress = page_index / max_pages
                progress_bar.progress(progress, text=f"📄 {page_index}페이지 읽는 중...")
                
                url = base_url.format(page_index)
                
                try:
                    # [핵심 수정] networkidle -> domcontentloaded (뼈대만 오면 통과)
                    # 타임아웃도 30초로 줄여서 빨리빨리 넘어가게 함
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except Exception as e:
                    st.error(f"{page_index}페이지 접속 실패 (재시도 필요): {e}")
                    page_index += 1
                    continue

                # 리스트 요소가 뜰 때까지 잠깐 대기 (최대 3초)
                try:
                    page.wait_for_selector(".list_in", state="attached", timeout=3000)
                except:
                    # 리스트가 안 뜨면 데이터가 없거나 로딩 실패로 간주
                    st.write(f"⚠️ {page_index}페이지에 게시물이 없거나 로딩이 늦습니다.")
                    break
                
                scroll_to_bottom(page)
                
                items = page.query_selector_all(".list_in")
                if not items:
                    st.write("게시물 없음, 종료합니다.")
                    break
                
                page_has_valid = False
                current_page_collected = 0
                
                for item in items:
                    try:
                        title_elem = item.query_selector(".bold.ellipsis")
                        date_elem = item.query_selector(".photo_info > span:nth-child(2)")
                        # [추가] 작성자 엘리먼트 선택자
                        author_elem = item.query_selector(".photo_info > span:nth-child(1)")
                        
                        if title_elem and date_elem:
                            Title_ = title_elem.inner_text().strip()
                            Date_str = date_elem.inner_text().strip()
                            # [추가] 작성자 텍스트 추출 (없을 경우 '미상' 처리)
                            Author_ = author_elem.inner_text().strip() if author_elem else "미상"

                            upload_date = parse_date(Date_str)
                            
                            if upload_date:
                                # 기간 내 데이터
                                if start_date <= upload_date <= end_date:
                                    # [수정] 데이터 저장 순서 변경: 제목 -> 작성자 -> 날짜
                                    data.append([Title_, Author_, Date_str])
                                    page_has_valid = True
                                    current_page_collected += 1
                                # 기간 지난 데이터 (과거 데이터) 나오면 종료
                                elif upload_date < start_date:
                                    st.success(f"⏹️ 설정된 기간({start_date.date()}) 이전 데이터 도달. 크롤링 종료.")
                                    return data
                    except Exception:
                        continue
                
                # 로그 출력 (디버깅용)
                # st.write(f"✅ {page_index}페이지: {current_page_collected}건 수집")

                # 이번 페이지에 유효한 데이터가 하나도 없고, 이미 과거 날짜도 아니라면? (빈 페이지 등)
                if not page_has_valid and current_page_collected == 0:
                    # 혹시 모르니 다음 페이지도 한 번 더 가보게 할 수도 있지만, 보통은 여기서 끝냄
                    pass 
                
                page_index += 1
                # 너무 빨리 요청하면 서버가 차단할 수 있으니 0.5초 휴식
                time.sleep(0.5)
            
            return data
        finally:
            browser.close()
    
    return data

# UI 설정
st.set_page_config(page_title="GD 복지 크롤러", page_icon="🐢")

st.title("🐢 GD 복지 사진 게시물 크롤러")
st.markdown("Playwright 엔진 (고속 모드) 가동 중")

st.sidebar.header("📅 설정")
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.sidebar.date_input("시작 날짜", value=datetime.now() - timedelta(days=30))
with col2:
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now())

if st.button("🚀 크롤링 시작", type="primary"):
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.min.time())
    
    progress_bar = st.progress(0)
    data = scrape_with_period(start_dt, end_dt, progress_bar)
    progress_bar.progress(1.0, text="완료!")
    
    if data:
        # [수정] DataFrame 컬럼 순서 변경: 제목, 작성자, 날짜
        df = pd.DataFrame(data, columns=['제목', '작성자', '날짜'])
        st.success(f"총 {len(data)}건 수집 완료!")
        st.dataframe(df)
        
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        st.download_button(
            label="📥 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"gd_welfare_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("수집된 데이터가 없습니다. 기간을 확인해주세요.")
