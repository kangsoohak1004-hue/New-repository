"""게으름 탈출구 — Streamlit + Supabase, 한 가족용.
실행: pip install -r requirements.txt && streamlit run app.py
최초 실행 화면의 배포 안내에 SQL과 Secrets 예시가 있습니다.
로그인 비밀번호와 Supabase 키는 GitHub 코드에 넣지 마세요.
"""
import base64
import copy
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from supabase import create_client

st.set_page_config(page_title="게으름 탈출구", page_icon="🚀", layout="wide")
KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).date()
SQL = """-- Supabase > SQL Editor에서 한 번 실행하세요.
create table if not exists public.family_planner (
  id text primary key,
  state jsonb not null default '{}'::jsonb,
  version bigint not null default 0
);
alter table public.family_planner enable row level security;
-- 공개 접근 정책을 만들지 않습니다. 서버의 service_role 키로만 접근합니다.
revoke all on public.family_planner from anon, authenticated;
insert into public.family_planner(id, state) values
('home', '{"weeks": {}, "ledger": [], "goal": {"name": "나의 첫 저축", "amount": 100000}}'::jsonb)
on conflict (id) do nothing;
"""
SECRETS = '''SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "서버 전용 service_role 키"
FAMILY_ID = "home"
CHILD_PASSWORD = "자녀용-긴-비밀번호를-정하세요"
PARENT_PASSWORD = "부모님만-아는-다른-긴-비밀번호"
'''


def guide():
    st.title("🚀 게으름 탈출구")
    st.write("작은 실천을 인증하고, 부모님의 응원을 모아 용돈과 저축으로 연결하세요.")
    st.subheader("처음 한 번만 설정하면 됩니다")
    st.markdown("""1. **비공개 GitHub 저장소**에 `app.py`, `requirements.txt` 두 파일을 올립니다.
2. Supabase 프로젝트를 만들고 **SQL Editor**에서 아래 SQL을 실행합니다.
3. Streamlit Community Cloud에서 GitHub 저장소와 `app.py`를 선택합니다.
4. 배포 설정의 **Secrets**에 아래 설정을 입력합니다. 로컬 실행은 `.streamlit/secrets.toml`을 사용합니다.
5. 부모님·자녀에게 같은 앱 주소를 공유하고 각자의 비밀번호를 알려주세요.

**한 가족 전용 앱입니다.** 가족마다 별도 배포를 권장합니다. Supabase에 데이터가 저장되므로
Streamlit 재시작에도 기록이 유지됩니다. 부모님 비밀번호와 서버 키는 자녀에게 공유하지 마세요.
미성년자의 인증 자료는 얼굴·학교·주소 등 개인정보가 드러나지 않도록 올려주세요.
""")
    st.code(SQL, language="sql")
    st.code(SECRETS, language="toml")
    st.info("실제 은행 송금 기능은 없습니다. 적립·지급·지출 내역을 기록하는 장부입니다. Supabase 이용 한도와 백업은 프로젝트 소유자가 관리합니다.")


required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "CHILD_PASSWORD", "PARENT_PASSWORD"]
try:
    configured = all(str(st.secrets.get(k, "")).strip() for k in required)
except Exception:
    configured = False
if not configured:
    guide()
    st.stop()
if st.secrets["CHILD_PASSWORD"] == st.secrets["PARENT_PASSWORD"]:
    st.error("부모님과 자녀의 비밀번호를 서로 다르게 설정하세요.")
    st.stop()


def digest(text):
    return hashlib.sha256(str(text).encode()).hexdigest()


if "role" not in st.session_state:
    st.title("🚀 게으름 탈출구")
    st.caption("이번 주의 나, 지난주보다 한 걸음 앞으로")
    with st.form("login"):
        role_name = st.selectbox("누가 들어왔나요?", ["자녀", "부모님"])
        password = st.text_input("비밀번호", type="password")
        entered = st.form_submit_button("우리 가족 공간 들어가기", use_container_width=True)
    if entered:
        key = "PARENT_PASSWORD" if role_name == "부모님" else "CHILD_PASSWORD"
        if hmac.compare_digest(digest(password), digest(st.secrets[key])):
            st.session_state.role = role_name
            st.session_state.auth_digest = digest(st.secrets[key])
            st.rerun()
        else:
            st.error("비밀번호를 확인해주세요.")
    st.caption("가족 공용 비밀번호 방식입니다. 공용 기기에서는 반드시 로그아웃하세요.")
    st.stop()

