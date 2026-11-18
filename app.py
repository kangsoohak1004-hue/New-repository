"""게으름 탈출구: Streamlit 앱.
연결 정보가 없으면 세션 한정 체험 모드. 실제 가족 공유는 Supabase와 Secrets 필요.
"""
import base64
import calendar
import copy
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import streamlit as st
from PIL import Image
from supabase import create_client

st.set_page_config(page_title="게으름 탈출구", page_icon="🌱", layout="wide")
TODAY = datetime.now(ZoneInfo("Asia/Seoul")).date()
DAYS = ["월", "화", "수", "목", "금", "토", "일"]
SQL = '''create table if not exists public.family_planner (
 id text primary key,
 state jsonb not null default '{}'::jsonb,
 version bigint not null default 0
);
alter table public.family_planner enable row level security;
revoke all on public.family_planner from anon, authenticated;
'''
EXAMPLE = '''SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "서버 전용 service_role 키"
CHILD_PASSWORD = "자녀용-긴-비밀번호"
PARENT_PASSWORD = "부모님만-아는-다른-긴-비밀번호"
'''
st.markdown('''<style>
.stApp {background:#F7FAF8;}
[data-testid="stMetric"] {background:white; padding:16px; border-radius:16px; border:1px solid #DFEAE2;}
[data-testid="stSidebar"] {background:#EDF5EF;}
</style>''', unsafe_allow_html=True)


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def fresh_state():
    return {"schema": 3, "tasks": []}


def coins(items):
    return sum(int(t.get("coins", 0)) for t in items if t["status"] == "approved")


def week_stats(items, start, today):
    end = min(start + timedelta(days=6), today)
    due = [t for t in items if start.isoformat() <= t["day"] <= end.isoformat()]
    approved = sum(t["status"] == "approved" for t in due)
    return len(due), approved, approved / len(due) * 100 if due else None


if not st.session_state.get("started"):
    st.write("")
    st.write("")
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title("🌱 게으름탈출구")
        if st.button("우리 가족 시작하기", type="primary", use_container_width=True):
            st.session_state.started = True
            st.rerun()
        st.caption("게으름을 해결할 수 있는 최고의 앱")
    st.stop()

try:
    configured = all(str(st.secrets.get(k, "")).strip() for k in ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "CHILD_PASSWORD", "PARENT_PASSWORD"])
except Exception:
    configured = False

