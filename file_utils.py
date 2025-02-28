# file_utils.py
import hashlib
import os
import textract
import streamlit as st

def save_uploaded_files(upload_dir, uploaded_files):
    """保存上传文件到临时目录并返回文件信息"""
    saved_files = []
    current_files = [f["name"] for f in st.session_state.get("uploaded_files", [])]

    for file in uploaded_files:
        if file.name in current_files:
            continue

        if file.size > 10 * 1024 * 1024:  # 1MB限制
            st.error(f"文件 {file.name} 超过大小限制")
            continue

        try:
            # 保存文件到指定目录
            file_path = os.path.join(upload_dir, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            # 解析文件内容
            if file.name.endswith(('.doc', '.docx', '.pdf', '.jpg', '.png')):
                content = textract.process(file_path).decode("utf-8")
            else:
                with open(file_path, "r") as f:
                    content = f.read()

            # 生成内容哈希值
            content_hash = hashlib.md5(content.encode()).hexdigest()

            # 检查重复内容
            if any(f["hash"] == content_hash for f in st.session_state.uploaded_files):
                continue

            saved_files.append({
                "name": file.name,
                "content": content,
                "size": file.size,
                "hash": content_hash
            })

        except Exception as e:
            st.error(f"解析文件 {file.name} 失败: {str(e)}")
            continue

    return saved_files

def format_file_contents(files):
    """将文件内容格式化为带分隔符的字符串"""
    return "\n".join([f"=== {f['name']} ===\n{f['content']}\n" for f in files])