role = st.session_state.role
parent = role == "부모님"
key = "PARENT_PASSWORD" if parent else "CHILD_PASSWORD"
if not hmac.compare_digest(st.session_state.get("auth_digest", ""), digest(st.secrets[key])):
    st.session_state.clear()
    st.rerun()

try:
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])
    family_id = str(st.secrets.get("FAMILY_ID", "home"))
    rows = db.table("family_planner").select("state,version").eq("id", family_id).execute().data
    if not rows:
        st.error("가족 데이터가 없습니다. 초기 SQL과 FAMILY_ID 설정을 확인하세요.")
        st.code(SQL, language="sql")
        st.stop()
    original = rows[0]
    state = copy.deepcopy(original["state"])
    state.setdefault("weeks", {})
    state.setdefault("ledger", [])
    state.setdefault("goal", {"name": "나의 첫 저축", "amount": 100000})
except Exception:
    st.error("저장소에 연결하지 못했습니다. Supabase URL·서버 키·테이블 설정을 확인해주세요. 잠시 후 새로고침해도 좋습니다.")
    st.stop()


def save(message):
    # 낙관적 잠금: 부모·자녀가 동시에 수정해도 다른 사람의 변경을 덮어쓰지 않습니다.
    if len(json.dumps(state).encode()) > 18_000_000:
        st.error("가족 저장 용량(18MB)에 도달했습니다. 부모님이 이전 인증 파일을 정리해주세요.")
        st.stop()
    try:
        changed = db.table("family_planner").update({"state": state, "version": original["version"] + 1}).eq("id", family_id).eq("version", original["version"]).execute().data
    except Exception:
        st.error("저장하지 못했습니다. 연결 상태를 확인하고 다시 시도해주세요.")
        st.stop()
    if not changed:
        st.warning("다른 가족이 먼저 수정했습니다. 새로고침 후 다시 시도해주세요. 이번 수정은 저장되지 않았습니다.")
        st.stop()
    st.session_state.notice = message
    st.rerun()


def uid():
    return uuid.uuid4().hex


def money(value):
    return f"{int(value):,}원"


def week_start(day):
    return day - timedelta(days=day.weekday())


def timestamp():
    return datetime.now(KST).isoformat(timespec="seconds")


def add_ledger(kind, amount, note, week=None):
    state["ledger"].append({"id": uid(), "date": timestamp(), "kind": kind, "amount": int(amount), "note": note, "week": week})


st.sidebar.title("🚀 게으름 탈출구")
st.sidebar.write(f"**{role} 공간**")
st.sidebar.caption("매주 월요일 ~ 일요일 · 한국 시간")
if st.sidebar.button("🔄 최신 기록 불러오기", use_container_width=True):
    st.rerun()
if st.sidebar.button("로그아웃", use_container_width=True):
    st.session_state.clear()
    st.rerun()
with st.sidebar.expander("이용 규칙"):
    st.write("① 일정을 적고 부모님이 확정합니다. ② 인증을 올립니다. ③ 부모님이 승인합니다. ④ 일요일이 지난 뒤 모든 일이 승인되어 있으면 용돈을 적립합니다. 지급은 별도로 기록합니다.")
    st.caption("확정 후 자녀는 일정 삭제·수정을 할 수 없습니다. 파일은 한 건당 1MB 이하이며 사진, PDF만 받습니다.")
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

st.title("작심삼일 대신, 주간 완주 🚀")
st.caption("완벽한 사람이 아니라, 약속을 끝까지 해내는 나를 응원해요.")
weekly_tab, wallet_tab, help_tab = st.tabs(["📅 주간 도전", "🐷 용돈 & 저축", "📖 사용 안내"])

