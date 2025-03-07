# app.py
import base64
import re
import streamlit as st
import uuid
import os
from dotenv import load_dotenv
from openai import OpenAI
from db_utils import conn, get_cursor
from auth_utils import login_form, register_form, hash_password
from admin_utils import admin_panel, setup_admin
from file_utils import save_uploaded_files, format_file_contents
from api_utils import web_search, get_active_api_config, process_stream
from helper_utils import save_session, load_session, display_chat_history

def handle_user_input():
    base_url, api_key, model_name = get_active_api_config()
    client = OpenAI(api_key=api_key, base_url=base_url)

    uploaded_files = st.file_uploader(
        "上传文本文件（支持多个）",
        type=["txt", "docx", "doc", 'pdf', 'jpg', 'png'],
        accept_multiple_files=True,
        key="file_uploader"
    )

    if uploaded_files:
        new_files = save_uploaded_files(dirs, uploaded_files)
        st.session_state.uploaded_files.extend(new_files)
        st.session_state['file_uploader'].clear()

    user_content = []
    if user_input := st.chat_input("请问我任何事!"):
        user_content.append(user_input)

        if st.session_state.get('enable_search', False):
            try:
                search_results = web_search(user_input, search_key)
                user_content.insert(0, search_results)
            except Exception as e:
                st.error(f"搜索失败: {str(e)}")

        if st.session_state.uploaded_files:
            file_content = format_file_contents(st.session_state.uploaded_files)
            user_content.append("\n[上传文件内容]\n" + file_content)
            st.session_state.uploaded_files = []

        full_content = "\n".join(user_content)
        if not st.session_state.get('valid_key'):
            st.error("请提供有效key，可联系管理员")
            return

        with get_cursor() as c:
            keys = c.execute('SELECT id, key, username, used_tokens, total_tokens FROM api_keys WHERE key = ?', 
                        (st.session_state.used_key,)).fetchone()
        adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in full_content)
        if keys[3] + adjusted_length >= keys[4]:
            st.error("额度已经用完，请联系管理员申请")
            return

        with get_cursor() as c:
            c.execute('UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?', 
                 (adjusted_length, st.session_state.used_key))

        st.session_state.messages.append({"role": "user", "content": full_content})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            stream = client.chat.completions.create(
                model=model_name,
                messages=st.session_state.messages,
                stream=True
            )
            total_content = process_stream(stream, st.session_state.used_key)
            st.session_state.messages.append(
                {"role": "assistant", "content": total_content}
            )

        save_session()