# 달력이 기본 진입 화면입니다. 로그인/설정은 사이드바에서만 진행합니다.
shared = False
parent = False
db = None
original = None
code = None
with st.sidebar:
    st.title("🌱 우리 가족")
    if not configured:
        st.info("체험 모드 · 이 브라우저 세션에서만 사용합니다. 새 세션에서는 기록이 사라질 수 있어요.")
        role = st.radio("체험할 화면", ["자녀", "부모님 체험"])
        parent = role == "부모님 체험"
        st.caption("부모님 체험은 기능 미리보기입니다. 실제 부모님 인증이 아닙니다.")
    else:
        if str(st.secrets["CHILD_PASSWORD"]) == str(st.secrets["PARENT_PASSWORD"]):
            st.error("부모님과 자녀 비밀번호를 다르게 설정해주세요.")
        else:
            saved_role = st.session_state.get("role")
            if saved_role:
                key = "PARENT_PASSWORD" if saved_role == "부모님" else "CHILD_PASSWORD"
                if not hmac.compare_digest(st.session_state.get("auth", ""), digest(st.secrets[key])):
                    for key_to_clear in ["role", "auth", "family_code"]:
                        st.session_state.pop(key_to_clear, None)
                    st.rerun()
            if "role" not in st.session_state:
                st.caption("달력은 바로 체험할 수 있어요. 가족과 실제 공유하려면 로그인하세요.")
                with st.form("login"):
                    role = st.selectbox("사용자", ["자녀", "부모님"])
                    password = st.text_input("비밀번호", type="password")
                    submit = st.form_submit_button("가족 로그인")
                if submit:
                    key = "PARENT_PASSWORD" if role == "부모님" else "CHILD_PASSWORD"
                    if hmac.compare_digest(digest(password), digest(st.secrets[key])):
                        st.session_state.role = role
                        st.session_state.auth = digest(st.secrets[key])
                        st.rerun()
                    else:
                        st.error("비밀번호를 확인해주세요.")
            else:
                parent = st.session_state.role == "부모님"
                st.write(f"**{st.session_state.role} 로그인됨**")
                try:
                    db = create_client(str(st.secrets["SUPABASE_URL"]), str(st.secrets["SUPABASE_SERVICE_ROLE_KEY"]))
                except Exception:
                    st.error("연결 정보를 확인해주세요.")
                if db and "family_code" not in st.session_state:
                    st.caption("가족 코드를 만들거나 받은 코드를 입력하세요.")
                    if st.button("가족 코드 생성"):
                        new_code = secrets.token_hex(5).upper()
                        try:
                            db.table("family_planner").insert({"id": "pair_" + digest(new_code), "state": fresh_state(), "version": 0}).execute()
                            st.session_state.family_code = new_code
                            st.rerun()
                        except Exception:
                            st.error("코드 생성 실패: 테이블 SQL과 연결 설정을 확인해주세요.")
                    with st.form("join"):
                        entered = st.text_input("가족 코드", max_chars=10).strip().upper()
                        join = st.form_submit_button("코드로 연결")
                    if join:
                        if len(entered) != 10 or any(c not in "0123456789ABCDEF" for c in entered):
                            st.error("10자리 코드를 확인해주세요.")
                        else:
                            try:
                                rows = db.table("family_planner").select("state").eq("id", "pair_" + digest(entered)).execute().data
                                if rows and rows[0]["state"].get("schema") in [2, 3]:
                                    st.session_state.family_code = entered
                                    st.rerun()
                                else:
                                    st.error("가족 코드를 찾지 못했습니다.")
                            except Exception:
                                st.error("코드 연결 실패. 저장소 설정을 확인해주세요.")
                if st.button("로그아웃"):
                    for k in ["role", "auth", "family_code"]:
                        st.session_state.pop(k, None)
                    st.rerun()
    with st.expander("관리자: 실제 가족 공유 연결"):
        st.caption("한 가족 전용 앱입니다. Supabase SQL Editor에서 SQL을 실행하고 Streamlit Settings → Secrets에 설정을 저장하세요. 체험 기록은 공유 저장소로 자동 이전되지 않습니다.")
        st.code(SQL, language="sql")
        st.code(EXAMPLE, language="toml")
        st.warning("서버 키와 비밀번호는 GitHub에 올리지 마세요. 부모님 비밀번호는 부모님만 보관하세요.")
    st.caption("사진에는 얼굴·학교·주소를 담지 마세요. 코인은 현금이 아닌 보상 점수입니다.")

if configured and db is not None and st.session_state.get("family_code"):
    code = st.session_state.family_code
    try:
        rows = db.table("family_planner").select("state,version").eq("id", "pair_" + digest(code)).execute().data
        if not rows:
            raise ValueError("missing family")
        original = rows[0]
        state = copy.deepcopy(original["state"])
        shared = True
    except Exception:
        st.error("가족 기록을 불러오지 못했어요. 새로고침하거나 사이드바에서 로그아웃 후 다시 연결하세요.")
        st.stop()
else:
    if "demo_state" not in st.session_state:
        st.session_state.demo_state = fresh_state()
    state = copy.deepcopy(st.session_state.demo_state)
    # 실제 로그인 없이 부모 승인 권한을 제공하는 것은 명시적 체험 모드에서만 허용합니다.
    if configured:
        parent = False

tasks = state.setdefault("tasks", [])