with weekly_tab:
    selected = st.date_input("확인할 주의 날짜", value=TODAY)
    start = week_start(selected)
    end = start + timedelta(days=6)
    wk = start.isoformat()
    week = state["weeks"].setdefault(wk, {"tasks": [], "locked": False, "reward": 10000, "paid": False})
    tasks = week["tasks"]
    done = sum(t["status"] == "approved" for t in tasks)
    st.subheader(f"{start:%m/%d} ~ {end:%m/%d} 주간 도전")
    a, b, c = st.columns(3)
    a.metric("승인된 약속", f"{done} / {len(tasks)}")
    b.metric("완주 보상", money(week["reward"]))
    c.metric("주간 상태", "보상 적립 완료" if week["paid"] else "확정됨" if week["locked"] else "계획 중")
    st.progress(done / len(tasks) if tasks else 0, text="부모님의 승인을 받아 완주 게이지를 채워보세요!")

    if not week["locked"]:
        with st.form(f"new_{wk}", clear_on_submit=True):
            st.markdown("#### ✏️ 이번 주에 할 일")
            title = st.text_input("할 일", max_chars=80, placeholder="예: 수요일 수학 문제집 3쪽 풀기")
            due = st.date_input("실천 날짜", value=max(start, min(TODAY, end)), min_value=start, max_value=end, key=f"due_{wk}")
            criterion = st.text_input("완료 기준", max_chars=200, placeholder="예: 풀이가 보이도록 사진 찍기")
            if st.form_submit_button("약속 추가", use_container_width=True):
                if not title.strip() or not criterion.strip():
                    st.warning("할 일과 완료 기준을 모두 입력해주세요.")
                elif len(tasks) >= 40:
                    st.warning("한 주에는 최대 40개까지 등록할 수 있습니다.")
                else:
                    tasks.append({"id": uid(), "title": title.strip(), "due": due.isoformat(), "criterion": criterion.strip(), "status": "todo", "evidence": None, "feedback": ""})
                    save("이번 주 약속을 추가했어요.")
        if parent:
            reward = st.number_input("이번 주 완주 용돈 (원)", min_value=0, max_value=1000000, value=int(week["reward"]), step=1000, key=f"reward_{wk}")
            agree = st.checkbox("해야 할 일·완료 기준·용돈을 아이와 함께 확인했습니다.", key=f"agree_{wk}")
            if st.button("🔒 이번 주 약속 확정", disabled=not tasks or not agree):
                week["reward"] = int(reward)
                week["locked"] = True
                save("주간 약속을 확정했어요. 이제 인증을 올릴 수 있습니다!")
        else:
            st.info("계획을 다 적었으면 부모님께 확정을 요청하세요. 확정 전에는 인증할 수 없습니다.")

    if not tasks:
        st.info("작고 구체적인 약속 하나부터 시작해볼까요?")
    labels = {"todo": "⬜ 시작 전", "pending": "🔎 확인 대기", "approved": "✅ 승인 완료", "retry": "💪 다시 도전"}
    for task in sorted(tasks, key=lambda t: (t["due"], t["title"])):
        tid = task["id"]
        with st.expander(f"{labels.get(task['status'], '⬜')} · {task['due'][5:]} · {task['title']}"):
            st.write(f"**완료 기준:** {task['criterion']}")
            if task.get("feedback"):
                st.info(f"부모님 메시지: {task['feedback']}")
            ev = task.get("evidence")
            if ev:
                st.write(f"**인증 메모:** {ev['note']}")
                st.caption(f"제출 시각: {ev['at']}")
                if ev.get("data"):
                    raw = base64.b64decode(ev["data"])
                    if ev["mime"] in ("image/png", "image/jpeg", "image/webp"):
                        st.image(raw, width=300)
                    st.download_button("인증 파일 보기 / 다운로드", raw, file_name=ev["name"], mime=ev["mime"], key=f"download_{tid}")
                else:
                    st.caption("보관 용량 관리를 위해 인증 파일은 삭제되었습니다. 승인 기록과 메모는 유지됩니다.")
            if not week["locked"]:
                if st.button("이 약속 삭제", key=f"delete_{tid}"):
                    week["tasks"] = [t for t in tasks if t["id"] != tid]
                    save("약속을 삭제했어요.")
            elif not parent and task["status"] in ("todo", "retry") and not week["paid"]:
                with st.form(f"submit_{tid}"):
                    note = st.text_area("어떻게 실천했나요?", max_chars=1000)
                    upload = st.file_uploader("증거 사진 또는 PDF (1MB 이하)", type=["jpg", "jpeg", "png", "webp", "pdf"], key=f"upload_{tid}")
                    if st.form_submit_button("🙋 부모님께 완료 확인 요청"):
                        if date.fromisoformat(task["due"]) > TODAY:
                            st.warning("실천 날짜가 된 뒤에 인증해주세요.")
                        elif not note.strip() or upload is None:
                            st.warning("인증 메모와 증거 파일을 모두 올려주세요.")
                        elif upload.size > 1_000_000:
                            st.warning("파일을 1MB 이하로 줄여주세요.")
                        else:
                            blob = upload.getvalue()
                            # 확장자뿐 아니라 파일 시그니처도 검증합니다.
                            mime = ("image/png" if blob.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if blob.startswith(b"\xff\xd8\xff") else "application/pdf" if blob.startswith(b"%PDF-") else "image/webp" if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP" else None)
                            if not mime:
                                st.warning("정상적인 JPG, PNG, WEBP 또는 PDF 파일을 올려주세요.")
                            else:
                                task["evidence"] = {"note": note.strip(), "name": upload.name, "mime": mime, "data": base64.b64encode(blob).decode(), "at": timestamp()}
                                task["status"] = "pending"
                                task["feedback"] = ""
                                save("인증을 보냈어요! 부모님의 확인을 기다려주세요.")
            elif parent and task["status"] == "pending" and not week["paid"]:
                feedback = st.text_input("응원 또는 재도전 이유", max_chars=300, key=f"feedback_{tid}")
                yes, no = st.columns(2)
                if yes.button("✅ 실천 승인", key=f"yes_{tid}", use_container_width=True):
                    task["status"] = "approved"
                    task["feedback"] = feedback.strip() or "약속을 지켰구나. 멋져!"
                    save("실천을 승인했어요.")
                if no.button("💪 재도전 요청", key=f"no_{tid}", use_container_width=True):
                    if not feedback.strip():
                        st.warning("다시 도전할 수 있도록 이유를 적어주세요.")
                    else:
                        task["status"] = "retry"
                        task["feedback"] = feedback.strip()
                        save("재도전 메시지를 보냈어요.")
            if parent and task["status"] == "approved" and not week["paid"]:
                if st.button("승인 취소 · 재확인", key=f"undo_{tid}"):
                    task["status"] = "pending"
                    save("승인을 취소했습니다. 다시 확인해주세요.")

    perfect = bool(tasks) and done == len(tasks) and week["locked"]
    if perfect:
        st.success("🏆 이번 주 약속을 모두 해냈어요! 정말 멋져요.")
    if parent and not week["paid"]:
        if TODAY <= end:
            st.caption("완주 용돈은 해당 주의 일요일이 지난 뒤 적립할 수 있습니다.")
        if st.button("🎁 완주 용돈 적립", disabled=not perfect or TODAY <= end):
            week["paid"] = True
            add_ledger("earned", week["reward"], f"{wk} 주간 완주 보상", wk)
            save("완주 용돈을 적립했어요. 실제 지급은 용돈 탭에서 기록하세요.")
    if parent and not week["paid"] and week["locked"]:
        with st.expander("부모님: 계획 수정이 필요한 경우"):
            st.warning("확정을 풀면 추가·삭제가 가능해집니다. 기존 인증과 승인은 유지됩니다. 아이와 합의한 경우에만 사용하세요.")
            unlock = st.checkbox("아이와 계획 변경을 합의했습니다.", key=f"unlock_check_{wk}")
            if st.button("약속 확정 해제", disabled=not unlock):
                week["locked"] = False
                save("계획 수정을 위해 확정을 풀었습니다.")

with wallet_tab:
    ledger = state["ledger"]
    earned = sum(x["amount"] for x in ledger if x["kind"] == "earned")
    received = sum(x["amount"] for x in ledger if x["kind"] == "received")
    spent = sum(x["amount"] for x in ledger if x["kind"] == "spent")
    pending = earned - received
    balance = received - spent
    a, b, c = st.columns(3)
    a.metric("아직 받을 용돈", money(pending))
    b.metric("남은 용돈 · 저축 잔액", money(balance))
    c.metric("누적 완주 보상", money(earned))
    st.caption("저축 잔액 = 실제로 받았다고 기록한 용돈 − 지출. 은행 잔액과 자동 연동되지 않습니다.")
    goal = state["goal"]
    st.subheader(f"🎯 {goal['name']}")
    st.progress(min(1.0, max(0.0, balance / max(1, goal["amount"]))), text=f"{money(balance)} / {money(goal['amount'])}")
    with st.expander("저축 목표 정하기"):
        with st.form("goal"):
            name = st.text_input("목표 이름", value=goal["name"], max_chars=60)
            amount = st.number_input("목표 금액 (원)", min_value=1000, max_value=100000000, value=int(goal["amount"]), step=1000)
            if st.form_submit_button("목표 저장"):
                if name.strip():
                    state["goal"] = {"name": name.strip(), "amount": int(amount)}
                    save("저축 목표를 저장했어요.")
                else:
                    st.warning("목표 이름을 적어주세요.")
    if parent:
        with st.form("payout"):
            st.markdown("#### 💸 실제 용돈 지급 기록")
            payout = st.number_input("지급한 금액 (원)", min_value=0, max_value=max(0, pending), value=0, step=100)
            if st.form_submit_button("지급 완료 기록", disabled=pending <= 0):
                if payout > 0:
                    add_ledger("received", payout, "부모님이 실제 지급 확인")
                    save("실제 지급 기록을 남겼어요.")
                else:
                    st.warning("지급 금액을 입력해주세요.")
    with st.form("expense", clear_on_submit=True):
        st.markdown("#### 🧾 사용한 돈 기록")
        reason = st.text_input("어디에 썼나요?", max_chars=100)
        cost = st.number_input("사용 금액 (원)", min_value=0, max_value=max(0, balance), value=0, step=100)
        if st.form_submit_button("지출 기록", disabled=balance <= 0):
            if reason.strip() and cost > 0:
                add_ledger("spent", cost, reason.strip())
                save("지출을 기록했어요.")
            else:
                st.warning("사용처와 금액을 입력해주세요.")
    st.subheader("용돈 히스토리")
    kind_names = {"earned": "🏆 완주 적립", "received": "💸 실제 지급", "spent": "🧾 지출"}
    if ledger:
        st.dataframe([{"날짜": x["date"][:10], "유형": kind_names[x["kind"]], "금액(원)": x["amount"], "내용": x["note"]} for x in reversed(ledger)], hide_index=True, use_container_width=True)
    else:
        st.info("첫 완주 보상을 향해 출발해볼까요?")

with help_tab:
    st.markdown("""### 한 주의 작은 약속이 용돈이 되기까지
1. **계획**: 아이가 한 주의 할 일과 완료 기준을 정합니다.
2. **합의**: 부모님이 용돈 금액을 정하고 주간 계획을 확정합니다.
3. **실천**: 실천 날짜부터 인증 메모와 사진 또는 PDF를 제출합니다.
4. **확인**: 부모님이 승인하거나 이유와 함께 재도전을 요청합니다.
5. **보상**: 일요일이 지난 뒤 그 주의 할 일이 하나 이상이고 모두 승인되면 부모님이 한 번만 용돈을 적립합니다.
6. **저축**: 실제 지급을 기록하고, 지출을 뺀 나머지를 저축 목표로 모읍니다.

인증·승인은 주가 끝난 뒤에도 가능합니다. 늦게 마무리한 과제의 인정 여부는 부모님이 판단합니다.
보상을 적립한 주는 변경할 수 없습니다. 확정한 약속을 바꾸려면 적립 전에 부모님이 확정을 해제하세요.

**안전 안내**: 인증 사진에 얼굴, 이름표, 학교, 주소가 드러나지 않도록 해주세요.
인증 자료는 가족용 Supabase 저장소에 보관됩니다. 운영자는 Supabase에서 기록을 관리·삭제할 수 있습니다.
이 앱은 소규모 한 가족용이며, 공개 회원가입·다중 가족 서비스용으로 설계되지 않았습니다.
""")
    if parent:
        with st.expander("백업과 인증 파일 정리"):
            st.download_button("가족 기록 백업 (인증 포함 JSON)", json.dumps(state, ensure_ascii=False, indent=2), "family_backup.json", "application/json")
            st.caption("백업에는 개인정보와 인증 사진이 포함됩니다. 비공개로 보관하세요. 앱 내 복원 기능은 없으며 관리자 복원이 필요합니다.")
            cutoff = TODAY - timedelta(days=90)
            remove_ok = st.checkbox("90일이 지난 보상 적립 완료 주의 인증 파일을 삭제합니다. 메모와 장부는 유지됩니다.")
            if st.button("오래된 인증 파일 삭제", disabled=not remove_ok):
                count = 0
                for key_week, old_week in state["weeks"].items():
                    if date.fromisoformat(key_week) + timedelta(days=6) < cutoff and old_week["paid"]:
                        for t in old_week["tasks"]:
                            if t.get("evidence", {}).get("data") if t.get("evidence") else False:
                                t["evidence"]["data"] = None
                                count += 1
                save(f"오래된 인증 파일 {count}개를 삭제했습니다.")
        with st.expander("배포 설정 안내"):
            guide()
