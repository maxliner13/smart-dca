"""
auth.py — Password Protection สำหรับ Streamlit App
====================================================
ใช้งาน: เรียก require_auth() ที่บรรทัดแรกของ dashboard.py
"""

import streamlit as st
import hmac
import hashlib


def _check_password(input_pw: str, correct_pw: str) -> bool:
    """เปรียบเทียบ password แบบ timing-safe (ป้องกัน timing attack)"""
    return hmac.compare_digest(
        hashlib.sha256(input_pw.encode()).digest(),
        hashlib.sha256(correct_pw.encode()).digest(),
    )


def require_auth():
    """
    บล็อก app จนกว่าจะใส่ password ถูก
    เรียกที่บรรทัดแรกของ dashboard.py ก่อนโค้ดอื่นทั้งหมด

    ตัวอย่าง:
        from auth import require_auth
        require_auth()
        # ... โค้ดที่เหลือ
    """

    # ถ้า login แล้ว ข้ามไปเลย
    if st.session_state.get("authenticated"):
        return

    # ดึง password จาก secrets
    try:
        correct_pw = st.secrets["auth"]["password"]
    except Exception:
        st.error("ไม่พบ [auth] password ใน secrets.toml")
        st.stop()

    # หน้า Login
    st.markdown(
        """
        <style>
        .login-wrap {
            max-width: 360px;
            margin: 80px auto 0;
            padding: 32px;
            background: var(--background-color);
            border: 1px solid rgba(128,128,128,0.2);
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown("<div class='login-wrap'>", unsafe_allow_html=True)
        st.markdown("### 🔒 Smart DCA")
        st.caption("กรุณาใส่ password เพื่อเข้าใช้งาน")

        pw_input = st.text_input(
            "Password",
            type="password",
            placeholder="ใส่ password ที่ตั้งไว้",
            key="pw_input",
        )
        login_btn = st.button("เข้าสู่ระบบ", use_container_width=True, type="primary")

        if login_btn:
            if _check_password(pw_input, correct_pw):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Password ไม่ถูกต้อง")

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()  # หยุด render โค้ดที่เหลือจนกว่าจะ login


def logout():
    """ปุ่ม logout — เรียกใน sidebar"""
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