def save(message):
    if len(json.dumps(state).encode()) > 18_000_000:
        st.error("저장 공간이 가득 찼습니다. 부모님이 승인된 사진을 정리해주세요.")
        st.stop()
    if shared:
        try:
            changed = db.table("family_planner").update({"state": state, "version": original["version"] + 1}).eq("id", "pair_" + digest(code)).eq("version", original["version"]).execute().data
        except Exception:
            st.error("저장 실패. 연결 상태를 확인하고 다시 시도해주세요.")
            st.stop()
        if not changed:
            st.warning("다른 가족이 먼저 수정했어요. 새로고침 후 다시 시도하세요. 이번 변경은 저장되지 않았습니다.")
            st.stop()
    else:
        st.session_state.demo_state = copy.deepcopy(state)
    st.session_state.notice = message
    st.rerun()


head, refresh = st.columns([4, 1])
head.title("🌱 게으름탈출구")
if refresh.button("🔄 새로고침", use_container_width=True):
    st.rerun()
if shared:
    st.caption(f"가족 연결됨 · 코드 {code} · {'부모님' if parent else '자녀'} 화면")
else:
    st.caption("🧪 체험 기록 · 가족 간 공유되지 않으며 영구 저장을 보장하지 않습니다. 실제 가족 연결은 왼쪽 메뉴에서 설정하세요.")
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))
nav = st.radio("메뉴", ["📅 달력", "📊 통계", f"🪙 코인 {coins(tasks):,}"], horizontal=True, label_visibility="collapsed")