def main_interface():
    st.markdown("<div style='text-align: center;'><img src='data:image/png;base64,{}' width='250'></div>"
               .format(base64.b64encode(open("public/deep-seek.png", "rb").read()).decode()), 
               unsafe_allow_html=True)

    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []

    with st.sidebar:
        if st.button("⚙️ - 设置"):
            st.session_state.show_admin = not st.session_state.get('show_admin', False)

        st.session_state.enable_search = st.checkbox(
            "🔍 启用联网搜索",
            value=st.session_state.get('enable_search', False),
            help="启用后将从互联网获取实时信息"
        )

        if st.session_state.get('valid_key'):
            with get_cursor() as c:
                username = c.execute('SELECT username FROM api_keys WHERE key = ?', 
                               (st.session_state.used_key,)).fetchone()[0]

            if st.button("🆕 - 新会话"):
                st.session_state.current_session_id = str(uuid.uuid4())
                system_messages = [msg for msg in st.session_state.messages if msg["role"] == "system"]
                st.session_state.messages = system_messages.copy()
                st.session_state.show_admin = False
                st.rerun()

            st.subheader("历史会话")
            with get_cursor() as c:
                histories = c.execute('''
                    SELECT session_id, session_name, updated_at 
                    FROM history 
                    WHERE username = ? 
                    ORDER BY updated_at DESC 
                    LIMIT 10
                ''', (username,)).fetchall()

            for hist in histories:
                session_id = hist[0]
                current_name = hist[1]
                
                # 使用三列布局：名称/输入框（4）、编辑/保存（1）、删除（1）
                col1, col2, col3 = st.columns([4, 1, 1])
                
                with col1:
                    if st.session_state.get('editing_session') == session_id:
                        # 编辑模式：显示输入框
                        new_name = st.text_input(
                            "修改名称",
                            value=current_name,
                            key=f"edit_{session_id}",
                            label_visibility="collapsed"  # 隐藏标签
                        )
                    else:
                        # 正常模式：显示会话加载按钮
                        if st.button(
                            f"🗨️ {current_name}",
                            key=f"load_{session_id}",
                            help="点击加载会话"
                        ):
                            st.session_state.show_admin = False
                            load_session(session_id)
                
                with col2:
                    if st.session_state.get('editing_session') == session_id:
                        # 编辑模式：显示保存按钮
                        if st.button(
                            "💾",
                            key=f"save_{session_id}",
                            help="保存修改",
                            type="primary"
                        ):
                            if new_name.strip():
                                with get_cursor() as c:
                                    c.execute(
                                        'UPDATE history SET session_name = ? WHERE session_id = ?',
                                        (new_name.strip(), session_id)
                                    )
                            del st.session_state.editing_session
                            st.rerun()
                    else:
                        # 正常模式：显示编辑按钮
                        if st.button(
                            "✏️",
                            key=f"edit_{session_id}",
                            help="修改名称"
                        ):
                            st.session_state.editing_session = session_id
                            st.rerun()
                
                with col3:
                    # 删除按钮
                    if st.button(
                        "×",
                        key=f"del_{session_id}",
                        help="删除会话"
                    ):
                        with get_cursor() as c:
                            c.execute('DELETE FROM history WHERE session_id = ?', (session_id,))
                        if st.session_state.get('editing_session') == session_id:
                            del st.session_state.editing_session
                        st.rerun()


    if st.session_state.get('show_admin'):
        admin_panel()
    else:
        display_chat_history()
        handle_user_input()

def main():
    setup_admin(admin_user, hash_password(admin_pass), api_key)

    if 'current_session_id' not in st.session_state:
        st.session_state.current_session_id = str(uuid.uuid4())

    if not st.session_state.get('valid_key'):
        user_key = st.chat_input("使用前，请先输入User Key")
        if user_key:
            if not re.fullmatch(r'^[A-Za-z0-9]+$', user_key):
                st.error("无效的 User Key")
            else:
                with get_cursor() as c:
                    c.execute('SELECT username FROM api_keys WHERE key = ? AND is_active = 1', (user_key,))
                    if result := c.fetchone():
                        st.session_state.valid_key = True
                        st.session_state.used_key = user_key
                        st.session_state.username = result[0]
                        st.rerun()
                    else:
                        st.error("无效的 User Key")

    main_interface()

if __name__ == "__main__":
    # 加载环境变量
    load_dotenv()

    dirs = 'uploads/'
    admin_user = os.getenv("ADMIN_USERNAME") 
    admin_pass = os.getenv("ADMIN_PASSWORD") 
    api_key = os.getenv("CHAT_API_KEY") 
    search_key = os.getenv("SEARCH_API_KEY") 
    # 初始url，以阿里云服务为例
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1" 
    model_name = "deepseek-r1"

    if not os.path.exists(dirs):
        os.makedirs(dirs)

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "system",
             "content": "你是一个AI助手，请回答用户提出的问题。同时，如果用户提供了搜索结果，请在回答中添加相应的引用。若需要输出LaTex格式的数学公式，请用 Obsidian 兼容的 LaTeX 格式编写数学公式，要求：1. 行内公式用单个 $ 包裹，如 $x^2$。2. 独立公式块用两个 $$ 包裹，如：$$\int_a^b f(x)dx$$。"}
        ]
        st.session_state.valid_key = False
    main()