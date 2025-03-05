# auth_utils.py
import bcrypt
import sqlite3
import streamlit as st
from db_utils import conn, get_cursor

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def is_blacklisted(username):
    with get_cursor() as c:  # 使用上下文管理器自动管理游标
        c.execute('SELECT 1 FROM blacklist WHERE username = ?', (username,))
        return c.fetchone() is not None

def authenticate_user(username, password):
    with get_cursor() as c: 
        c.execute('SELECT password_hash, is_admin FROM users WHERE username = ?', (username,))
        result = c.fetchone()
    if result and verify_password(password, result[0]):
        st.session_state.is_admin = bool(result[1])
        return True
    return False

def login_form():
    with st.form("Login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if is_blacklisted(username):
                st.error("用户名已被封禁")
                return
            elif authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("凭证错误")

def register_form():
    with st.form("Register"):
        username = st.text_input("新用户名")
        password = st.text_input("新密码", type="password")
        if st.form_submit_button("注册"):
            if is_blacklisted(username):
                st.error("用户名已被封禁")
                return
            try:
                with get_cursor() as c: 
                    c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, hash_password(password)))
                st.success("注册成功！请登录")
            except sqlite3.IntegrityError:
                st.error("用户名已存在")