if nav == "📅 달력":
    if "month" not in st.session_state:
        st.session_state.month = TODAY.replace(day=1)
    month = st.session_state.month
    left, mid, right = st.columns([1, 3, 1])
    if left.button("← 이전 달", use_container_width=True):
        st.session_state.month = (month - timedelta(days=1)).replace(day=1)
        st.rerun()
    mid.subheader(f"{month.year}년 {month.month}월")
    if right.button("다음 달 →", use_container_width=True):
        st.session_state.month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.rerun()
    for col, name in zip(st.columns(7), DAYS):
        col.markdown(f"**{name}**")
    for week in calendar.Calendar().monthdatescalendar(month.year, month.month):
        for col, day in zip(st.columns(7), week):
            day_tasks = [t for t in tasks if t["day"] == day.isoformat()]
            label = f"{'● ' if day == TODAY else ''}{day.day}" + (f" · {len(day_tasks)}" if day_tasks else "")
            if col.button(label, key=f"day_{day}", disabled=day.month != month.month, use_container_width=True):
                st.session_state.selected = day
                st.rerun()
    selected = st.session_state.get("selected", TODAY)
    st.divider()
    st.subheader(f"{selected.month}월 {selected.day}일 {DAYS[selected.weekday()]}요일")
    st.caption("날짜를 누르고 계획을 적은 뒤, 실천한 사진을 올려보세요. 날짜 옆 숫자는 계획 개수입니다.")
    daily = [t for t in tasks if t["day"] == selected.isoformat()]
    with st.expander("✏️ 해야 할 일 계획하기", expanded=not daily):
        with st.form(f"plan_{selected}", clear_on_submit=True):
            title = st.text_input("해야 할 일", max_chars=80, placeholder="예: 수학 숙제 3쪽 풀기")
            criterion = st.text_input("완료 기준 (선택)", max_chars=200, placeholder="예: 풀이가 보이는 사진")
            submit = st.form_submit_button("계획 올리기", type="primary")
        if submit:
            if not title.strip():
                st.warning("해야 할 일을 적어주세요.")
            elif len(tasks) >= 300:
                st.warning("최대 300개까지 계획을 등록할 수 있어요.")
            else:
                tasks.append({"id": uuid.uuid4().hex, "title": title.strip(), "criterion": criterion.strip(), "day": selected.isoformat(), "status": "todo", "coins": 0, "evidence": None, "note": "", "feedback": ""})
                save("계획을 올렸어요. 완료하면 아래에서 사진으로 인증하세요!")
    if not parent:
        st.markdown("#### 📷 실천 인증")
        source = st.radio("사진 입력 방법", ["카메라", "사진 업로드"], horizontal=True, key=f"source_{selected}")
        if source == "카메라":
            image = st.camera_input("📷 카메라로 찍기", key=f"camera_{selected}")
        else:
            image = st.file_uploader("사진 선택", type=["png", "jpg", "jpeg"], key=f"file_{selected}")
        st.markdown("### 해야 할 일을 올려보세요!")
        st.caption("카메라 사용 권한을 허용해주세요. 촬영할 수 없다면 사진 업로드를 선택하세요. 사진은 1MB 이하로 올려주세요.")
        choices = [t for t in daily if t["status"] in ["todo", "retry"]]
        if choices:
            chosen = st.selectbox("어떤 계획을 완료했나요?", [t["id"] for t in choices], format_func=lambda v: next(t["title"] for t in choices if t["id"] == v), key=f"choice_{selected}")
            note = st.text_input("실천 한마디 (선택)", max_chars=300, key=f"note_{selected}")
            if st.button("부모님께 승인 요청", type="primary"):
                if image is None:
                    st.warning("사진을 먼저 찍거나 선택해주세요.")
                elif image.size > 1_000_000:
                    st.warning("사진 크기를 1MB 이하로 줄여주세요.")
                else:
                    raw = image.getvalue()
                    valid = True
                    try:
                        with Image.open(BytesIO(raw)) as check:
                            check.verify()
                    except (OSError, ValueError, Image.DecompressionBombError):
                        valid = False
                        st.error("읽을 수 없는 사진이에요. JPG 또는 PNG 사진으로 다시 시도해주세요.")
                    if valid:
                        task = next(t for t in tasks if t["id"] == chosen)
                        task["evidence"] = base64.b64encode(raw).decode()
                        task["status"] = "pending"
                        task["note"] = note.strip()
                        save("인증을 올렸어요! 부모님이 승인하면 코인이 쌓여요.")
        else:
            st.info("인증할 계획이 없어요. 위에서 계획을 먼저 등록하거나 다른 날짜를 선택하세요.")
    status_text = {"todo": "실천 전", "retry": "재도전", "pending": "부모님 확인 중", "approved": "승인 완료"}
    for task in daily:
        with st.container(border=True):
            st.write(f"**{task['title']}** · {status_text[task['status']]}")
            if task.get("criterion"):
                st.caption("완료 기준: " + task["criterion"])
            if task.get("feedback"):
                st.info(task["feedback"])
            if task["status"] == "approved":
                st.success(f"🪙 {task['coins']}코인 적립 완료")
            if task["status"] == "todo" and not task.get("locked", False):
                if st.button("계획 삭제", key=f"delete_{task['id']}"):
                    state["tasks"] = [t for t in tasks if t["id"] != task["id"]]
                    save("계획을 삭제했어요.")

elif nav == "📊 통계":
    st.subheader("📊 나의 실천 변화")
    st.caption("계획 대비 부모님 승인 완료율로 실천 변화를 확인합니다. 실제 게으름이나 성격을 측정하는 진단은 아닙니다. 오늘까지의 계획만 포함하며, 미래 계획은 제외합니다.")
    start = TODAY - timedelta(days=TODAY.weekday())
    n, done, rate = week_stats(tasks, start, TODAY)
    # 지난주는 이번 주와 같은 경과 요일까지만 비교합니다.
    prev_start = start - timedelta(days=7)
    pn, pdone, prate = week_stats(tasks, prev_start, TODAY - timedelta(days=7))
    a, b, c = st.columns(3)
    a.metric("이번 주 완료율", f"{rate:.0f}%" if rate is not None else "기록 없음")
    b.metric("이번 주 승인", f"{done} / {n}개")
    change = rate - prate if rate is not None and prate is not None else None
    c.metric("지난주 같은 요일까지 대비", f"{change:+.1f}%p" if change is not None else "비교 기록 부족")
    st.progress((rate or 0) / 100, text="이번 주 실천 게이지")
    st.markdown("#### 최근 4주 실천 추이")
    st.caption("각 주 월요일부터 오늘과 같은 요일까지의 완료율입니다. 승인 시점이 아니라 계획 날짜 기준으로 집계되며, 추가 승인에 따라 바뀔 수 있습니다.")
    import pandas as pd
    data = []
    for offset in [3, 2, 1, 0]:
        ws = start - timedelta(days=7 * offset)
        total, approved, pct = week_stats(tasks, ws, TODAY - timedelta(days=7 * offset))
        data.append({"주 시작일": ws.strftime("%m/%d"), "완료율 (%)": pct})
    chart = pd.DataFrame(data).set_index("주 시작일")
    if chart["완료율 (%)"].notna().any():
        st.bar_chart(chart, color="#1751D0", y_label="승인 완료율 (%)")
        with st.expander("통계 수치 보기"):
            st.dataframe(chart, use_container_width=True)
    else:
        st.info("계획을 올리고 첫 승인을 받으면 실천 추이가 표시돼요.")
    st.write("계획을 작게 나누고 꾸준히 인증해보세요. 수치가 낮아도 다시 시작하면 됩니다. 🌱")

else:
    st.subheader("🪙 나의 코인")
    st.metric("모은 코인", f"{coins(tasks):,}")
    st.caption("부모님이 인증을 승인할 때 코인이 쌓입니다. 같은 계획은 한 번만 적립되며, 현금 환전·자동 송금 기능은 없습니다.")
    if parent:
        st.markdown("### ✅ 부모님 승인하기")
        pending = [t for t in tasks if t["status"] == "pending"]
        if not pending:
            st.info("승인을 기다리는 인증이 없어요.")
        for task in pending:
            tid = task["id"]
            with st.container(border=True):
                st.write(f"**{task['day']} · {task['title']}**")
                if task.get("criterion"):
                    st.caption("완료 기준: " + task["criterion"])
                if task.get("evidence"):
                    st.image(base64.b64decode(task["evidence"]), width=400)
                st.write(task.get("note") or "인증 메모 없음")
                reward = st.number_input("지급할 코인", min_value=1, max_value=10000, value=max(1, int(task.get("coins", 10) or 10)), key=f"reward_{tid}")
                feedback = st.text_input("응원 / 재도전 안내", max_chars=300, key=f"feedback_{tid}")
                yes, no = st.columns(2)
                if yes.button("승인하고 코인 적립", key=f"approve_{tid}", type="primary"):
                    task["status"] = "approved"
                    task["coins"] = int(reward)
                    task["feedback"] = feedback.strip()
                    task["approved_at"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
                    save(f"승인했어요! {reward}코인이 쌓였어요.")
                if no.button("재도전 요청", key=f"retry_{tid}"):
                    if not feedback.strip():
                        st.warning("어떤 부분을 보완하면 좋을지 적어주세요.")
                    else:
                        task["status"] = "retry"
                        task["feedback"] = feedback.strip()
                        task["evidence"] = None
                        save("재도전 피드백을 보냈어요.")
        with st.expander("저장 공간 관리"):
            agree = st.checkbox("승인된 인증 사진을 영구 삭제합니다. 코인과 승인 기록은 유지됩니다.")
            if st.button("승인된 사진 삭제", disabled=not agree):
                for task in tasks:
                    if task["status"] == "approved":
                        task["evidence"] = None
                save("사진을 정리했어요.")
    else:
        st.info("부모님이 부모님 계정으로 로그인한 후 이 코인 메뉴에서 인증을 승인할 수 있어요.")
    st.markdown("### 코인 적립 기록")
    approved = sorted([t for t in tasks if t["status"] == "approved"], key=lambda t: t.get("approved_at", ""), reverse=True)
    if not approved:
        st.caption("첫 코인을 기다리고 있어요!")
    for task in approved:
        st.write(f"🪙 +{task['coins']} · {task['title']} · 계획 날짜 {task['day']}")
